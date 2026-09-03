"""Tests for the SM-2 scheduler.

The expected numbers here are computed by hand from Wozniak's formulas rather
than captured from this implementation's own output, so they would catch the
implementation drifting.
"""

from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase

from . import sm2
from .models import UserVocabState, VocabItem

TODAY = date(2026, 9, 3)


class EaseFactorTests(TestCase):
    """EF' = EF + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))"""

    def test_ease_factor_adjustment_for_each_grade(self):
        # Hand-computed from EF = 2.5:
        #   q=5: 0.1 - 0*(0.08+0.00) = +0.10
        #   q=4: 0.1 - 1*(0.08+0.02) =  0.00
        #   q=3: 0.1 - 2*(0.08+0.04) = -0.14
        #   q=2: 0.1 - 3*(0.08+0.06) = -0.32
        #   q=1: 0.1 - 4*(0.08+0.08) = -0.54
        #   q=0: 0.1 - 5*(0.08+0.10) = -0.80
        expected = {5: 2.6, 4: 2.5, 3: 2.36, 2: 2.18, 1: 1.96, 0: 1.7}
        for quality, ease in expected.items():
            with self.subTest(quality=quality):
                self.assertAlmostEqual(
                    sm2.next_ease_factor(2.5, quality), ease, places=4
                )

    def test_perfect_grade_raises_ease_factor(self):
        self.assertGreater(sm2.next_ease_factor(2.5, 5), 2.5)

    def test_grade_of_four_leaves_ease_factor_unchanged(self):
        self.assertAlmostEqual(sm2.next_ease_factor(2.5, 4), 2.5, places=4)

    def test_ease_factor_never_falls_below_floor(self):
        ease = 2.5
        for _ in range(10):
            ease = sm2.next_ease_factor(ease, 0)
        self.assertEqual(ease, sm2.MIN_EASE_FACTOR)

    def test_floor_is_reached_not_crossed(self):
        # 2.5 -> 1.7 -> (0.9 clamped) 1.3
        self.assertAlmostEqual(sm2.next_ease_factor(2.5, 0), 1.7, places=4)
        self.assertAlmostEqual(sm2.next_ease_factor(1.7, 0), 1.3, places=4)


class IntervalProgressionTests(TestCase):
    """I(1) = 1, I(2) = 6, I(n) = I(n-1) * EF"""

    def test_first_success_schedules_one_day_out(self):
        result = sm2.review(repetitions=0, ease_factor=2.5, interval_days=0,
                            quality=4, today=TODAY)
        self.assertEqual(result.interval_days, 1)
        self.assertEqual(result.repetitions, 1)
        self.assertEqual(result.due_date, TODAY + timedelta(days=1))

    def test_second_success_schedules_six_days_out(self):
        result = sm2.review(repetitions=1, ease_factor=2.5, interval_days=1,
                            quality=4, today=TODAY)
        self.assertEqual(result.interval_days, 6)
        self.assertEqual(result.repetitions, 2)
        self.assertEqual(result.due_date, TODAY + timedelta(days=6))

    def test_later_successes_multiply_by_ease_factor(self):
        # 6 * 2.5 = 15
        result = sm2.review(repetitions=2, ease_factor=2.5, interval_days=6,
                            quality=4, today=TODAY)
        self.assertEqual(result.interval_days, 15)
        self.assertEqual(result.repetitions, 3)

    def test_full_progression_at_grade_four(self):
        # A grade of 4 holds EF at 2.5, so intervals are 1, 6, 15, 38, 95.
        expected_intervals = [1, 6, 15, 38, 95]
        repetitions, ease, interval = 0, 2.5, 0
        for expected in expected_intervals:
            result = sm2.review(repetitions=repetitions, ease_factor=ease,
                                interval_days=interval, quality=4, today=TODAY)
            self.assertEqual(result.interval_days, expected)
            self.assertAlmostEqual(result.ease_factor, 2.5, places=4)
            repetitions, ease, interval = (
                result.repetitions, result.ease_factor, result.interval_days
            )

    def test_interval_uses_ease_factor_from_before_the_update(self):
        # A perfect grade raises EF to 2.6, but this interval must still use
        # the old 2.5: 6 * 2.5 = 15, not 6 * 2.6 = 16.
        result = sm2.review(repetitions=2, ease_factor=2.5, interval_days=6,
                            quality=5, today=TODAY)
        self.assertEqual(result.interval_days, 15)
        self.assertAlmostEqual(result.ease_factor, 2.6, places=4)

    def test_rounding_is_half_up_not_bankers(self):
        # 15 * 2.5 = 37.5. Python's round() would give 38 here but 2 for
        # round(2.5); half-up rounding is the predictable choice.
        result = sm2.review(repetitions=3, ease_factor=2.5, interval_days=15,
                            quality=4, today=TODAY)
        self.assertEqual(result.interval_days, 38)

    def test_low_ease_factor_never_shrinks_interval_below_one_day(self):
        result = sm2.review(repetitions=5, ease_factor=1.3, interval_days=0,
                            quality=4, today=TODAY)
        self.assertGreaterEqual(result.interval_days, 1)


