from django.urls import path

from .views import (
    NextTurnView,
    ProgressView,
    SessionRecapView,
    StartSessionView,
    TopicListView,
)

urlpatterns = [
    path('topics/', TopicListView.as_view(), name='topic-list'),
    path('progress/', ProgressView.as_view(), name='progress'),
    path('sessions/start/', StartSessionView.as_view(), name='session-start'),
    path('sessions/<int:session_id>/next/', NextTurnView.as_view(), name='session-next'),
    path('sessions/<int:session_id>/recap/', SessionRecapView.as_view(), name='session-recap'),
]
