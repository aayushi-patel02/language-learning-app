"""Session API.

Three endpoints: start a session, answer a turn, read the recap.

Requests carry a token identifying a guest or a full account; without one they
fall back to the seeded demo learner.

The rule that matters most here: **chip grading reads `is_correct` from the
stored turn, never from the request body.** The browser is told which options
exist but not which is right, so a learner (or a judge poking at the network
tab) cannot mark their own answer correct.
"""

from datetime import date, timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

# Imported as modules, not as bare names: `llm.get_next_turn` is looked up at
# call time, so tests can patch it without the reference being frozen here.
from . import insights, llm, sm2
from .models import (
    DEFAULT_LANGUAGE,
    LANGUAGE_CHOICES,
    LANGUAGES,
    TOPIC_CHOICES,
    TOPIC_SLUGS,
    ConversationSession,
    Turn,
    UserVocabState,
    VocabItem,
)
from .serializers import TurnSerializer


def get_demo_user():
    """The seeded fallback learner, used when a request carries no token."""
    user, created = User.objects.get_or_create(
        username=settings.DEMO_USERNAME,
        defaults={'first_name': 'Demo', 'last_name': 'Learner'},
    )
    if created:
        # Nothing ever logs in as this user, so give it no usable credential.
        user.set_unusable_password()
        user.save(update_fields=['password'])
    return user


def current_learner(request):
    """Whose progress this request is about.

    A token identifies a guest or a full account, and either owns its own
    schedule. Without one the seeded demo learner answers, which keeps the
    browsable API and curl usable and means the app still runs for anyone who
    has not signed in.
    """
    if request.user.is_authenticated:
        return request.user
    return get_demo_user()


def _history(session):
    """The conversation so far, in the shape the prompts expect."""
    return [
        {'tutor': turn.tutor_message, 'user': turn.user_reply}
        for turn in session.turns.order_by('index')
    ]


def learner_language(user):
    """The language this learner is studying.

    Falls back to the default rather than raising: the seeded demo learner
    has no profile, and a lesson still has to start for them.
    """
    profile = getattr(user, 'profile', None)
    language = getattr(profile, 'learning_language', '') or DEFAULT_LANGUAGE
    return language if language in LANGUAGES else DEFAULT_LANGUAGE


def _resolve_target(topic, language, target_word, planned_item):
    """The vocab item a turn actually drills.

    The scheduler decides what *should* be practised and tells the model, but
    the turn on screen can differ: a fallback turn comes from a fixed bank, and
    a live model can drift onto a neighbouring word. The SM-2 update has to
    follow the vocabulary the learner actually saw, or the recap credits a word
    they were never shown - so match the turn's own target back to the topic's
    vocab, and only fall back to the plan when it doesn't match anything.

    Scoped to the session's language as well as its topic, because a spelling
    is only unique within a language.
    """
    word = str(target_word or '').strip()
    if word:
        match = VocabItem.objects.filter(
            language=language, topic=topic, term__iexact=word).first()
        if match is not None:
            return match
    return planned_item


def _create_turn(session, index, planned_item, result):
    return Turn.objects.create(
        session=session,
        index=index,
        tutor_message=result['tutor_message'],
        tutor_message_en=result['tutor_message_en'],
        sentence_starter=result.get('sentence_starter', ''),
        suggested_replies=result['replies'],
        target_item=_resolve_target(
            session.topic, session.language, result.get('target_word'),
            planned_item),
        llm_provider=result['provider'],
        from_cache=result['from_cache'],
    )


def _focus_word_payload(item):
    """The word a lesson was opened for, echoed back to the client.

    A learner who taps "practise this word" lands on a screen headed with the
    topic, so nothing on it acknowledges the word they asked for. Returning it
    lets the lesson name it, and lets the recap offer the way back.
    """
    if item is None:
        return None
    return {
        'id': item.pk,
        'term': item.term,
        'romanisation': item.romanisation,
        'english': item.english,
    }


def _correct_option(chips):
    for chip in chips or []:
        if chip.get('is_correct'):
            return chip.get('text', '')
    return ''


class LanguageListView(APIView):
    """GET /api/languages/ - what Charla can actually teach.

    Built from the vocabulary table rather than from a constant, so the
    profile picker can only ever offer a language that has words behind it.
    Offering one that does not is how the picker came to promise seven
    languages while every lesson ran in Spanish.
    """

    def get(self, request):
        counts = dict(
            VocabItem.objects.values_list('language')
            .annotate(n=Count('id'))
            .values_list('language', 'n')
        )
        return Response({
            'languages': [
                {'code': code, 'label': label, 'word_count': counts[code]}
                for code, label in LANGUAGE_CHOICES
                if counts.get(code)
            ],
            'current': learner_language(current_learner(request)),
        })


