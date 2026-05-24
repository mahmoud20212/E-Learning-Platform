from __future__ import annotations

import logging

from celery import shared_task

from courses.embedding_service import reindex_course_embeddings

logger = logging.getLogger(__name__)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def reindex_course_embeddings_task(
    self,
    *,
    course_id: int,
    scope: str = "full",
    module_id: int | None = None,
    content_id: int | None = None,
    reason: str = "",
) -> int:
    logger.info(
        "Celery reindex task started: course_id=%s scope=%s module_id=%s content_id=%s reason=%s",
        course_id,
        scope,
        module_id,
        content_id,
        reason,
    )
    return reindex_course_embeddings(
        course_id,
        scope=scope,
        module_id=module_id,
        content_id=content_id,
        use_debounce=False,
    )
