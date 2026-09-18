"""Tutor LLM adapter.

One `_call()` entry point sits in front of every provider, so switching between
Groq, Gemini, DeepSeek and Sarvam is the `LLM_PROVIDER` env var and nothing
else. Groq and DeepSeek share an OpenAI-protocol code path; the other two have
their own.

Three layers of defence, because a live demo cannot depend on someone else's
uptime:

1. `DEMO_MODE=true` skips the network entirely and serves turns from
   `FALLBACK_TURNS`, indexed by turn number so a demo replays identically.
2. Every model response goes through `_extract_json` (tolerates markdown
   fences and prose wrappers) and then a normaliser that guarantees the shape
   the API layer expects.
3. Anything that still fails falls back to a hand-written turn for the topic.
   `get_next_turn` and `evaluate_freetext_reply` do not raise.

A failed *evaluation* returns `graded=False`. The caller must not run an SM-2
update in that case: a provider outage should never corrupt the learner's
review schedule by recording a wrong answer they didn't give.
"""

import copy
import json
import logging
import os
import re

from django.conf import settings

from .demo_turns import FALLBACK_TURNS
from .models import (
    DAILY_ROUTINE,
    DEFAULT_LANGUAGE,
    ORDERING_FOOD,
    TRAVEL_BASICS,
)

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 20
# A turn's JSON is only ~250 tokens, but reasoning models spend a large hidden
# budget before emitting anything. Too low a cap truncates them mid-document
# and the whole response is wasted, so this is deliberately generous - it is a
# ceiling, not a target, and non-reasoning models stay well under it.
MAX_TOKENS = 2500

# Groq is the default: at the time of writing it is the one provider whose
# free tier accepts new accounts. The others stay registered so switching is
# one env var if that changes.
DEFAULT_PROVIDER = 'groq'
# Model names churn fast and availability varies per account, so these are only
# starting guesses. `manage.py check_llm --list-models` is the authority.
DEFAULT_GEMINI_MODEL = 'gemini-flash-latest'
DEFAULT_DEEPSEEK_MODEL = 'deepseek-chat'
DEFAULT_GROQ_MODEL = 'llama-3.3-70b-versatile'
# Low but not zero: identical phrasing every session feels canned, wild
# variation makes the distractors unreliable.
TEMPERATURE = 0.4

VERDICTS = ('perfect', 'minor', 'awkward', 'wrong', 'blank')


class LLMError(RuntimeError):
    """Raised internally when a response can't be used. Never escapes this module."""


# --- prompts ---------------------------------------------------------------

# The distractor rules are the part of the prompt that most affects quality,
# and "a concrete grammatical error" means something different in each
# language. Left generic, the model invents errors that are not errors - it
# marked optional Spanish articles wrong until the permitted kinds were
# enumerated - so each language names its own.
ERROR_KINDS = {
    'Spanish': """\
  wrong verb conjugation or person, an infinitive left unconjugated, a missing
  or wrong reflexive pronoun, wrong gender or article agreement, ser used where
  estar belongs (or the reverse), a missing or wrong preposition, or a
  confusable word substituted for the target.""",
    'French': """\
  wrong verb conjugation or person, an infinitive left unconjugated, a missing
  or wrong reflexive pronoun, wrong gender or article agreement (le/la, un/une),
  avoir used where etre belongs in a compound tense (or the reverse), a missing
  or wrong preposition (a/de), a past participle left unagreed, or a confusable
  word substituted for the target.""",
    'German': """\
  wrong verb conjugation or person, the verb in the wrong position (it must be
  second in a main clause and final in a subordinate one), wrong case on an
  article, adjective or pronoun (nominative where accusative or dative belongs),
  wrong gender (der/die/das), a separable prefix left attached or dropped, a
  preposition governing the wrong case, or a confusable word substituted for
  the target.""",
    'Hindi': """\
  wrong verb conjugation or person, wrong gender agreement on the verb or
  adjective, a wrong postposition (ko/se/mein/par), a noun left direct where the
  oblique form belongs before a postposition, a mismatched formality level
  (tu/tum/aap disagreeing with the verb), a missing or wrongly used "ne" with a
  transitive verb in the past, or a confusable word substituted for the
  target.""",
}