def streak_from(active_days, today):
    """Consecutive days of practice ending today, or zero if already broken.

    Yesterday still counts while today is unfinished, so a streak does not
    appear to reset the moment the clock rolls over.
    """
    streak = 0
    cursor = today
    if today not in active_days and (today - timedelta(days=1)) in active_days:
        cursor = today - timedelta(days=1)
    while cursor in active_days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def practice_days(user, language):
    """The local dates this learner answered something in this language.

    Local, not UTC: the streak is compared against `timezone.localdate()`,
    and mixing the two would end a streak early for anyone whose evening
    practice lands on the next UTC day.
    """
    stamps = Turn.objects.filter(
        session__user=user, session__language=language,
        answered_at__isnull=False,
    ).values_list('answered_at', flat=True)
    return {timezone.localtime(stamp).date() for stamp in stamps}


def next_review_after(user, language, today):
    """When the soonest batch of words comes back, and how many."""
    upcoming = UserVocabState.objects.filter(
        user=user, item__language=language,
        total_reviews__gt=0, due_date__gt=today,
    ).order_by('due_date')
    first = upcoming.first()
    if first is None:
        return None
    return {
        'date': first.due_date,
        'count': upcoming.filter(due_date=first.due_date).count(),
    }


class TopicListView(APIView):
    """GET /api/topics/ - the three topics with each one's review load.

    The whole premise is "practise what you are about to forget", so the
    learner has to be able to see that *before* starting a session rather
    than discovering it turn by turn.

    Read-only on purpose: it does not create UserVocabState rows the way the
    scheduler does, because a GET on the home screen should not write.
    """

    def get(self, request):
        user = current_learner(request)
        language = learner_language(user)
        today = timezone.localdate()

        states = {
            state.item_id: state
            for state in UserVocabState.objects.filter(user=user)
        }

        payload = []
        for slug, label in TOPIC_CHOICES:
            due = new = scheduled = 0
            items = VocabItem.objects.filter(
                language=language, topic=slug).only('id')
            for item in items:
                state = states.get(item.pk)
                if state is None or state.total_reviews == 0:
                    new += 1
                elif state.due_date <= today:
                    due += 1
                else:
                    scheduled += 1

            payload.append({
                'id': slug,
                'label': label,
                'total': due + new + scheduled,
                'due': due,              # seen before, ready for review now
                'new': new,              # never practised
                'scheduled': scheduled,  # known, not due yet
            })

        return Response({
            'topics': payload,
            'streak': streak_from(practice_days(user, language), today),
            # Lets the home screen say when work comes back instead of only
            # that there is none today.
            'next_review': next_review_after(user, language, today),
        })


def _word_payload(item, state):
    """One vocabulary row, shared by the library and the detail screen."""
    return {
        'id': item.pk,
        'term': item.term,
        # Empty for the Latin-script languages; the library only renders
        # it when there is something to render.
        'romanisation': item.romanisation,
        'language': item.language,
        'english': item.english,
        'topic': item.topic,
        'topic_label': item.get_topic_display(),
        'part_of_speech': item.part_of_speech,
        'example': item.example,
        'example_en': item.example_en,
        'shelf': state.shelf,
        'is_saved': state.is_saved,
        'due_date': state.due_date if state.total_reviews else None,
        'repetitions': state.repetitions,
        'total_reviews': state.total_reviews,
        'correct_reviews': state.correct_reviews,
        'lapses': state.lapses,
        'accuracy': round(state.accuracy, 2) if state.accuracy is not None else None,
        'last_reviewed_at': state.last_reviewed_at,
    }


