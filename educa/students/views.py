# from django.shortcuts import render
from django.shortcuts import redirect
import redis
from django.conf import settings
from django.urls import reverse_lazy
import json
from django.http import HttpResponseForbidden, JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.generic.list import ListView
from django.views.generic.edit import CreateView, FormView
from django.views.generic.detail import DetailView
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import authenticate, login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from .forms import CourseEnrollForm
from courses.models import Course
from courses.ai_helpers import answer_student_question, get_conversation_history
from courses.views import BreadcrumbMixin

# Setting up the Redis connection
r = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=settings.REDIS_DB,
)


def format_message_timestamp(raw_timestamp):
    parsed = parse_datetime(str(raw_timestamp or '').strip())
    if not parsed:
        return ''
    return timezone.localtime(parsed).strftime('%b %d, %I:%M %p')

class StudentRegistrationView(BreadcrumbMixin, CreateView):
    template_name = 'students/student/registration.html'
    form_class = UserCreationForm
    success_url = reverse_lazy('student_course_list')
    
    def get_breadcrumbs(self):
        return [
            {'label': 'Sign Up', 'url': None},
        ]
    
    def form_valid(self, form):
        result = super().form_valid(form)
        cd = form.cleaned_data
        user = authenticate(username=cd['username'], password=cd['password1'])
        login(self.request, user)
        return result

class StudentEnrollCourseView(LoginRequiredMixin, FormView):
    course = None
    form_class = CourseEnrollForm

    def form_valid(self, form):
        self.course = form.cleaned_data['course']
        self.course.students.add(self.request.user)
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('student_course_detail', args=[self.course.id])

class StudentCourseListView(BreadcrumbMixin, LoginRequiredMixin, ListView):
    model = Course
    template_name = 'students/course/list.html'

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(students__in=[self.request.user])
    
    def get_breadcrumbs(self):
        return [
            {'label': 'My Learning', 'url': None},
        ]

class StudentCourseDetailView(BreadcrumbMixin, DetailView):
    model = Course
    template_name = 'students/course/detail.html'

    def _last_module_key(self, course_id):
        # Redis key naming convention: app:entity:id:subentity:id:attribute
        return f'educa:student:{self.request.user.id}:course:{course_id}:last-module-id'

    def _get_last_module_id(self, course_id):
        try:
            value = r.get(self._last_module_key(course_id))
            return int(value) if value is not None else None
        except (ValueError, TypeError, redis.RedisError):
            return None

    def _set_last_module_id(self, course_id, module_id):
        try:
            r.set(self._last_module_key(course_id), module_id)
        except redis.RedisError:
            # Fallback silently if Redis is temporarily unavailable.
            pass

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(students__in=[self.request.user])

    def get(self, request, *args, **kwargs):
        # If module is not provided, resume from the last visited module URL.
        if 'module_id' not in self.kwargs:
            self.object = self.get_object()
            last_module_id = self._get_last_module_id(self.object.id)
            if last_module_id and self.object.modules.filter(id=last_module_id).exists():
                return redirect(
                    'student_course_detail_module',
                    pk=self.object.id,
                    module_id=last_module_id,
                )
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # get course object
        course = self.get_object()
        if 'module_id' in self.kwargs:
            # get current module
            context['module'] = course.modules.get(id=self.kwargs['module_id'])
        else:
            # get last visited module from Redis, fallback to first module
            last_module_id = self._get_last_module_id(course.id)
            if last_module_id:
                context['module'] = course.modules.filter(id=last_module_id).first()
            if not context.get('module'):
                context['module'] = course.modules.all()[0]

        # persist current module so the student can resume later
        self._set_last_module_id(course.id, context['module'].id)
        context['assistant_messages'] = self._get_assistant_messages(course.id)
        context['assistant_endpoint'] = reverse_lazy('student_course_assistant', kwargs={'pk': course.id})
        return context

    def _get_assistant_messages(self, course_id):
        try:
            history = get_conversation_history(self.request.user.id, course_id)
        except Exception:
            return []

        messages = []
        for message in history[-8:]:
            role = str(message.get('role', 'user')).strip() or 'user'
            content = str(message.get('content', '')).strip()
            if content:
                messages.append(
                    {
                        'role': role,
                        'content': content,
                        'sent_at': format_message_timestamp(message.get('sent_at')),
                    }
                )
        return messages
    
    def get_breadcrumbs(self):
        return [
            {'label': 'My Learning', 'url': reverse_lazy('student_course_list')},
            {'label': self.object.title, 'url': None},
        ]


@login_required
@require_POST
def student_course_assistant(request, pk):
    try:
        course = request.user.courses_joined.get(id=pk)
    except Course.DoesNotExist:
        return HttpResponseForbidden()

    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid request payload.'}, status=400)

    message = str(payload.get('message', '')).strip()
    if not message:
        return JsonResponse({'error': 'Message is required.'}, status=400)

    try:
        result = answer_student_question(
            student_question=message,
            course_id=course.id,
            user_id=request.user.id,
        )
    except Exception as exc:
        return JsonResponse({'error': str(exc)}, status=500)

    return JsonResponse(
        {
            'answer': result['answer'],
            'citations': result['citations'],
            'retrieved_chunks': result['retrieved_chunks'],
            'sent_at': format_message_timestamp(result.get('sent_at')),
        }
    )