# What a native speaker accepts that a pedantic grader might not. Without
# this the model rejects perfectly ordinary sentences for being terse.
ALLOWANCES = {
    'Spanish': 'Optional articles, dropped subject pronouns and shorter '
               'phrasings are all correct Spanish.',
    'French': 'Contractions, "on" in place of "nous", and shorter phrasings '
              'are all correct French.',
    'German': 'Both orders of a dative and accusative object, and shorter '
              'phrasings, are correct German.',
    'Hindi': 'Dropped subject pronouns, and either Devanagari or Roman '
             'transliteration, are correct Hindi. Never mark an answer wrong '
             'for being written in Roman script.',
}

CHIP_TEMPLATE = """\
You are a warm, patient LANGUAGE tutor talking with an English-speaking beginner.
You are holding a short, natural conversation on a fixed topic.

Each turn you must:
1. Say ONE line of LANGUAGE, at most 15 words, that stays on the given topic and
   directly sets up a reply using the TARGET WORD. The target word must appear
   in your line or be the obvious word needed to answer it. Never drift to a
   different subject.
2. Offer exactly THREE replies. Exactly ONE is correct, natural LANGUAGE that
   answers your line and uses the target word properly.
3. Keep every reply under 12 words.

The two wrong replies are the most important part, and there are strict rules:

- Each must contain a CONCRETE GRAMMATICAL ERROR, of one of these kinds only:
ERROR_KINDS
- A reply is NOT wrong merely because it is off-topic, incomplete, informal, or
  answers a different question. Never use "doesn't answer the question" as a
  reason.
- If a native speaker would accept the sentence as correct, IT IS NOT WRONG.
  ALLOWANCES
- Make wrong options tempting, never absurd or comical.
- The three replies must be three DIFFERENT sentences. Never repeat the same
  wording twice, and never mark two identical sentences differently.
- `why_wrong` must name the specific grammatical error, not a vague judgement,
  and that error must actually be present in that reply's text.

Return ONLY a JSON object. No prose, no markdown fences.

Also give a SENTENCE STARTER: the shape of a correct answer with the part the
learner has to supply replaced by ____ . It scaffolds someone typing their own
answer, so leave out the word being tested, never the easy scaffolding around
it. For "What time do you get up?" a good starter leaves only the time blank,
and a useless one is "____".

{
  "tutor_message": "your line in LANGUAGE",
  "tutor_message_en": "literal English translation",
  "target_word": "the LANGUAGE vocabulary item this turn drills",
  "sentence_starter": "a frame with ____ where the answer goes",
  "replies": [
    {"text": "...", "en": "...", "is_correct": true},
    {"text": "...", "en": "...", "is_correct": false, "why_wrong": "short reason in English"},
    {"text": "...", "en": "...", "is_correct": false, "why_wrong": "short reason in English"}
  ]
}

Every "text" value must be written in LANGUAGE, never in English.
Vary which position holds the correct reply - do not always put it first.
"""

EVAL_TEMPLATE = """\
You are grading ONE free-text LANGUAGE reply from an English-speaking beginner in
a conversation practice app, then continuing the conversation.

Grade with exactly one verdict:
  "perfect" - correct, natural, uses the target word appropriately
  "minor"   - right answer, only an accent, spelling or typo slip
  "awkward" - understandable but grammatically wrong
  "wrong"   - incorrect, or ignores the target word
  "blank"   - empty, or not a genuine attempt

Be fair but not generous: a missing accent is "minor", a wrong verb person is
"awkward", the wrong word entirely is "wrong". Feedback names the specific fix
in one short encouraging English sentence - never a lecture.

What a native speaker accepts, you accept: ALLOWANCES

Return ONLY a JSON object. No prose, no markdown fences.

{
  "verdict": "perfect|minor|awkward|wrong|blank",
  "used_target_word": true,
  "corrected": "their sentence rewritten correctly, or \\"\\" if already correct",
  "feedback_en": "one short encouraging sentence naming the fix",
  "tutor_message": "your next line in LANGUAGE, at most 15 words",
  "tutor_message_en": "literal English translation",
  "replies": [
    {"text": "...", "en": "...", "is_correct": true},
    {"text": "...", "en": "...", "is_correct": false, "why_wrong": "short reason in English"},
    {"text": "...", "en": "...", "is_correct": false, "why_wrong": "short reason in English"}
  ]
}

Every "text" value must be written in LANGUAGE, never in English.
"""


