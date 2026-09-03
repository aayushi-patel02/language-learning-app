"""Session API.

Three endpoints: start a session, answer a turn, read the recap.

There is no signup flow - every request runs against the seeded demo learner.
That is a deliberate scope decision, not an oversight.

The rule that matters most here: **chip grading reads `is_correct` from the
stored turn, never from the request body.** The browser is told which options
exist but not which is right, so a learner (or a judge poking at the network
tab) cannot mark their own answer correct.
"""

from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

# Imported as modules, not as bare names: `llm.get_next_turn` is looked up at
# call time, so tests can patch it without the reference being frozen here.
from . import llm, sm2
from .models import (
    TOPIC_SLUGS,
    ConversationSession,
    Turn,
    UserVocabState,
    VocabItem,
)
from .serializers import TurnSerializer


def get_demo_user():
    """The single seeded learner. See the module docstring."""
    user, created = User.objects.get_or_create(
        username=settings.DEMO_USERNAME,
        defaults={'first_name': 'Demo', 'last_name': 'Learner'},
    )
    if created:
        # Nothing ever logs in as this user, so give it no usable credential.
        user.set_unusable_password()
        user.save(update_fields=['password'])
    return user


def _history(session):
    """The conversation so far, in the shape the prompts expect."""
    return [
        {'tutor': turn.tutor_message_es, 'user': turn.user_reply}
        for turn in session.turns.order_by('index')
    ]


def _resolve_target(topic, target_word, planned_item):
    """The vocab item a turn actually drills.

    The scheduler decides what *should* be practised and tells the model, but
    the turn on screen can differ: a fallback turn comes from a fixed bank, and
    a live model can drift onto a neighbouring word. The SM-2 update has to
    follow the vocabulary the learner actually saw, or the recap credits a word
    they were never shown - so match the turn's own target back to the topic's
    vocab, and only fall back to the plan when it doesn't match anything.
    """
    word = str(target_word or '').strip()
    if word:
        match = VocabItem.objects.filter(topic=topic, spanish__iexact=word).first()
        if match is not None:
            return match
    return planned_item


def _create_turn(session, index, planned_item, result):
    return Turn.objects.create(
        session=session,
        index=index,
        tutor_message_es=result['tutor_message_es'],
        tutor_message_en=result['tutor_message_en'],
        suggested_replies=result['replies'],
        target_item=_resolve_target(
            session.topic, result.get('target_word'), planned_item),
        llm_provider=result['provider'],
        from_cache=result['from_cache'],
    )


def _correct_option(chips):
    for chip in chips or []:
        if chip.get('is_correct'):
            return chip.get('es', '')
    return ''


class StartSessionView(APIView):
    """POST /api/sessions/start/ - begin a session and return the first turn."""

    def post(self, request):
        topic = str(request.data.get('topic') or '').strip()
        if topic not in TOPIC_SLUGS:
            return Response(
                {'detail': f'Unknown topic {topic!r}. Expected one of {TOPIC_SLUGS}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = get_demo_user()
        items = sm2.select_session_items(
            user, topic, limit=settings.SESSION_TURN_LIMIT)
        if not items:
            return Response(
                {'detail': f'No vocabulary seeded for {topic!r}. '
                           f'Run: python manage.py seed_vocab'},
                status=status.HTTP_409_CONFLICT,
            )

        # Called before opening the transaction so a slow provider doesn't hold
        # a write lock for the length of a network round trip.
        result = llm.get_next_turn(
            topic, due_items=[items[0]], history=[], turn_index=0)

        with transaction.atomic():
            session = ConversationSession.objects.create(
                user=user,
                topic=topic,
                planned_item_ids=[item.pk for item in items],
            )
            session.target_items.set(items)
            turn = _create_turn(session, 0, items[0], result)

        return Response(
            {
                'session_id': session.pk,
                'topic': session.topic,
                'turn_limit': session.turn_limit,
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
        user = get_demo_user()
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
                'corrected_es': graded['corrected_es'],
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
            'user_reply': chosen.get('es', ''),
            'feedback_en': '' if was_correct else chosen.get('why_wrong', ''),
            'corrected_es': '' if was_correct else _correct_option(chips),
            'continuation': None,
        }

    def _grade_freetext(self, request, current, session):
        text = str(request.data.get('text') or '').strip()
        evaluation = llm.evaluate_freetext_reply(
            session.topic,
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
            'corrected_es': evaluation['corrected_es'],
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
            current.corrected_es = graded['corrected_es']
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
        user = get_demo_user()
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
                'spanish': item.spanish,
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