class VocabularyListView(APIView):
    """GET /api/vocabulary/ - the whole collection, grouped by mastery.

    Shelves are mutually exclusive (see UserVocabState.shelf), so the counts
    add up to the collection with nothing double-counted. `saved` and
    `recent` are cross-cuts over the same words rather than shelves, which is
    why they are returned as id lists instead of a fourth group.
    """

    def get(self, request):
        user = current_learner(request)
        states = sm2.ensure_states(
            user, language=learner_language(user)).select_related('item')

        shelves = {'due': [], 'learning': [], 'mastered': [], 'new': []}
        saved = []
        for state in states:
            payload = _word_payload(state.item, state)
            shelves[payload['shelf']].append(payload)
            if state.is_saved:
                saved.append(payload)

        # Ordering per shelf: the most useful thing first in each case.
        shelves['due'].sort(key=lambda w: (w['due_date'] or date.max, w['term']))
        shelves['learning'].sort(key=lambda w: (w['due_date'] or date.max, w['term']))
        shelves['mastered'].sort(key=lambda w: -w['repetitions'])
        shelves['new'].sort(key=lambda w: (w['topic'], w['term']))
        saved.sort(key=lambda w: w['term'])

        recent_ids = list(
            Turn.objects.filter(
                session__user=user,
                answered_at__isnull=False,
                target_item__isnull=False,
            )
            .order_by('-answered_at')
            .values_list('target_item_id', flat=True)[:40]
        )
        # De-duplicate while keeping most-recent-first order.
        seen, recent_order = set(), []
        for item_id in recent_ids:
            if item_id not in seen:
                seen.add(item_id)
                recent_order.append(item_id)

        by_id = {
            word['id']: word
            for shelf in shelves.values()
            for word in shelf
        }
        recent = [by_id[i] for i in recent_order[:12] if i in by_id]

        return Response({
            'counts': {name: len(words) for name, words in shelves.items()},
            'total': sum(len(words) for words in shelves.values()),
            'shelves': shelves,
            'saved': saved,
            'recent': recent,
        })


class WordDetailView(APIView):
    """GET /api/vocabulary/<id>/ and POST to toggle the bookmark."""

    def get_state(self, request, item_id):
        user = current_learner(request)
        item = get_object_or_404(VocabItem, pk=item_id)
        state, _ = UserVocabState.objects.get_or_create(user=user, item=item)
        return user, item, state

    def get(self, request, item_id):
        user, item, state = self.get_state(request, item_id)

        # Where the learner has actually met this word, newest first, so the
        # detail screen can show it in the context it was practised in.
        appearances = [
            {
                'session_id': turn.session_id,
                'tutor_message': turn.tutor_message,
                'tutor_message_en': turn.tutor_message_en,
                'user_reply': turn.user_reply,
                'was_correct': turn.was_correct,
                'feedback_en': turn.feedback_en,
                'answered_at': turn.answered_at,
            }
            for turn in Turn.objects.filter(
                session__user=user, target_item=item, answered_at__isnull=False
            ).order_by('-answered_at')[:5]
        ]

        payload = _word_payload(item, state)
        payload['appearances'] = appearances
        payload['ease_factor'] = round(state.ease_factor, 2)
        payload['interval_days'] = state.interval_days
        return Response(payload)

    def post(self, request, item_id):
        _user, item, state = self.get_state(request, item_id)
        state.is_saved = bool(request.data.get('is_saved', not state.is_saved))
        state.save(update_fields=['is_saved'])
        return Response({'id': item.pk, 'is_saved': state.is_saved})


