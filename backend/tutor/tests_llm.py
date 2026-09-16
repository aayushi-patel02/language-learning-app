"""Tests for the LLM adapter.

Every test stubs the provider function, so the suite never touches the network
and never spends API credit. The point is to prove the parsing and fallback
layers hold up against the specific ways models malform output.
"""

import json
import os
from unittest import mock

from django.test import TestCase, override_settings

from . import llm
from .models import DAILY_ROUTINE, ORDERING_FOOD, TRAVEL_BASICS

GOOD_TURN = {
    'tutor_message_es': '¿A qué hora te levantas?',
    'tutor_message_en': 'What time do you get up?',
    'target_word': 'levantarse',
    'replies': [
        {'es': 'Me levanto a las siete.', 'en': 'I get up at seven.', 'is_correct': True},
        {'es': 'Yo levanto a las siete.', 'en': 'I get up at seven.',
         'is_correct': False, 'why_wrong': 'needs the reflexive pronoun'},
        {'es': 'Me levanta a las siete.', 'en': 'I get up at seven.',
         'is_correct': False, 'why_wrong': 'wrong person'},
    ],
}

GOOD_EVAL = {
    'verdict': 'minor',
    'used_target_word': True,
    'corrected_es': 'Me levanto a las siete.',
    'feedback_en': 'Almost - just add the accent.',
    'tutor_message_es': '¿Y desayunas en casa?',
    'tutor_message_en': 'And do you have breakfast at home?',
    'replies': GOOD_TURN['replies'],
}


def _all_providers(call):
    """Register the stub under every real provider name.

    Keyed off llm.PROVIDERS rather than a hardcoded list, so adding a
    provider cannot silently leave these helpers behind: an unregistered
    name makes active_provider fall back and the test looks like a
    behaviour failure rather than a missing stub.
    """
    return {name: call for name in llm.PROVIDERS}


def stub(response_text):
    """Patch every provider to return a fixed raw string."""
    def _call(system_prompt, user_content):
        return response_text
    return mock.patch.object(llm, 'PROVIDERS', _all_providers(_call))


def raising_stub(exc):
    def _call(system_prompt, user_content):
        raise exc
    return mock.patch.object(llm, 'PROVIDERS', _all_providers(_call))


class ExtractJsonTests(TestCase):
    def test_plain_json(self):
        self.assertEqual(llm._extract_json('{"a": 1}'), {'a': 1})

    def test_markdown_fenced_json(self):
        self.assertEqual(llm._extract_json('```json\n{"a": 1}\n```'), {'a': 1})

    def test_bare_fenced_json(self):
        self.assertEqual(llm._extract_json('```\n{"a": 1}\n```'), {'a': 1})

    def test_json_with_prose_prefix(self):
        text = 'Sure! Here is the JSON you asked for:\n{"a": 1}'
        self.assertEqual(llm._extract_json(text), {'a': 1})

    def test_json_with_trailing_commentary(self):
        text = '{"a": 1}\n\nLet me know if you want another turn!'
        self.assertEqual(llm._extract_json(text), {'a': 1})

    def test_json_wrapped_in_both_prose_and_fences(self):
        text = 'Here you go:\n```json\n{"a": 1}\n```\nHope that helps.'
        self.assertEqual(llm._extract_json(text), {'a': 1})

    def test_nested_braces_survive(self):
        text = 'Result: {"a": {"b": [1, 2]}} done'
        self.assertEqual(llm._extract_json(text), {'a': {'b': [1, 2]}})

    def test_empty_response_raises(self):
        for bad in ('', '   ', '\n', None):
            with self.subTest(raw=bad):
                with self.assertRaises(llm.LLMError):
                    llm._extract_json(bad)

    def test_response_with_no_object_raises(self):
        with self.assertRaises(llm.LLMError):
            llm._extract_json('I cannot help with that request.')

    def test_truncated_json_raises(self):
        with self.assertRaises(llm.LLMError):
            llm._extract_json('{"tutor_message_es": "hola", "replies": [')


