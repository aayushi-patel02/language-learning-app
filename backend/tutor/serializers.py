from rest_framework import serializers

from .models import Turn


class TurnSerializer(serializers.ModelSerializer):
    """One tutor turn as the frontend sees it.

    Field names are the ones the React client expects (`ai_message`,
    `reply_options`) rather than the model's internal names.
    """

    ai_message = serializers.CharField(source='tutor_message_es', read_only=True)
    ai_message_en = serializers.CharField(source='tutor_message_en', read_only=True)
    reply_options = serializers.SerializerMethodField()
    target_word = serializers.SerializerMethodField()

    class Meta:
        model = Turn
        fields = [
            'id',
            'index',
            'ai_message',
            'ai_message_en',
            'reply_options',
            'sentence_starter',
            'target_word',
        ]

    def get_reply_options(self, turn):
        """The tappable chips, stripped of the answer key.

        `is_correct` and `why_wrong` are deliberately withheld: they are on the
        stored turn so grading happens server-side, and shipping them would put
        the correct answer in the browser's network tab.
        """
        return [
            {
                'id': reply.get('id', position),
                'es': reply.get('es', ''),
                'en': reply.get('en', ''),
            }
            for position, reply in enumerate(turn.suggested_replies or [])
        ]

    def get_target_word(self, turn):
        return turn.target_item.spanish if turn.target_item_id else ''


class GradeSerializer(serializers.Serializer):
    """The verdict on a single answer, returned alongside the next turn."""

    was_correct = serializers.BooleanField(allow_null=True)
    graded = serializers.BooleanField()
    quality = serializers.IntegerField(allow_null=True)
    feedback_en = serializers.CharField(allow_blank=True)
    corrected_es = serializers.CharField(allow_blank=True)
    interval_days = serializers.IntegerField(allow_null=True)
    due_date = serializers.DateField(allow_null=True)
