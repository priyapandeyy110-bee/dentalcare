from django.contrib import admin

from .models import DentalHistoryEntry, Prescription, PrescriptionItem, Treatment


class PrescriptionItemInline(admin.TabularInline):
    model = PrescriptionItem
    extra = 1


@admin.register(Treatment)
class TreatmentAdmin(admin.ModelAdmin):
    list_display = ("patient", "dentist", "procedure", "treatment_date", "status", "cost")
    list_filter = ("procedure", "status", "treatment_date")
    search_fields = ("patient__user__first_name", "patient__patient_code", "diagnosis")
    date_hierarchy = "treatment_date"


@admin.register(Prescription)
class PrescriptionAdmin(admin.ModelAdmin):
    list_display = ("id", "patient", "dentist", "issued_on")
    list_filter = ("issued_on", "dentist")
    inlines = [PrescriptionItemInline]


@admin.register(DentalHistoryEntry)
class DentalHistoryEntryAdmin(admin.ModelAdmin):
    list_display = ("patient", "category", "title", "recorded_on")
    list_filter = ("category",)
    search_fields = ("title", "description", "patient__patient_code")
