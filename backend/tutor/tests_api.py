"""Tests for the session API.

The LLM is stubbed throughout, so these run offline and deterministically. What
they're checking is the wiring: that grading is server-side, that SM-2 runs
exactly when it should, and that an ungraded turn doesn't strand the learner.
"""

from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import llm
from .models import (
    DAILY_ROUTINE,
    ConversationSession,
    Turn,
    UserVocabState,
    VocabItem,
)

TOPIC = DAILY_ROUTINE


def make_turn_payload(marker='one'):
    """A well-formed adapter result, with the correct reply in the middle."""
    return {
        'tutor_message_es': f'¿Pregunta {marker}?',
        'tutor_message_en': f'Question {marker}?',
        'target_word': 'levantarse',
        'replies': [
            {'id': 0, 'es': 'Respuesta mala.', 'en': 'Bad answer.',
             'is_correct': False, 'why_wrong': 'needs the reflexive pronoun'},
            {'id': 1, 'es': 'Respuesta buena.', 'en': 'Good answer.',
             'is_correct': True, 'why_wrong': ''},
            {'id': 2, 'es': 'Otra mala.', 'en': 'Another bad one.',
             'is_correct': False, 'why_wrong': 'wrong verb person'},
        ],
        'provider': 'stub',
        'from_cache': False,
    }


def stub_turn(marker='one'):
    return mock.patch.object(
        llm, 'get_next_turn',
        side_effect=lambda *a, **k: make_turn_payload(marker))


def stub_eval(**overrides):
    payload = {
        'verdict': 'perfect',
        'graded': True,
        'used_target_word': True,
        'corrected_es': '',
        'feedback_en': 'Perfecto!',
        'tutor_message_es': '¿Y luego?',
        'tutor_message_en': 'And then?',
        'replies': make_turn_payload()['replies'],
        'provider': 'stub',
        'from_cache': False,
    }
    payload.update(overrides)
    return mock.patch.object(
        llm, 'evaluate_freetext_reply', side_effect=lambda *a, **k: dict(payload))


@override_settings(SESSION_TURN_LIMIT=3, DEMO_MODE=False)
class ApiTestCase(TestCase):
    """Shared fixtures: enough vocab for a 3-turn session."""

    def setUp(self):
        for n in range(4):
            VocabItem.objects.create(
                spanish=f'palabra{n}', english=f'word{n}',
                topic=TOPIC, difficulty=1)

    def start(self, topic=TOPIC):
        with stub_turn('one'):
            return self.client.post(
                reverse('session-start'), {'topic': topic},
                content_type='application/json')

    def answer_chip(self, session_id, reply_id, marker='two'):
        with stub_turn(marker):
            return self.client.post(
                reverse('session-next', args=[session_id]),
                {'mode': 'chip', 'reply_id': reply_id},
                content_type='application/json')


