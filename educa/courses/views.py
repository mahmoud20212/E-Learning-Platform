# from django.shortcuts import render
from django.views.generic.list import ListView
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.views.generic.base import TemplateResponseMixin
from django.contrib.auth.views import LoginView as DjangoLoginView, LogoutView as DjangoLogoutView
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.shortcuts import redirect, get_object_or_404
from django.views.generic.base import TemplateResponseMixin, View
from .forms import ModuleFormSet
from django.forms.models import modelform_factory
from django.apps import apps
from .models import Course, Module, Content
from braces.views import CsrfExemptMixin, JsonRequestResponseMixin
from django.db.models import Count
from .models import Subject
from courses.embedding_service import (
    SCOPE_COURSE_OVERVIEW,
    SCOPE_CONTENT_ITEM,
    SCOPE_FULL,
    SCOPE_MODULE_DESCRIPTION,
    schedule_course_embedding_reindex,
)
from students.forms import CourseEnrollForm
from django.core.cache import cache


class BreadcrumbMixin:
    """Mixin لإضافة breadcrumb إلى context"""
    breadcrumbs = None
    
    def get_breadcrumbs(self):
        """Override this method to set custom breadcrumbs"""
        return self.breadcrumbs or []
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['breadcrumbs'] = self.get_breadcrumbs()
        return context
    
    def render_to_response(self, context, **response_kwargs):
        context['breadcrumbs'] = self.get_breadcrumbs()
        return super().render_to_response(context, **response_kwargs)


class OwnerMixin:
    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(owner=self.request.user)

class OwnerEditMixin:
    def form_valid(self, form):
        form.instance.owner = self.request.user
        return super().form_valid(form)

class OwnerCourseMixin(OwnerMixin, LoginRequiredMixin, PermissionRequiredMixin):
    model = Course
    fields = ['subject', 'title', 'slug', 'overview']
    success_url = reverse_lazy('manage_course_list')

class OwnerCourseEditMixin(OwnerCourseMixin, OwnerEditMixin):
    template_name = 'courses/manage/course/form.html'

class ManageCourseListView(OwnerCourseMixin, BreadcrumbMixin, ListView):
    template_name = 'courses/manage/course/list.html'
    permission_required = 'courses.view_course'
    
    def get_breadcrumbs(self):
        return [
            # {'label': 'Dashboard', 'url': reverse_lazy('manage_course_list')},
            {'label': 'My Courses', 'url': None},
        ]

class CourseCreateView(OwnerCourseEditMixin, BreadcrumbMixin, CreateView):
    permission_required = 'courses.add_course'

    def form_valid(self, form):
        response = super().form_valid(form)
        schedule_course_embedding_reindex(
            self.object.id,
            scope=SCOPE_FULL,
            reason="course-created",
        )
        return response
    
    def get_breadcrumbs(self):
        return [
            # {'label': 'Dashboard', 'url': reverse_lazy('manage_course_list')},
            {'label': 'My Courses', 'url': reverse_lazy('manage_course_list')},
            {'label': 'Create New Course', 'url': None},
        ]

class CourseUpdateView(OwnerCourseEditMixin, BreadcrumbMixin, UpdateView):
    permission_required = 'courses.change_course'

    def form_valid(self, form):
        response = super().form_valid(form)
        changed_fields = set(form.changed_data or [])
        if changed_fields and changed_fields.issubset({'overview'}):
            schedule_course_embedding_reindex(
                self.object.id,
                scope=SCOPE_COURSE_OVERVIEW,
                reason="course-overview-updated",
            )
        else:
            schedule_course_embedding_reindex(
                self.object.id,
                scope=SCOPE_FULL,
                reason="course-updated-structural",
            )
        return response
    
    def get_breadcrumbs(self):
        return [
            # {'label': 'Dashboard', 'url': reverse_lazy('manage_course_list')},
            {'label': 'My Courses', 'url': reverse_lazy('manage_course_list')},
            {'label': f'Edit {self.object.title}', 'url': None},
        ]

class CourseDeleteView(OwnerCourseMixin, BreadcrumbMixin, DeleteView):
    template_name = 'courses/manage/course/delete.html'
    permission_required = 'courses.delete_course'
    
    def get_breadcrumbs(self):
        return [
            # {'label': 'Dashboard', 'url': reverse_lazy('manage_course_list')},
            {'label': 'My Courses', 'url': reverse_lazy('manage_course_list')},
            {'label': f'Delete {self.object.title}', 'url': None},
        ]

