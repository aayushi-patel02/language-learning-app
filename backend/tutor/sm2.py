"""The SM-2 spaced-repetition algorithm, plus the session scheduler built on it.

SM-2 is Piotr Wozniak's 1987 algorithm for SuperMemo. Each item carries three
variables:

    n   repetitions  - consecutive successful recalls
    EF  ease_factor  - how easily the item is remembered (starts at 2.5)
    I   interval     - days until the next review

After a review graded ``q`` on a 0-5 scale:

    if q >= 3 (recalled):
        I(1) = 1, I(2) = 6, I(n) = I(n-1) * EF   for n > 2
        n = n + 1
    else (forgotten):
        n = 0, I = 1                             start the item over

    EF' = EF + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
    EF' = max(1.3, EF')

Two deliberate choices worth knowing, since both are places implementations
differ:

1. The interval is computed with the *old* EF, before the EF update, matching
   the ordering of steps 3 and 5 in Wozniak's original description.
2. The EF update is applied on every review, including failures. Step 7 of the
   original text can be read as leaving EF untouched on a lapse, but that lets
   a repeatedly-failed item keep a high EF and re-grow its interval quickly.
   Applying the penalty is what most SM-2 implementations do.

The grading functions map this app's two answer modes onto the 0-5 scale.
Tapping a correct chip is recognition rather than free recall, so it earns 4
rather than 5; a wrong chip earns 2, "incorrect, but the right answer looked
familiar", since the correct option was on screen.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from django.conf import settings
from django.utils import timezone

# --- algorithm constants (from the original SM-2 description) ---
INITIAL_EASE_FACTOR = 2.5
MIN_EASE_FACTOR = 1.3
FIRST_INTERVAL_DAYS = 1
SECOND_INTERVAL_DAYS = 6

MIN_QUALITY = 0
MAX_QUALITY = 5
# A grade of 3 or better counts as a successful recall.
PASSING_QUALITY = 3

# Consecutive successful recalls before a word is reported as well retained.
# Three is where SM-2's interval has grown past a fortnight, so it is a fair
# point to call something learned rather than merely seen.
STRONG_REPETITIONS = 3

# --- mapping this app's answer modes onto the 0-5 grade scale ---
QUALITY_CHIP_CORRECT = 4
QUALITY_CHIP_INCORRECT = 2

# Verdicts the LLM returns for a free-text answer, in descending quality.
FREETEXT_QUALITY = {
    'perfect': 5,      # correct and idiomatic
    'minor': 4,        # right answer, small accent or spelling slip
    'awkward': 3,      # understandable but grammatically off
    'wrong': 1,        # incorrect
    'blank': 0,        # no meaningful attempt
}
DEFAULT_FREETEXT_VERDICT = 'wrong'


@dataclass(frozen=True)
class SM2Result:
    """The new scheduling state produced by one review."""

    repetitions: int
    ease_factor: float
    interval_days: int
    due_date: date
    quality: int

    @property
    def passed(self):
        return self.quality >= PASSING_QUALITY


def _round_half_up(value):
    """Round to the nearest integer, .5 always going up.

    Python's built-in round() uses banker's rounding, so round(2.5) == 2. That
    is a surprising way to compute a review interval, so round half up instead.
    Intervals are always positive, which is what makes this shortcut safe.
    """
    return int(value + 0.5)


def next_ease_factor(ease_factor, quality):
    """Apply the SM-2 ease-factor update, clamped to the 1.3 floor."""
    adjustment = 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)
    return max(MIN_EASE_FACTOR, round(ease_factor + adjustment, 4))


def review(repetitions, ease_factor, interval_days, quality, today=None):
    """Run one SM-2 review and return the new state.

    A pure function of its arguments - it touches no database. `today` is
    injectable so tests can check due dates without freezing the clock.
    """
    if not isinstance(quality, int):
        raise TypeError(f'quality must be an int 0-5, got {quality!r}')
    if not MIN_QUALITY <= quality <= MAX_QUALITY:
        raise ValueError(f'quality must be between 0 and 5, got {quality}')
    if today is None:
        today = timezone.localdate()

    passed = quality >= PASSING_QUALITY

    if passed:
        if repetitions == 0:
            new_interval = FIRST_INTERVAL_DAYS
        elif repetitions == 1:
            new_interval = SECOND_INTERVAL_DAYS
        else:
            # Uses the pre-update ease factor, per the original step ordering.
            new_interval = max(FIRST_INTERVAL_DAYS,
                               _round_half_up(interval_days * ease_factor))
        new_repetitions = repetitions + 1
    else:
        # A lapse sends the item back to the start of the schedule.
        new_repetitions = 0
        new_interval = FIRST_INTERVAL_DAYS

    return SM2Result(
        repetitions=new_repetitions,
        ease_factor=next_ease_factor(ease_factor, quality),
        interval_days=new_interval,
        due_date=today + timedelta(days=new_interval),
        quality=quality,
    )


def apply_review(state, quality, today=None):
    """Update a UserVocabState in place from a grade. The caller saves it.

    Returns the SM2Result so the view can report the new interval back to the
    frontend for the recap screen.
    """
    result = review(
        repetitions=state.repetitions,
        ease_factor=state.ease_factor,
        interval_days=state.interval_days,
        quality=quality,
        today=today,
    )

    # A lapse only counts if the learner had previously got this item right;
    # failing a brand-new item is not forgetting it.
    if state.repetitions > 0 and not result.passed:
        state.lapses += 1

    state.repetitions = result.repetitions
    state.ease_factor = result.ease_factor
    state.interval_days = result.interval_days
    state.due_date = result.due_date

    state.last_quality = quality
    state.last_reviewed_at = timezone.now()
    state.total_reviews += 1
    if result.passed:
        state.correct_reviews += 1

    return result


# --- grading helpers -------------------------------------------------------

def quality_for_chip(is_correct):
    """Grade a tapped suggested reply."""
    return QUALITY_CHIP_CORRECT if is_correct else QUALITY_CHIP_INCORRECT


def quality_for_freetext(verdict):
    """Grade a typed reply from the LLM's verdict label.

    Unrecognised verdicts fall back to 'wrong' rather than raising, so a
    malformed LLM response degrades the grade instead of breaking the turn.
    """
    key = (verdict or '').strip().lower()
    return FREETEXT_QUALITY.get(key, FREETEXT_QUALITY[DEFAULT_FREETEXT_VERDICT])


# --- session scheduling ----------------------------------------------------

def ensure_states(user, topic=None, language=None):
    """Make sure `user` has a UserVocabState row for every item in `topic`.

    Returns a queryset of those states. New vocab added later is picked up the
    next time a session starts.

    `language` matters more than it looks. Without it a learner studying
    Spanish would be given a scheduling row for all 240 items, so their
    vocabulary library would fill with German they have never seen and the
    scheduler could pick a Hindi word for a Spanish lesson. Callers inside the
    app always pass it; it stays optional so a test can ask about every
    language at once.
    """
    from .models import UserVocabState, VocabItem

    items = VocabItem.objects.all()
    if language:
        items = items.filter(language=language)
    if topic:
        items = items.filter(topic=topic)

    existing_item_ids = set(
        UserVocabState.objects.filter(user=user, item__in=items)
        .values_list('item_id', flat=True)
    )
    missing = [
        UserVocabState(user=user, item=item)
        for item in items
        if item.id not in existing_item_ids
    ]
    if missing:
        UserVocabState.objects.bulk_create(missing, ignore_conflicts=True)

    return UserVocabState.objects.filter(user=user, item__in=items)


def select_session_items(user, topic, limit=None, language=None, first_item=None):
    """Choose the vocab for one practice session, in the order to drill it.

    Scoped to one `language`: a Spanish lesson must never be handed a German
    word, however overdue that word is.

    Priority:
      1. Due or overdue items, oldest due date first, and among items due the
         same day the lowest ease factor (hardest) first.
      2. Items never seen before, easiest first, so new material is introduced
         gently.
      3. Items not due yet, nearest due date first - only reached when the
         learner has cleared everything and wants to keep going.

    `first_item` overrides all of that for one word, moving it to the head of
    the plan. It is what makes "practise this word" honest: a hard word sorts
    behind every easier one, so a learner who asked for it by name would
    otherwise never reach it inside a session's turn limit.
    """
    if limit is None:
        limit = settings.SESSION_TURN_LIMIT

    states = list(ensure_states(user, topic, language).select_related('item'))
    today = timezone.localdate()

    due, unseen, upcoming = [], [], []
    for state in states:
        if state.total_reviews == 0:
            unseen.append(state)
        elif state.due_date <= today:
            due.append(state)
        else:
            upcoming.append(state)

    due.sort(key=lambda s: (s.due_date, s.ease_factor))
    unseen.sort(key=lambda s: (s.item.difficulty, s.item.term))
    upcoming.sort(key=lambda s: s.due_date)

    items = [state.item for state in due + unseen + upcoming]

    if first_item is not None:
        # Pulled out and put back at the front, so asking for a word neither
        # duplicates it nor lengthens the session.
        items = [first_item] + [i for i in items if i.pk != first_item.pk]

    return items[:limit]
