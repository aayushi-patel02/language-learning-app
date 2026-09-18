from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

# The three practice topics. Stored as slugs so they are safe in URLs and JSON.
DAILY_ROUTINE = 'daily_routine'
ORDERING_FOOD = 'ordering_food'
TRAVEL_BASICS = 'travel_basics'

TOPIC_CHOICES = [
    (DAILY_ROUTINE, 'Daily Routine'),
    (ORDERING_FOOD, 'Ordering Food'),
    (TRAVEL_BASICS, 'Travel Basics'),
]

TOPIC_SLUGS = [slug for slug, _label in TOPIC_CHOICES]

# The languages Charla can teach. A language earns a place here only once
# seed_vocab has vocabulary for it: the scheduler picks the words a lesson
# drills, so offering a language with an empty vocabulary table would open a
# lesson with nothing in it. The profile picker is built from this list for
# exactly that reason.
LANGUAGE_CHOICES = [
    ('Spanish', 'Spanish'),
    ('French', 'French'),
    ('German', 'German'),
    ('Hindi', 'Hindi'),
]

LANGUAGES = [code for code, _label in LANGUAGE_CHOICES]
DEFAULT_LANGUAGE = 'Spanish'


def default_turn_limit():
    """Read the turn limit at row-creation time, not at migration time."""
    return settings.SESSION_TURN_LIMIT


class Profile(models.Model):
    """Everything about a learner that is not authentication.

    `is_guest` is the important flag. A guest is a real User row with an
    unusable password, so all their practice is recorded normally; signing up
    converts that same row into a full account rather than copying anything
    across. Progress therefore follows them with no migration step, which
    matters because the alternative punishes someone for trying the app
    before committing to it.
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    is_guest = models.BooleanField(default=False)

    display_name = models.CharField(max_length=80, blank=True)
    # An emoji rather than an uploaded image: no storage, no upload handling,
    # no moderation, and it renders identically everywhere.
    avatar = models.CharField(max_length=8, default='🦉')

    native_language = models.CharField(max_length=40, default='English')
    # Constrained to the languages that actually have vocabulary seeded, so
    # a profile can never point a lesson at an empty table.
    learning_language = models.CharField(
        max_length=40, choices=LANGUAGE_CHOICES, default=DEFAULT_LANGUAGE,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        kind = 'guest' if self.is_guest else 'account'
        return f'{self.user.username} ({kind})'

    @property
    def name(self):
        return self.display_name or self.user.first_name or self.user.username


class VocabItem(models.Model):
    """One word or phrase the tutor can drill, scoped to a language and topic."""

    language = models.CharField(
        max_length=20, choices=LANGUAGE_CHOICES,
        default=DEFAULT_LANGUAGE, db_index=True,
    )
    # The word in the language being learned. Named neutrally because the
    # same row shape holds 'despertarse', 'se réveiller' and 'उठना'.
    term = models.CharField(max_length=200)
    # How the term sounds, for languages an English beginner cannot read at
    # all. Blank for the Latin-script languages, where the spelling already
    # does this job and a transliteration would just be noise.
    romanisation = models.CharField(max_length=200, blank=True)
    english = models.CharField(max_length=200)
    topic = models.CharField(max_length=32, choices=TOPIC_CHOICES, db_index=True)

    part_of_speech = models.CharField(max_length=32, blank=True)
    example = models.CharField(max_length=300, blank=True)
    example_en = models.CharField(max_length=300, blank=True)

    # 1 = introduce first, 3 = only once the basics are solid.
    difficulty = models.PositiveSmallIntegerField(default=1)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['language', 'topic', 'difficulty', 'term']
        constraints = [
            # Language is part of the key: 'tarde' is a Spanish word and
            # every language is free to reuse a spelling.
            models.UniqueConstraint(
                fields=['language', 'topic', 'term'],
                name='uniq_vocabitem_language_topic_term',
            ),
        ]

    def __str__(self):
        return f'{self.term} → {self.english} ({self.language})'


class UserVocabState(models.Model):
    """Per-learner SM-2 scheduling state for a single vocab item.

    The three SM-2 variables are `repetitions`, `ease_factor` and
    `interval_days`; `due_date` is derived from them. See tutor/sm2.py for the
    update rule.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='vocab_states')
    item = models.ForeignKey(VocabItem, on_delete=models.CASCADE, related_name='user_states')

    # --- SM-2 state ---
    # n: number of consecutive successful recalls (reset to 0 on a lapse).
    repetitions = models.PositiveIntegerField(default=0)
    # EF: ease factor, clamped to a floor of 1.3 by the algorithm.
    ease_factor = models.FloatField(default=2.5)
    # I: current inter-repetition interval in days (0 until first success).
    interval_days = models.PositiveIntegerField(default=0)
    # Next date this item should be reviewed on.
    due_date = models.DateField(default=timezone.localdate, db_index=True)

    # Bookmarked by the learner from the vocabulary library. Independent of
    # the schedule: saving a word says "I want to find this again", not
    # anything about when it is next due.
    is_saved = models.BooleanField(default=False)

    # --- bookkeeping, used by the recap dashboard ---
    last_reviewed_at = models.DateTimeField(null=True, blank=True)
    last_quality = models.PositiveSmallIntegerField(null=True, blank=True)
    total_reviews = models.PositiveIntegerField(default=0)
    correct_reviews = models.PositiveIntegerField(default=0)
    lapses = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['due_date', 'item__term']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'item'],
                name='uniq_uservocabstate_user_item',
            ),
        ]

    def __str__(self):
        return f'{self.user.username} · {self.item.term} (due {self.due_date})'

    @property
    def is_due(self):
        return self.due_date <= timezone.localdate()

    @property
    def is_new(self):
        """True until the learner has answered this item at least once."""
        return self.total_reviews == 0

    @property
    def accuracy(self):
        """Share of reviews answered correctly, or None if never reviewed."""
        if not self.total_reviews:
            return None
        return self.correct_reviews / self.total_reviews

    @property
    def shelf(self):
        """Which section of the vocabulary library this word belongs in.

        A word is only ever in one of these, so the library adds up to the
        whole collection with nothing double-counted.
        """
        from . import sm2

        if self.total_reviews == 0:
            return 'new'
        if self.repetitions >= sm2.STRONG_REPETITIONS:
            return 'mastered'
        if self.due_date <= timezone.localdate():
            return 'due'
        return 'learning'