class ProgressView(APIView):
    """GET /api/progress/ - cumulative progress across every lesson so far.

    Every number here already existed in UserVocabState; none of it was
    reachable from the app. A learner could see what was due today but never
    how far they had come, which is the part that makes spaced repetition feel
    worth continuing.
    """

    def get(self, request):
        user = current_learner(request)
        language = learner_language(user)
        today = timezone.localdate()

        # Scoped to the language being studied, like the home screen and the
        # library. Unscoped, the by-topic totals counted all four languages'
        # vocabulary, so a topic of twenty words reported progress out of
        # eighty, and a streak built in Spanish showed up under Hindi.
        states = list(
            UserVocabState.objects.filter(user=user, item__language=language)
            .select_related('item')
        )
        # A row exists as soon as the scheduler looks at a word, so "started"
        # has to mean actually answered at least once.
        started = [state for state in states if state.total_reviews > 0]

        reviews = sum(state.total_reviews for state in started)
        correct = sum(state.correct_reviews for state in started)
        lapses = sum(state.lapses for state in started)

        def is_strong(state):
            return state.repetitions >= sm2.STRONG_REPETITIONS

        topics = []
        for slug, label in TOPIC_CHOICES:
            topic_total = VocabItem.objects.filter(
                language=language, topic=slug).count()
            topic_started = [s for s in started if s.item.topic == slug]
            topics.append({
                'id': slug,
                'label': label,
                'total': topic_total,
                'started': len(topic_started),
                'strong': sum(1 for s in topic_started if is_strong(s)),
            })

        answered = list(
            Turn.objects.filter(
                session__user=user, session__language=language,
                answered_at__isnull=False,
            )
            .select_related('session')
            .only('answered_at', 'was_correct', 'feedback_en', 'session__started_at')
        )

        # --- streak -----------------------------------------------------
        active_days = {timezone.localtime(t.answered_at).date() for t in answered}
        streak = streak_from(active_days, today)

        # --- this week against last week --------------------------------
        week_start = today - timedelta(days=6)
        prev_start = today - timedelta(days=13)

        def window(start, end):
            return [t for t in answered if start <= t.answered_at.date() <= end]

        this_week = window(week_start, today)
        prev_week = window(prev_start, week_start - timedelta(days=1))

        def accuracy_of(turns):
            graded = [t for t in turns if t.was_correct is not None]
            if not graded:
                return None
            return round(sum(1 for t in graded if t.was_correct) / len(graded), 3)

        # Practice time is measured from when a session opened to its last
        # answer, which is real elapsed time rather than a turn count guess.
        by_session = {}
        for turn in answered:
            key = turn.session_id
            current = by_session.get(key)
            if current is None or turn.answered_at > current[1]:
                by_session[key] = (turn.session.started_at, turn.answered_at)
        practice_seconds = sum(
            max(0, int((last - start).total_seconds()))
            for start, last in by_session.values()
            if last.date() >= week_start
        )

        # --- daily calendar ---------------------------------------------
        per_day = {}
        for turn in answered:
            per_day[turn.answered_at.date()] = per_day.get(turn.answered_at.date(), 0) + 1
        calendar = [
            {
                'date': (today - timedelta(days=offset)).isoformat(),
                'answers': per_day.get(today - timedelta(days=offset), 0),
            }
            for offset in range(27, -1, -1)
        ]

        # --- hardest words ----------------------------------------------
        # Lapses first: a word forgotten after being known is a sharper
        # signal than one simply answered wrong on a first attempt.
        hardest = sorted(
            (s for s in started if s.lapses or (s.accuracy or 1) < 0.6),
            key=lambda s: (-s.lapses, s.accuracy if s.accuracy is not None else 1),
        )[:5]

        return Response({
            # Scoped like everything else on this screen. Counting all four
            # languages reported "42 of 240" directly above a by-topic
            # breakdown that added up to 42 of 60.
            'vocabulary_total': VocabItem.objects.filter(
                language=language).count(),
            'words_started': len(started),
            'words_strong': sum(1 for state in started if is_strong(state)),
            'words_due_today': sum(
                1 for state in started if state.due_date <= today),
            'total_reviews': reviews,
            'total_correct': correct,
            'total_lapses': lapses,
            'accuracy': round(correct / reviews, 3) if reviews else None,
            'lessons_completed': ConversationSession.objects.filter(
                user=user, is_complete=True).count(),
            'topics': topics,

            'streak_days': streak,
            'practised_today': today in active_days,
            'practice_seconds_this_week': practice_seconds,
            'answers_this_week': len(this_week),
            'accuracy_this_week': accuracy_of(this_week),
            'accuracy_last_week': accuracy_of(prev_week),
            'calendar': calendar,
            'hardest_words': [
                {
                    'id': state.item_id,
                    'term': state.item.term,
                    'english': state.item.english,
                    'lapses': state.lapses,
                    'accuracy': round(state.accuracy, 2)
                    if state.accuracy is not None else None,
                }
                for state in hardest
            ],
            'grammar': insights.grammar_breakdown(
                [t.feedback_en for t in this_week if t.was_correct is False],
                [t.feedback_en for t in prev_week if t.was_correct is False],
            ),
        })


