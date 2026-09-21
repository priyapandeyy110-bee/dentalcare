from django.contrib import admin

from .models import Appointment, DentistAvailability, TimeOff


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ("reference", "patient", "dentist", "scheduled_for", "reason", "status")
    list_filter = ("status", "reason", "dentist")
    search_fields = ("reference", "patient__user__first_name", "patient__patient_code")
    date_hierarchy = "scheduled_for"
    readonly_fields = ("reference", "created_at", "updated_at")


@admin.register(DentistAvailability)
class DentistAvailabilityAdmin(admin.ModelAdmin):
    list_display = ("dentist", "weekday", "start_time", "end_time", "is_active")
    list_filter = ("weekday", "is_active", "dentist")


@admin.register(TimeOff)
class TimeOffAdmin(admin.ModelAdmin):
    list_display = ("dentist", "start_date", "end_date", "reason")
    list_filter = ("dentist",)
