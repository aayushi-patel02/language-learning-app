"""Root URL configuration.

`/` returns a small JSON index instead of Django's default welcome page, so the
deployed backend responds usefully to a bare visit and Render's health check has
something cheap to hit.
"""

from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def api_index(request):
    return JsonResponse({
        'service': 'charla',
        'endpoints': {
            'start_session': '/api/sessions/start/',
            'next_turn': '/api/sessions/<session_id>/next/',
            'recap': '/api/sessions/<session_id>/recap/',
            'admin': '/admin/',
        },
    })


urlpatterns = [
    path('', api_index, name='api-index'),
    path('admin/', admin.site.urls),
    path('api/', include('tutor.urls')),
]
