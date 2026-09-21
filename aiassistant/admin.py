from django.contrib import admin

from .models import AIMessage, AIQueryLog, CarePlan, Conversation, SymptomAnalysis


class AIMessageInline(admin.TabularInline):
    model = AIMessage
    extra = 0
    readonly_fields = ("role", "content", "provider", "created_at")


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "updated_at", "is_archived")
    list_filter = ("is_archived",)
    search_fields = ("title", "user__username")
    inlines = [AIMessageInline]


@admin.register(SymptomAnalysis)
class SymptomAnalysisAdmin(admin.ModelAdmin):
    list_display = ("user", "urgency", "pain_level", "provider", "reviewed_by_dentist", "created_at")
    list_filter = ("urgency", "reviewed_by_dentist", "is_fallback")
    search_fields = ("user__username", "summary", "description")
    readonly_fields = ("created_at",)


@admin.register(CarePlan)
class CarePlanAdmin(admin.ModelAdmin):
    list_display = ("patient", "generated_for", "provider", "is_fallback")
    list_filter = ("is_fallback",)


@admin.register(AIQueryLog)
class AIQueryLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at", "feature", "provider", "user", "input_tokens",
        "output_tokens", "latency_ms", "succeeded",
    )
    list_filter = ("feature", "provider", "succeeded")
    search_fields = ("prompt_excerpt", "response_excerpt", "error_message")
    readonly_fields = [f.name for f in AIQueryLog._meta.fields]