class CourseModuleUpdateView(BreadcrumbMixin, TemplateResponseMixin, View):
    template_name = 'courses/manage/module/formset.html'
    course = None

    # Get Formset
    def get_formset(self, data=None):
        return ModuleFormSet(instance=self.course, data=data)

    def dispatch(self, request, pk):
        self.course = get_object_or_404(Course, id=pk, owner=request.user)
        return super().dispatch(request, pk)
    
    def get_breadcrumbs(self):
        return [
            # {'label': 'Dashboard', 'url': reverse_lazy('manage_course_list')},
            {'label': 'My Courses', 'url': reverse_lazy('manage_course_list')},
            {'label': f'{self.course.title}', 'url': None},
            {'label': 'Edit Modules', 'url': None},
        ]

    def get(self, request, *args, **kwargs):
        formset = self.get_formset()
        return self.render_to_response({'course': self.course, 'formset': formset})

    def post(self, request, *args, **kwargs):
        formset = self.get_formset(data=request.POST)
        if formset.is_valid():
            formset.save()

            changed_objects = getattr(formset, 'changed_objects', [])
            new_objects = getattr(formset, 'new_objects', [])
            deleted_objects = getattr(formset, 'deleted_objects', [])

            # Structural or order changes impact retrieval ordering, so reindex full course.
            requires_full = bool(new_objects or deleted_objects)
            module_description_ids: list[int] = []

            for changed in changed_objects:
                if not isinstance(changed, tuple) or len(changed) < 2:
                    requires_full = True
                    break

                module_obj, changed_fields = changed
                field_names = set(changed_fields or [])

                if 'order' in field_names:
                    requires_full = True
                    break

                if field_names.intersection({'title', 'description'}) and getattr(module_obj, 'id', None):
                    module_description_ids.append(module_obj.id)

            if requires_full:
                schedule_course_embedding_reindex(
                    self.course.id,
                    scope=SCOPE_FULL,
                    reason="module-formset-structural-or-order-change",
                )
            elif module_description_ids:
                for module_id in sorted(set(module_description_ids)):
                    schedule_course_embedding_reindex(
                        self.course.id,
                        scope=SCOPE_MODULE_DESCRIPTION,
                        module_id=module_id,
                        reason="module-description-updated",
                    )
            return redirect('manage_course_list')
        return self.render_to_response({'course': self.course, 'formset': formset})

class ContentCreateUpdateView(BreadcrumbMixin, TemplateResponseMixin, View):
    module = None
    model = None
    obj = None
    template_name = 'courses/manage/content/form.html'

    # Get model automatic
    def get_model(self, model_name):
        if model_name in ['text', 'video', 'image', 'file']:
            return apps.get_model(app_label='courses', model_name=model_name)
        return None

    # Create form automatic
    def get_form(self, model, *args, **kwargs):
        Form = modelform_factory(model, exclude=['owner',
                                                'order',
                                                'created',
                                                'updated'])
        return Form(*args, **kwargs)
    
    def dispatch(self, request, module_id, model_name, id=None):
        self.module = get_object_or_404(Module,
                                        id=module_id,
                                        course__owner=request.user)
        self.model = self.get_model(model_name)
        if id:
            self.obj = get_object_or_404(self.model,
                                        id=id,
                                        owner=request.user)
        return super().dispatch(request, module_id, model_name, id)
    
    def get_breadcrumbs(self):
        breadcrumbs = [
            # {'label': 'Dashboard', 'url': reverse_lazy('manage_course_list')},
            {'label': 'My Courses', 'url': reverse_lazy('manage_course_list')},
            {'label': self.module.course.title, 'url': None},
            {'label': f'Module: {self.module.title}', 'url': reverse_lazy('module_content_list', kwargs={'module_id': self.module.id})},
        ]
        
        action = 'Edit' if self.obj else 'Create'
        model_name = self.model.__name__ if self.model else 'Content'
        breadcrumbs.append({'label': f'{action} {model_name}', 'url': None})
        
        return breadcrumbs
    
    def get(self, request, module_id, model_name, id=None):
        form = self.get_form(self.model, instance=self.obj)
        return self.render_to_response({'form': form, 'object': self.obj})
    
    def post(self, request, module_id, model_name, id=None):
        form = self.get_form(self.model, instance=self.obj, data=request.POST, files=request.FILES)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.owner = request.user
            obj.save()
            content_ref = None
            if not id:
                # new content
                content_ref = Content.objects.create(module=self.module, item=obj)
            else:
                content_ref = (
                    Content.objects
                    .filter(module=self.module, object_id=obj.id, content_type__model=model_name)
                    .only('id')
                    .first()
                )

            if content_ref:
                schedule_course_embedding_reindex(
                    self.module.course.id,
                    scope=SCOPE_CONTENT_ITEM,
                    content_id=content_ref.id,
                    reason="content-item-updated",
                )
            else:
                schedule_course_embedding_reindex(
                    self.module.course.id,
                    scope=SCOPE_FULL,
                    reason="content-item-updated-fallback-full",
                )
            return redirect('module_content_list', self.module.id)
        return self.render_to_response({'form': form, 'object': self.obj})