def _build_prompt(template, language):
    """Fill a prompt template for one language.

    Plain substitution rather than str.format, because both templates contain
    a literal JSON object and every brace in it would have to be doubled.
    """
    language = language if language in ERROR_KINDS else DEFAULT_LANGUAGE
    return (
        template
        .replace('ERROR_KINDS', ERROR_KINDS[language])
        .replace('ALLOWANCES', ALLOWANCES[language])
        .replace('LANGUAGE', language)
    )


# --- providers -------------------------------------------------------------

def _call_openai_compatible(base_url, key_var, model, system_prompt, user_content,
                            extra_body=None):
    """Talk to any provider that speaks the OpenAI chat-completions protocol.

    Both DeepSeek and Groq do, so the official `openai` SDK reaches them by
    pointing base_url elsewhere. That is why `openai` is a dependency here
    despite no OpenAI model being used.
    """
    from openai import OpenAI

    api_key = os.getenv(key_var)
    if not api_key:
        raise LLMError(f'{key_var} is not set')

    client = OpenAI(
        api_key=api_key, base_url=base_url, timeout=REQUEST_TIMEOUT_SECONDS)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_content},
        ],
        max_tokens=MAX_TOKENS,
        temperature=TEMPERATURE,
        # JSON mode removes most parse failures at the source. _extract_json
        # still guards whatever slips through.
        response_format={'type': 'json_object'},
        **({'extra_body': extra_body} if extra_body else {}),
    )
    return response.choices[0].message.content or ''


DEEPSEEK_BASE_URL = 'https://api.deepseek.com'
GROQ_BASE_URL = 'https://api.groq.com/openai/v1'


def _call_deepseek(system_prompt, user_content):
    return _call_openai_compatible(
        DEEPSEEK_BASE_URL,
        'DEEPSEEK_API_KEY',
        os.getenv('DEEPSEEK_MODEL', DEFAULT_DEEPSEEK_MODEL),
        system_prompt,
        user_content,
    )


def _call_groq(system_prompt, user_content):
    model = os.getenv('GROQ_MODEL', DEFAULT_GROQ_MODEL)

    # gpt-oss is a reasoning model: left alone it spends several hundred
    # hidden tokens deliberating before it writes anything, which on a
    # measured run was 1.68s versus 0.76s at low effort. Same model, same
    # Spanish, less than half the wait. Only gpt-oss accepts the parameter,
    # so it is not sent to anything else.
    extra_body = None
    if 'gpt-oss' in model:
        effort = os.getenv('GROQ_REASONING_EFFORT', 'low').strip().lower()
        if effort:
            extra_body = {'reasoning_effort': effort}

    return _call_openai_compatible(
        GROQ_BASE_URL,
        'GROQ_API_KEY',
        model,
        system_prompt,
        user_content,
        extra_body=extra_body,
    )


GEMINI_BASE_URL = 'https://generativelanguage.googleapis.com/v1beta'


