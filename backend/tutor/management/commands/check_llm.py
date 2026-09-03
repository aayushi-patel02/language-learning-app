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
from tutor.models import TOPIC_SLUGS, VocabItem

# Which env var holds the key and model for each provider.
PROVIDER_ENV = {
    'gemini': ('GEMINI_API_KEY', 'GEMINI_MODEL', llm.DEFAULT_GEMINI_MODEL),
    'deepseek': ('DEEPSEEK_API_KEY', 'DEEPSEEK_MODEL', 'deepseek-chat'),
    'sarvam': ('SARVAM_API_KEY', 'SARVAM_MODEL', 'sarvam-105b-conversations'),
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

        if options['list_models']:
            self.stdout.write('')
            if provider != 'gemini':
                self.stdout.write(self.style.WARNING(
                    f'--list-models is only implemented for Gemini, not {provider}.'
                ))
            elif not self.list_gemini_models():
                return self.fail()

        if settings.DEMO_MODE:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING(
                'DEMO_MODE is on, so get_next_turn will not call the provider. '
                'Set DEMO_MODE=false to test the live path.'
            ))

        return self.try_one_turn(options['topic'])

    def list_gemini_models(self):
        import requests

        self.stdout.write(self.style.MIGRATE_HEADING('Models this key can reach'))
        try:
            response = requests.get(
                f'{llm.GEMINI_BASE_URL}/models',
                headers={'x-goog-api-key': os.getenv('GEMINI_API_KEY')},
                timeout=llm.REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f'  could not list models: {exc}'))
            return False

        names = [
            entry['name'].removeprefix('models/')
            for entry in response.json().get('models', [])
            if 'generateContent' in entry.get('supportedGenerationMethods', [])
        ]
        if not names:
            self.stdout.write(self.style.ERROR('  none support generateContent'))
            return False

        configured = os.getenv('GEMINI_MODEL', llm.DEFAULT_GEMINI_MODEL)
        for name in sorted(names):
            marker = '  <- GEMINI_MODEL' if name == configured else ''
            self.stdout.write(f'  {name}{self.style.SUCCESS(marker)}')

        if configured not in names:
            self.stdout.write('')
            self.stdout.write(self.style.ERROR(
                f'GEMINI_MODEL={configured} is not in that list. Set it to one '
                f'of the names above in backend/.env.'
            ))
            return False
        return True

    def try_one_turn(self, topic):
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING(f'Live turn ({topic})'))

        due = list(VocabItem.objects.filter(topic=topic)[:3])
        if not due:
            self.stdout.write(self.style.WARNING(
                '  no vocab seeded - run `python manage.py seed_vocab` first'
            ))

        started = time.time()
        turn = llm.get_next_turn(topic, due_items=due, history=[])
        elapsed = time.time() - started

        used_fallback = turn['provider'] in ('fallback', 'demo')
        self.stdout.write(f"  provider       {turn['provider']}  ({elapsed:.1f}s)")
        self.stdout.write(f"  tutor          {turn['tutor_message_es']}")
        self.stdout.write(f"  translation    {turn['tutor_message_en']}")
        self.stdout.write(f"  target         {turn['target_word'] or '(none given)'}")

        correct = sum(reply['is_correct'] for reply in turn['replies'])
        for reply in turn['replies']:
            mark = self.style.SUCCESS('correct') if reply['is_correct'] else '  wrong'
            self.stdout.write(f"  [{mark}] {reply['es']}")
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
