"""Send appointment and follow-up reminders.

Run from cron or Windows Task Scheduler, e.g. hourly:

    python manage.py send_reminders

The command is idempotent -- each appointment and follow-up is reminded once.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from appointments.models import ACTIVE_APPOINTMENT_STATUSES, Appointment
from notifications import services as notify
from records.models import Treatment


class Command(BaseCommand):
    help = "Send appointment reminders and follow-up reminders that are due."

    def add_arguments(self, parser):
        parser.add_argument(
            "--hours",
            type=int,
            default=24,
            help="Remind about appointments this many hours ahead (default 24).",
        )
        parser.add_argument(
            "--follow-up-days",
            type=int,
            default=3,
            help="Remind about follow-ups due within this many days (default 3).",
        )
        parser.add_argument(
            "--no-email",
            action="store_true",
            help="Create in-app notifications only, do not send email.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be sent without sending anything.",
        )

    def handle(self, *args, **options):
        send_email = not options["no_email"]
        dry_run = options["dry_run"]
        now = timezone.now()

        window_end = now + timedelta(hours=options["hours"])
        due_appointments = (
            Appointment.objects.filter(
                status__in=ACTIVE_APPOINTMENT_STATUSES,
                scheduled_for__gt=now,
                scheduled_for__lte=window_end,
                reminder_sent_at__isnull=True,
            )
            .select_related("patient__user", "dentist__user")
            .order_by("scheduled_for")
        )

        sent = 0
        for appointment in due_appointments:
            local = timezone.localtime(appointment.scheduled_for)
            label = "%s - %s on %s" % (
                appointment.reference,
                appointment.patient.user.display_name,
                local.strftime("%d %b %H:%M"),
            )
            if dry_run:
                self.stdout.write("  would remind: %s" % label)
                continue

            notify.appointment_reminder(appointment, email=send_email)
            appointment.reminder_sent_at = now
            appointment.save(update_fields=["reminder_sent_at"])
            sent += 1
            self.stdout.write("  reminded: %s" % label)

        follow_up_cutoff = timezone.localdate() + timedelta(days=options["follow_up_days"])
        due_follow_ups = (
            Treatment.objects.filter(
                follow_up_date__isnull=False,
                follow_up_date__lte=follow_up_cutoff,
                follow_up_date__gte=timezone.localdate(),
                follow_up_reminder_sent_at__isnull=True,
            )
            .select_related("patient__user", "dentist__user")
            .order_by("follow_up_date")
        )

        follow_ups_sent = 0
        for treatment in due_follow_ups:
            label = "%s follow-up on %s" % (
                treatment.patient.user.display_name,
                treatment.follow_up_date,
            )
            if dry_run:
                self.stdout.write("  would remind: %s" % label)
                continue

            notify.follow_up_reminder(treatment, email=send_email)
            treatment.follow_up_reminder_sent_at = now
            treatment.save(update_fields=["follow_up_reminder_sent_at"])
            follow_ups_sent += 1
            self.stdout.write("  reminded: %s" % label)

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "Dry run: %s appointment and %s follow-up reminders would be sent."
                    % (due_appointments.count(), due_follow_ups.count())
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    "Sent %s appointment reminders and %s follow-up reminders."
                    % (sent, follow_ups_sent)
                )
            )