def _call_gemini(system_prompt, user_content):
    import requests

    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        raise LLMError('GEMINI_API_KEY is not set')

    model = os.getenv('GEMINI_MODEL', DEFAULT_GEMINI_MODEL)
    response = requests.post(
        f'{GEMINI_BASE_URL}/models/{model}:generateContent',
        # The key goes in a header rather than the query string Google's docs
        # sometimes show, so it stays out of proxy and access logs.
        headers={'x-goog-api-key': api_key, 'Content-Type': 'application/json'},
        json={
            'system_instruction': {'parts': [{'text': system_prompt}]},
            'contents': [{'role': 'user', 'parts': [{'text': user_content}]}],
            'generationConfig': {
                'temperature': TEMPERATURE,
                'maxOutputTokens': MAX_TOKENS,
                # Gemini's native JSON mode - the equivalent of OpenAI's
                # response_format={'type': 'json_object'}.
                'responseMimeType': 'application/json',
            },
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if response.status_code != 200:
        # raise_for_status() throws away the body, and Google puts the useful
        # part there: SERVICE_DISABLED vs PERMISSION_DENIED vs
        # RESOURCE_EXHAUSTED are three very different problems.
        try:
            error = response.json().get('error', {})
            detail = error.get('message', response.text[:200])
            reason = error.get('status', '')
        except ValueError:
            detail, reason = response.text[:200], ''
        raise LLMError(
            f'Gemini {response.status_code}'
            + (f' {reason}' if reason else '')
            + f': {detail}'
        )

    payload = response.json()

    candidates = payload.get('candidates') or []
    if not candidates:
        # Almost always a safety block or a prompt-level rejection.
        reason = (payload.get('promptFeedback') or {}).get('blockReason', 'no candidates')
        raise LLMError(f'Gemini returned no candidates ({reason})')

    finish_reason = candidates[0].get('finishReason')
    parts = (candidates[0].get('content') or {}).get('parts') or []
    text = ''.join(
        str(part.get('text') or '') for part in parts if isinstance(part, dict)
    ).strip()

    if not text:
        raise LLMError(f'Gemini returned no text (finishReason={finish_reason})')
    if finish_reason == 'MAX_TOKENS':
        logger.warning('Gemini hit the token cap; JSON may be truncated')
    return text


def _call_sarvam(system_prompt, user_content):
    # Called over plain REST on purpose: the `sarvamai` PyPI package is still
    # alpha, and this keeps the two providers structurally identical.
    import requests

    api_key = os.getenv('SARVAM_API_KEY')
    if not api_key:
        raise LLMError('SARVAM_API_KEY is not set')

    response = requests.post(
        'https://api.sarvam.ai/v1/chat/completions',
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        },
        json={
            'model': os.getenv('SARVAM_MODEL', 'sarvam-105b-conversations'),
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_content},
            ],
            'max_tokens': MAX_TOKENS,
            'temperature': TEMPERATURE,
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    try:
        return response.json()['choices'][0]['message']['content'] or ''
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise LLMError(f'unexpected Sarvam response envelope: {exc}') from exc


PROVIDERS = {
    'groq': _call_groq,
    'gemini': _call_gemini,
    'deepseek': _call_deepseek,
    'sarvam': _call_sarvam,
}


def active_provider():
    name = (settings.LLM_PROVIDER or DEFAULT_PROVIDER).strip().lower()
    if name not in PROVIDERS:
        logger.warning(
            'unknown LLM_PROVIDER %r, falling back to %s', name, DEFAULT_PROVIDER)
        return DEFAULT_PROVIDER
    return name


def _call(system_prompt, user_content):
    """Send one request to the configured provider and return parsed JSON."""
    name = active_provider()
    raw = PROVIDERS[name](system_prompt, user_content)
    return _extract_json(raw), name


# --- response hardening ----------------------------------------------------

_FENCE_RE = re.compile(r'^\s*```(?:json)?\s*|\s*```\s*$', re.IGNORECASE)


def _extract_json(text):
    """Parse a JSON object out of a model response.

    Handles the three things models actually do wrong: wrapping the object in
    markdown fences, prefixing it with prose ("Here is the JSON:"), and
    trailing commentary after the closing brace.
    """
    if not text or not text.strip():
        raise LLMError('empty response from provider')

    cleaned = _FENCE_RE.sub('', text.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    start, end = cleaned.find('{'), cleaned.rfind('}')
    if start == -1 or end <= start:
        raise LLMError(f'no JSON object in response: {text[:200]!r}')
    try:
        return json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError as exc:
        raise LLMError(f'malformed JSON: {exc}; raw={text[:200]!r}') from exc


def _clean_str(value):
    return str(value).strip() if value is not None else ''


def _drop_duplicate_replies(chips):
    """Collapse replies that say exactly the same thing.

    Models sometimes emit one sentence twice, marking one copy correct and
    the other wrong, with a `why_wrong` describing an error that is not in
    the text. Tapping the wrong copy then produces "Not quite, the correct
    answer is" followed by the identical sentence, which reads as a broken
    app rather than a wrong answer.

    Correct wins when copies disagree, and a chip that is correct cannot
    keep a reason for being wrong. If this leaves fewer than two replies the
    caller's own checks reject the turn and the hand-written bank answers
    instead, which is the right outcome: a turn with one option is not a
    question.
    """
    kept = []
    first_by_text = {}

    for chip in chips:
        key = ' '.join(chip['text'].split()).casefold()
        first = first_by_text.get(key)
        if first is None:
            first_by_text[key] = chip
            kept.append(chip)
            continue
        if chip['is_correct'] and not first['is_correct']:
            first['is_correct'] = True
            first['why_wrong'] = ''

    if len(kept) != len(chips):
        logger.warning('dropped %d duplicate reply(ies)', len(chips) - len(kept))

    # Ids are how the client names its choice, so they have to stay
    # contiguous after anything is removed.
    for position, chip in enumerate(kept):
        chip['id'] = position
    return kept


def _normalise_replies(raw):
    """Force the model's reply list into usable chips.

    `is_correct` deliberately stays server-side - the API never ships it to the
    browser, or the answer would be visible in the network tab.
    """
    if isinstance(raw, dict):          # single reply sent unwrapped
        raw = [raw]
    if not isinstance(raw, list):
        raise LLMError(f'replies must be a list, got {type(raw).__name__}')

    chips = []
    for position, entry in enumerate(raw):
        if isinstance(entry, str):
            # Some responses give bare strings; assume the first is the answer.
            entry = {'text': entry, 'is_correct': position == 0}
        if not isinstance(entry, dict):
            continue
        # 'text' is what the prompt asks for; the others are what models
        # actually emit when they echo a field name back instead.
        text = _clean_str(
            entry.get('text') or entry.get('term') or entry.get('es'))
        if not text:
            continue
        chips.append({
            'id': len(chips),
            'text': text,
            'en': _clean_str(entry.get('en') or entry.get('english')),
            'is_correct': bool(entry.get('is_correct')),
            'why_wrong': _clean_str(entry.get('why_wrong')),
        })

    chips = _drop_duplicate_replies(chips)

    if len(chips) < 2:
        raise LLMError(f'need at least 2 usable replies, got {len(chips)}')
    if not any(chip['is_correct'] for chip in chips):
        raise LLMError('no reply was marked correct')
    if all(chip['is_correct'] for chip in chips):
        # Usable, but the turn can't distinguish a right answer from a wrong
        # one, which is the whole point of chip mode.
        logger.warning('every reply marked correct; chip turn has no distractors')

    return chips[:3]


def _normalise_turn(payload):
    if not isinstance(payload, dict):
        raise LLMError(f'expected a JSON object, got {type(payload).__name__}')

    text = _clean_str(payload.get('tutor_message') or payload.get('ai_message'))
    if not text:
        raise LLMError('response has no tutor_message')

    return {
        'tutor_message': text,
        'tutor_message_en': _clean_str(payload.get('tutor_message_en')),
        'target_word': _clean_str(payload.get('target_word')),
        'sentence_starter': _normalise_starter(payload.get('sentence_starter')),
        'replies': _normalise_replies(payload.get('replies') or payload.get('reply_options')),
    }


def _normalise_starter(value):
    """A usable sentence frame, or nothing.

    A starter is optional scaffolding, so anything malformed is dropped
    rather than raised on: losing the hint is a far smaller cost than losing
    the whole turn. It must contain a blank and some actual words, since a
    bare "____" scaffolds nothing.
    """
    starter = _clean_str(value)
    if not starter or '_' not in starter:
        return ''
    if len(starter.replace('_', '').strip()) < 4:
        return ''
    return starter[:200]


def _normalise_evaluation(payload, fallback_turn):
    """Normalise a grading response.

    The grade matters more than the conversational continuation, so a missing
    tutor message borrows one from the fallback bank rather than discarding a
    perfectly good verdict.
    """
    if not isinstance(payload, dict):
        raise LLMError(f'expected a JSON object, got {type(payload).__name__}')

    verdict = _clean_str(payload.get('verdict')).lower()
    if verdict not in VERDICTS:
        logger.warning('unrecognised verdict %r, grading as wrong', verdict)
        verdict = 'wrong'

    text = _clean_str(payload.get('tutor_message') or payload.get('ai_message'))
    try:
        replies = _normalise_replies(payload.get('replies') or payload.get('reply_options'))
    except LLMError as exc:
        logger.warning('evaluation replies unusable (%s); using fallback chips', exc)
        replies = copy.deepcopy(fallback_turn['replies'])

    if not text:
        text = fallback_turn['tutor_message']
        english = fallback_turn['tutor_message_en']
    else:
        english = _clean_str(payload.get('tutor_message_en'))

    return {
        'verdict': verdict,
        'graded': True,
        'used_target_word': bool(payload.get('used_target_word')),
        'corrected': _clean_str(payload.get('corrected')),
        'feedback_en': _clean_str(payload.get('feedback_en')),
        'tutor_message': text,
        'tutor_message_en': english,
        'replies': replies,
    }


# --- prompt input formatting ----------------------------------------------

def _format_vocab(items):
    if not items:
        return '(no specific vocabulary due - keep the conversation going)'
    lines = []
    for item in items:
        term = getattr(item, 'term', None) or (
            item.get('term') if isinstance(item, dict) else str(item))
        english = getattr(item, 'english', None) or (
            item.get('english') if isinstance(item, dict) else '')
        lines.append(f'- {term}' + (f' ({english})' if english else ''))
    return '\n'.join(lines)


def _format_history(history, limit=6):
    """Render the tail of the conversation for the prompt."""
    if not history:
        return '(this is the first turn of the conversation)'
    lines = []
    for turn in history[-limit:]:
        tutor = _clean_str(turn.get('tutor') or turn.get('ai') or turn.get('ai_message'))
        learner = _clean_str(turn.get('user') or turn.get('user_input'))
        if tutor:
            lines.append(f'Tutor: {tutor}')
        if learner:
            lines.append(f'Learner: {learner}')
    return '\n'.join(lines) or '(this is the first turn of the conversation)'


def _topic_label(topic):
    return {
        DAILY_ROUTINE: 'daily routine',
        ORDERING_FOOD: 'ordering food in a restaurant',
        TRAVEL_BASICS: 'travel basics',
    }.get(topic, 'everyday conversation')


# --- hand-written fallback bank -------------------------------------------
# Lives in demo_turns.py: it is data, not logic, and it is long enough to
# bury the adapter if it sits inline. Re-exported here so callers and tests
# can keep using llm.FALLBACK_TURNS.

FALLBACK_FEEDBACK_EN = (
    "I couldn't check that one just now, so it hasn't affected your review "
    "schedule. Keep going!"
)


def _bank_for(topic, language=DEFAULT_LANGUAGE):
    """The hand-written turns for one language and topic.

    An unknown language falls back to the default's bank, but an unknown
    topic within a known language falls back inside that language - never
    across one, because serving Spanish into a German lesson would teach
    the wrong thing.
    """
    by_topic = FALLBACK_TURNS.get(language) or FALLBACK_TURNS[DEFAULT_LANGUAGE]
    return by_topic.get(topic) or by_topic[DAILY_ROUTINE]


def fallback_turn(topic, language=DEFAULT_LANGUAGE, turn_index=0):
    """A known-good turn for `topic`, chosen by index so demos are repeatable."""
    bank = _bank_for(topic, language)
    return copy.deepcopy(bank[turn_index % len(bank)])


def demo_bank_size(topic, language=DEFAULT_LANGUAGE):
    """How many distinct canned turns exist for a topic in a language.

    The index wraps past the end of the bank, so a demo session longer than
    this repeats itself. Callers cap the session length with it.
    """
    return len(_bank_for(topic, language))


# --- public API ------------------------------------------------------------

def get_next_turn(topic, language=DEFAULT_LANGUAGE, due_items=None,
                  history=None, turn_index=0):
    """Produce the next tutor turn. Never raises.

    Returns a dict with `tutor_message`, `tutor_message_en`, `target_word`,
    `replies`, plus `provider` and `from_cache` for debugging a bad demo turn.
    """
    if settings.DEMO_MODE:
        turn = fallback_turn(topic, language, turn_index)
        turn.update(provider='demo', from_cache=True)
        return turn

    user_content = (
        f'Language being learned: {language}\n'
        f'Topic: {_topic_label(topic)}\n\n'
        f'Vocabulary due for review:\n{_format_vocab(due_items)}\n\n'
        f'Conversation so far:\n{_format_history(history)}\n\n'
        'Continue the conversation.'
    )

    try:
        payload, provider = _call(_build_prompt(CHIP_TEMPLATE, language), user_content)
        turn = _normalise_turn(payload)
        turn.update(provider=provider, from_cache=False)
        return turn
    except Exception as exc:
        logger.warning('get_next_turn falling back (%s: %s)', type(exc).__name__, exc)
        turn = fallback_turn(topic, language, turn_index)
        turn.update(provider='fallback', from_cache=True)
        return turn


def evaluate_freetext_reply(topic, language, target_item, user_reply,
                            history=None, turn_index=0):
    """Grade a typed reply and continue the conversation. Never raises.

    On failure the result carries `graded=False`, and the caller must skip the
    SM-2 update - an outage must not record an answer the learner never gave.
    """
    backup = fallback_turn(topic, language, turn_index)

    if not _clean_str(user_reply):
        return {
            'verdict': 'blank',
            'graded': True,
            'used_target_word': False,
            'corrected': '',
            'feedback_en': 'Nothing came through - try typing an answer.',
            'tutor_message': backup['tutor_message'],
            'tutor_message_en': backup['tutor_message_en'],
            'replies': backup['replies'],
            'provider': 'local',
            'from_cache': True,
        }

    if settings.DEMO_MODE:
        # Free text can't be pre-cached meaningfully, so demo mode still calls
        # out; the caller decides whether to expose typing during a demo.
        logger.info('DEMO_MODE is on but free text needs a live call')

    target_term = getattr(target_item, 'term', None) or _clean_str(target_item)
    target_en = getattr(target_item, 'english', '')
    user_content = (
        f'Language being learned: {language}\n'
        f'Topic: {_topic_label(topic)}\n'
        f'Target vocabulary: {target_term}' + (f' ({target_en})' if target_en else '') + '\n\n'
        f'Conversation so far:\n{_format_history(history)}\n\n'
        f"Learner's typed reply: {user_reply}\n\n"
        'Grade the reply, then continue the conversation.'
    )

    try:
        payload, provider = _call(_build_prompt(EVAL_TEMPLATE, language), user_content)
        result = _normalise_evaluation(payload, backup)
        result.update(provider=provider, from_cache=False)
        return result
    except Exception as exc:
        logger.warning(
            'evaluate_freetext_reply falling back ungraded (%s: %s)',
            type(exc).__name__, exc,
        )
        return {
            'verdict': None,
            'graded': False,
            'used_target_word': False,
            'corrected': '',
            'feedback_en': FALLBACK_FEEDBACK_EN,
            'tutor_message': backup['tutor_message'],
            'tutor_message_en': backup['tutor_message_en'],
            'replies': backup['replies'],
            'provider': 'fallback',
            'from_cache': True,
        }
