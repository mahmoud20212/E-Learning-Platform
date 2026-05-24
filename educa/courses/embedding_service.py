from __future__ import annotations

from dataclasses import dataclass
import logging

from django.conf import settings
from django.db import transaction

from courses.ai_helpers import get_embeddings, get_redis_client
from courses.models import Content, Course, CourseContentEmbedding, File, Image, Text, Video


logger = logging.getLogger(__name__)

SCOPE_FULL = "full"
SCOPE_COURSE_OVERVIEW = "course_overview"
SCOPE_MODULE_DESCRIPTION = "module_description"
SCOPE_CONTENT_ITEM = "content_item"
VALID_SCOPES = {
    SCOPE_FULL,
    SCOPE_COURSE_OVERVIEW,
    SCOPE_MODULE_DESCRIPTION,
    SCOPE_CONTENT_ITEM,
}


@dataclass
class RawUnit:
    text: str
    course_id: int
    module_id: int
    module_order: int
    source: str


def chunk_text(text: str, chunk_size: int = 900, overlap: int = 120) -> list[str]:
    cleaned = (text or "").strip()
    if not cleaned:
        return []

    chunks: list[str] = []
    start = 0
    length = len(cleaned)
    while start < length:
        end = min(start + chunk_size, length)
        chunks.append(cleaned[start:end])
        if end == length:
            break
        start = max(0, end - overlap)
    return chunks


def content_to_text(item) -> str:
    if isinstance(item, Text):
        return f"Title: {item.title}\n\n{item.content}"
    if isinstance(item, Video):
        return f"Video title: {item.title}\nVideo URL: {item.url}"
    if isinstance(item, File):
        return f"File title: {item.title}\nFile name: {item.file.name}"
    if isinstance(item, Image):
        return f"Image title: {item.title}\nImage path: {item.file.name}"
    return ""


def build_raw_units(
    course: Course,
    *,
    scope: str = SCOPE_FULL,
    module_id: int | None = None,
    content_id: int | None = None,
) -> list[RawUnit]:
    units: list[RawUnit] = []

    if scope in (SCOPE_FULL, SCOPE_COURSE_OVERVIEW) and course.overview:
        units.append(
            RawUnit(
                text=f"Course title: {course.title}\n\nOverview:\n{course.overview}",
                course_id=course.id,
                module_id=0,
                module_order=0,
                source=f"course:{course.id}:overview",
            )
        )

    modules = course.modules.prefetch_related("contents", "contents__content_type")
    if module_id is not None:
        modules = modules.filter(id=module_id)

    for module in modules:
        include_module_description = scope in (SCOPE_FULL, SCOPE_MODULE_DESCRIPTION)
        if include_module_description and module.description:
            units.append(
                RawUnit(
                    text=f"Module title: {module.title}\n\nDescription:\n{module.description}",
                    course_id=course.id,
                    module_id=module.id,
                    module_order=int(module.order or 0),
                    source=f"course:{course.id}:module:{module.id}:description",
                )
            )

        if scope not in (SCOPE_FULL, SCOPE_CONTENT_ITEM):
            continue

        for content in module.contents.all():
            if content_id is not None and content.id != content_id:
                continue
            item = content.item
            if item is None:
                continue
            body = content_to_text(item)
            if not body:
                continue
            units.append(
                RawUnit(
                    text=body,
                    course_id=course.id,
                    module_id=module.id,
                    module_order=int(module.order or 0),
                    source=f"course:{course.id}:module:{module.id}:content:{content.id}",
                )
            )

    return units


def build_rows(
    course: Course,
    *,
    scope: str = SCOPE_FULL,
    module_id: int | None = None,
    content_id: int | None = None,
) -> list[dict]:
    rows: list[dict] = []

    for unit in build_raw_units(
        course,
        scope=scope,
        module_id=module_id,
        content_id=content_id,
    ):
        chunks = chunk_text(unit.text)
        if not chunks:
            continue

        vectors = get_embeddings().embed_documents(chunks)
        for idx, chunk in enumerate(chunks, start=1):
            chunk_id = f"{unit.source}:chunk:{idx}"
            rows.append(
                {
                    "course_id": unit.course_id,
                    "module_id": unit.module_id or None,
                    "module_order": unit.module_order,
                    "chunk_id": chunk_id,
                    "source": unit.source,
                    "title": course.title,
                    "content": chunk,
                    "embedding": vectors[idx - 1],
                }
            )

    return rows


def _normalize_scope(scope: str) -> str:
    normalized = (scope or SCOPE_FULL).strip().lower()
    if normalized not in VALID_SCOPES:
        return SCOPE_FULL
    return normalized


def _validate_scope_inputs(scope: str, module_id: int | None, content_id: int | None) -> tuple[int | None, int | None]:
    if scope == SCOPE_MODULE_DESCRIPTION and module_id is None:
        logger.warning("Missing module_id for scope '%s'; fallback to full", scope)
        return None, None

    if scope == SCOPE_CONTENT_ITEM and content_id is None:
        logger.warning("Missing content_id for scope '%s'; fallback to full", scope)
        return None, None

    return module_id, content_id