class NormaliseRepliesTests(TestCase):
    def test_well_formed_replies(self):
        chips = llm._normalise_replies(GOOD_TURN['replies'])
        self.assertEqual(len(chips), 3)
        self.assertEqual([c['id'] for c in chips], [0, 1, 2])
        self.assertEqual(sum(c['is_correct'] for c in chips), 1)

    def test_bare_strings_are_accepted_with_first_as_answer(self):
        chips = llm._normalise_replies(['Me levanto.', 'Yo levanto.', 'Me levanta.'])
        self.assertEqual(len(chips), 3)
        self.assertTrue(chips[0]['is_correct'])
        self.assertFalse(chips[1]['is_correct'])

    def test_single_reply_sent_unwrapped_as_dict(self):
        with self.assertRaises(llm.LLMError):
            # One chip is not enough for a choice, even if well-formed.
            llm._normalise_replies({'es': 'Me levanto.', 'is_correct': True})

    def test_alternate_field_names_are_accepted(self):
        chips = llm._normalise_replies([
            {'spanish': 'Me levanto.', 'english': 'I get up.', 'is_correct': True},
            {'spanish': 'Yo levanto.', 'english': 'I get up.', 'is_correct': False},
        ])
        self.assertEqual(chips[0]['es'], 'Me levanto.')
        self.assertEqual(chips[0]['en'], 'I get up.')

    def test_entries_without_spanish_are_dropped(self):
        chips = llm._normalise_replies([
            {'es': 'Me levanto.', 'is_correct': True},
            {'es': '', 'is_correct': False},
            {'en': 'no spanish here', 'is_correct': False},
            {'es': 'Yo levanto.', 'is_correct': False},
        ])
        self.assertEqual(len(chips), 2)

    def test_more_than_three_replies_are_trimmed(self):
        chips = llm._normalise_replies([
            {'es': f'Opción {i}.', 'is_correct': i == 0} for i in range(6)
        ])
        self.assertEqual(len(chips), 3)

    def test_truthy_is_correct_values_are_coerced(self):
        chips = llm._normalise_replies([
            {'es': 'Sí.', 'is_correct': 'true'},
            {'es': 'No.', 'is_correct': 0},
        ])
        self.assertTrue(chips[0]['is_correct'])
        self.assertFalse(chips[1]['is_correct'])

    def test_no_correct_reply_raises(self):
        with self.assertRaises(llm.LLMError):
            llm._normalise_replies([
                {'es': 'Uno.', 'is_correct': False},
                {'es': 'Dos.', 'is_correct': False},
            ])

    def test_non_list_raises(self):
        for bad in ('not a list', 42, None):
            with self.subTest(raw=bad):
                with self.assertRaises(llm.LLMError):
                    llm._normalise_replies(bad)


