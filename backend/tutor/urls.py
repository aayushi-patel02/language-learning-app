from django.urls import path

from .views import (
    NextTurnView,
    ProgressView,
    SessionRecapView,
    StartSessionView,
    TopicListView,
    VocabularyListView,
    WordDetailView,
)

urlpatterns = [
    path('topics/', TopicListView.as_view(), name='topic-list'),
    path('progress/', ProgressView.as_view(), name='progress'),
    path('vocabulary/', VocabularyListView.as_view(), name='vocabulary-list'),
    path('vocabulary/<int:item_id>/', WordDetailView.as_view(), name='word-detail'),
    path('sessions/start/', StartSessionView.as_view(), name='session-start'),
    path('sessions/<int:session_id>/next/', NextTurnView.as_view(), name='session-next'),
    path('sessions/<int:session_id>/recap/', SessionRecapView.as_view(), name='session-recap'),
]
