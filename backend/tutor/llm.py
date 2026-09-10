"""Tutor LLM adapter.

One `_call()` entry point sits in front of every provider, so switching between
DeepSeek and Sarvam is the `LLM_PROVIDER` env var and nothing else.

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

from .models import DAILY_ROUTINE, ORDERING_FOOD, TRAVEL_BASICS

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 20
# A turn's JSON is only ~250 tokens, but reasoning models spend a large hidden
# budget before emitting anything. Too low a cap truncates them mid-document
# and the whole response is wasted, so this is deliberately generous - it is a
# ceiling, not a target, and non-reasoning models stay well under it.
MAX_TOKENS = 2500

# Gemini is the default because it's the provider with a usable free tier.
# DeepSeek and Sarvam stay registered so switching back is one env var.
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

CHIP_SYSTEM_PROMPT = """\
You are a warm, patient Spanish tutor talking with an English-speaking beginner.
You are holding a short, natural conversation on a fixed topic.

Each turn you must:
1. Say ONE line of Spanish, at most 15 words, that stays on the given topic and
   directly sets up a reply using the TARGET WORD. The target word must appear
   in your line or be the obvious word needed to answer it. Never drift to a
   different subject.
2. Offer exactly THREE replies. Exactly ONE is correct, natural Spanish that
   answers your line and uses the target word properly.
3. Keep every reply under 12 words.

The two wrong replies are the most important part, and there are strict rules:

- Each must contain a CONCRETE GRAMMATICAL ERROR, of one of these kinds only:
  wrong verb conjugation or person, an infinitive left unconjugated, a missing
  or wrong reflexive pronoun, wrong gender or article agreement, ser used where
  estar belongs (or the reverse), a missing or wrong preposition, or a
  confusable word substituted for the target.
- A reply is NOT wrong merely because it is off-topic, incomplete, informal, or
  answers a different question. Never use "doesn't answer the question" as a
  reason.
- If a native speaker would accept the sentence as correct, IT IS NOT WRONG.
  Optional articles, optional subject pronouns and shorter phrasings are all
  perfectly correct Spanish - do not mark them wrong.
- Make wrong options tempting, never absurd or comical.
- `why_wrong` must name the specific grammatical error, not a vague judgement.

Return ONLY a JSON object. No prose, no markdown fences.

{
  "tutor_message_es": "your line in Spanish",
  "tutor_message_en": "literal English translation",
  "target_word": "the Spanish vocabulary item this turn drills",
  "replies": [
    {"es": "...", "en": "...", "is_correct": true},
    {"es": "...", "en": "...", "is_correct": false, "why_wrong": "short reason in English"},
    {"es": "...", "en": "...", "is_correct": false, "why_wrong": "short reason in English"}
  ]
}

Vary which position holds the correct reply - do not always put it first.
"""

EVAL_SYSTEM_PROMPT = """\
You are grading ONE free-text Spanish reply from an English-speaking beginner in
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

Return ONLY a JSON object. No prose, no markdown fences.