def _clear_embeddings_for_scope(
    *,
    course_id: int,
    scope: str,
    module_id: int | None,
    content_id: int | None,
) -> None:
    qs = CourseContentEmbedding.objects.filter(course_id=course_id)

    if scope == SCOPE_FULL:
        qs.delete()
        return

    if scope == SCOPE_COURSE_OVERVIEW:
        qs.filter(source=f"course:{course_id}:overview").delete()
        return

    if scope == SCOPE_MODULE_DESCRIPTION and module_id is not None:
        qs.filter(source=f"course:{course_id}:module:{module_id}:description").delete()
        return

    if scope == SCOPE_CONTENT_ITEM and content_id is not None:
        qs.filter(source__endswith=f":content:{content_id}").delete()
        return

    qs.delete()


def _reindex_lock_key(course_id: int, scope: str, module_id: int | None, content_id: int | None) -> str:
    return (
        "educa:embeddings:reindex:"
        f"course:{course_id}:scope:{scope}:module:{module_id or 0}:content:{content_id or 0}"
    )


def _acquire_debounce_lock(course_id: int, scope: str, module_id: int | None, content_id: int | None) -> bool:
    ttl = int(getattr(settings, "EMBEDDING_REINDEX_DEBOUNCE_SECONDS", 45))
    key = _reindex_lock_key(course_id, scope, module_id, content_id)
    try:
        return bool(get_redis_client().set(key, "1", ex=ttl, nx=True))
    except Exception:
        # If Redis is unavailable, do not block indexing.
        logger.exception("Failed to acquire debounce lock for key=%s", key)
        return True


def reindex_course_embeddings(
    course_id: int,
    *,
    clear_existing: bool = True,
    raise_if_empty: bool = False,
    scope: str = SCOPE_FULL,
    module_id: int | None = None,
    content_id: int | None = None,
    use_debounce: bool = False,
) -> int:
    scope = _normalize_scope(scope)
    module_id, content_id = _validate_scope_inputs(scope, module_id, content_id)
    if scope in (SCOPE_MODULE_DESCRIPTION, SCOPE_CONTENT_ITEM) and module_id is None and content_id is None:
        scope = SCOPE_FULL

    if use_debounce and not _acquire_debounce_lock(course_id, scope, module_id, content_id):
        logger.info(
            "Skipped reindex due to debounce: course_id=%s scope=%s module_id=%s content_id=%s",
            course_id,
            scope,
            module_id,
            content_id,
        )
        return 0

    logger.info(
        "Starting embeddings reindex: course_id=%s scope=%s module_id=%s content_id=%s",
        course_id,
        scope,
        module_id,
        content_id,
    )

    course = Course.objects.get(id=course_id)
    rows = build_rows(
        course,
        scope=scope,
        module_id=module_id,
        content_id=content_id,
    )

    if clear_existing:
        _clear_embeddings_for_scope(
            course_id=course_id,
            scope=scope,
            module_id=module_id,
            content_id=content_id,
        )

    if not rows:
        logger.info(
            "No rows built for embeddings reindex: course_id=%s scope=%s module_id=%s content_id=%s",
            course_id,
            scope,
            module_id,
            content_id,
        )
        if raise_if_empty:
            raise ValueError("No indexable content found for this course.")
        return 0

    objects = [CourseContentEmbedding(**row) for row in rows]
    CourseContentEmbedding.objects.bulk_create(
        objects,
        update_conflicts=True,
        update_fields=["module", "module_order", "source", "title", "content", "embedding"],
        unique_fields=["chunk_id"],
    )
    logger.info(
        "Completed embeddings reindex: course_id=%s scope=%s rows=%s",
        course_id,
        scope,
        len(rows),
    )
    return len(rows)


def schedule_course_embedding_reindex(
    course_id: int,
    *,
    scope: str = SCOPE_FULL,
    module_id: int | None = None,
    content_id: int | None = None,
    reason: str = "",
) -> None:
    scope = _normalize_scope(scope)

    def _enqueue() -> None:
        if not _acquire_debounce_lock(course_id, scope, module_id, content_id):
            logger.info(
                "Skipped enqueue due to debounce: course_id=%s scope=%s reason=%s",
                course_id,
                scope,
                reason,
            )
            return

        run_async = bool(getattr(settings, "EMBEDDING_REINDEX_ASYNC", True))
        if run_async:
            try:
                from courses.tasks import reindex_course_embeddings_task

                reindex_course_embeddings_task.delay(
                    course_id=course_id,
                    scope=scope,
                    module_id=module_id,
                    content_id=content_id,
                    reason=reason,
                )
                logger.info(
                    "Queued async embeddings reindex: course_id=%s scope=%s reason=%s",
                    course_id,
                    scope,
                    reason,
                )
                return
            except Exception:
                logger.exception(
                    "Failed to enqueue async reindex; fallback to sync: course_id=%s scope=%s",
                    course_id,
                    scope,
                )

        try:
            reindex_course_embeddings(
                course_id,
                scope=scope,
                module_id=module_id,
                content_id=content_id,
                use_debounce=False,
            )
        except Exception:
            logger.exception(
                "Synchronous fallback reindex failed: course_id=%s scope=%s",
                course_id,
                scope,
            )

    transaction.on_commit(_enqueue)