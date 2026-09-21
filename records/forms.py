from django import forms
from django.forms import inlineformset_factory

from accounts.forms import BootstrapMixin

from .models import DentalHistoryEntry, Prescription, PrescriptionItem, Treatment


class TreatmentForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Treatment
        fields = (
            "treatment_date", "chief_complaint", "diagnosis", "procedure",
            "tooth_region", "tooth_numbers", "treatment_notes", "status",
            "cost", "follow_up_date", "follow_up_instructions",
        )
        widgets = {
            "treatment_date": forms.DateInput(attrs={"type": "date"}),
            "follow_up_date": forms.DateInput(attrs={"type": "date"}),
            "diagnosis": forms.Textarea(attrs={"rows": 3}),
            "treatment_notes": forms.Textarea(attrs={"rows": 3}),
            "follow_up_instructions": forms.Textarea(attrs={"rows": 2}),
        }
        help_texts = {
            "diagnosis": "Clinical findings and diagnosis. Shown to the patient.",
            "cost": "Charge for this procedure -- used when generating the bill.",
        }

    def clean(self):
        cleaned = super().clean()
        treatment_date = cleaned.get("treatment_date")
        follow_up = cleaned.get("follow_up_date")
        if treatment_date and follow_up and follow_up < treatment_date:
            self.add_error(
                "follow_up_date", "The follow-up cannot be before the treatment date."
            )
        return cleaned


class PrescriptionForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Prescription
        fields = ("issued_on", "advice")
        widgets = {
            "issued_on": forms.DateInput(attrs={"type": "date"}),
            "advice": forms.Textarea(attrs={"rows": 3}),
        }


class PrescriptionItemForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = PrescriptionItem
        fields = ("medicine_name", "dosage", "frequency", "duration", "instructions")


PrescriptionItemFormSet = inlineformset_factory(
    Prescription,
    PrescriptionItem,
    form=PrescriptionItemForm,
    extra=3,
    can_delete=True,
    min_num=1,
    validate_min=True,
)


class DentalHistoryForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = DentalHistoryEntry
        fields = ("category", "title", "description", "recorded_on")
        widgets = {
            "recorded_on": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 3}),
        }
