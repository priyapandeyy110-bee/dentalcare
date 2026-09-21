from django import forms

from accounts.forms import BootstrapMixin

from .models import SymptomAnalysis


class ChatMessageForm(BootstrapMixin, forms.Form):
    """Used for the no-JavaScript fallback of the chat page."""

    message = forms.CharField(
        max_length=2000,
        widget=forms.TextInput(attrs={
            "placeholder": "Ask about teeth, gums, or your appointment...",
            "autocomplete": "off",
        }),
        label="",
    )

    def clean_message(self):
        message = self.cleaned_data["message"].strip()
        if not message:
            raise forms.ValidationError("Type a question first.")
        return message


class SymptomCheckerForm(BootstrapMixin, forms.Form):
    """Preliminary symptom checker input (synopsis 6.2)."""

    symptoms = forms.MultipleChoiceField(
        choices=SymptomAnalysis.SYMPTOM_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Which of these apply?",
    )
    description = forms.CharField(
        widget=forms.Textarea(attrs={
            "rows": 4,
            "placeholder": "For example: sharp pain in my lower right back tooth when "
                           "I drink something cold, started three days ago.",
        }),
        required=False,
        label="Describe it in your own words",
    )
    pain_level = forms.TypedChoiceField(
        choices=SymptomAnalysis.PAIN_LEVEL_CHOICES,
        coerce=int,
        initial=0,
        label="Pain right now (0 = none, 10 = worst imaginable)",
    )
    duration = forms.ChoiceField(
        choices=SymptomAnalysis.DURATION_CHOICES,
        initial="days",
        label="How long has this been going on?",
    )
    has_swelling = forms.BooleanField(
        required=False, label="I have swelling in my face, gum or jaw"
    )
    has_fever = forms.BooleanField(required=False, label="I have a fever")
    difficulty_swallowing = forms.BooleanField(
        required=False, label="I have difficulty swallowing or breathing"
    )
    consent = forms.BooleanField(
        required=True,
        label="I understand this is preliminary guidance, not a diagnosis, and that "
              "only a dentist can diagnose my problem.",
    )

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("symptoms") and not (cleaned.get("description") or "").strip():
            raise forms.ValidationError(
                "Select at least one symptom, or describe what you are experiencing."
            )
        return cleaned

    def to_payload(self):
        data = self.cleaned_data
        return {
            "symptoms": data.get("symptoms") or [],
            "description": data.get("description", ""),
            "pain_level": data.get("pain_level", 0),
            "duration": data.get("duration", "days"),
            "has_swelling": data.get("has_swelling", False),
            "has_fever": data.get("has_fever", False),
            "difficulty_swallowing": data.get("difficulty_swallowing", False),
        }
