from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from courses.embedding_service import reindex_course_embeddings
from courses.models import Course, CourseContentEmbedding


class Command(BaseCommand):
    help = "Index course content into pgvector table for RAG retrieval"

    def add_arguments(self, parser):
        parser.add_argument("--course-id", type=int, required=True, help="Course ID to index")
        parser.add_argument(
            "--clear-existing",
            action="store_true",
            help="Delete existing vectors for this course before indexing",
        )

    def handle(self, *args, **options):
        course_id = options["course_id"]
        clear_existing = options["clear_existing"]

        try:
            course = Course.objects.get(id=course_id)
        except Course.DoesNotExist as exc:
            raise CommandError(f"Course with id={course_id} does not exist") from exc

        try:
            rows_count = reindex_course_embeddings(
                course_id,
                clear_existing=clear_existing,
                raise_if_empty=True,
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        total = CourseContentEmbedding.objects.filter(course_id=course_id).count()

        self.stdout.write(
            self.style.SUCCESS(
                f"Indexed {rows_count} chunks for course id={course_id} into pgvector table (total={total})."
            )
        )
