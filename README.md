# E-Learning Platform

## Short Description
E-Learning Platform is a Django-based learning system that combines course management, student progress tracking, real-time chat, and an AI assistant (Larry) powered by RAG to answer from course content.

It is designed to provide both:
1. A complete content management flow for instructors.
2. A guided and interactive learning experience for students.

## Technologies
Core backend
1. Python
2. Django
3. Django REST Framework

Async, realtime, and background processing
1. Django Channels
2. Daphne (ASGI)
3. Celery
4. Redis

AI and retrieval
1. LangChain
2. Groq LLM API
3. Hugging Face Inference API (embeddings)
4. PostgreSQL + pgvector

Frontend and UI
1. Django Templates
2. Tailwind CSS

Infrastructure and deployment
1. Docker and Docker Compose
2. Nginx
3. uWSGI and Gunicorn (depending on runtime)
4. WhiteNoise for static assets

## Features
Learning platform features
1. Course, module, and content management.
2. Student enrollment and course navigation.
3. Resume learning from the last visited module.
4. API endpoints for course data.

AI features (Larry assistant)
1. Embedded chat assistant directly in the course detail page.
2. RAG-based answers grounded in indexed course content.
3. Conversation memory with Redis-backed history.
4. First-turn greeting policy with deterministic backend handling.
5. Message timestamps and typing indicator in the chat UI.

Performance and reliability features
1. Embedding indexing service with scoped reindexing.
2. Incremental reindex on selected CRUD operations.
3. Async indexing with Celery worker.
4. Debounce and safety fallback in indexing flow.

## The Process (How It Works)
1. Instructor creates or updates course/module/content.
2. The platform schedules embedding indexing for affected content.
3. Content is chunked, embedded, and stored in PostgreSQL pgvector.
4. Student opens course and can continue from their last module.
5. Student asks Larry a question.
6. The system embeds the question, retrieves the best chunks, and sends context to the LLM.
7. Larry responds with concise, context-grounded answers and keeps conversation memory.

## Running the Project
Prerequisites
1. Python 3.10+ (for local run)
2. Docker and Docker Compose (for containerized run)
3. A configured environment file with required variables (database, Redis, AI keys)

### Option A: Run with Docker Compose
1. Clone the repository.
	git clone https://github.com/mahmoud20212/E-Learning-Platform.git

2. Move into the project root.
	cd E-Learning-Platform

3. Start services.
	docker compose up -d --build

4. Run database migrations.
	docker compose exec web python /code/educa/manage.py migrate

5. Create admin user.
	docker compose exec web python /code/educa/manage.py createsuperuser

6. Collect static assets.
	docker compose exec web python /code/educa/manage.py collectstatic --noinput

7. Open the app in browser.
	http://127.0.0.1

### Option B: Run Locally (without Docker)
1. Create and activate a virtual environment.

2. Install dependencies.
	pip install -r requirements.txt

3. Move to Django project directory.
	cd educa

4. Apply migrations.
	python manage.py migrate

5. Run development server.
	python manage.py runserver --settings=educa.settings.local

## Notes
1. If you run in production-like environments, make sure static files are collected.
2. AI features require valid Groq and Hugging Face credentials.
3. RAG quality depends on successful content indexing and available embeddings.