@override_settings(DEMO_MODE=False, LLM_PROVIDER='deepseek')
class GetNextTurnTests(TestCase):
    def test_well_formed_response_is_used(self):
        with stub(json.dumps(GOOD_TURN)):
            turn = llm.get_next_turn(DAILY_ROUTINE)
        self.assertEqual(turn['tutor_message_es'], '¿A qué hora te levantas?')
        self.assertEqual(turn['provider'], 'deepseek')
        self.assertFalse(turn['from_cache'])
        self.assertEqual(len(turn['replies']), 3)

    def test_fenced_response_is_used(self):
        with stub(f'```json\n{json.dumps(GOOD_TURN)}\n```'):
            turn = llm.get_next_turn(DAILY_ROUTINE)
        self.assertFalse(turn['from_cache'])

    def test_provider_exception_falls_back(self):
        with raising_stub(TimeoutError('connection timed out')):
            turn = llm.get_next_turn(ORDERING_FOOD)
        self.assertEqual(turn['provider'], 'fallback')
        self.assertTrue(turn['from_cache'])
        # Still a usable turn, not an error dict.
        self.assertTrue(turn['tutor_message_es'])
        self.assertGreaterEqual(len(turn['replies']), 2)

    def test_garbage_response_falls_back(self):
        for raw in ('', 'I refuse.', '{"broken": ', '[]', 'null'):
            with self.subTest(raw=raw):
                with stub(raw):
                    turn = llm.get_next_turn(TRAVEL_BASICS)
                self.assertEqual(turn['provider'], 'fallback')
                self.assertTrue(turn['tutor_message_es'])

    def test_response_missing_tutor_message_falls_back(self):
        with stub(json.dumps({'replies': GOOD_TURN['replies']})):
            turn = llm.get_next_turn(DAILY_ROUTINE)
        self.assertEqual(turn['provider'], 'fallback')

    def test_response_with_no_correct_reply_falls_back(self):
        payload = dict(GOOD_TURN, replies=[
            {'es': 'Uno.', 'is_correct': False},
            {'es': 'Dos.', 'is_correct': False},
        ])
        with stub(json.dumps(payload)):
            turn = llm.get_next_turn(DAILY_ROUTINE)
        self.assertEqual(turn['provider'], 'fallback')

    def test_fallback_is_topic_appropriate(self):
        with raising_stub(RuntimeError('boom')):
            food = llm.get_next_turn(ORDERING_FOOD, turn_index=0)
            travel = llm.get_next_turn(TRAVEL_BASICS, turn_index=0)
        self.assertNotEqual(food['tutor_message_es'], travel['tutor_message_es'])

    def test_unknown_topic_still_returns_a_turn(self):
        with raising_stub(RuntimeError('boom')):
            turn = llm.get_next_turn('not_a_real_topic')
        self.assertTrue(turn['tutor_message_es'])

    def test_history_and_vocab_reach_the_prompt(self):
        seen = {}

        def _capture(system_prompt, user_content):
            seen['user'] = user_content
            seen['system'] = system_prompt
            return json.dumps(GOOD_TURN)

        with mock.patch.object(llm, 'PROVIDERS', {'deepseek': _capture}):
            llm.get_next_turn(
                ORDERING_FOOD,
                due_items=[{'spanish': 'la cuenta', 'english': 'the bill'}],
                history=[{'tutor': 'Hola.', 'user': 'Hola.'}],
            )
        self.assertIn('la cuenta', seen['user'])
        self.assertIn('the bill', seen['user'])
        self.assertIn('Hola.', seen['user'])
        self.assertIn('ordering food', seen['user'])


@override_settings(DEMO_MODE=True)
class DemoModeTests(TestCase):
    def test_demo_mode_never_calls_the_provider(self):
        def _explode(system_prompt, user_content):
            raise AssertionError('DEMO_MODE must not hit the network')

        with mock.patch.object(llm, 'PROVIDERS', {'deepseek': _explode}):
            turn = llm.get_next_turn(DAILY_ROUTINE)
        self.assertTrue(turn['from_cache'])
        self.assertEqual(turn['provider'], 'demo')

    def test_demo_mode_is_deterministic(self):
        first = llm.get_next_turn(ORDERING_FOOD, turn_index=1)
        second = llm.get_next_turn(ORDERING_FOOD, turn_index=1)
        self.assertEqual(first, second)

    def test_demo_mode_advances_with_turn_index(self):
        turns = [llm.get_next_turn(DAILY_ROUTINE, turn_index=i)['tutor_message_es']
                 for i in range(3)]
        self.assertEqual(len(set(turns)), 3, 'each turn should be a different line')

    def test_turn_index_wraps_past_the_end_of_the_bank(self):
        bank_size = len(llm.FALLBACK_TURNS[DAILY_ROUTINE])
        first = llm.get_next_turn(DAILY_ROUTINE, turn_index=0)
        wrapped = llm.get_next_turn(DAILY_ROUTINE, turn_index=bank_size)
        self.assertEqual(first['tutor_message_es'], wrapped['tutor_message_es'])

    def test_mutating_a_returned_turn_does_not_poison_the_bank(self):
        turn = llm.get_next_turn(DAILY_ROUTINE, turn_index=0)
        turn['replies'][0]['es'] = 'MUTATED'
        fresh = llm.get_next_turn(DAILY_ROUTINE, turn_index=0)
        self.assertNotEqual(fresh['replies'][0]['es'], 'MUTATED')