class StartSessionView(APIView):
    """POST /api/sessions/start/ - begin a session and return the first turn."""

    def post(self, request):
        topic = str(request.data.get('topic') or '').strip()
        if topic not in TOPIC_SLUGS:
            return Response(
                {'detail': f'Unknown topic {topic!r}. Expected one of {TOPIC_SLUGS}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = current_learner(request)
        language = learner_language(user)

        # Optional: the word the learner asked for by name, from its detail
        # screen. Scoped to this topic and language so a stale or hand-typed
        # id cannot smuggle a word from elsewhere into the plan.
        first_item = None
        word_id = request.data.get('word_id')
        if word_id not in (None, ''):
            first_item = VocabItem.objects.filter(
                pk=word_id, topic=topic, language=language).first()
            if first_item is None:
                return Response(
                    {'detail': f'Word {word_id!r} is not in {topic!r} for {language}.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        turn_limit = settings.SESSION_TURN_LIMIT
        if settings.DEMO_MODE:
            # The canned bank wraps, so a longer session would replay the same
            # questions. Better a short demo than a visibly repeating one.
            turn_limit = min(turn_limit, llm.demo_bank_size(topic, language))

        items = sm2.select_session_items(
            user, topic, limit=turn_limit, language=language,
            first_item=first_item)
        # Never plan more turns than there is vocabulary to drill. Otherwise
        # the tail of the session has no target item, so those turns grade
        # nothing and the recap silently under-reports.
        turn_limit = min(turn_limit, len(items))
        if not items:
            return Response(
                {'detail': f'No {language} vocabulary seeded for {topic!r}. '
                           f'Run: python manage.py seed_vocab'},
                status=status.HTTP_409_CONFLICT,
            )

        # Called before opening the transaction so a slow provider doesn't hold
        # a write lock for the length of a network round trip.
        result = llm.get_next_turn(
            topic, language, due_items=[items[0]], history=[], turn_index=0)

        with transaction.atomic():
            session = ConversationSession.objects.create(
                user=user,
                topic=topic,
                language=language,
                turn_limit=turn_limit,
                planned_item_ids=[item.pk for item in items],
            )
            session.target_items.set(items)
            turn = _create_turn(session, 0, items[0], result)

        return Response(
            {
                'session_id': session.pk,
                'topic': session.topic,
                'turn_limit': session.turn_limit,
                # Null for an ordinary lesson off the home screen.
                'focus_word': _focus_word_payload(first_item),
                'turn': TurnSerializer(turn).data,
            },
            status=status.HTTP_201_CREATED,
        )


class NextTurnView(APIView):
    """POST /api/sessions/<id>/next/ - grade an answer, return the next turn.

    Body is either ``{"mode": "chip", "reply_id": 0}`` or
    ``{"mode": "freetext", "text": "..."}``. Mode defaults to chip.
    """

    def post(self, request, session_id):
        user = current_learner(request)
        session = get_object_or_404(ConversationSession, pk=session_id, user=user)

        if session.is_complete:
            return Response(
                {'detail': 'This session is already complete.'},
                status=status.HTTP_409_CONFLICT,
            )

        current = (
            session.turns.filter(answered_at__isnull=True)
            .order_by('index')
            .first()
        )
        if current is None:
            return Response(
                {'detail': 'Every turn in this session has been answered.'},
                status=status.HTTP_409_CONFLICT,
            )

        mode = str(request.data.get('mode') or Turn.MODE_CHIP).strip().lower()
        if mode == Turn.MODE_CHIP:
            graded = self._grade_chip(request, current)
        elif mode == Turn.MODE_FREETEXT:
            graded = self._grade_freetext(request, current, session)
        else:
            return Response(
                {'detail': f'Unknown mode {mode!r}. Expected "chip" or "freetext".'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if isinstance(graded, Response):
            return graded

        sm2_result = self._record(user, current, mode, graded)

        answered = session.turns.filter(answered_at__isnull=False).count()
        finished = answered >= session.turn_limit

        next_turn = None
        if finished:
            session.is_complete = True
            session.ended_at = timezone.now()
            session.save(update_fields=['is_complete', 'ended_at'])
        else:
            next_index = current.index + 1
            target = session.target_for_index(next_index)
            # A free-text evaluation already returned a continuation, so reuse
            # it instead of paying for a second call.
            result = graded.get('continuation') or llm.get_next_turn(
                session.topic,
                session.language,
                due_items=[target] if target else [],
                history=_history(session),
                turn_index=next_index,
            )
            next_turn = _create_turn(session, next_index, target, result)

        return Response({
            'session_id': session.pk,
            'grade': {
                'was_correct': graded['was_correct'],
                'graded': graded['graded'],
                'quality': graded['quality'],
                'feedback_en': graded['feedback_en'],
                'corrected': graded['corrected'],
                'interval_days': sm2_result.interval_days if sm2_result else None,
                'due_date': sm2_result.due_date if sm2_result else None,
            },
            'is_complete': finished,
            'turn': TurnSerializer(next_turn).data if next_turn else None,
        })

    def _grade_chip(self, request, current):
        """Grade a tapped chip against the stored answer key."""
        reply_id = request.data.get('reply_id')
        chips = current.suggested_replies or []
        chosen = next(
            (chip for chip in chips if chip.get('id') == reply_id), None)
        if chosen is None:
            available = [chip.get('id') for chip in chips]
            return Response(
                {'detail': f'reply_id {reply_id!r} is not an option on this '
                           f'turn. Available: {available}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Server-side truth. The request only says *which* chip, never whether
        # it was right.
        was_correct = bool(chosen.get('is_correct'))
        return {
            'graded': True,
            'was_correct': was_correct,
            'quality': sm2.quality_for_chip(was_correct),
            'user_reply': chosen.get('text', ''),
            'feedback_en': '' if was_correct else chosen.get('why_wrong', ''),
            'corrected': '' if was_correct else _correct_option(chips),
            'continuation': None,
        }

    def _grade_freetext(self, request, current, session):
        text = str(request.data.get('text') or '').strip()
        evaluation = llm.evaluate_freetext_reply(
            session.topic,
            session.language,
            current.target_item,
            text,
            history=_history(session),
            turn_index=current.index,
        )

        if evaluation['graded']:
            quality = sm2.quality_for_freetext(evaluation['verdict'])
            was_correct = quality >= sm2.PASSING_QUALITY
        else:
            # The provider failed. Record the answer but grade nothing - see
            # the note in llm.evaluate_freetext_reply.
            quality = None
            was_correct = None

        return {
            'graded': evaluation['graded'],
            'was_correct': was_correct,
            'quality': quality,
            'user_reply': text,
            'feedback_en': evaluation['feedback_en'],
            'corrected': evaluation['corrected'],
            'continuation': evaluation,
        }

    def _record(self, user, current, mode, graded):
        """Persist the answer and, if it was graded, run the SM-2 update."""
        with transaction.atomic():
            current.user_reply = graded['user_reply']
            current.reply_mode = mode
            current.was_correct = graded['was_correct']
            current.sm2_quality = graded['quality']
            current.feedback_en = graded['feedback_en']
            current.corrected = graded['corrected']
            current.answered_at = timezone.now()
            current.save()

            if not graded['graded'] or not current.target_item_id:
                return None

            state, _ = UserVocabState.objects.get_or_create(
                user=user, item_id=current.target_item_id)
            result = sm2.apply_review(state, graded['quality'])
            state.save()
            return result


class SessionRecapView(APIView):
    """GET /api/sessions/<id>/recap/ - what was practised and when it's next due."""

    def get(self, request, session_id):
        user = current_learner(request)
        session = get_object_or_404(ConversationSession, pk=session_id, user=user)

        answered = list(
            session.turns.filter(answered_at__isnull=False)
            .select_related('target_item')
            .order_by('index')
        )
        graded = [turn for turn in answered if turn.sm2_quality is not None]
        correct = [turn for turn in graded if turn.was_correct]

        # Keyed on what the turns actually drilled, not session.target_items.
        # The plan is what the scheduler queued; _resolve_target can land on a
        # different word, and the recap must report the schedule for the words
        # the learner really saw.
        practised_ids = [
            turn.target_item_id for turn in answered if turn.target_item_id
        ]
        states = {
            state.item_id: state
            for state in UserVocabState.objects.filter(
                user=user, item_id__in=practised_ids
            )
        }

        words = []
        seen = set()
        for turn in answered:
            item = turn.target_item
            if item is None or item.pk in seen:
                continue
            seen.add(item.pk)
            state = states.get(item.pk)
            words.append({
                # Carried so the recap can link a word back to its own page,
                # and can pick out the one the lesson was opened for.
                'id': item.pk,
                'term': item.term,
                # Blank for the Latin-script languages, so the recap only
                # shows a second line where there is one to show.
                'romanisation': item.romanisation,
                'language': item.language,
                'english': item.english,
                'was_correct': turn.was_correct,
                'graded': turn.sm2_quality is not None,
                'due_date': state.due_date if state else None,
                'interval_days': state.interval_days if state else None,
                'repetitions': state.repetitions if state else None,
                'ease_factor': round(state.ease_factor, 2) if state else None,
            })

        return Response({
            'session_id': session.pk,
            'topic': session.topic,
            'topic_label': session.get_topic_display(),
            'is_complete': session.is_complete,
            'started_at': session.started_at,
            'ended_at': session.ended_at,
            'turns_answered': len(answered),
            'turns_graded': len(graded),
            'turns_correct': len(correct),
            'accuracy': round(len(correct) / len(graded), 2) if graded else None,
            'words_practiced': len(words),
            'words': words,
        })
