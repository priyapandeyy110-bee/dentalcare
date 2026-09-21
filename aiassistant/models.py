from django.db import models
from django.utils import timezone

from accounts.models import PatientProfile


class Conversation(models.Model):
    """A chat thread between one user and the AI dental assistant."""

    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="ai_conversations"
    )
    title = models.CharField(max_length=120, default="New conversation")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_archived = models.BooleanField(default=False)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return "%s - %s" % (self.user.display_name, self.title)

    @property
    def preview(self):
        first = self.messages.filter(role=MessageRole.USER).first()
        return first.content[:90] if first else "No messages yet"

    def touch(self):
        self.updated_at = timezone.now()
        self.save(update_fields=["updated_at"])


class MessageRole(models.TextChoices):
    USER = "user", "Patient / staff"
    ASSISTANT = "assistant", "AI assistant"


class AIMessage(models.Model):
    """One turn in a conversation. Stored so history survives page reloads."""

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    role = models.CharField(max_length=10, choices=MessageRole.choices)
    content = models.TextField()
    provider = models.CharField(
        max_length=30, blank=True, help_text="Which engine produced this answer."
    )
    model = models.CharField(max_length=60, blank=True)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    latency_ms = models.PositiveIntegerField(default=0)
    is_fallback = models.BooleanField(
        default=False, help_text="True when the offline rule engine answered."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["conversation", "created_at"])]

    def __str__(self):
        return "%s: %s" % (self.role, self.content[:60])


class UrgencyLevel(models.TextChoices):
    ROUTINE = "ROUTINE", "Routine - book at your convenience"
    SOON = "SOON", "See a dentist within a few days"
    URGENT = "URGENT", "Urgent - see a dentist within 24 hours"
    EMERGENCY = "EMERGENCY", "Emergency - seek care immediately"


URGENCY_CSS = {
    UrgencyLevel.ROUTINE: "success",
    UrgencyLevel.SOON: "info",
    UrgencyLevel.URGENT: "warning",
    UrgencyLevel.EMERGENCY: "danger",
}


class SymptomAnalysis(models.Model):
    """Result of the preliminary symptom checker (synopsis 6.2).

    Explicitly not a diagnosis -- every record carries the disclaimer shown
    to the patient, and a dentist always reviews before treatment.
    """

    SYMPTOM_CHOICES = [
        ("tooth_pain", "Tooth pain"),
        ("sensitivity", "Tooth sensitivity (hot / cold / sweet)"),
        ("gum_bleeding", "Bleeding gums"),
        ("swelling", "Swelling of face, gum or jaw"),
        ("bad_breath", "Persistent bad breath"),
        ("discoloration", "Tooth discoloration"),
        ("loose_tooth", "Loose or shifting tooth"),
        ("jaw_pain", "Jaw pain or clicking"),
        ("broken_tooth", "Broken or chipped tooth"),
        ("mouth_ulcer", "Mouth ulcer or sore"),
        ("dry_mouth", "Dry mouth"),
        ("bleeding_after_extraction", "Bleeding after an extraction"),
    ]

    PAIN_LEVEL_CHOICES = [(i, str(i)) for i in range(0, 11)]

    DURATION_CHOICES = [
        ("today", "Started today"),
        ("days", "A few days"),
        ("weeks", "A few weeks"),
        ("months", "Several months or longer"),
    ]

    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="symptom_analyses"
    )
    patient = models.ForeignKey(
        PatientProfile, on_delete=models.CASCADE, null=True, blank=True,
        related_name="symptom_analyses",
    )
    symptoms = models.JSONField(default=list)
    description = models.TextField(blank=True)
    pain_level = models.PositiveSmallIntegerField(default=0, choices=PAIN_LEVEL_CHOICES)
    duration = models.CharField(max_length=10, choices=DURATION_CHOICES, default="days")
    has_swelling = models.BooleanField(default=False)
    has_fever = models.BooleanField(default=False)
    difficulty_swallowing = models.BooleanField(default=False)

    urgency = models.CharField(
        max_length=10, choices=UrgencyLevel.choices, default=UrgencyLevel.ROUTINE
    )
    summary = models.TextField(blank=True)
    possible_areas = models.JSONField(default=list)
    self_care_advice = models.JSONField(default=list)
    red_flags = models.JSONField(default=list)
    recommended_within = models.CharField(max_length=60, blank=True)
    suggested_reason = models.CharField(max_length=20, blank=True)
    provider = models.CharField(max_length=30, blank=True)
    is_fallback = models.BooleanField(default=False)
    appointment = models.ForeignKey(
        "appointments.Appointment", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="symptom_analyses",
    )
    reviewed_by_dentist = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "Symptom analyses"

    def __str__(self):
        return "%s - %s (%s)" % (self.user.display_name, self.urgency, self.created_at.date())

    @property
    def urgency_css(self):
        return URGENCY_CSS.get(self.urgency, "secondary")

    @property
    def symptom_labels(self):
        mapping = dict(self.SYMPTOM_CHOICES)
        return [mapping.get(code, code) for code in self.symptoms or []]

    @property
    def needs_immediate_care(self):
        return self.urgency in (UrgencyLevel.URGENT, UrgencyLevel.EMERGENCY)


class CarePlan(models.Model):
    """Personalized preventive-care suggestions for one patient (synopsis 6.3)."""

    patient = models.ForeignKey(
        PatientProfile, on_delete=models.CASCADE, related_name="care_plans"
    )
    generated_for = models.DateField(default=timezone.localdate)
    headline = models.CharField(max_length=200, blank=True)
    daily_routine = models.JSONField(default=list)
    diet_tips = models.JSONField(default=list)
    warning_signs = models.JSONField(default=list)
    next_checkup_advice = models.CharField(max_length=200, blank=True)
    provider = models.CharField(max_length=30, blank=True)
    is_fallback = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return "Care plan for %s (%s)" % (self.patient.user.display_name, self.generated_for)


class AIQueryLog(models.Model):
    """Audit trail of every AI call -- the AI_Queries table from the synopsis."""

    FEATURE_CHOICES = [
        ("chat", "Dental assistant chat"),
        ("symptom", "Symptom analysis"),
        ("care_plan", "Care plan"),
        ("appointment_help", "Appointment assistance"),
        ("clinical_summary", "Clinical summary for dentist"),
    ]

    user = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, related_name="ai_queries"
    )
    feature = models.CharField(max_length=20, choices=FEATURE_CHOICES)
    provider = models.CharField(max_length=30)
    model = models.CharField(max_length=60, blank=True)
    prompt_excerpt = models.TextField(blank=True)
    response_excerpt = models.TextField(blank=True)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    latency_ms = models.PositiveIntegerField(default=0)
    succeeded = models.BooleanField(default=True)
    error_message = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "AI query log"
        verbose_name_plural = "AI query logs"

    def __str__(self):
        return "%s / %s at %s" % (self.feature, self.provider, self.created_at)