@override_settings(DEMO_MODE=False, LLM_PROVIDER='deepseek')
class EvaluateFreetextTests(TestCase):
    def test_well_formed_evaluation_is_used(self):
        with stub(json.dumps(GOOD_EVAL)):
            result = llm.evaluate_freetext_reply(
                DAILY_ROUTINE, 'levantarse', 'Me levanto a las siete')
        self.assertEqual(result['verdict'], 'minor')
        self.assertTrue(result['graded'])
        self.assertTrue(result['used_target_word'])
        self.assertEqual(result['corrected_es'], 'Me levanto a las siete.')

    def test_every_documented_verdict_is_accepted(self):
        for verdict in llm.VERDICTS:
            with self.subTest(verdict=verdict):
                with stub(json.dumps(dict(GOOD_EVAL, verdict=verdict))):
                    result = llm.evaluate_freetext_reply(
                        DAILY_ROUTINE, 'levantarse', 'algo')
                self.assertEqual(result['verdict'], verdict)

    def test_unknown_verdict_degrades_to_wrong_but_stays_graded(self):
        with stub(json.dumps(dict(GOOD_EVAL, verdict='excellent'))):
            result = llm.evaluate_freetext_reply(
                DAILY_ROUTINE, 'levantarse', 'Me levanto')
        self.assertEqual(result['verdict'], 'wrong')
        self.assertTrue(result['graded'])

    def test_verdict_is_case_insensitive(self):
        with stub(json.dumps(dict(GOOD_EVAL, verdict='PERFECT'))):
            result = llm.evaluate_freetext_reply(
                DAILY_ROUTINE, 'levantarse', 'Me levanto')
        self.assertEqual(result['verdict'], 'perfect')

    def test_empty_reply_is_graded_blank_without_calling_out(self):
        def _explode(system_prompt, user_content):
            raise AssertionError('should not call the provider for a blank reply')

        with mock.patch.object(llm, 'PROVIDERS', {'deepseek': _explode}):
            for blank in ('', '   ', '\n\t'):
                with self.subTest(reply=blank):
                    result = llm.evaluate_freetext_reply(
                        DAILY_ROUTINE, 'levantarse', blank)
                    self.assertEqual(result['verdict'], 'blank')
                    self.assertTrue(result['graded'])

    def test_provider_failure_returns_ungraded(self):
        # The critical case: an outage must not record a wrong answer.
        with raising_stub(TimeoutError('timed out')):
            result = llm.evaluate_freetext_reply(
                DAILY_ROUTINE, 'levantarse', 'Me levanto a las siete')
        self.assertFalse(result['graded'])
        self.assertIsNone(result['verdict'])
        self.assertTrue(result['tutor_message_es'], 'conversation should still continue')
        self.assertIn("hasn't affected your review", result['feedback_en'])

    def test_garbage_response_returns_ungraded(self):
        for raw in ('', 'nope', '{"verdict": '):
            with self.subTest(raw=raw):
                with stub(raw):
                    result = llm.evaluate_freetext_reply(
                        DAILY_ROUTINE, 'levantarse', 'Me levanto')
                self.assertFalse(result['graded'])

    def test_evaluation_missing_tutor_message_keeps_the_grade(self):
        payload = {k: v for k, v in GOOD_EVAL.items() if k != 'tutor_message_es'}
        with stub(json.dumps(payload)):
            result = llm.evaluate_freetext_reply(
                DAILY_ROUTINE, 'levantarse', 'Me levanto')
        self.assertTrue(result['graded'], 'a good grade should survive a missing message')
        self.assertEqual(result['verdict'], 'minor')
        self.assertTrue(result['tutor_message_es'], 'borrowed from the fallback bank')

    def test_evaluation_with_unusable_replies_keeps_the_grade(self):
        payload = dict(GOOD_EVAL, replies='not a list')
        with stub(json.dumps(payload)):
            result = llm.evaluate_freetext_reply(
                DAILY_ROUTINE, 'levantarse', 'Me levanto')
        self.assertTrue(result['graded'])
        self.assertGreaterEqual(len(result['replies']), 2)

    def test_vocab_object_is_read_for_the_prompt(self):
        seen = {}

        def _capture(system_prompt, user_content):
            seen['user'] = user_content
            return json.dumps(GOOD_EVAL)

        class FakeItem:
            spanish = 'la cuenta'
            english = 'the bill'

        with mock.patch.object(llm, 'PROVIDERS', {'deepseek': _capture}):
            llm.evaluate_freetext_reply(ORDERING_FOOD, FakeItem(), 'La cuenta por favor')
        self.assertIn('la cuenta', seen['user'])
        self.assertIn('La cuenta por favor', seen['user'])