class LapseTests(TestCase):
    def test_failure_resets_repetitions_and_interval(self):
        result = sm2.review(repetitions=6, ease_factor=2.5, interval_days=95,
                            quality=2, today=TODAY)
        self.assertEqual(result.repetitions, 0)
        self.assertEqual(result.interval_days, 1)
        self.assertEqual(result.due_date, TODAY + timedelta(days=1))
        self.assertFalse(result.passed)

    def test_failure_also_penalises_the_ease_factor(self):
        result = sm2.review(repetitions=6, ease_factor=2.5, interval_days=95,
                            quality=2, today=TODAY)
        self.assertAlmostEqual(result.ease_factor, 2.18, places=4)

    def test_grade_three_passes_and_grade_two_fails(self):
        passing = sm2.review(repetitions=1, ease_factor=2.5, interval_days=1,
                             quality=3, today=TODAY)
        failing = sm2.review(repetitions=1, ease_factor=2.5, interval_days=1,
                             quality=2, today=TODAY)
        self.assertTrue(passing.passed)
        self.assertEqual(passing.interval_days, 6)
        self.assertFalse(failing.passed)
        self.assertEqual(failing.interval_days, 1)


class QualityValidationTests(TestCase):
    def test_out_of_range_grades_are_rejected(self):
        for bad in (-1, 6, 100):
            with self.subTest(quality=bad):
                with self.assertRaises(ValueError):
                    sm2.review(repetitions=0, ease_factor=2.5,
                               interval_days=0, quality=bad, today=TODAY)

    def test_non_integer_grades_are_rejected(self):
        for bad in (3.5, '4', None):
            with self.subTest(quality=bad):
                with self.assertRaises(TypeError):
                    sm2.review(repetitions=0, ease_factor=2.5,
                               interval_days=0, quality=bad, today=TODAY)


class GradingHelperTests(TestCase):
    def test_chip_grades(self):
        self.assertEqual(sm2.quality_for_chip(True), 4)
        self.assertEqual(sm2.quality_for_chip(False), 2)

    def test_correct_chip_passes_and_wrong_chip_fails(self):
        self.assertGreaterEqual(sm2.quality_for_chip(True), sm2.PASSING_QUALITY)
        self.assertLess(sm2.quality_for_chip(False), sm2.PASSING_QUALITY)

    def test_freetext_verdicts_map_to_grades(self):
        self.assertEqual(sm2.quality_for_freetext('perfect'), 5)
        self.assertEqual(sm2.quality_for_freetext('minor'), 4)
        self.assertEqual(sm2.quality_for_freetext('awkward'), 3)
        self.assertEqual(sm2.quality_for_freetext('wrong'), 1)
        self.assertEqual(sm2.quality_for_freetext('blank'), 0)

    def test_freetext_verdict_is_case_and_space_insensitive(self):
        self.assertEqual(sm2.quality_for_freetext('  PERFECT '), 5)

    def test_unknown_freetext_verdict_degrades_instead_of_raising(self):
        # A malformed LLM response must not break the turn.
        for bad in ('excellent', '', None, 'null'):
            with self.subTest(verdict=bad):
                self.assertEqual(sm2.quality_for_freetext(bad), 1)


class ApplyReviewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='learner')
        self.item = VocabItem.objects.create(
            spanish='desayunar', english='to have breakfast',
            topic='daily_routine',
        )
        self.state = UserVocabState.objects.create(user=self.user, item=self.item)

    def test_successful_review_updates_state_and_counters(self):
        sm2.apply_review(self.state, 4, today=TODAY)
        self.state.save()
        self.state.refresh_from_db()

        self.assertEqual(self.state.repetitions, 1)
        self.assertEqual(self.state.interval_days, 1)
        self.assertEqual(self.state.due_date, TODAY + timedelta(days=1))
        self.assertEqual(self.state.total_reviews, 1)
        self.assertEqual(self.state.correct_reviews, 1)
        self.assertEqual(self.state.lapses, 0)
        self.assertEqual(self.state.last_quality, 4)
        self.assertIsNotNone(self.state.last_reviewed_at)
        self.assertFalse(self.state.is_new)
        self.assertEqual(self.state.accuracy, 1.0)

    def test_failing_a_brand_new_item_is_not_counted_as_a_lapse(self):
        # Never having known a word is not the same as forgetting it.
        sm2.apply_review(self.state, 2, today=TODAY)
        self.assertEqual(self.state.lapses, 0)
        self.assertEqual(self.state.total_reviews, 1)
        self.assertEqual(self.state.correct_reviews, 0)

    def test_forgetting_a_known_item_is_counted_as_a_lapse(self):
        sm2.apply_review(self.state, 4, today=TODAY)   # learn it
        sm2.apply_review(self.state, 1, today=TODAY)   # then forget it
        self.assertEqual(self.state.lapses, 1)
        self.assertEqual(self.state.repetitions, 0)
        self.assertEqual(self.state.total_reviews, 2)
        self.assertEqual(self.state.correct_reviews, 1)
        self.assertEqual(self.state.accuracy, 0.5)

    def test_accuracy_is_none_before_any_review(self):
        self.assertIsNone(self.state.accuracy)
        self.assertTrue(self.state.is_new)


class SchedulerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='learner')
        self.easy = VocabItem.objects.create(
            spanish='el pan', english='bread', topic='ordering_food', difficulty=1)
        self.hard = VocabItem.objects.create(
            spanish='soy alérgico a', english="I'm allergic to",
            topic='ordering_food', difficulty=3)
        self.other_topic = VocabItem.objects.create(
            spanish='el tren', english='train', topic='travel_basics')

    def test_ensure_states_creates_one_state_per_item_in_topic(self):
        states = sm2.ensure_states(self.user, 'ordering_food')
        self.assertEqual(states.count(), 2)
        self.assertEqual(
            UserVocabState.objects.filter(user=self.user).count(), 2)

    def test_ensure_states_is_idempotent(self):
        sm2.ensure_states(self.user, 'ordering_food')
        sm2.ensure_states(self.user, 'ordering_food')
        self.assertEqual(
            UserVocabState.objects.filter(user=self.user).count(), 2)

    def test_ensure_states_picks_up_vocab_added_later(self):
        sm2.ensure_states(self.user, 'ordering_food')
        VocabItem.objects.create(
            spanish='la cuenta', english='the bill', topic='ordering_food')
        self.assertEqual(sm2.ensure_states(self.user, 'ordering_food').count(), 3)

    def test_selection_is_scoped_to_the_requested_topic(self):
        items = sm2.select_session_items(self.user, 'ordering_food')
        self.assertNotIn(self.other_topic, items)
        self.assertEqual(len(items), 2)

    def test_new_items_are_introduced_easiest_first(self):
        items = sm2.select_session_items(self.user, 'ordering_food')
        self.assertEqual(items[0], self.easy)
        self.assertEqual(items[1], self.hard)

    def test_due_items_come_before_new_ones(self):
        sm2.ensure_states(self.user, 'ordering_food')
        overdue = UserVocabState.objects.get(user=self.user, item=self.hard)
        overdue.total_reviews = 1
        overdue.repetitions = 1
        overdue.due_date = date.today() - timedelta(days=3)
        overdue.save()

        items = sm2.select_session_items(self.user, 'ordering_food')
        self.assertEqual(items[0], self.hard, 'overdue review should outrank new vocab')

    def test_items_not_yet_due_come_last(self):
        sm2.ensure_states(self.user, 'ordering_food')
        scheduled = UserVocabState.objects.get(user=self.user, item=self.hard)
        scheduled.total_reviews = 1
        scheduled.repetitions = 2
        scheduled.due_date = date.today() + timedelta(days=30)
        scheduled.save()

        items = sm2.select_session_items(self.user, 'ordering_food')
        self.assertEqual(items[0], self.easy, 'unseen vocab should outrank a future review')
        self.assertEqual(items[-1], self.hard)

    def test_hardest_item_comes_first_among_those_due_the_same_day(self):
        sm2.ensure_states(self.user, 'ordering_food')
        yesterday = date.today() - timedelta(days=1)
        for item, ease in ((self.easy, 2.5), (self.hard, 1.4)):
            state = UserVocabState.objects.get(user=self.user, item=item)
            state.total_reviews = 1
            state.repetitions = 1
            state.ease_factor = ease
            state.due_date = yesterday
            state.save()

        items = sm2.select_session_items(self.user, 'ordering_food')
        self.assertEqual(items[0], self.hard, 'lower ease factor should be drilled first')

    def test_limit_caps_the_number_of_items(self):
        self.assertEqual(len(sm2.select_session_items(self.user, 'ordering_food', limit=1)), 1)

    def test_limit_defaults_to_the_configured_session_turn_limit(self):
        with self.settings(SESSION_TURN_LIMIT=1):
            self.assertEqual(len(sm2.select_session_items(self.user, 'ordering_food')), 1)
