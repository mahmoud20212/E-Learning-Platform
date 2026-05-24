from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, TypedDict

import redis
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.contrib.auth import get_user_model
from django.db.models import Count
from django.utils import timezone
from pgvector.django import CosineDistance

from langchain_community.chat_message_histories import RedisChatMessageHistory
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from langchain_core.prompts import MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory

from courses.models import Course, CourseContentEmbedding, Module


class RAGResponse(TypedDict):
    answer: str
    current_module_order: int
    retrieved_chunks: int
    citations: list[dict[str, Any]]
    sent_at: str
    user_sent_at: str


class RetrievedChunk(TypedDict):
    content: str
    source: str
    module_id: int | None
    module_order: int
    chunk_id: str


class CourseSummary(TypedDict):
    title: str
    subject: str
    overview: str
    instructor: str
    module_count: int


class ConversationTurn(TypedDict):
    role: str
    content: str
    sent_at: str


GREETING_PUNCTUATION_TABLE = str.maketrans(
    {char: " " for char in ",.!?;:()[]{}'\"-_/\\|@#%^&*+=~`"}
)

GREETING_PREFIXES = (
    "hi",
    "hello",
    "hey",
    "good morning",
    "good afternoon",
    "good evening",
    "salam",
    "marhaba",
    "مرحبا",
    "اهلا",
    "أهلا",
    "السلام عليكم",
    "السلام",
    "هلا",
)


class HuggingFaceHubEmbeddings:
    """Embedding adapter compatible with Chroma/LangChain embedding interface."""

    def __init__(self, api_token: str, model_name: str):
        try:
            from huggingface_hub import InferenceClient
        except ImportError as exc:
            raise ImproperlyConfigured(
                "huggingface_hub is not installed. Run: pip install huggingface_hub"
            ) from exc

        self.client = InferenceClient(token=api_token)
        self.model_name = model_name

    @staticmethod
    def _to_vector(raw_embedding: Any) -> list[float]:
        if hasattr(raw_embedding, "tolist"):
            raw_embedding = raw_embedding.tolist()

        # Already a sentence-level vector.
        if raw_embedding and isinstance(raw_embedding[0], (int, float)):
            return [float(x) for x in raw_embedding]

        # Token-level embeddings: mean-pool tokens to one vector.
        if (
            raw_embedding
            and isinstance(raw_embedding[0], list)
            and raw_embedding[0]
            and isinstance(raw_embedding[0][0], (int, float))
        ):
            token_count = len(raw_embedding)
            dim = len(raw_embedding[0])
            return [
                float(sum(token[i] for token in raw_embedding) / token_count)
                for i in range(dim)
            ]

        raise ValueError("Unsupported embedding format returned by Hugging Face Inference API")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            raw = self.client.feature_extraction(text=text, model=self.model_name)
            vectors.append(self._to_vector(raw))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def last_module_redis_key(user_id: int, course_id: int) -> str:
    """Redis naming convention: namespace:entity:id:entity:id:attribute."""
    return f"educa:student:{user_id}:course:{course_id}:last-module-id"


def conversation_history_redis_key(user_id: int, course_id: int) -> str:
    return f"educa:student:{user_id}:course:{course_id}:conversation-history"


def get_conversation_memory_ttl_seconds() -> int:
    return int(getattr(settings, "AI_CONVERSATION_MEMORY_TTL_SECONDS", 3600))


def get_conversation_memory_max_messages() -> int:
    return int(getattr(settings, "AI_CONVERSATION_MEMORY_MAX_MESSAGES", 12))


def get_redis_url() -> str:
    return f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"


@lru_cache(maxsize=1)
def get_redis_client() -> redis.Redis:
    return redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
    )


def get_langchain_history(session_id: str) -> RedisChatMessageHistory:
    return RedisChatMessageHistory(
        session_id=session_id,
        url=get_redis_url(),
        key_prefix="educa:chat:history:",
        ttl=get_conversation_memory_ttl_seconds(),
    )


def append_conversation_turn(user_id: int, course_id: int, role: str, content: str) -> str:
    key = conversation_history_redis_key(user_id=user_id, course_id=course_id)
    sent_at = timezone.now().isoformat()
    payload = json.dumps({"role": role, "content": content, "sent_at": sent_at}, ensure_ascii=False)
    ttl_seconds = get_conversation_memory_ttl_seconds()
    max_messages = get_conversation_memory_max_messages()

    try:
        client = get_redis_client()
        pipeline = client.pipeline()
        pipeline.rpush(key, payload)
        pipeline.ltrim(key, -max_messages, -1)
        pipeline.expire(key, ttl_seconds)
        pipeline.execute()
    except redis.RedisError:
        return sent_at
    return sent_at


