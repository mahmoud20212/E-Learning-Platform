from django.shortcuts import render
from django.http import HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from django.urls import reverse

@login_required
def course_chat_room(request, course_id):
    try:
        # retrieve course with given id joined by the current user
        course = request.user.courses_joined.get(id=course_id)
    except:
        # user is not a student of the course or course does not exist
        return HttpResponseForbidden()
    
    # retrieve chat history
    latest_messages = course.chat_messages.select_related(
        'user'
    ).order_by('-id')[:5]
    latest_messages = reversed(latest_messages)

    breadcrumbs = [
        {'label': 'My Learning', 'url': reverse('student_course_list')},
        {'label': course.title, 'url': reverse('student_course_detail', kwargs={'pk': course.id})},
        {'label': 'Chat Room', 'url': None},
    ]

    return render(request, 'chat/room.html', {
        'course': course,
        'breadcrumbs': breadcrumbs,
        'latest_messages': latest_messages,
    })