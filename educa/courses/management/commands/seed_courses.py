from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from courses.models import Content, Course, File, Image, Module, Subject, Text, Video


SEED_DATA = [
    {
        "subject": {"title": "Web Development", "slug": "web-development"},
        "course": {
            "title": "Full-Stack Web Development Bootcamp",
            "slug": "full-stack-web-development-bootcamp",
            "overview": "Learn HTML, CSS, JavaScript, Django, and deployment by building real projects.",
            "modules": [
                {
                    "title": "Introduction to the Web",
                    "description": "How the internet works, client-server model, and project setup.",
                    "contents": [
                        {
                            "type": "text",
                            "title": "What is the web?",
                            "content": "The web is a distributed system where browsers request resources from servers using HTTP.",
                        },
                        {
                            "type": "video",
                            "title": "HTTP basics",
                            "url": "https://www.youtube.com/watch?v=bybQvh2N4Vw",
                        },
                    ],
                },
                {
                    "title": "HTML and CSS Fundamentals",
                    "description": "Structure pages with semantic HTML and style them with modern CSS.",
                    "contents": [
                        {
                            "type": "text",
                            "title": "Semantic HTML",
                            "content": "Use header, main, section, article, and footer tags to improve accessibility and structure.",
                        },
                        {
                            "type": "text",
                            "title": "CSS layout",
                            "content": "Flexbox and Grid help create responsive layouts across different screen sizes.",
                        },
                    ],
                },
                {
                    "title": "Django Project Structure",
                    "description": "Understand Django apps, settings, URLs, templates, and models.",
                    "contents": [
                        {
                            "type": "text",
                            "title": "Django MVT",
                            "content": "Django organizes code around Model, View, and Template, with URLs routing requests to views.",
                        },
                        {
                            "type": "video",
                            "title": "Django project layout",
                            "url": "https://www.youtube.com/watch?v=F5mRW0jo-U4",
                        },
                    ],
                },
            ],
        },
    },
    {
        "subject": {"title": "Data Science", "slug": "data-science"},
        "course": {
            "title": "Python Data Science Essentials",
            "slug": "python-data-science-essentials",
            "overview": "A practical introduction to Python, pandas, visualization, and machine learning basics.",
            "modules": [
                {
                    "title": "Python for Analysis",
                    "description": "Review Python syntax, data structures, and workflows for analysis.",
                    "contents": [
                        {
                            "type": "text",
                            "title": "Python data structures",
                            "content": "Lists, tuples, dictionaries, and sets are the building blocks for handling data in Python.",
                        },
                        {
                            "type": "video",
                            "title": "Python refresher",
                            "url": "https://www.youtube.com/watch?v=rfscVS0vtbw",
                        },
                    ],
                },
                {
                    "title": "Data Analysis with pandas",
                    "description": "Load, clean, filter, and transform tabular data efficiently.",
                    "contents": [
                        {
                            "type": "text",
                            "title": "DataFrames",
                            "content": "A DataFrame is a 2D labeled data structure for tabular data.",
                        },
                        {
                            "type": "text",
                            "title": "Missing values",
                            "content": "Missing data can be handled with dropna, fillna, interpolation, or domain-specific strategies.",
                        },
                    ],
                },
                {
                    "title": "Visualization and Communication",
                    "description": "Communicate insights clearly using charts and narratives.",
                    "contents": [
                        {
                            "type": "text",
                            "title": "Visualization principles",
                            "content": "Choose chart types that match the question, reduce clutter, and emphasize the signal.",
                        },
                        {
                            "type": "video",
                            "title": "Matplotlib and seaborn",
                            "url": "https://www.youtube.com/watch?v=GPVsHOlRBBI",
                        },
                    ],
                },
            ],
        },
    },
    {
        "subject": {"title": "AI Fundamentals", "slug": "ai-fundamentals"},
        "course": {
            "title": "Introduction to AI and Prompting",
            "slug": "introduction-to-ai-and-prompting",
            "overview": "Understand AI concepts, prompt writing, retrieval-augmented generation, and practical workflows.",
            "modules": [
                {
                    "title": "What is AI?",
                    "description": "Basic AI concepts, machine learning, and generative models.",
                    "contents": [
                        {
                            "type": "text",
                            "title": "AI basics",
                            "content": "Artificial intelligence systems perform tasks that typically require human intelligence.",
                        },
                        {
                            "type": "video",
                            "title": "Intro to AI",
                            "url": "https://www.youtube.com/watch?v=ad79nYk2keg",
                        },
                    ],
                },
                {
                    "title": "Prompt Engineering",
                    "description": "Write clear, scoped prompts to get better responses from LLMs.",
                    "contents": [
                        {
                            "type": "text",
                            "title": "Prompt patterns",
                            "content": "State the task, give constraints, provide context, and ask for the format you want.",
                        },
                        {
                            "type": "text",
                            "title": "Prompt pitfalls",
                            "content": "Avoid vague instructions, conflicting goals, and missing context.",
                        },
                    ],
                },
                {
                    "title": "RAG Workflows",
                    "description": "Use retrieval augmented generation to ground answers in course materials.",
                    "contents": [
                        {
                            "type": "text",
                            "title": "RAG overview",
                            "content": "Retrieval-augmented generation combines search over stored documents with model generation.",
                        },
                        {
                            "type": "video",
                            "title": "RAG concept video",
                            "url": "https://www.youtube.com/watch?v=T-D1OfcDW1M",
                        },
                    ],
                },
            ],
        },
    },
]


