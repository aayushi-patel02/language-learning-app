"""Accounts.

Token authentication rather than session cookies, because the frontend and
backend are deployed to different origins (Vercel and Render). A session
cookie would be a third-party cookie there, which Safari blocks outright, so
a learner on an iPhone would silently fail to stay signed in. The token is
held in localStorage and sent as an Authorization header, which no browser
interferes with.

A guest is a real User with an unusable password and `profile.is_guest` set.
Signing up converts that same row in place, so practice done before signing
up simply stays attached to the account. Nothing is copied and nothing can be
half-migrated.
"""

import uuid

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Profile

GUEST_PREFIX = 'guest_'


def profile_payload(user):
    profile, _ = Profile.objects.get_or_create(user=user)
    return {
        'id': user.pk,
        'username': user.username,
        'email': user.email,
        'name': profile.name,
        'avatar': profile.avatar,
        'is_guest': profile.is_guest,
        'native_language': profile.native_language,
        'learning_language': profile.learning_language,
        'joined': profile.created_at,
    }


def issue(user):
    token, _ = Token.objects.get_or_create(user=user)
    return {'token': token.key, 'user': profile_payload(user)}


def normalise_email(value):
    return str(value or '').strip().lower()


class GuestView(APIView):
    """POST /api/auth/guest/ - start practising with no account."""

    def post(self, request):
        with transaction.atomic():
            user = User.objects.create(username=f'{GUEST_PREFIX}{uuid.uuid4().hex[:12]}')
            user.set_unusable_password()
            user.save(update_fields=['password'])
            Profile.objects.create(user=user, is_guest=True, display_name='Guest')
        return Response(issue(user), status=status.HTTP_201_CREATED)


class SignUpView(APIView):
    """POST /api/auth/signup/ - create an account, or upgrade a guest in place."""

    def post(self, request):
        name = str(request.data.get('name') or '').strip()
        email = normalise_email(request.data.get('email'))
        password = request.data.get('password') or ''
        accepted = bool(request.data.get('accepted_terms'))

        if not email or '@' not in email:
            return Response({'detail': 'Enter a valid email address.',
                             'field': 'email'},
                            status=status.HTTP_400_BAD_REQUEST)
        if not accepted:
            return Response({'detail': 'Please accept the terms to continue.',
                             'field': 'accepted_terms'},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            validate_password(password)
        except ValidationError as error:
            return Response({'detail': ' '.join(error.messages), 'field': 'password'},
                            status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(email__iexact=email).exclude(
                pk=getattr(request.user, 'pk', None)).exists():
            return Response({'detail': 'An account already uses that email.',
                             'field': 'email'},
                            status=status.HTTP_400_BAD_REQUEST)

        existing = request.user if request.user.is_authenticated else None
        guest = (
            existing
            if existing and getattr(existing, 'profile', None)
            and existing.profile.is_guest
            else None
        )

        with transaction.atomic():
            # Converting the guest row keeps every UserVocabState and
            # ConversationSession already attached to it.
            user = guest or User.objects.create(username=email)
            user.username = email
            user.email = email
            user.first_name = name[:150]
            user.set_password(password)
            user.save()

            profile, _ = Profile.objects.get_or_create(user=user)
            profile.is_guest = False
            profile.display_name = name
            profile.save(update_fields=['is_guest', 'display_name'])

            # A converted guest keeps practising under the same identity, so
            # the old token is retired to avoid two live credentials.
            Token.objects.filter(user=user).delete()

        return Response(issue(user), status=status.HTTP_201_CREATED)


class LoginView(APIView):
    """POST /api/auth/login/"""

    def post(self, request):
        email = normalise_email(request.data.get('email'))
        password = request.data.get('password') or ''

        user = authenticate(username=email, password=password)
        if user is None:
            # Deliberately does not say which half was wrong.
            return Response({'detail': 'Email or password is incorrect.'},
                            status=status.HTTP_401_UNAUTHORIZED)
        return Response(issue(user))


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    """GET and PATCH /api/auth/me/ - the profile screen."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(profile_payload(request.user))

    def patch(self, request):
        profile, _ = Profile.objects.get_or_create(user=request.user)
        for field in ('display_name', 'avatar', 'native_language', 'learning_language'):
            if field in request.data:
                setattr(profile, field, str(request.data[field])[:80])
        profile.save()
        return Response(profile_payload(request.user))

    def delete(self, request):
        """Remove the account and everything attached to it."""
        request.user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