{
  "verdict": "perfect|minor|awkward|wrong|blank",
  "used_target_word": true,
  "corrected_es": "their sentence rewritten correctly, or \\"\\" if already correct",
  "feedback_en": "one short encouraging sentence naming the fix",
  "tutor_message_es": "your next line in Spanish, at most 15 words",
  "tutor_message_en": "literal English translation",
  "replies": [
    {"es": "...", "en": "...", "is_correct": true},
    {"es": "...", "en": "...", "is_correct": false, "why_wrong": "short reason in English"},
    {"es": "...", "en": "...", "is_correct": false, "why_wrong": "short reason in English"}
  ]
}
"""


# --- providers -------------------------------------------------------------

def _call_openai_compatible(base_url, key_var, model, system_prompt, user_content):
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
    return _call_openai_compatible(
        GROQ_BASE_URL,
        'GROQ_API_KEY',
        os.getenv('GROQ_MODEL', DEFAULT_GROQ_MODEL),
        system_prompt,
        user_content,
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
            entry = {'es': entry, 'is_correct': position == 0}
        if not isinstance(entry, dict):
            continue
        spanish = _clean_str(entry.get('es') or entry.get('spanish'))
        if not spanish:
            continue
        chips.append({
            'id': len(chips),
            'es': spanish,
            'en': _clean_str(entry.get('en') or entry.get('english')),
            'is_correct': bool(entry.get('is_correct')),
            'why_wrong': _clean_str(entry.get('why_wrong')),
        })

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

    spanish = _clean_str(payload.get('tutor_message_es') or payload.get('ai_message'))
    if not spanish:
        raise LLMError('response has no tutor_message_es')

    return {
        'tutor_message_es': spanish,
        'tutor_message_en': _clean_str(payload.get('tutor_message_en')),
        'target_word': _clean_str(payload.get('target_word')),
        'replies': _normalise_replies(payload.get('replies') or payload.get('reply_options')),
    }


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

    spanish = _clean_str(payload.get('tutor_message_es') or payload.get('ai_message'))
    try:
        replies = _normalise_replies(payload.get('replies') or payload.get('reply_options'))
    except LLMError as exc:
        logger.warning('evaluation replies unusable (%s); using fallback chips', exc)
        replies = copy.deepcopy(fallback_turn['replies'])

    if not spanish:
        spanish = fallback_turn['tutor_message_es']
        english = fallback_turn['tutor_message_en']
    else:
        english = _clean_str(payload.get('tutor_message_en'))

    return {
        'verdict': verdict,
        'graded': True,
        'used_target_word': bool(payload.get('used_target_word')),
        'corrected_es': _clean_str(payload.get('corrected_es')),
        'feedback_en': _clean_str(payload.get('feedback_en')),
        'tutor_message_es': spanish,
        'tutor_message_en': english,
        'replies': replies,
    }


# --- prompt input formatting ----------------------------------------------

def _format_vocab(items):
    if not items:
        return '(no specific vocabulary due - keep the conversation going)'
    lines = []
    for item in items:
        spanish = getattr(item, 'spanish', None) or (
            item.get('spanish') if isinstance(item, dict) else str(item))
        english = getattr(item, 'english', None) or (
            item.get('english') if isinstance(item, dict) else '')
        lines.append(f'- {spanish}' + (f' ({english})' if english else ''))
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
# Correct Spanish, written and checked by hand. Serves DEMO_MODE and every
# failure path, so the app is never dead in the water.

FALLBACK_TURNS = {
    DAILY_ROUTINE: [
        {
            'tutor_message_es': '¡Hola! ¿A qué hora te levantas normalmente?',
            'tutor_message_en': 'Hi! What time do you usually get up?',
            'target_word': 'levantarse',
            'replies': [
                {'id': 0, 'es': 'Yo levanto a las siete.', 'en': 'I get up at seven.',
                 'is_correct': False, 'why_wrong': "'levantarse' is reflexive - it needs 'me'."},
                {'id': 1, 'es': 'Me levanto a las siete.', 'en': 'I get up at seven.',
                 'is_correct': True, 'why_wrong': ''},
                {'id': 2, 'es': 'Me levanta a las siete.', 'en': 'I get up at seven.',
                 'is_correct': False, 'why_wrong': "'levanta' is he/she - you need 'levanto' for I."},
            ],
        },
        {
            'tutor_message_es': '¿Y desayunas en casa o en el trabajo?',
            'tutor_message_en': 'And do you have breakfast at home or at work?',
            'target_word': 'desayunar',
            'replies': [
                {'id': 0, 'es': 'Desayuno en casa.', 'en': 'I have breakfast at home.',
                 'is_correct': True, 'why_wrong': ''},
                {'id': 1, 'es': 'Yo desayunar en casa.', 'en': 'I have breakfast at home.',
                 'is_correct': False, 'why_wrong': "Conjugate the verb: 'desayuno', not 'desayunar'."},
                {'id': 2, 'es': 'Desayunas en casa.', 'en': 'You have breakfast at home.',
                 'is_correct': False, 'why_wrong': "'desayunas' means you - use 'desayuno' for I."},
            ],
        },
        {
            'tutor_message_es': 'Qué bien. ¿Y a qué hora te acuestas?',
            'tutor_message_en': 'Nice. And what time do you go to bed?',
            'target_word': 'acostarse',
            'replies': [
                {'id': 0, 'es': 'Me acosto a las once.', 'en': 'I go to bed at eleven.',
                 'is_correct': False, 'why_wrong': "The stem changes: 'me acuesto', not 'me acosto'."},
                {'id': 1, 'es': 'Me acuesto en las once.', 'en': 'I go to bed at eleven.',
                 'is_correct': False, 'why_wrong': "Clock times take 'a las', not 'en las'."},
                {'id': 2, 'es': 'Me acuesto a las once.', 'en': 'I go to bed at eleven.',
                 'is_correct': True, 'why_wrong': ''},
            ],
        },
    ],
    ORDERING_FOOD: [
        {
            'tutor_message_es': 'Buenas tardes. ¿Una mesa para cuántas personas?',
            'tutor_message_en': 'Good afternoon. A table for how many people?',
            'target_word': 'la mesa',
            'replies': [
                {'id': 0, 'es': 'Una mesa para dos, por favor.', 'en': 'A table for two, please.',
                 'is_correct': True, 'why_wrong': ''},
                {'id': 1, 'es': 'Un mesa para dos, por favor.', 'en': 'A table for two, please.',
                 'is_correct': False, 'why_wrong': "'mesa' is feminine - it takes 'una'."},
                {'id': 2, 'es': 'Una mesa por dos, por favor.', 'en': 'A table for two, please.',
                 'is_correct': False, 'why_wrong': "Use 'para' for purpose, not 'por'."},
            ],
        },
        {
            'tutor_message_es': 'Perfecto. ¿Qué quiere beber?',
            'tutor_message_en': 'Perfect. What would you like to drink?',
            'target_word': 'el agua',
            'replies': [
                {'id': 0, 'es': 'Una vaso de agua, por favor.', 'en': 'A glass of water, please.',
                 'is_correct': False, 'why_wrong': "'vaso' is masculine - it takes 'un'."},
                {'id': 1, 'es': 'Un vaso de agua, por favor.', 'en': 'A glass of water, please.',
                 'is_correct': True, 'why_wrong': ''},
                {'id': 2, 'es': 'Un vaso de la agua, por favor.', 'en': 'A glass of water, please.',
                 'is_correct': False, 'why_wrong': "Drop the article: 'de agua', not 'de la agua'."},
            ],
        },
        {
            'tutor_message_es': '¿Desea algo de postre?',
            'tutor_message_en': 'Would you like any dessert?',
            'target_word': 'la cuenta',
            'replies': [
                {'id': 0, 'es': 'No, gracias. El cuenta, por favor.', 'en': 'No thanks. The bill, please.',
                 'is_correct': False, 'why_wrong': "'cuenta' is feminine - it takes 'la'."},
                {'id': 1, 'es': 'No, gracias. La cuento, por favor.', 'en': 'No thanks. The bill, please.',
                 'is_correct': False, 'why_wrong': "'cuento' means a story - you want 'cuenta'."},
                {'id': 2, 'es': 'No, gracias. La cuenta, por favor.', 'en': 'No thanks. The bill, please.',
                 'is_correct': True, 'why_wrong': ''},
            ],
        },
    ],
    TRAVEL_BASICS: [
        {
            'tutor_message_es': 'Buenos días. ¿Adónde va?',
            'tutor_message_en': 'Good morning. Where are you going?',
            'target_word': 'el billete',
            'replies': [
                {'id': 0, 'es': 'Un billete a Madrid, por favor.', 'en': 'A ticket to Madrid, please.',
                 'is_correct': True, 'why_wrong': ''},
                {'id': 1, 'es': 'Una billete a Madrid, por favor.', 'en': 'A ticket to Madrid, please.',
                 'is_correct': False, 'why_wrong': "'billete' is masculine - it takes 'un'."},
                {'id': 2, 'es': 'Un billete en Madrid, por favor.', 'en': 'A ticket to Madrid, please.',
                 'is_correct': False, 'why_wrong': "Destinations take 'a', not 'en'."},
            ],
        },
        {
            'tutor_message_es': 'Aquí tiene. ¿Busca usted algo más?',
            'tutor_message_en': 'Here you are. Are you looking for anything else?',
            'target_word': '¿dónde está?',
            'replies': [
                {'id': 0, 'es': '¿Dónde es la estación?', 'en': 'Where is the station?',
                 'is_correct': False, 'why_wrong': "Location uses 'estar': '¿Dónde está?'"},
                {'id': 1, 'es': '¿Dónde está la estación?', 'en': 'Where is the station?',
                 'is_correct': True, 'why_wrong': ''},
                {'id': 2, 'es': '¿Dónde está el estación?', 'en': 'Where is the station?',
                 'is_correct': False, 'why_wrong': "'estación' is feminine - it takes 'la'."},
            ],
        },
        {
            'tutor_message_es': 'La estación está muy cerca de aquí.',
            'tutor_message_en': 'The station is very close to here.',
            'target_word': 'a la derecha',
            'replies': [
                {'id': 0, 'es': 'Gracias. ¿Es a la derecha?', 'en': 'Thanks. Is it to the right?',
                 'is_correct': False, 'why_wrong': "Location uses 'estar': '¿Está a la derecha?'"},
                {'id': 1, 'es': 'Gracias. ¿Está a la derecho?', 'en': 'Thanks. Is it to the right?',
                 'is_correct': False, 'why_wrong': "The phrase is 'a la derecha', with an -a."},
                {'id': 2, 'es': 'Gracias. ¿Está a la derecha?', 'en': 'Thanks. Is it to the right?',
                 'is_correct': True, 'why_wrong': ''},
            ],
        },
    ],
}

FALLBACK_FEEDBACK_EN = (
    "I couldn't check that one just now, so it hasn't affected your review "
    "schedule. Keep going!"
)


def _bank_for(topic):
    return FALLBACK_TURNS.get(topic) or FALLBACK_TURNS[DAILY_ROUTINE]


def fallback_turn(topic, turn_index=0):
    """A known-good turn for `topic`, chosen by index so demos are repeatable."""
    bank = _bank_for(topic)
    return copy.deepcopy(bank[turn_index % len(bank)])


def demo_bank_size(topic):
    """How many distinct canned turns exist for a topic.

    The index wraps past the end of the bank, so a demo session longer than
    this repeats itself. Callers cap the session length with it.
    """
    return len(_bank_for(topic))


# --- public API ------------------------------------------------------------

def get_next_turn(topic, due_items=None, history=None, turn_index=0):
    """Produce the next tutor turn. Never raises.

    Returns a dict with `tutor_message_es`, `tutor_message_en`, `target_word`,
    `replies`, plus `provider` and `from_cache` for debugging a bad demo turn.
    """
    if settings.DEMO_MODE:
        turn = fallback_turn(topic, turn_index)
        turn.update(provider='demo', from_cache=True)
        return turn

    user_content = (
        f'Topic: {_topic_label(topic)}\n\n'
        f'Vocabulary due for review:\n{_format_vocab(due_items)}\n\n'
        f'Conversation so far:\n{_format_history(history)}\n\n'
        'Continue the conversation.'
    )

    try:
        payload, provider = _call(CHIP_SYSTEM_PROMPT, user_content)
        turn = _normalise_turn(payload)
        turn.update(provider=provider, from_cache=False)
        return turn
    except Exception as exc:
        logger.warning('get_next_turn falling back (%s: %s)', type(exc).__name__, exc)
        turn = fallback_turn(topic, turn_index)
        turn.update(provider='fallback', from_cache=True)
        return turn


def evaluate_freetext_reply(topic, target_item, user_reply, history=None, turn_index=0):
    """Grade a typed reply and continue the conversation. Never raises.

    On failure the result carries `graded=False`, and the caller must skip the
    SM-2 update - an outage must not record an answer the learner never gave.
    """
    backup = fallback_turn(topic, turn_index)

    if not _clean_str(user_reply):
        return {
            'verdict': 'blank',
            'graded': True,
            'used_target_word': False,
            'corrected_es': '',
            'feedback_en': 'Nothing came through - try typing an answer.',
            'tutor_message_es': backup['tutor_message_es'],
            'tutor_message_en': backup['tutor_message_en'],
            'replies': backup['replies'],
            'provider': 'local',
            'from_cache': True,
        }

    if settings.DEMO_MODE:
        # Free text can't be pre-cached meaningfully, so demo mode still calls
        # out; the caller decides whether to expose typing during a demo.
        logger.info('DEMO_MODE is on but free text needs a live call')

    target_es = getattr(target_item, 'spanish', None) or _clean_str(target_item)
    target_en = getattr(target_item, 'english', '')
    user_content = (
        f'Topic: {_topic_label(topic)}\n'
        f'Target vocabulary: {target_es}' + (f' ({target_en})' if target_en else '') + '\n\n'
        f'Conversation so far:\n{_format_history(history)}\n\n'
        f"Learner's typed reply: {user_reply}\n\n"
        'Grade the reply, then continue the conversation.'
    )

    try:
        payload, provider = _call(EVAL_SYSTEM_PROMPT, user_content)
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
            'corrected_es': '',
            'feedback_en': FALLBACK_FEEDBACK_EN,
            'tutor_message_es': backup['tutor_message_es'],
            'tutor_message_en': backup['tutor_message_en'],
            'replies': backup['replies'],
            'provider': 'fallback',
            'from_cache': True,
        }
