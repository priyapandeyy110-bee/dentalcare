from django.conf import settings


def clinic_context(request):
    """Clinic branding + role flags available in every template."""
    user = getattr(request, "user", None)
    authed = bool(user and user.is_authenticated)
    unread = (
        user.notifications.filter(is_read=False).count() if authed else 0
    )
    return {
        "unread_notifications": unread,
        "CLINIC_NAME": settings.CLINIC_NAME,
        "CLINIC_PHONE": settings.CLINIC_PHONE,
        "CLINIC_ADDRESS": settings.CLINIC_ADDRESS,
        "CLINIC_EMERGENCY_NUMBER": settings.CLINIC_EMERGENCY_NUMBER,
        "is_admin_role": authed and user.is_admin_role,
        "is_dentist_role": authed and user.is_dentist,
        "is_patient_role": authed and user.is_patient,
    }