def get_conversation_history(user_id: int, course_id: int) -> list[ConversationTurn]:
    key = conversation_history_redis_key(user_id=user_id, course_id=course_id)
    try:
        raw_messages = get_redis_client().lrange(key, 0, -1)
    except redis.RedisError:
        return []

    history: list[ConversationTurn] = []
    for raw_message in raw_messages:
        try:
            decoded = json.loads(raw_message)
            role = str(decoded.get("role", "user"))
            content = str(decoded.get("content", "")).strip()
            sent_at = str(decoded.get("sent_at", "")).strip()
            if content:
                history.append({"role": role, "content": content, "sent_at": sent_at})
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    return history


def has_conversation_turns(user_id: int, course_id: int) -> bool:
    key = conversation_history_redis_key(user_id=user_id, course_id=course_id)
    try:
        return int(get_redis_client().llen(key)) > 0
    except (TypeError, ValueError, redis.RedisError):
        return False


def format_conversation_history(history: list[ConversationTurn]) -> str:
    if not history:
        return ""

    lines: list[str] = []
    for turn in history:
        role = turn.get("role", "user")
        content = turn.get("content", "").strip()
        if content:
            lines.append(f"{role.capitalize()}: {content}")
    return "\n".join(lines)


@lru_cache(maxsize=1)
def get_embeddings() -> Any:
    """
    Use hosted Hugging Face inference embeddings to avoid local torch dependencies.
    """
    hf_token = getattr(settings, "HUGGINGFACEHUB_API_TOKEN", "")
    if not hf_token:
        raise ImproperlyConfigured(
            "HUGGINGFACEHUB_API_TOKEN is missing. Set it in environment variables."
        )

    model_name = getattr(
        settings,
        "RAG_EMBEDDING_MODEL",
        "sentence-transformers/all-MiniLM-L6-v2",
    )
    return HuggingFaceHubEmbeddings(api_token=hf_token, model_name=model_name)


def get_current_module_order(user_id: int, course_id: int) -> int:
    """
    Resolve student's current module order from Redis module-id tracking.
    Falls back to the first module order when Redis value is missing/invalid.
    """
    module_qs = Module.objects.filter(course_id=course_id).order_by("order")
    if not module_qs.exists():
        raise ValueError(f"Course {course_id} has no modules.")

    module_id: int | None = None
    try:
        value = get_redis_client().get(last_module_redis_key(user_id=user_id, course_id=course_id))
        if value is not None:
            module_id = int(value)
    except (ValueError, TypeError, redis.RedisError):
        module_id = None

    if module_id is not None:
        current_order = (
            module_qs.filter(id=module_id).values_list("order", flat=True).first()
        )
        if current_order is not None:
            return int(current_order)

    first_order = module_qs.values_list("order", flat=True).first()
    if first_order is None:
        raise ValueError(f"Cannot resolve first module order for course {course_id}.")
    return int(first_order)


def get_student_identity(user_id: int) -> dict[str, str]:
    User = get_user_model()
    user = User.objects.filter(id=user_id).only("username", "first_name", "last_name").first()
    if not user:
        return {
            "username": f"user-{user_id}",
            "display_name": f"User {user_id}",
            "greeting_name": "",
        }

    first_name = (user.first_name or "").strip()
    display_name = first_name or user.username or f"User {user_id}"
    return {
        "username": user.username,
        "display_name": display_name.strip(),
        "greeting_name": first_name,
    }


def get_current_course_summary(course_id: int) -> CourseSummary | None:
    course = (
        Course.objects
        .select_related("subject", "owner")
        .annotate(module_count=Count("modules", distinct=True))
        .filter(id=course_id)
        .values(
            "title",
            "overview",
            "subject__title",
            "owner__first_name",
            "owner__last_name",
            "owner__username",
            "module_count",
        )
        .first()
    )

    if not course:
        return None

    instructor_name = (
        f"{course['owner__first_name']} {course['owner__last_name']}".strip()
        or course["owner__username"]
        or "Course instructor"
    )

    return {
        "title": course["title"],
        "subject": course["subject__title"],
        "overview": course["overview"],
        "instructor": instructor_name,
        "module_count": int(course["module_count"] or 0),
    }