class StartSessionTests(ApiTestCase):
    def test_start_returns_first_turn(self):
        response = self.start()
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body['topic'], TOPIC)
        self.assertEqual(body['turn']['index'], 0)
        self.assertEqual(body['turn']['ai_message'], '¿Pregunta one?')
        self.assertEqual(len(body['turn']['reply_options']), 3)

    def test_answer_key_is_never_sent_to_the_client(self):
        body = self.start().json()
        serialised = str(body)
        self.assertNotIn('is_correct', serialised)
        self.assertNotIn('why_wrong', serialised)
        for option in body['turn']['reply_options']:
            self.assertEqual(set(option), {'id', 'es', 'en'})

    def test_session_records_an_ordered_plan(self):
        self.start()
        session = ConversationSession.objects.get()
        self.assertEqual(len(session.planned_item_ids), 3)
        self.assertEqual(session.target_items.count(), 3)
        self.assertEqual(
            session.planned_item_ids,
            [item.pk for item in session.target_items.all()][:3])

    def test_unknown_topic_is_rejected(self):
        response = self.client.post(
            reverse('session-start'), {'topic': 'quantum_physics'},
            content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('Unknown topic', response.json()['detail'])

    def test_missing_topic_is_rejected(self):
        response = self.client.post(
            reverse('session-start'), {}, content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_topic_with_no_vocab_returns_conflict_not_a_crash(self):
        VocabItem.objects.all().delete()
        response = self.client.post(
            reverse('session-start'), {'topic': TOPIC},
            content_type='application/json')
        self.assertEqual(response.status_code, 409)
        self.assertIn('seed_vocab', response.json()['detail'])

    def test_demo_user_is_created_on_first_use(self):
        self.assertFalse(User.objects.filter(username='demo').exists())
        self.start()
        user = User.objects.get(username='demo')
        self.assertFalse(user.has_usable_password())

    def test_provider_is_recorded_on_the_turn(self):
        self.start()
        turn = Turn.objects.get(index=0)
        self.assertEqual(turn.llm_provider, 'stub')
        self.assertFalse(turn.from_cache)


class TargetResolutionTests(ApiTestCase):
    """Grading must follow the word the learner actually saw on screen."""

    def test_turns_target_word_wins_over_the_scheduler_plan(self):
        # DEMO_MODE and fallback turns come from a fixed bank whose content may
        # not be the word the scheduler queued up.
        shown = VocabItem.objects.create(
            spanish='la mesa', english='table', topic=TOPIC, difficulty=2)
        payload = dict(make_turn_payload(), target_word='la mesa')
        with mock.patch.object(llm, 'get_next_turn',
                               side_effect=lambda *a, **k: dict(payload)):
            response = self.client.post(
                reverse('session-start'), {'topic': TOPIC},
                content_type='application/json')

        turn = Turn.objects.get(index=0)
        self.assertEqual(turn.target_item, shown)
        self.assertEqual(response.json()['turn']['target_word'], 'la mesa')

    def test_matching_is_case_insensitive(self):
        shown = VocabItem.objects.create(
            spanish='la mesa', english='table', topic=TOPIC)
        payload = dict(make_turn_payload(), target_word='LA MESA')
        with mock.patch.object(llm, 'get_next_turn',
                               side_effect=lambda *a, **k: dict(payload)):
            self.client.post(reverse('session-start'), {'topic': TOPIC},
                             content_type='application/json')
        self.assertEqual(Turn.objects.get(index=0).target_item, shown)

    def test_unrecognised_target_word_falls_back_to_the_plan(self):
        payload = dict(make_turn_payload(), target_word='una palabra inventada')
        with mock.patch.object(llm, 'get_next_turn',
                               side_effect=lambda *a, **k: dict(payload)):
            self.client.post(reverse('session-start'), {'topic': TOPIC},
                             content_type='application/json')
        session = ConversationSession.objects.get()
        self.assertEqual(
            Turn.objects.get(index=0).target_item_id, session.planned_item_ids[0])

    def test_target_word_from_another_topic_is_ignored(self):
        VocabItem.objects.create(
            spanish='el tren', english='train', topic='travel_basics')
        payload = dict(make_turn_payload(), target_word='el tren')
        with mock.patch.object(llm, 'get_next_turn',
                               side_effect=lambda *a, **k: dict(payload)):
            self.client.post(reverse('session-start'), {'topic': TOPIC},
                             content_type='application/json')
        session = ConversationSession.objects.get()
        self.assertEqual(
            Turn.objects.get(index=0).target_item_id, session.planned_item_ids[0])

    def test_sm2_credits_the_word_that_was_shown(self):
        shown = VocabItem.objects.create(
            spanish='la mesa', english='table', topic=TOPIC)
        payload = dict(make_turn_payload(), target_word='la mesa')
        with mock.patch.object(llm, 'get_next_turn',
                               side_effect=lambda *a, **k: dict(payload)):
            session_id = self.client.post(
                reverse('session-start'), {'topic': TOPIC},
                content_type='application/json').json()['session_id']
            self.client.post(
                reverse('session-next', args=[session_id]),
                {'mode': 'chip', 'reply_id': 1},
                content_type='application/json')

        reviewed = UserVocabState.objects.get(total_reviews=1)
        self.assertEqual(reviewed.item, shown, 'must credit the word on screen')


class ChipGradingTests(ApiTestCase):
    def test_correct_chip_is_graded_four_and_advances_sm2(self):
        session_id = self.start().json()['session_id']
        body = self.answer_chip(session_id, reply_id=1).json()

        self.assertTrue(body['grade']['was_correct'])
        self.assertEqual(body['grade']['quality'], 4)
        self.assertEqual(body['grade']['interval_days'], 1)
        self.assertIsNotNone(body['grade']['due_date'])
        self.assertFalse(body['is_complete'])
        self.assertEqual(body['turn']['index'], 1)

    def test_wrong_chip_is_graded_two_and_returns_the_correction(self):
        session_id = self.start().json()['session_id']
        body = self.answer_chip(session_id, reply_id=0).json()

        self.assertFalse(body['grade']['was_correct'])
        self.assertEqual(body['grade']['quality'], 2)
        self.assertEqual(body['grade']['feedback_en'], 'needs the reflexive pronoun')
        self.assertEqual(body['grade']['corrected_es'], 'Respuesta buena.')

    def test_grading_ignores_a_spoofed_is_correct_in_the_request(self):
        # The whole point of keeping the answer key server-side.
        session_id = self.start().json()['session_id']
        with stub_turn('two'):
            response = self.client.post(
                reverse('session-next', args=[session_id]),
                {'mode': 'chip', 'reply_id': 0,
                 'is_correct': True, 'was_correct': True, 'quality': 5},
                content_type='application/json')
        grade = response.json()['grade']
        self.assertFalse(grade['was_correct'], 'a wrong chip must stay wrong')
        self.assertEqual(grade['quality'], 2)

    def test_invalid_reply_id_is_rejected(self):
        session_id = self.start().json()['session_id']
        for bad in (99, -1, None, 'one'):
            with self.subTest(reply_id=bad):
                response = self.client.post(
                    reverse('session-next', args=[session_id]),
                    {'mode': 'chip', 'reply_id': bad},
                    content_type='application/json')
                self.assertEqual(response.status_code, 400)

    def test_rejected_answer_does_not_consume_the_turn(self):
        session_id = self.start().json()['session_id']
        self.client.post(
            reverse('session-next', args=[session_id]),
            {'mode': 'chip', 'reply_id': 99}, content_type='application/json')
        turn = Turn.objects.get(session_id=session_id, index=0)
        self.assertIsNone(turn.answered_at)
        self.assertEqual(Turn.objects.filter(session_id=session_id).count(), 1)

    def test_answer_is_persisted_on_the_turn(self):
        session_id = self.start().json()['session_id']
        self.answer_chip(session_id, reply_id=1)
        turn = Turn.objects.get(session_id=session_id, index=0)
        self.assertEqual(turn.user_reply, 'Respuesta buena.')
        self.assertEqual(turn.reply_mode, Turn.MODE_CHIP)
        self.assertTrue(turn.was_correct)
        self.assertEqual(turn.sm2_quality, 4)
        self.assertIsNotNone(turn.answered_at)
        self.assertTrue(turn.is_answered)
        self.assertTrue(turn.is_graded)

    def test_each_turn_drills_the_next_planned_item(self):
        session_id = self.start().json()['session_id']
        session = ConversationSession.objects.get(pk=session_id)
        self.answer_chip(session_id, reply_id=1)
        self.answer_chip(session_id, reply_id=1, marker='three')

        targets = list(
            Turn.objects.filter(session_id=session_id)
            .order_by('index').values_list('target_item_id', flat=True))
        self.assertEqual(targets, session.planned_item_ids[:len(targets)])
        self.assertEqual(len(set(targets)), len(targets), 'no repeats')

    def test_session_completes_at_the_turn_limit(self):
        session_id = self.start().json()['session_id']
        self.answer_chip(session_id, reply_id=1)
        self.answer_chip(session_id, reply_id=1)
        final = self.answer_chip(session_id, reply_id=1).json()

        self.assertTrue(final['is_complete'])
        self.assertIsNone(final['turn'], 'no turn after the last one')
        session = ConversationSession.objects.get(pk=session_id)
        self.assertTrue(session.is_complete)
        self.assertIsNotNone(session.ended_at)

    def test_answering_a_completed_session_is_rejected(self):
        session_id = self.start().json()['session_id']
        for _ in range(3):
            self.answer_chip(session_id, reply_id=1)
        response = self.answer_chip(session_id, reply_id=1)
        self.assertEqual(response.status_code, 409)

    def test_missing_session_returns_404(self):
        response = self.client.post(
            reverse('session-next', args=[9999]),
            {'mode': 'chip', 'reply_id': 0}, content_type='application/json')
        self.assertEqual(response.status_code, 404)

    def test_unknown_mode_is_rejected(self):
        session_id = self.start().json()['session_id']
        response = self.client.post(
            reverse('session-next', args=[session_id]),
            {'mode': 'telepathy'}, content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_mode_defaults_to_chip(self):
        session_id = self.start().json()['session_id']
        with stub_turn('two'):
            response = self.client.post(
                reverse('session-next', args=[session_id]),
                {'reply_id': 1}, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['grade']['was_correct'])


class FreetextGradingTests(ApiTestCase):
    def test_perfect_reply_is_graded_five(self):
        session_id = self.start().json()['session_id']
        with stub_eval(verdict='perfect'):
            body = self.client.post(
                reverse('session-next', args=[session_id]),
                {'mode': 'freetext', 'text': 'Me levanto a las siete.'},
                content_type='application/json').json()
        self.assertEqual(body['grade']['quality'], 5)
        self.assertTrue(body['grade']['was_correct'])

    def test_verdicts_map_onto_sm2_grades(self):
        expected = {'perfect': 5, 'minor': 4, 'awkward': 3, 'wrong': 1, 'blank': 0}
        for verdict, quality in expected.items():
            with self.subTest(verdict=verdict):
                session_id = self.start().json()['session_id']
                with stub_eval(verdict=verdict):
                    body = self.client.post(
                        reverse('session-next', args=[session_id]),
                        {'mode': 'freetext', 'text': 'algo'},
                        content_type='application/json').json()
                self.assertEqual(body['grade']['quality'], quality)
                self.assertEqual(
                    body['grade']['was_correct'], quality >= 3)

    def test_freetext_reuses_the_evaluation_continuation(self):
        # The eval call already returns the next line, so no second call.
        session_id = self.start().json()['session_id']
        with stub_eval() as evaluated, stub_turn('unused') as generated:
            body = self.client.post(
                reverse('session-next', args=[session_id]),
                {'mode': 'freetext', 'text': 'algo'},
                content_type='application/json').json()
        self.assertEqual(evaluated.call_count, 1)
        self.assertEqual(generated.call_count, 0, 'should not call get_next_turn')
        self.assertEqual(body['turn']['ai_message'], '¿Y luego?')

    def test_ungraded_reply_skips_sm2_but_still_advances(self):
        # The critical case: a provider outage must not corrupt the schedule.
        session_id = self.start().json()['session_id']
        with stub_eval(graded=False, verdict=None,
                       feedback_en="Couldn't check that one."):
            body = self.client.post(
                reverse('session-next', args=[session_id]),
                {'mode': 'freetext', 'text': 'Me levanto a las siete.'},
                content_type='application/json').json()

        self.assertFalse(body['grade']['graded'])
        self.assertIsNone(body['grade']['quality'])
        self.assertIsNone(body['grade']['was_correct'])
        self.assertIsNone(body['grade']['interval_days'])
        self.assertEqual(UserVocabState.objects.filter(total_reviews__gt=0).count(), 0)

        # ...but the turn is consumed, so the learner is not stuck on it.
        turn = Turn.objects.get(session_id=session_id, index=0)
        self.assertIsNotNone(turn.answered_at)
        self.assertTrue(turn.is_answered)
        self.assertFalse(turn.is_graded)
        self.assertIsNotNone(body['turn'], 'conversation should continue')

    def test_ungraded_turn_does_not_block_the_next_answer(self):
        session_id = self.start().json()['session_id']
        with stub_eval(graded=False, verdict=None):
            self.client.post(
                reverse('session-next', args=[session_id]),
                {'mode': 'freetext', 'text': 'algo'},
                content_type='application/json')
        follow_up = self.answer_chip(session_id, reply_id=1)
        self.assertEqual(follow_up.status_code, 200)
        self.assertTrue(follow_up.json()['grade']['was_correct'])

    def test_empty_text_is_still_recorded(self):
        session_id = self.start().json()['session_id']
        with stub_eval(verdict='blank', feedback_en='Nothing came through.'):
            body = self.client.post(
                reverse('session-next', args=[session_id]),
                {'mode': 'freetext', 'text': ''},
                content_type='application/json').json()
        self.assertEqual(body['grade']['quality'], 0)
        self.assertFalse(body['grade']['was_correct'])


class Sm2IntegrationTests(ApiTestCase):
    def test_correct_answer_schedules_the_word_for_tomorrow(self):
        session_id = self.start().json()['session_id']
        self.answer_chip(session_id, reply_id=1)

        state = UserVocabState.objects.get(total_reviews=1)
        self.assertEqual(state.repetitions, 1)
        self.assertEqual(state.interval_days, 1)
        self.assertEqual(state.due_date, timezone.localdate() + timedelta(days=1))
        self.assertEqual(state.correct_reviews, 1)
        self.assertEqual(state.lapses, 0)

    def test_wrong_answer_lowers_the_ease_factor(self):
        session_id = self.start().json()['session_id']
        self.answer_chip(session_id, reply_id=0)

        state = UserVocabState.objects.get(total_reviews=1)
        self.assertEqual(state.repetitions, 0)
        self.assertAlmostEqual(state.ease_factor, 2.18, places=4)
        self.assertEqual(state.correct_reviews, 0)

    def test_one_review_recorded_per_answered_turn(self):
        session_id = self.start().json()['session_id']
        self.answer_chip(session_id, reply_id=1)
        self.answer_chip(session_id, reply_id=1)
        self.assertEqual(
            UserVocabState.objects.filter(total_reviews=1).count(), 2)
        self.assertEqual(
            UserVocabState.objects.filter(total_reviews__gt=1).count(), 0)


class RecapTests(ApiTestCase):
    def test_recap_summarises_a_finished_session(self):
        session_id = self.start().json()['session_id']
        self.answer_chip(session_id, reply_id=1)   # right
        self.answer_chip(session_id, reply_id=0)   # wrong
        self.answer_chip(session_id, reply_id=1)   # right

        body = self.client.get(reverse('session-recap', args=[session_id])).json()
        self.assertEqual(body['turns_answered'], 3)
        self.assertEqual(body['turns_graded'], 3)
        self.assertEqual(body['turns_correct'], 2)
        self.assertAlmostEqual(body['accuracy'], 0.67, places=2)
        self.assertEqual(body['words_practiced'], 3)
        self.assertTrue(body['is_complete'])
        self.assertEqual(body['topic_label'], 'Daily Routine')

    def test_recap_lists_each_word_with_its_next_due_date(self):
        session_id = self.start().json()['session_id']
        self.answer_chip(session_id, reply_id=1)

        body = self.client.get(reverse('session-recap', args=[session_id])).json()
        word = body['words'][0]
        self.assertEqual(set(word), {
            'spanish', 'english', 'was_correct', 'graded',
            'due_date', 'interval_days', 'repetitions', 'ease_factor'})
        self.assertTrue(word['was_correct'])
        self.assertEqual(word['interval_days'], 1)
        self.assertEqual(word['repetitions'], 1)

    def test_recap_of_an_untouched_session_is_empty_not_an_error(self):
        session_id = self.start().json()['session_id']
        body = self.client.get(reverse('session-recap', args=[session_id])).json()
        self.assertEqual(body['turns_answered'], 0)
        self.assertEqual(body['words_practiced'], 0)
        self.assertIsNone(body['accuracy'])
        self.assertFalse(body['is_complete'])

    def test_recap_marks_ungraded_words(self):
        session_id = self.start().json()['session_id']
        with stub_eval(graded=False, verdict=None):
            self.client.post(
                reverse('session-next', args=[session_id]),
                {'mode': 'freetext', 'text': 'algo'},
                content_type='application/json')

        body = self.client.get(reverse('session-recap', args=[session_id])).json()
        self.assertEqual(body['turns_answered'], 1)
        self.assertEqual(body['turns_graded'], 0)
        self.assertIsNone(body['accuracy'])
        self.assertFalse(body['words'][0]['graded'])

    def test_recap_reports_schedules_for_words_outside_the_plan(self):
        # A fallback turn can drill a word the scheduler never queued. The
        # recap has to show its real due date, not nulls.
        VocabItem.objects.create(
            spanish='la mesa', english='table', topic=TOPIC, difficulty=3)
        payload = dict(make_turn_payload(), target_word='la mesa')
        with mock.patch.object(llm, 'get_next_turn',
                               side_effect=lambda *a, **k: dict(payload)):
            session_id = self.client.post(
                reverse('session-start'), {'topic': TOPIC},
                content_type='application/json').json()['session_id']
            self.client.post(
                reverse('session-next', args=[session_id]),
                {'mode': 'chip', 'reply_id': 1},
                content_type='application/json')

        session = ConversationSession.objects.get(pk=session_id)
        self.assertNotIn(
            'la mesa',
            [item.spanish for item in session.target_items.all()],
            'precondition: the drilled word is outside the plan')

        word = self.client.get(
            reverse('session-recap', args=[session_id])).json()['words'][0]
        self.assertEqual(word['spanish'], 'la mesa')
        self.assertIsNotNone(word['due_date'], 'due date must not be null')
        self.assertEqual(word['interval_days'], 1)
        self.assertEqual(word['repetitions'], 1)
        self.assertEqual(word['ease_factor'], 2.5)

    def test_every_graded_word_in_a_recap_has_a_due_date(self):
        session_id = self.start().json()['session_id']
        for _ in range(3):
            self.answer_chip(session_id, reply_id=1)
        body = self.client.get(reverse('session-recap', args=[session_id])).json()
        for word in body['words']:
            with self.subTest(word=word['spanish']):
                if word['graded']:
                    self.assertIsNotNone(word['due_date'])
                    self.assertIsNotNone(word['interval_days'])

    def test_recap_of_a_missing_session_is_404(self):
        self.assertEqual(
            self.client.get(reverse('session-recap', args=[9999])).status_code, 404)


class RoutingTests(TestCase):
    def test_index_lists_the_endpoints(self):
        body = self.client.get('/').json()
        self.assertEqual(body['service'], 'charla')
        self.assertIn('start_session', body['endpoints'])

    def test_endpoint_paths_match_the_documented_contract(self):
        self.assertEqual(reverse('session-start'), '/api/sessions/start/')
        self.assertEqual(reverse('session-next', args=[7]), '/api/sessions/7/next/')
        self.assertEqual(reverse('session-recap', args=[7]), '/api/sessions/7/recap/')