class GeminiTransportTests(TestCase):
    """Gemini's envelope and failure modes differ from the OpenAI-shaped ones."""

    def _run(self, json_body, status=200):
        response = mock.Mock()
        response.status_code = status
        response.json.return_value = json_body
        response.text = str(json_body)
        with mock.patch.dict(os.environ, {'GEMINI_API_KEY': 'test-key'}):
            with mock.patch('requests.post', return_value=response) as posted:
                return llm._call_gemini('system', 'user'), posted

    def test_text_is_extracted_from_the_candidate(self):
        text, _ = self._run({
            'candidates': [{'content': {'parts': [{'text': '{"ok": true}'}]},
                            'finishReason': 'STOP'}]
        })
        self.assertEqual(text, '{"ok": true}')

    def test_multipart_responses_are_joined(self):
        text, _ = self._run({
            'candidates': [{'content': {'parts': [{'text': '{"a":'}, {'text': ' 1}'}]},
                            'finishReason': 'STOP'}]
        })
        self.assertEqual(text, '{"a": 1}')

    def test_missing_key_raises_before_any_request(self):
        with mock.patch.dict(os.environ, {'GEMINI_API_KEY': ''}):
            with mock.patch('requests.post') as posted:
                with self.assertRaises(llm.LLMError):
                    llm._call_gemini('system', 'user')
        posted.assert_not_called()

    def test_safety_block_raises_with_the_reason(self):
        with self.assertRaises(llm.LLMError) as caught:
            self._run({'candidates': [], 'promptFeedback': {'blockReason': 'SAFETY'}})
        self.assertIn('SAFETY', str(caught.exception))

    def test_no_candidates_raises(self):
        with self.assertRaises(llm.LLMError):
            self._run({})

    def test_empty_parts_raises_with_finish_reason(self):
        with self.assertRaises(llm.LLMError) as caught:
            self._run({'candidates': [{'content': {'parts': []},
                                       'finishReason': 'RECITATION'}]})
        self.assertIn('RECITATION', str(caught.exception))

    def test_api_key_is_sent_as_a_header_not_in_the_url(self):
        # A key in a query string leaks into proxy and access logs.
        _, posted = self._run({
            'candidates': [{'content': {'parts': [{'text': '{}'}]},
                            'finishReason': 'STOP'}]
        })
        url = posted.call_args.args[0]
        headers = posted.call_args.kwargs['headers']
        self.assertNotIn('test-key', url)
        self.assertNotIn('key=', url)
        self.assertEqual(headers['x-goog-api-key'], 'test-key')

    def test_json_mode_is_requested(self):
        _, posted = self._run({
            'candidates': [{'content': {'parts': [{'text': '{}'}]},
                            'finishReason': 'STOP'}]
        })
        body = posted.call_args.kwargs['json']
        self.assertEqual(
            body['generationConfig']['responseMimeType'], 'application/json')
        self.assertEqual(body['system_instruction']['parts'][0]['text'], 'system')

    def test_configured_model_lands_in_the_url(self):
        with mock.patch.dict(os.environ, {'GEMINI_MODEL': 'gemini-3-turbo'}):
            _, posted = self._run({
                'candidates': [{'content': {'parts': [{'text': '{}'}]},
                                'finishReason': 'STOP'}]
            })
        self.assertIn('gemini-3-turbo:generateContent', posted.call_args.args[0])

    def test_http_error_surfaces_googles_own_message(self):
        # raise_for_status() would hide this, and the body is where the
        # difference between "API not enabled" and "project denied" lives.
        body = {'error': {'code': 403, 'status': 'PERMISSION_DENIED',
                          'message': 'Your project has been denied access.'}}
        with self.assertRaises(llm.LLMError) as caught:
            self._run(body, status=403)
        message = str(caught.exception)
        self.assertIn('403', message)
        self.assertIn('PERMISSION_DENIED', message)
        self.assertIn('denied access', message)

    def test_http_error_with_a_non_json_body_still_raises_cleanly(self):
        response = mock.Mock()
        response.status_code = 500
        response.json.side_effect = ValueError('not json')
        response.text = '<html>Internal Server Error</html>'
        with mock.patch.dict(os.environ, {'GEMINI_API_KEY': 'test-key'}):
            with mock.patch('requests.post', return_value=response):
                with self.assertRaises(llm.LLMError) as caught:
                    llm._call_gemini('system', 'user')
        self.assertIn('500', str(caught.exception))

    def test_service_disabled_is_distinguishable_from_permission_denied(self):
        body = {'error': {'code': 403, 'status': 'SERVICE_DISABLED',
                          'message': 'Generative Language API has not been used.'}}
        with self.assertRaises(llm.LLMError) as caught:
            self._run(body, status=403)
        self.assertIn('SERVICE_DISABLED', str(caught.exception))

    @override_settings(DEMO_MODE=False, LLM_PROVIDER='gemini')
    def test_gemini_failure_still_falls_back_to_a_usable_turn(self):
        with raising_stub(RuntimeError('402 no quota')):
            turn = llm.get_next_turn(DAILY_ROUTINE)
        self.assertEqual(turn['provider'], 'fallback')
        self.assertTrue(turn['tutor_message_es'])


