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


def default_turn_limit():
    """Read the turn limit at row-creation time, not at migration time."""
    return settings.SESSION_TURN_LIMIT


class VocabItem(models.Model):
    """One Spanish word or phrase the tutor can drill, scoped to a topic."""

    spanish = models.CharField(max_length=200)
    english = models.CharField(max_length=200)
    topic = models.CharField(max_length=32, choices=TOPIC_CHOICES, db_index=True)

    part_of_speech = models.CharField(max_length=32, blank=True)
    example_es = models.CharField(max_length=300, blank=True)
    example_en = models.CharField(max_length=300, blank=True)

    # 1 = introduce first, 3 = only once the basics are solid.
    difficulty = models.PositiveSmallIntegerField(default=1)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['topic', 'difficulty', 'spanish']
        constraints = [
            models.UniqueConstraint(
                fields=['topic', 'spanish'],
                name='uniq_vocabitem_topic_spanish',
            ),
        ]

    def __str__(self):
        return f'{self.spanish} → {self.english}'


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
        ordering = ['due_date', 'item__spanish']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'item'],
                name='uniq_uservocabstate_user_item',
            ),
        ]

    def __str__(self):
        return f'{self.user.username} · {self.item.spanish} (due {self.due_date})'

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
    tutor_message_es = models.TextField()
    tutor_message_en = models.TextField(blank=True)
    # List of {"es": ..., "en": ..., "is_correct": bool} dicts backing the
    # tappable reply chips. Empty when the turn is free-text only.
    suggested_replies = models.JSONField(default=list, blank=True)
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
    corrected_es = models.CharField(max_length=300, blank=True)

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
        return f'{self.session_id} #{self.index}: {self.tutor_message_es[:40]}'

    @property
    def is_answered(self):
        # was_correct stays null when grading failed, so it can't mean this.
        return self.answered_at is not None

    @property
    def is_graded(self):
        return self.sm2_quality is not None