def get_available_courses_context(limit: int = 12) -> str:
    courses = (
        Course.objects
        .select_related("subject", "owner")
        .annotate(module_count=Count("modules", distinct=True))
        .values(
            "id",
            "title",
            "overview",
            "subject__title",
            "owner__first_name",
            "owner__last_name",
            "owner__username",
            "module_count",
        )
        .order_by("title")
        .distinct()[:limit]
    )

    if not courses:
        return ""

    lines: list[str] = []
    for course in courses:
        instructor_name = (
            f"{course['owner__first_name']} {course['owner__last_name']}".strip()
            or course["owner__username"]
            or "Course instructor"
        )
        lines.append(
            "- "
            f"{course['title']} | Subject: {course['subject__title']} | "
            f"Instructor: {instructor_name} | Modules: {int(course['module_count'] or 0)} | "
            f"Overview: {course['overview']}"
        )

    return "Available courses:\n" + "\n".join(lines)


def retrieve_filtered_context(
    student_question: str,
    course_id: int,
    current_module_order: int,
    top_k: int | None = None,
) -> list[RetrievedChunk]:
    k = top_k or int(getattr(settings, "RAG_TOP_K", 5))
    query_vector = get_embeddings().embed_query(student_question)

    rows = (
        CourseContentEmbedding.objects
        .filter(course_id=course_id, module_order__lte=current_module_order)
        .annotate(distance=CosineDistance('embedding', query_vector))
        .order_by('distance')[:k]
        .values('content', 'source', 'module_id', 'module_order', 'chunk_id')
    )
    return list(rows)


def is_greeting_message(text: str) -> bool:
    cleaned = text.strip().lower()
    cleaned = cleaned.translate(GREETING_PUNCTUATION_TABLE)
    cleaned = " ".join(cleaned.split())
    if not cleaned:
        return False

    return any(cleaned.startswith(prefix) for prefix in GREETING_PREFIXES)


@lru_cache(maxsize=1)
def _build_prompt() -> ChatPromptTemplate:
    assistant_name = getattr(settings, "AI_ASSISTANT_NAME", "Larry")
    assistant_persona = getattr(
        settings,
        "AI_ASSISTANT_PERSONA",
        "You are friendly, warm, cheerful, and helpful. Keep answers concise, encouraging, and easy to understand.",
    )

    return ChatPromptTemplate.from_messages(
        [
            (
                "system",
                f"You are {assistant_name}, an e-learning assistant. {assistant_persona} "
                "Keep the tone cheerful, light, and a little playful, but still clear and professional. "
                "You know the student's display name, the current course details, the course instructor, "
                "and the list of available courses. Answer using the provided context and catalog only. "
                "You can also use the recent conversation history to stay on topic and continue the same discussion. "
                "Do not reveal or infer future modules. If context is insufficient, explicitly say so.",
            ),
            MessagesPlaceholder(variable_name="history"),
            (
                "human",
                "Student username: {student_username}\n\n"
                "Student identity:\n{student_identity}\n\n"
                "Greeting rule:\n{greeting_rule}\n\n"
                "Current course details:\n{current_course}\n\n"
                "Available courses:\n{available_courses}\n\n"
                "Question:\n{question}\n\n"
                "Current module order: {current_order}\n\n"
                "Allowed context:\n{context}\n\n"
                "Instructions:\n"
                "1) Keep answer concise and accurate.\n"
                "2) Follow the greeting rule exactly.\n"
                "3) Reply only in English.\n"
                "4) If the user asks about their account name, use the student username or display name.\n"
                "5) If the user asks about available courses, answer from the available courses list.\n"
                "6) If the user asks about this course's instructor or details, answer from the current course details.\n"
                "7) If not found in context, reply: 'I do not have enough course context to answer this yet.'\n"
                "8) Do not mention modules beyond current module order.",
            ),
        ]
    )


@lru_cache(maxsize=1)
def get_conversation_chain() -> RunnableWithMessageHistory:
    llm = ChatGroq(
        api_key=settings.GROQ_API_KEY,
        model=getattr(settings, "GROQ_MODEL", "llama-3.3-70b-versatile"),
        temperature=0,
    )
    chain = _build_prompt() | llm
    return RunnableWithMessageHistory(
        chain,
        get_langchain_history,
        input_messages_key="question",
        history_messages_key="history",
    )


