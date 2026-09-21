from django.db import models
from django.utils import timezone


class NotificationType(models.TextChoices):
    APPOINTMENT_BOOKED = "APT_BOOKED", "Appointment booked"
    APPOINTMENT_CONFIRMED = "APT_CONFIRMED", "Appointment confirmed"
    APPOINTMENT_CANCELLED = "APT_CANCELLED", "Appointment cancelled"
    APPOINTMENT_REMINDER = "APT_REMINDER", "Appointment reminder"
    FOLLOW_UP = "FOLLOW_UP", "Follow-up reminder"
    TREATMENT_ADDED = "TREATMENT", "Treatment record added"
    PRESCRIPTION_ADDED = "PRESCRIPTION", "Prescription issued"
    BILL_GENERATED = "BILL", "Bill generated"
    PAYMENT_RECEIVED = "PAYMENT", "Payment received"
    AI_ALERT = "AI_ALERT", "AI urgency alert"
    SYSTEM = "SYSTEM", "System message"


class Notification(models.Model):
    """In-app notification; optionally mirrored to email by the reminder command."""

    recipient = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="notifications"
    )
    notification_type = models.CharField(
        max_length=16, choices=NotificationType.choices, default=NotificationType.SYSTEM
    )
    title = models.CharField(max_length=160)
    message = models.TextField()
    link = models.CharField(max_length=300, blank=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    emailed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["recipient", "is_read"])]

    def __str__(self):
        return "%s -> %s" % (self.title, self.recipient.display_name)

    def mark_read(self):
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=["is_read", "read_at"])

    @property
    def icon(self):
        return {
            NotificationType.APPOINTMENT_BOOKED: "calendar-plus",
            NotificationType.APPOINTMENT_CONFIRMED: "calendar-check",
            NotificationType.APPOINTMENT_CANCELLED: "calendar-x",
            NotificationType.APPOINTMENT_REMINDER: "alarm",
            NotificationType.FOLLOW_UP: "arrow-repeat",
            NotificationType.TREATMENT_ADDED: "clipboard-pulse",
            NotificationType.PRESCRIPTION_ADDED: "capsule",
            NotificationType.BILL_GENERATED: "receipt",
            NotificationType.PAYMENT_RECEIVED: "cash-coin",
            NotificationType.AI_ALERT: "robot",
        }.get(self.notification_type, "bell")
