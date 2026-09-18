"""Tests for accounts.

The case that matters most is guest conversion: someone practises, then signs
up, and their schedule has to still be theirs. Getting that wrong silently
punishes the people who tried the app before committing to it.
"""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from rest_framework.authtoken.models import Token

from .models import Profile, UserVocabState, VocabItem

PASSWORD = 'correct-horse-battery-42'


class AuthTestCase(TestCase):
    def setUp(self):
        self.item = VocabItem.objects.create(
            term='desayunar', english='to have breakfast',
            topic='daily_routine',
        )

    def post(self, name, payload=None, token=None):
        headers = {'HTTP_AUTHORIZATION': f'Token {token}'} if token else {}
        return self.client.post(
            reverse(name), payload or {},
            content_type='application/json', **headers,
        )

    def start_guest(self):
        response = self.post('auth-guest')
        return response.json()['token'], response.json()['user']

    def practise(self, user, reviews=3):
        """Give this learner some history to protect."""
        state, _ = UserVocabState.objects.get_or_create(user=user, item=self.item)
        state.total_reviews = reviews
        state.correct_reviews = reviews
        state.repetitions = reviews
        state.save()
        return state


class GuestTests(AuthTestCase):
    def test_a_guest_gets_a_token_and_a_profile(self):
        token, user = self.start_guest()
        self.assertTrue(token)
        self.assertTrue(user['is_guest'])
        self.assertTrue(user['username'].startswith('guest_'))
        self.assertEqual(Profile.objects.filter(is_guest=True).count(), 1)

    def test_guests_do_not_share_an_identity(self):
        first, _ = self.start_guest()
        second, _ = self.start_guest()
        self.assertNotEqual(first, second)
        self.assertEqual(User.objects.count(), 2)

    def test_a_guest_cannot_log_in(self):
        self.start_guest()
        guest = User.objects.get()
        self.assertFalse(guest.has_usable_password())


class SignUpTests(AuthTestCase):
    def valid(self, **overrides):
        payload = {
            'name': 'Aayushi',
            'email': 'learner@example.com',
            'password': PASSWORD,
            'accepted_terms': True,
        }
        payload.update(overrides)
        return payload

    def test_signing_up_creates_an_account(self):
        response = self.post('auth-signup', self.valid())
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertFalse(body['user']['is_guest'])
        self.assertEqual(body['user']['email'], 'learner@example.com')
        self.assertEqual(body['user']['name'], 'Aayushi')
        self.assertTrue(body['token'])

    def test_email_is_stored_lowercased(self):
        self.post('auth-signup', self.valid(email='Learner@Example.COM'))
        self.assertTrue(User.objects.filter(email='learner@example.com').exists())

    def test_a_duplicate_email_is_refused(self):
        self.post('auth-signup', self.valid())
        response = self.post('auth-signup', self.valid(name='Someone else'))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['field'], 'email')
        self.assertEqual(User.objects.count(), 1)

    def test_a_duplicate_email_is_refused_regardless_of_case(self):
        self.post('auth-signup', self.valid(email='learner@example.com'))
        response = self.post('auth-signup', self.valid(email='LEARNER@example.com'))
        self.assertEqual(response.status_code, 400)

    def test_an_invalid_email_is_refused(self):
        for bad in ('', 'not-an-email', '   '):
            with self.subTest(email=bad):
                response = self.post('auth-signup', self.valid(email=bad))
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()['field'], 'email')

    def test_a_weak_password_is_refused(self):
        for weak in ('abc', 'password', '12345678'):
            with self.subTest(password=weak):
                response = self.post('auth-signup', self.valid(password=weak))
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()['field'], 'password')

    def test_the_terms_must_be_accepted(self):
        response = self.post('auth-signup', self.valid(accepted_terms=False))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['field'], 'accepted_terms')
        self.assertEqual(User.objects.count(), 0)

    def test_a_refused_signup_creates_nothing(self):
        self.post('auth-signup', self.valid(password='abc'))
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(Profile.objects.count(), 0)


class GuestConversionTests(AuthTestCase):
    """Signing up after practising must not cost the learner their history."""

    def test_progress_survives_signing_up(self):
        token, user = self.start_guest()
        guest = User.objects.get(pk=user['id'])
        self.practise(guest, reviews=3)

        response = self.post('auth-signup', {
            'name': 'Aayushi',
            'email': 'learner@example.com',
            'password': PASSWORD,
            'accepted_terms': True,
        }, token=token)

        self.assertEqual(response.status_code, 201)
        # The same row, upgraded. Not a copy, and not a second account.
        self.assertEqual(User.objects.count(), 1)
        state = UserVocabState.objects.get()
        self.assertEqual(state.user_id, guest.pk)
        self.assertEqual(state.total_reviews, 3)

    def test_the_guest_row_becomes_the_account(self):
        token, user = self.start_guest()
        self.post('auth-signup', {
            'name': 'Aayushi', 'email': 'learner@example.com',
            'password': PASSWORD, 'accepted_terms': True,
        }, token=token)

        upgraded = User.objects.get(pk=user['id'])
        self.assertEqual(upgraded.email, 'learner@example.com')
        self.assertTrue(upgraded.has_usable_password())
        self.assertFalse(upgraded.profile.is_guest)

    def test_the_guest_token_stops_working(self):
        token, _ = self.start_guest()
        self.post('auth-signup', {
            'name': 'Aayushi', 'email': 'learner@example.com',
            'password': PASSWORD, 'accepted_terms': True,
        }, token=token)

        response = self.client.get(
            reverse('auth-me'), HTTP_AUTHORIZATION=f'Token {token}')
        self.assertEqual(response.status_code, 401)

    def test_signing_up_without_a_guest_token_starts_fresh(self):
        token, user = self.start_guest()
        guest = User.objects.get(pk=user['id'])
        self.practise(guest)

        # No Authorization header: a different person on a different device.
        self.post('auth-signup', {
            'name': 'Someone', 'email': 'other@example.com',
            'password': PASSWORD, 'accepted_terms': True,
        })

        self.assertEqual(User.objects.count(), 2)
        self.assertTrue(User.objects.get(pk=guest.pk).profile.is_guest)