def _format_context_for_llm(docs: list[RetrievedChunk]) -> str:
    if not docs:
        return ""

    parts: list[str] = []
    for idx, doc in enumerate(docs, start=1):
        source = doc.get("source", "unknown")
        module_order = doc.get("module_order", "unknown")
        module_id = doc.get("module_id", "unknown")
        parts.append(
            f"[Chunk {idx}] source={source} module_id={module_id} module_order={module_order}\n{doc['content']}"
        )
    return "\n\n".join(parts)


def answer_student_question(
    student_question: str,
    course_id: int,
    user_id: int,
) -> RAGResponse:
    """
    Main entrypoint for RAG answering with strict module-order filtering.
    """
    question = student_question.strip()
    if not question:
        raise ValueError("student_question must not be empty.")

    if not getattr(settings, "GROQ_API_KEY", ""):
        raise ImproperlyConfigured("GROQ_API_KEY is missing in environment/settings.")

    student_identity = get_student_identity(user_id)
    current_order = get_current_module_order(user_id=user_id, course_id=course_id)
    is_first_turn = not has_conversation_turns(user_id=user_id, course_id=course_id)
    should_greet = is_first_turn and is_greeting_message(question)
    greeting_rule = (
        "Greet briefly at the start of this answer."
        if should_greet
        else "Do not add a greeting. Start directly with the answer."
    )

    if should_greet:
        greeting_name = student_identity.get("greeting_name", "").strip()
        greeting_prefix = f"Hello {greeting_name}," if greeting_name else "Hello,"
        answer_text = (
            f"{greeting_prefix} I'm Larry. "
            "How can I help you with this course today?"
        )
        user_sent_at = append_conversation_turn(
            user_id=user_id,
            course_id=course_id,
            role="user",
            content=question,
        )
        assistant_sent_at = append_conversation_turn(
            user_id=user_id,
            course_id=course_id,
            role="assistant",
            content=answer_text,
        )

        return {
            "answer": answer_text,
            "current_module_order": current_order,
            "retrieved_chunks": 0,
            "citations": [],
            "sent_at": assistant_sent_at,
            "user_sent_at": user_sent_at,
        }

    docs = retrieve_filtered_context(
        student_question=question,
        course_id=course_id,
        current_module_order=current_order,
    )
    context_text = _format_context_for_llm(docs)
    current_course = get_current_course_summary(course_id)
    available_courses = get_available_courses_context()
    conversation_chain = get_conversation_chain()
    session_id = f"{user_id}:{course_id}"

    result = conversation_chain.invoke(
        {
            "student_identity": student_identity["display_name"],
            "student_username": student_identity["username"],
            "greeting_rule": greeting_rule,
            "current_course": (
                "" if not current_course else
                f"Title: {current_course['title']}\nSubject: {current_course['subject']}\n"
                f"Instructor: {current_course['instructor']}\nModules: {current_course['module_count']}\n"
                f"Overview: {current_course['overview']}"
            ),
            "available_courses": available_courses or "No course catalog available.",
            "question": question,
            "current_order": current_order,
            "context": context_text,
        },
        config={"configurable": {"session_id": session_id}},
    )
    answer_text = str(result.content).strip()
    user_sent_at = append_conversation_turn(
        user_id=user_id,
        course_id=course_id,
        role="user",
        content=question,
    )
    assistant_sent_at = append_conversation_turn(
        user_id=user_id,
        course_id=course_id,
        role="assistant",
        content=answer_text,
    )

    citations = [
        {
            "source": doc.get("source"),
            "module_id": doc.get("module_id"),
            "module_order": doc.get("module_order"),
            "chunk_id": doc.get("chunk_id"),
        }
        for doc in docs
    ]

    return {
        "answer": answer_text,
        "current_module_order": current_order,
        "retrieved_chunks": len(docs),
        "citations": citations,
        "sent_at": assistant_sent_at,
        "user_sent_at": user_sent_at,
    }


def build_chunk_metadata(
    *,
    course_id: int,
    module_id: int,
    module_order: int,
    chunk_id: str,
    source: str,
    title: str | None = None,
) -> dict[str, Any]:
    """
    Standard metadata schema for ingestion to support strict filtering.
    """
    metadata: dict[str, Any] = {
        "course_id": int(course_id),
        "module_id": int(module_id),
        "module_order": int(module_order),
        "chunk_id": chunk_id,
        "source": source,
    }
    if title:
        metadata["title"] = title
    return metadata