class ContentDeleteView(View):
    def post(self, request, id):
        content = get_object_or_404(Content,
                                    id=id,
                                    module__course__owner=request.user)
        module = content.module
        course_id = module.course_id
        content_id = content.id
        content.item.delete()
        content.delete()
        schedule_course_embedding_reindex(
            course_id,
            scope=SCOPE_CONTENT_ITEM,
            content_id=content_id,
            reason="content-item-deleted",
        )
        return redirect('module_content_list', module.id)

class ModuleContentListView(BreadcrumbMixin, TemplateResponseMixin, View):
    template_name = 'courses/manage/module/content_list.html'

    def get(self, request, module_id):
        module = get_object_or_404(Module,
                                    id=module_id,
                                    course__owner=request.user)
        return self.render_to_response({'module': module})
    
    def get_breadcrumbs(self):
        # Get module from request
        module = get_object_or_404(Module,
                                    id=self.request.resolver_match.kwargs.get('module_id'),
                                    course__owner=self.request.user)
        return [
            # {'label': 'Dashboard', 'url': reverse_lazy('manage_course_list')},
            {'label': 'My Courses', 'url': reverse_lazy('manage_course_list')},
            {'label': module.course.title, 'url': None},
            {'label': f'Module: {module.title}', 'url': None},
            {'label': 'Manage Content', 'url': None},
        ]

class ModuleOrderView(CsrfExemptMixin, JsonRequestResponseMixin, View):
    def post(self, request):
        course_ids = set(
            Module.objects.filter(id__in=self.request_json.keys(), course__owner=request.user)
            .values_list('course_id', flat=True)
        )
        for id, order in self.request_json.items():
            Module.objects.filter(id=id,
                                course__owner=request.user).update(order=order)
        for course_id in course_ids:
            schedule_course_embedding_reindex(
                course_id,
                scope=SCOPE_FULL,
                reason="module-order-updated",
            )
        return self.render_json_response({'saved': 'OK'})

class ContentOrderView(CsrfExemptMixin, JsonRequestResponseMixin, View):
    def post(self, request):
        for id, order in self.request_json.items():
            Content.objects.filter(id=id,
                                    module__course__owner=request.user).update(order=order)
        return self.render_json_response({'saved': 'OK'})

class CourseListView(BreadcrumbMixin, TemplateResponseMixin, View):
    model = Course
    template_name = 'courses/course/list.html'

    def get(self, request, subject=None):
        subjects = cache.get('all_subjects')
        if not subjects:
            subjects = Subject.objects.annotate(total_courses=Count('courses'))
            cache.set('all_subjects', subjects)
        
        all_courses = Course.objects.annotate(total_modules=Count('modules'))
        if subject:
            subject = get_object_or_404(Subject, slug=subject)
            key = f'subject_{subject.id}_courses'
            courses = cache.get(key)
            if not courses:
                courses = all_courses.filter(subject=subject)
                cache.set(key, courses)
        else:
            courses = cache.get('all_courses')
            if not courses:
                courses = all_courses
                cache.set('all_courses', courses)
        return self.render_to_response({'subjects': subjects,
                                        'subject': subject,
                                        'courses': courses})
    
    def get_breadcrumbs(self):
        subject = None
        # Try to get subject from kwargs if it's a subject-specific view
        subject_slug = self.request.resolver_match.kwargs.get('subject')
        if subject_slug:
            try:
                subject = Subject.objects.get(slug=subject_slug)
                return [
                    {'label': 'Courses', 'url': reverse_lazy('course_list')},
                    {'label': subject.title, 'url': None},
                ]
            except Subject.DoesNotExist:
                pass
        
        # Default: no breadcrumb for main course list
        return []

class CourseDetailView(BreadcrumbMixin, DetailView):
    model = Course
    template_name = 'courses/course/detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['enroll_form'] = CourseEnrollForm(initial={'course': self.object})
        return context
    
    def get_breadcrumbs(self):
        return [
            {'label': 'Courses', 'url': reverse_lazy('course_list')},
            {'label': self.object.subject.title, 'url': reverse_lazy('course_list_subject', kwargs={'subject': self.object.subject.slug})},
            {'label': self.object.title, 'url': None},
        ]


class LoginView(BreadcrumbMixin, DjangoLoginView):
    def get_breadcrumbs(self):
        return [
            {'label': 'Sign In', 'url': None},
        ]


class LogoutView(BreadcrumbMixin, DjangoLogoutView):
    def get_breadcrumbs(self):
        return [
            {'label': 'Logged Out', 'url': None},
        ]