class LoginTests(AuthTestCase):
    def setUp(self):
        super().setUp()
        self.post('auth-signup', {
            'name': 'Aayushi', 'email': 'learner@example.com',
            'password': PASSWORD, 'accepted_terms': True,
        })

    def test_login_returns_a_token(self):
        response = self.post('auth-login', {
            'email': 'learner@example.com', 'password': PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['token'])

    def test_login_accepts_any_case_of_the_email(self):
        response = self.post('auth-login', {
            'email': 'LEARNER@Example.com', 'password': PASSWORD})
        self.assertEqual(response.status_code, 200)

    def test_a_wrong_password_is_rejected(self):
        response = self.post('auth-login', {
            'email': 'learner@example.com', 'password': 'not-it'})
        self.assertEqual(response.status_code, 401)

    def test_an_unknown_email_says_so_rather_than_blaming_the_password(self):
        response = self.post('auth-login', {
            'email': 'nobody@example.com', 'password': PASSWORD})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()['field'], 'email')

    def test_a_wrong_password_and_an_unknown_email_are_told_apart(self):
        unknown = self.post('auth-login', {
            'email': 'nobody@example.com', 'password': PASSWORD})
        wrong = self.post('auth-login', {
            'email': 'learner@example.com', 'password': 'not-it'})
        self.assertNotEqual(unknown.json()['detail'], wrong.json()['detail'])

    def test_a_missing_password_is_named_before_anything_is_checked(self):
        response = self.post('auth-login', {
            'email': 'learner@example.com', 'password': ''})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['field'], 'password')

    def test_a_missing_email_is_named(self):
        response = self.post('auth-login', {'email': '', 'password': PASSWORD})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['field'], 'email')

    def test_an_account_whose_username_is_not_its_email_can_log_in(self):
        # createsuperuser produces exactly this shape. Authenticating on the
        # email directly used to lock these accounts out permanently.
        User.objects.create_user(
            username='aayushipatel', email='admin@example.com', password=PASSWORD)
        response = self.post('auth-login', {
            'email': 'admin@example.com', 'password': PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['token'])

    def test_logging_out_revokes_the_token(self):
        token = self.post('auth-login', {
            'email': 'learner@example.com', 'password': PASSWORD}).json()['token']
        self.assertEqual(self.post('auth-logout', token=token).status_code, 204)
        self.assertEqual(
            self.client.get(reverse('auth-me'),
                            HTTP_AUTHORIZATION=f'Token {token}').status_code,
            401,
        )


class ProfileTests(AuthTestCase):
    def setUp(self):
        super().setUp()
        self.token = self.post('auth-signup', {
            'name': 'Aayushi', 'email': 'learner@example.com',
            'password': PASSWORD, 'accepted_terms': True,
        }).json()['token']

    def auth(self):
        return {'HTTP_AUTHORIZATION': f'Token {self.token}'}

    def test_profile_requires_a_token(self):
        self.assertEqual(self.client.get(reverse('auth-me')).status_code, 401)

    def test_profile_can_be_updated(self):
        response = self.client.patch(
            reverse('auth-me'),
            {'avatar': '🦊', 'native_language': 'Gujarati'},
            content_type='application/json', **self.auth(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['avatar'], '🦊')
        self.assertEqual(response.json()['native_language'], 'Gujarati')

    def test_deleting_the_account_removes_its_progress(self):
        user = User.objects.get(email='learner@example.com')
        self.practise(user)
        self.assertEqual(UserVocabState.objects.count(), 1)

        response = self.client.delete(reverse('auth-me'), **self.auth())
        self.assertEqual(response.status_code, 204)
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(UserVocabState.objects.count(), 0)
        self.assertEqual(Token.objects.count(), 0)


class LearnerScopingTests(AuthTestCase):
    """One learner's schedule must never be visible to another."""

    def test_two_learners_have_separate_progress(self):
        first_token, first = self.start_guest()
        second_token, _ = self.start_guest()
        self.practise(User.objects.get(pk=first['id']), reviews=4)

        def progress(token):
            return self.client.get(
                reverse('progress'), HTTP_AUTHORIZATION=f'Token {token}').json()

        self.assertEqual(progress(first_token)['words_started'], 1)
        self.assertEqual(progress(second_token)['words_started'], 0)

    def test_an_unauthenticated_request_falls_back_to_the_demo_learner(self):
        # Keeps curl and the browsable API usable without a token.
        response = self.client.get(reverse('progress'))
        self.assertEqual(response.status_code, 200)