class SentenceStarterTests(TestCase):
    """Scaffolding is optional, so anything unusable is dropped, not raised on."""

    def test_a_well_formed_starter_is_kept(self):
        self.assertEqual(
            llm._normalise_starter('Me levanto a las ____.'),
            'Me levanto a las ____.',
        )

    def test_a_starter_without_a_blank_is_dropped(self):
        # With nothing left out it is just the answer.
        self.assertEqual(llm._normalise_starter('Me levanto a las siete.'), '')

    def test_a_bare_blank_is_dropped(self):
        # "____" scaffolds nothing at all.
        for useless in ('____', '_', '  ___  ', '____.'):
            with self.subTest(starter=useless):
                self.assertEqual(llm._normalise_starter(useless), '')

    def test_missing_or_non_string_values_are_dropped(self):
        for bad in (None, '', '   ', 123):
            with self.subTest(value=bad):
                self.assertEqual(llm._normalise_starter(bad), '')

    def test_an_overlong_starter_is_truncated_not_rejected(self):
        self.assertEqual(len(llm._normalise_starter('a' * 400 + ' ____')), 200)

    @override_settings(DEMO_MODE=False, LLM_PROVIDER='groq')
    def test_a_turn_survives_an_unusable_starter(self):
        payload = dict(GOOD_TURN, sentence_starter='____')
        with stub(json.dumps(payload)):
            turn = llm.get_next_turn(DAILY_ROUTINE)
        self.assertEqual(turn['provider'], 'groq', 'must not fall back')
        self.assertEqual(turn['sentence_starter'], '')

    def test_every_demo_turn_has_a_usable_starter(self):
        for topic, bank in llm.FALLBACK_TURNS.items():
            for index, turn in enumerate(bank):
                with self.subTest(topic=topic, index=index):
                    starter = turn['sentence_starter']
                    self.assertTrue(starter, 'demo mode should never lack one')
                    self.assertEqual(llm._normalise_starter(starter), starter)


