"""Generate a presenter script for the scripted (DEMO_MODE) demo.

    python manage.py demo_script                    # print to the terminal
    python manage.py demo_script --out ../docs/demo-script.md
    python manage.py demo_script --topic ordering_food

Generated from tutor/demo_turns.py rather than written by hand, so the script
can never drift from what the app actually puts on screen. Regenerate it
whenever the bank changes.

Only meaningful with DEMO_MODE=true - with a live provider the turns are
generated fresh each time and nothing can be scripted in advance.
"""

from django.core.management.base import BaseCommand

from tutor.demo_turns import FALLBACK_TURNS
from tutor.models import TOPIC_CHOICES, TOPIC_SLUGS

TOPIC_LABELS = dict(TOPIC_CHOICES)

PREAMBLE = """\
# Presenter script

Generated from the demo bank - do not edit by hand. Regenerate with:

    python manage.py demo_script --out ../docs/demo-script.md

## Before you start

1. Set `DEMO_MODE=true` in `backend/.env` and restart the backend. Every turn
   below then appears in exactly this order, with no network call.
2. The **bold** reply is the correct one. The others are wrong, and the reason
   given is what the app will show you if you pick them.

## How to run it

You do not need to know Spanish. Two things carry the demo:

- **The English line under each chip gives it away.** The correct reply reads
  as natural English; the wrong ones read as broken English.
- **Pick a wrong answer on purpose at least once.** The app prints the
  correction and the reason, and you read that out. You are not explaining
  Spanish - you are showing that the product explains it.

The strongest beat is the contrast: get one wrong and it returns tomorrow; get
the next one right and watch the interval stretch to 6 days, then 15. That is
the whole spaced-repetition argument in about twenty seconds, and the recap
screen at the end shows it as a list.
"""


class Command(BaseCommand):
    help = 'Generate the presenter script for a DEMO_MODE walkthrough.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--out', help='Write to this path instead of printing.')
        parser.add_argument(
            '--topic', choices=TOPIC_SLUGS,
            help='Only this topic (default: all three).')

    def handle(self, *args, **options):
        topics = [options['topic']] if options['topic'] else TOPIC_SLUGS
        lines = [PREAMBLE]

        for topic in topics:
            bank = FALLBACK_TURNS[topic]
            lines.append(f'\n---\n\n## {TOPIC_LABELS[topic]}\n')
            lines.append(f'{len(bank)} turns. Target vocabulary in order: '
                         + ', '.join(f'`{t["target_word"]}`' for t in bank)
                         + '\n')

            for index, turn in enumerate(bank, start=1):
                lines.append(f'\n### Turn {index} — `{turn["target_word"]}`\n')
                lines.append(f'> {turn["tutor_message"]}  ')
                lines.append(f'> *{turn["tutor_message_en"]}*\n')

                for position, reply in enumerate(turn['replies'], start=1):
                    if reply['is_correct']:
                        lines.append(
                            f'{position}. **{reply["es"]}** — *{reply["en"]}* '
                            f'← correct')
                    else:
                        lines.append(
                            f'{position}. {reply["es"]} — *{reply["en"]}*  \n'
                            f'   app will say: {reply["why_wrong"]}')
                lines.append('')

        output = '\n'.join(lines)

        if options['out']:
            from pathlib import Path

            path = Path(options['out']).resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(output)
            self.stdout.write(self.style.SUCCESS(f'Wrote {path}'))
            self.stdout.write(
                f'{sum(len(FALLBACK_TURNS[t]) for t in topics)} turns across '
                f'{len(topics)} topic(s).')
        else:
            self.stdout.write(output)
