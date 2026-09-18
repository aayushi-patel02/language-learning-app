from django.urls import path

from .auth_views import (
    GuestView,
    LoginView,
    LogoutView,
    MeView,
    SignUpView,
)
from .views import (
    LanguageListView,
    NextTurnView,
    ProgressView,
    SessionRecapView,
    StartSessionView,
    TopicListView,
    VocabularyListView,
    WordDetailView,
)

urlpatterns = [
    # Accounts
    path('auth/guest/', GuestView.as_view(), name='auth-guest'),
    path('auth/signup/', SignUpView.as_view(), name='auth-signup'),
    path('auth/login/', LoginView.as_view(), name='auth-login'),
    path('auth/logout/', LogoutView.as_view(), name='auth-logout'),
    path('auth/me/', MeView.as_view(), name='auth-me'),

    # Learning
    path('languages/', LanguageListView.as_view(), name='language-list'),
    path('topics/', TopicListView.as_view(), name='topic-list'),
    path('progress/', ProgressView.as_view(), name='progress'),
    path('vocabulary/', VocabularyListView.as_view(), name='vocabulary-list'),
    path('vocabulary/<int:item_id>/', WordDetailView.as_view(), name='word-detail'),
    path('sessions/start/', StartSessionView.as_view(), name='session-start'),
    path('sessions/<int:session_id>/next/', NextTurnView.as_view(), name='session-next'),
    path('sessions/<int:session_id>/recap/', SessionRecapView.as_view(), name='session-recap'),
]