class OpenAiCompatibleTransportTests(TestCase):
    """DeepSeek and Groq share one code path; check it routes correctly."""

    def _client(self, content='{"ok": true}'):
        message = mock.Mock()
        message.content = content
        choice = mock.Mock()
        choice.message = message
        completion = mock.Mock()
        completion.choices = [choice]

        client = mock.Mock()
        client.chat.completions.create.return_value = completion
        factory = mock.Mock(return_value=client)
        return factory, client

    def test_groq_uses_its_own_base_url_key_and_model(self):
        factory, client = self._client()
        env = {'GROQ_API_KEY': 'groq-key', 'GROQ_MODEL': 'llama-test'}
        with mock.patch.dict(os.environ, env):
            with mock.patch('openai.OpenAI', factory):
                text = llm._call_groq('system', 'user')

        self.assertEqual(text, '{"ok": true}')
        self.assertEqual(factory.call_args.kwargs['base_url'], llm.GROQ_BASE_URL)
        self.assertEqual(factory.call_args.kwargs['api_key'], 'groq-key')
        self.assertEqual(
            client.chat.completions.create.call_args.kwargs['model'], 'llama-test')

    def test_deepseek_uses_its_own_base_url(self):
        factory, _ = self._client()
        with mock.patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'ds-key'}):
            with mock.patch('openai.OpenAI', factory):
                llm._call_deepseek('system', 'user')
        self.assertEqual(factory.call_args.kwargs['base_url'], llm.DEEPSEEK_BASE_URL)

    def test_json_mode_is_requested(self):
        factory, client = self._client()
        with mock.patch.dict(os.environ, {'GROQ_API_KEY': 'k'}):
            with mock.patch('openai.OpenAI', factory):
                llm._call_groq('system', 'user')
        sent = client.chat.completions.create.call_args.kwargs
        self.assertEqual(sent['response_format'], {'type': 'json_object'})
        self.assertEqual(sent['messages'][0]['role'], 'system')

    def test_missing_key_raises_before_constructing_a_client(self):
        factory, _ = self._client()
        with mock.patch.dict(os.environ, {'GROQ_API_KEY': ''}):
            with mock.patch('openai.OpenAI', factory):
                with self.assertRaises(llm.LLMError) as caught:
                    llm._call_groq('system', 'user')
        self.assertIn('GROQ_API_KEY', str(caught.exception))
        factory.assert_not_called()

    def test_empty_content_returns_empty_string_for_the_parser_to_reject(self):
        factory, _ = self._client(content=None)
        with mock.patch.dict(os.environ, {'GROQ_API_KEY': 'k'}):
            with mock.patch('openai.OpenAI', factory):
                self.assertEqual(llm._call_groq('system', 'user'), '')