class ConversationSession(models.Model):
    """One practice conversation on a single topic."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sessions')
    topic = models.CharField(max_length=32, choices=TOPIC_CHOICES)

    # Pinned when the session starts rather than read from the profile at each
    # turn. Switching the profile to French halfway through a Spanish lesson
    # would otherwise leave the conversation answering itself in two languages.
    language = models.CharField(
        max_length=20, choices=LANGUAGE_CHOICES,
        default=DEFAULT_LANGUAGE, db_index=True,
    )

    # The vocab this session was built to practise, chosen by the SM-2 scheduler
    # when the session starts.
    target_items = models.ManyToManyField(VocabItem, related_name='sessions', blank=True)
    # The same items as an ordered list of ids. A ManyToMany has no inherent
    # order, but turn N must drill the scheduler's Nth choice - overdue items
    # before new ones - so the order is stored explicitly.
    planned_item_ids = models.JSONField(default=list, blank=True)

    turn_limit = models.PositiveSmallIntegerField(default=default_turn_limit)
    is_complete = models.BooleanField(default=False)

    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f'{self.user.username} · {self.get_topic_display()} · {self.started_at:%Y-%m-%d %H:%M}'

    @property
    def answered_turn_count(self):
        # Keyed on answered_at, not was_correct: a turn the provider failed to
        # grade still consumed the learner's answer and must not be re-served.
        return self.turns.filter(answered_at__isnull=False).count()

    def target_for_index(self, index):
        """The vocab item turn `index` should drill, or None past the plan."""
        ids = self.planned_item_ids or []
        if not 0 <= index < len(ids):
            return None
        return VocabItem.objects.filter(pk=ids[index]).first()

    @property
    def is_finished(self):
        return self.is_complete or self.answered_turn_count >= self.turn_limit


class Turn(models.Model):
    """A single tutor prompt plus the learner's reply to it.

    A Turn is created when the tutor speaks, then updated in place once the
    learner answers — so `was_correct` is null for an unanswered turn.
    """

    MODE_CHIP = 'chip'
    MODE_FREETEXT = 'freetext'
    MODE_CHOICES = [
        (MODE_CHIP, 'Suggested reply (chip)'),
        (MODE_FREETEXT, 'Free text'),
    ]

    session = models.ForeignKey(
        ConversationSession, on_delete=models.CASCADE, related_name='turns'
    )
    # 0-based position within the session.
    index = models.PositiveSmallIntegerField()

    # --- what the tutor said ---
    tutor_message = models.TextField()
    tutor_message_en = models.TextField(blank=True)
    # List of {"text": ..., "en": ..., "is_correct": bool} dicts backing the
    # tappable reply chips. Empty when the turn is free-text only.
    suggested_replies = models.JSONField(default=list, blank=True)
    # Scaffolding for the free-text answer: a frame with the hard part left
    # blank, e.g. "Me gustaria ____, por favor." Shown only when the learner
    # chooses to type, so it supports without doing the work for them.
    sentence_starter = models.CharField(max_length=200, blank=True)
    # The vocab item this turn is drilling, if any.
    target_item = models.ForeignKey(
        VocabItem,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='turns',
    )

    # --- what the learner replied ---
    user_reply = models.TextField(blank=True)
    reply_mode = models.CharField(max_length=16, choices=MODE_CHOICES, blank=True)
    was_correct = models.BooleanField(null=True, blank=True)
    # SM-2 grade 0-5 derived from the reply; feeds sm2.review().
    sm2_quality = models.PositiveSmallIntegerField(null=True, blank=True)
    feedback_en = models.TextField(blank=True)
    corrected = models.CharField(max_length=300, blank=True)

    # --- provenance, useful when debugging a bad demo turn ---
    llm_provider = models.CharField(max_length=32, blank=True)
    from_cache = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    answered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['session', 'index']
        constraints = [
            models.UniqueConstraint(
                fields=['session', 'index'],
                name='uniq_turn_session_index',
            ),
        ]

    def __str__(self):
        return f'{self.session_id} #{self.index}: {self.tutor_message[:40]}'

    @property
    def is_answered(self):
        # was_correct stays null when grading failed, so it can't mean this.
        return self.answered_at is not None

    @property
    def is_graded(self):
        return self.sm2_quality is not None
