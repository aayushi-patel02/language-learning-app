"""Verify the configured LLM provider actually works, end to end.

    python manage.py check_llm                # one real turn through the adapter
    python manage.py check_llm --list-models  # what models the key can reach
    python manage.py check_llm --topic travel_basics

Exits non-zero if the live path is broken, so it doubles as a pre-demo check.
API keys are never printed - only whether they are present.
"""

import os
import time

from django.conf import settings
from django.core.management.base import BaseCommand

from tutor import llm
from tutor.models import DEFAULT_LANGUAGE, LANGUAGES, TOPIC_SLUGS, VocabItem

# Which env var holds the key and model for each provider.
PROVIDER_ENV = {
    'groq': ('GROQ_API_KEY', 'GROQ_MODEL', llm.DEFAULT_GROQ_MODEL),
    'gemini': ('GEMINI_API_KEY', 'GEMINI_MODEL', llm.DEFAULT_GEMINI_MODEL),
    'deepseek': ('DEEPSEEK_API_KEY', 'DEEPSEEK_MODEL', llm.DEFAULT_DEEPSEEK_MODEL),
    'sarvam': ('SARVAM_API_KEY', 'SARVAM_MODEL', 'sarvam-105b-conversations'),
}

# Providers that expose OpenAI's GET /models listing endpoint.
OPENAI_COMPATIBLE_BASE_URLS = {
    'groq': llm.GROQ_BASE_URL,
    'deepseek': llm.DEEPSEEK_BASE_URL,
}


class Command(BaseCommand):
    help = 'Check that the configured LLM provider responds and parses correctly.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--list-models',
            action='store_true',
            help='List models the current key can reach (Gemini only).',
        )
        parser.add_argument(
            '--topic',
            default=TOPIC_SLUGS[0],
            choices=TOPIC_SLUGS,
            help='Topic to request a turn for.',
        )
        parser.add_argument(
            '--language',
            default=DEFAULT_LANGUAGE,
            choices=LANGUAGES + ['all'],
            help='Language to request a turn in, or "all" to try each.',
        )

    def handle(self, *args, **options):
        provider = llm.active_provider()
        key_var, model_var, model_default = PROVIDER_ENV[provider]
        key_present = bool(os.getenv(key_var))
        model = os.getenv(model_var, model_default)

        self.stdout.write(self.style.MIGRATE_HEADING('Configuration'))
        self.stdout.write(f'  LLM_PROVIDER   {settings.LLM_PROVIDER!r} -> {provider}')
        self.stdout.write(f'  model          {model}')
        self.stdout.write(
            f'  {key_var:<15}'
            + (self.style.SUCCESS('set') if key_present
               else self.style.ERROR('MISSING'))
        )
        self.stdout.write(f'  DEMO_MODE      {settings.DEMO_MODE}')

        if not key_present:
            self.stdout.write('')
            self.stdout.write(self.style.ERROR(
                f'{key_var} is not set in backend/.env - the adapter will use '
                f'its hand-written fallback turns for every request.'
            ))
            return self.fail()

        if options['list_models'] and not self.list_models(provider):
            return self.fail()

        if settings.DEMO_MODE:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING(
                'DEMO_MODE is on, so get_next_turn will not call the provider. '
                'Set DEMO_MODE=false to test the live path.'
            ))

        if options['language'] == 'all':
            return all([
                self.try_one_turn(options['topic'], language)
                for language in LANGUAGES
            ])
        return self.try_one_turn(options['topic'], options['language'])

    def list_models(self, provider):
        """Print the models this key can reach, and flag a bad model name.

        Worth running before anything else: model names churn, and access is
        per-account, so a plausible-looking name in .env is often simply not
        one this key is allowed to use.
        """
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('Models this key can reach'))

        try:
            if provider == 'gemini':
                names = self._gemini_model_names()
            elif provider in OPENAI_COMPATIBLE_BASE_URLS:
                names = self._openai_compatible_model_names(provider)
            else:
                self.stdout.write(self.style.WARNING(
                    f'  listing is not implemented for {provider}.'))
                return True
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f'  could not list models: {exc}'))
            return False

        if not names:
            self.stdout.write(self.style.ERROR('  the key can reach no models'))
            return False

        key_var, model_var, model_default = PROVIDER_ENV[provider]
        configured = os.getenv(model_var, model_default)
        for name in names:
            marker = f'  <- {model_var}' if name == configured else ''
            self.stdout.write(f'  {name}{self.style.SUCCESS(marker)}')

        if configured not in names:
            self.stdout.write('')
            self.stdout.write(self.style.ERROR(
                f'{model_var}={configured} is not in that list. Set it to one '
                f'of the names above in backend/.env.'
            ))
            return False
        return True

    def _gemini_model_names(self):
        import requests

        response = requests.get(
            f'{llm.GEMINI_BASE_URL}/models',
            headers={'x-goog-api-key': os.getenv('GEMINI_API_KEY')},
            timeout=llm.REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return sorted(
            entry['name'].removeprefix('models/')
            for entry in response.json().get('models', [])
            if 'generateContent' in entry.get('supportedGenerationMethods', [])
        )

    def _openai_compatible_model_names(self, provider):
        import requests

        key_var = PROVIDER_ENV[provider][0]
        response = requests.get(
            f'{OPENAI_COMPATIBLE_BASE_URLS[provider]}/models',
            headers={'Authorization': f'Bearer {os.getenv(key_var)}'},
            timeout=llm.REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return sorted(entry['id'] for entry in response.json().get('data', []))

    def try_one_turn(self, topic, language=DEFAULT_LANGUAGE):
        self.stdout.write('')
        self.stdout.write(
            self.style.MIGRATE_HEADING(f'Live turn ({language}, {topic})'))

        due = list(VocabItem.objects.filter(language=language, topic=topic)[:3])
        if not due:
            self.stdout.write(self.style.WARNING(
                '  no vocab seeded - run `python manage.py seed_vocab` first'
            ))

        started = time.time()
        turn = llm.get_next_turn(topic, language, due_items=due, history=[])
        elapsed = time.time() - started

        used_fallback = turn['provider'] in ('fallback', 'demo')
        self.stdout.write(f"  provider       {turn['provider']}  ({elapsed:.1f}s)")
        self.stdout.write(f"  tutor          {turn['tutor_message']}")
        self.stdout.write(f"  translation    {turn['tutor_message_en']}")
        self.stdout.write(f"  target         {turn['target_word'] or '(none given)'}")

        correct = sum(reply['is_correct'] for reply in turn['replies'])
        for reply in turn['replies']:
            mark = self.style.SUCCESS('correct') if reply['is_correct'] else '  wrong'
            self.stdout.write(f"  [{mark}] {reply['text']}")
            if reply['why_wrong']:
                self.stdout.write(f"             {reply['why_wrong']}")

        self.stdout.write('')
        if used_fallback:
            self.stdout.write(self.style.ERROR(
                'FELL BACK - the app still works, but this turn came from the '
                'hand-written bank, not the model. Re-run with DJANGO_LOG_LEVEL '
                'or check the warning above for the reason.'
            ))
            return self.fail()

        if correct != 1:
            self.stdout.write(self.style.WARNING(
                f'Live response OK, but {correct} replies were marked correct '
                f'(want exactly 1). Chip grading still works; the distractors '
                f'are just weaker than intended.'
            ))
            return

        self.stdout.write(self.style.SUCCESS(
            'Live path works: real response, parsed cleanly, exactly one '
            'correct reply.'
        ))

    def fail(self):
        raise SystemExit(1)