def unique_item_title(course_title: str, item_title: str) -> str:
    return f"{course_title} - {item_title}"


class Command(BaseCommand):
    help = "Seed the database with sample courses, modules, and content"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clean",
            action="store_true",
            help="Delete existing seeded subjects/courses and recreate them",
        )
        parser.add_argument(
            "--username",
            default="mahmoudai2025",
            help="Owner username to use/create for seeded courses",
        )
        parser.add_argument(
            "--password",
            default="mahmoud123",
            help="Password for created owner user",
        )

    def handle(self, *args, **options):
        clean = options["clean"]
        username = options["username"]
        password = options["password"]

        User = get_user_model()
        owner, created = User.objects.get_or_create(username=username, defaults={"email": f"{username}@example.com"})
        if created:
            owner.set_password(password)
            owner.save(update_fields=["password"])
            self.stdout.write(self.style.SUCCESS(f"Created owner user '{username}'."))
        else:
            self.stdout.write(self.style.WARNING(f"Using existing owner user '{username}'."))

        if clean:
            subject_slugs = [item["subject"]["slug"] for item in SEED_DATA]
            course_slugs = [item["course"]["slug"] for item in SEED_DATA]
            Content.objects.filter(module__course__slug__in=course_slugs).delete()
            Video.objects.filter(owner=owner, title__in=[unique_item_title(item["course"]["title"], content["title"]) for item in SEED_DATA for module in item["course"]["modules"] for content in module["contents"] if content["type"] == "video"]).delete()
            Text.objects.filter(owner=owner, title__in=[unique_item_title(item["course"]["title"], content["title"]) for item in SEED_DATA for module in item["course"]["modules"] for content in module["contents"] if content["type"] == "text"]).delete()
            File.objects.filter(owner=owner).delete()
            Image.objects.filter(owner=owner).delete()
            Module.objects.filter(course__slug__in=course_slugs).delete()
            Course.objects.filter(slug__in=course_slugs).delete()
            Subject.objects.filter(slug__in=subject_slugs).delete()

        created_subjects = 0
        created_courses = 0
        created_modules = 0
        created_contents = 0

        for item in SEED_DATA:
            subject_data = item["subject"]
            course_data = item["course"]

            subject, subject_created = Subject.objects.get_or_create(
                slug=subject_data["slug"],
                defaults={"title": subject_data["title"]},
            )
            if subject_created:
                created_subjects += 1

            course, course_created = Course.objects.get_or_create(
                slug=course_data["slug"],
                defaults={
                    "title": course_data["title"],
                    "overview": course_data["overview"],
                    "owner": owner,
                    "subject": subject,
                },
            )
            if not course_created:
                course.title = course_data["title"]
                course.overview = course_data["overview"]
                course.owner = owner
                course.subject = subject
                course.save(update_fields=["title", "overview", "owner", "subject"])
            else:
                created_courses += 1

            for module_index, module_data in enumerate(course_data["modules"], start=1):
                module, module_created = Module.objects.get_or_create(
                    course=course,
                    title=module_data["title"],
                    defaults={"description": module_data["description"]},
                )
                if not module_created:
                    module.description = module_data["description"]
                    module.save(update_fields=["description"])
                else:
                    created_modules += 1

                module.order = module_index
                module.save(update_fields=["order"])

                for content_index, content_data in enumerate(module_data["contents"], start=1):
                    item_title = unique_item_title(course_data["title"], content_data["title"])
                    if content_data["type"] == "text":
                        item_obj, _ = Text.objects.get_or_create(
                            owner=owner,
                            title=item_title,
                            defaults={"content": content_data["content"]},
                        )
                        if item_obj.content != content_data["content"]:
                            item_obj.content = content_data["content"]
                            item_obj.save(update_fields=["content"])
                    elif content_data["type"] == "video":
                        item_obj, _ = Video.objects.get_or_create(
                            owner=owner,
                            title=item_title,
                            defaults={"url": content_data["url"]},
                        )
                        if item_obj.url != content_data["url"]:
                            item_obj.url = content_data["url"]
                            item_obj.save(update_fields=["url"])
                    else:
                        continue

                    content, content_created = Content.objects.get_or_create(
                        module=module,
                        object_id=item_obj.id,
                        content_type=ContentType.objects.get_for_model(item_obj.__class__),
                        defaults={},
                    )
                    if content_created:
                        created_contents += 1
                    content.order = content_index
                    content.save(update_fields=["order"])

        self.stdout.write(self.style.SUCCESS(
            f"Seed complete: subjects={created_subjects}, courses={created_courses}, modules={created_modules}, contents={created_contents}."
        ))
