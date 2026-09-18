from django.contrib import admin

from .models import ConversationSession, Turn, UserVocabState, VocabItem


@admin.register(VocabItem)
class VocabItemAdmin(admin.ModelAdmin):
    list_display = ['term', 'english', 'topic', 'difficulty', 'part_of_speech']
    list_filter = ['topic', 'difficulty', 'part_of_speech']
    search_fields = ['term', 'english']
    ordering = ['topic', 'difficulty', 'term']


@admin.register(UserVocabState)
class UserVocabStateAdmin(admin.ModelAdmin):
    list_display = [
        'user',
        'item',
        'due_date',
        'repetitions',
        'interval_days',
        'ease_factor',
        'total_reviews',
        'correct_reviews',
        'lapses',
    ]
    list_filter = ['user', 'due_date', 'item__topic']
    search_fields = ['item__term', 'item__english']
    autocomplete_fields = ['item']
    readonly_fields = ['last_reviewed_at']


class TurnInline(admin.TabularInline):
    model = Turn
    extra = 0
    fields = [
        'index',
        'tutor_message',
        'target_item',
        'user_reply',
        'reply_mode',
        'was_correct',
        'sm2_quality',
        'from_cache',
    ]
    readonly_fields = ['index', 'from_cache']
    ordering = ['index']


@admin.register(ConversationSession)
class ConversationSessionAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'topic', 'started_at', 'is_complete', 'turn_limit']
    list_filter = ['topic', 'is_complete', 'user']
    filter_horizontal = ['target_items']
    inlines = [TurnInline]
    readonly_fields = ['started_at']


@admin.register(Turn)
class TurnAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'session',
        'index',
        'target_item',
        'reply_mode',
        'was_correct',
        'sm2_quality',
        'llm_provider',
        'from_cache',
    ]
    list_filter = ['reply_mode', 'was_correct', 'from_cache', 'llm_provider']
    search_fields = ['tutor_message', 'user_reply']
    autocomplete_fields = ['target_item']
