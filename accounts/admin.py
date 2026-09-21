from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import DentistProfile, PatientProfile, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "get_full_name", "email", "role", "phone", "is_active")
    list_filter = ("role", "is_active", "is_staff")
    search_fields = ("username", "first_name", "last_name", "email", "phone")
    fieldsets = BaseUserAdmin.fieldsets + (
        ("Clinic details", {"fields": ("role", "phone", "address", "date_of_birth")}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ("Clinic details", {"fields": ("role", "phone")}),
    )


@admin.register(PatientProfile)
class PatientProfileAdmin(admin.ModelAdmin):
    list_display = ("patient_code", "user", "gender", "blood_group", "is_smoker")
    list_filter = ("gender", "blood_group", "is_smoker")
    search_fields = ("patient_code", "user__first_name", "user__last_name", "user__phone")
    readonly_fields = ("patient_code", "created_at", "updated_at")


@admin.register(DentistProfile)
class DentistProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user", "registration_number", "specialization", "experience_years",
        "consultation_fee", "is_accepting_patients",
    )
    list_filter = ("specialization", "is_accepting_patients")
    search_fields = ("user__first_name", "user__last_name", "registration_number")