class ProviderSelectionTests(TestCase):
    @override_settings(LLM_PROVIDER='groq')
    def test_groq_selected(self):
        self.assertEqual(llm.active_provider(), 'groq')

    @override_settings(LLM_PROVIDER='gemini')
    def test_gemini_selected(self):
        self.assertEqual(llm.active_provider(), 'gemini')

    @override_settings(LLM_PROVIDER='deepseek')
    def test_deepseek_selected(self):
        self.assertEqual(llm.active_provider(), 'deepseek')

    @override_settings(LLM_PROVIDER='sarvam')
    def test_sarvam_selected(self):
        self.assertEqual(llm.active_provider(), 'sarvam')

    @override_settings(LLM_PROVIDER='  SARVAM  ')
    def test_selection_tolerates_case_and_whitespace(self):
        self.assertEqual(llm.active_provider(), 'sarvam')

    @override_settings(LLM_PROVIDER='gpt-9')
    def test_unknown_provider_falls_back_to_the_default(self):
        self.assertEqual(llm.active_provider(), llm.DEFAULT_PROVIDER)

    @override_settings(LLM_PROVIDER='')
    def test_empty_provider_falls_back_to_the_default(self):
        self.assertEqual(llm.active_provider(), llm.DEFAULT_PROVIDER)

    @override_settings(LLM_PROVIDER='sarvam', DEMO_MODE=False)
    def test_configured_provider_is_the_one_called(self):
        calls = []

        def _deepseek(s, u):
            calls.append('deepseek')
            return json.dumps(GOOD_TURN)

        def _sarvam(s, u):
            calls.append('sarvam')
            return json.dumps(GOOD_TURN)

        with mock.patch.object(
            llm, 'PROVIDERS', {'deepseek': _deepseek, 'sarvam': _sarvam}
        ):
            turn = llm.get_next_turn(DAILY_ROUTINE)
        self.assertEqual(calls, ['sarvam'])
        self.assertEqual(turn['provider'], 'sarvam')


class FallbackBankTests(TestCase):
    """The hand-written bank is the safety net, so validate its shape."""

    def test_every_topic_has_a_bank(self):
        for topic in (DAILY_ROUTINE, ORDERING_FOOD, TRAVEL_BASICS):
            with self.subTest(topic=topic):
                self.assertGreaterEqual(len(llm.FALLBACK_TURNS[topic]), 3)

    def test_every_fallback_turn_is_well_formed(self):
        for topic, bank in llm.FALLBACK_TURNS.items():
            for index, turn in enumerate(bank):
                with self.subTest(topic=topic, index=index):
                    self.assertTrue(turn['tutor_message_es'])
                    self.assertTrue(turn['tutor_message_en'])
                    self.assertTrue(turn['target_word'])
                    self.assertEqual(len(turn['replies']), 3)
                    self.assertEqual(
                        sum(r['is_correct'] for r in turn['replies']), 1,
                        'exactly one reply must be correct')
                    self.assertEqual([r['id'] for r in turn['replies']], [0, 1, 2])

    def test_every_wrong_reply_explains_itself(self):
        for topic, bank in llm.FALLBACK_TURNS.items():
            for index, turn in enumerate(bank):
                for reply in turn['replies']:
                    if not reply['is_correct']:
                        with self.subTest(topic=topic, index=index, es=reply['es']):
                            self.assertTrue(
                                reply['why_wrong'],
                                'a distractor needs a reason so the app can teach')

    def test_fallback_turns_pass_the_normaliser(self):
        # Whatever the bank contains must survive the same validation a live
        # response goes through.
        for topic, bank in llm.FALLBACK_TURNS.items():
            for index, turn in enumerate(bank):
                with self.subTest(topic=topic, index=index):
                    llm._normalise_turn(turn)

    def test_correct_answer_is_not_always_in_the_same_position(self):
        positions = set()
        for bank in llm.FALLBACK_TURNS.values():
            for turn in bank:
                for i, reply in enumerate(turn['replies']):
                    if reply['is_correct']:
                        positions.add(i)
        self.assertGreater(len(positions), 1, 'a fixed position is guessable')
