"""Populate the database with a realistic demo clinic.

    python manage.py seed_demo

Creates an administrator, four dentists with working hours, twelve patients,
and a spread of appointments, treatments, prescriptions, bills and payments
across the past and the coming weeks -- enough for every dashboard, report
and AI feature to have something to show.
"""

import random
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import DentistProfile, PatientProfile, Role
from aiassistant.models import (
    AIMessage, Conversation, MessageRole, SymptomAnalysis,
)
from aiassistant.services import rule_engine
from appointments.models import (
    Appointment, AppointmentStatus, DentistAvailability,
)
from billing.models import Bill, BillItem, Payment, PaymentMethod
from records.models import DentalHistoryEntry, Prescription, PrescriptionItem, Treatment

User = get_user_model()

DEFAULT_PASSWORD = "dental123"

DENTISTS = [
    ("anita.rao", "Anita", "Rao", "Orthodontics", "MDS (Orthodontics)", 14, 900, "DCI-MH-11234"),
    ("vikram.shah", "Vikram", "Shah", "Endodontics", "MDS (Conservative Dentistry)", 9, 800, "DCI-MH-22871"),
    ("priya.nair", "Priya", "Nair", "Periodontics", "MDS (Periodontology)", 6, 700, "DCI-MH-30442"),
    ("rahul.mehta", "Rahul", "Mehta", "General Dentistry", "BDS", 4, 500, "DCI-MH-41190"),
]

PATIENTS = [
    ("arjun.patel", "Arjun", "Patel", "M", "9812345601", 34, "", "", False, True, False),
    ("sneha.kulkarni", "Sneha", "Kulkarni", "F", "9812345602", 27, "Penicillin", "", False, True, True),
    ("mohammed.ali", "Mohammed", "Ali", "M", "9812345603", 52, "", "Type 2 diabetes", True, False, False),
    ("lakshmi.iyer", "Lakshmi", "Iyer", "F", "9812345604", 61, "Latex", "Hypertension", False, True, False),
    ("rohan.desai", "Rohan", "Desai", "M", "9812345605", 19, "", "", False, False, False),
    ("fatima.sheikh", "Fatima", "Sheikh", "F", "9812345606", 41, "", "Asthma", False, True, True),
    ("karan.singh", "Karan", "Singh", "M", "9812345607", 29, "Ibuprofen", "", True, True, False),
    ("divya.menon", "Divya", "Menon", "F", "9812345608", 36, "", "", False, True, True),
    ("suresh.reddy", "Suresh", "Reddy", "M", "9812345609", 47, "", "Type 2 diabetes, hypertension", True, False, False),
    ("ananya.ghosh", "Ananya", "Ghosh", "F", "9812345610", 23, "", "", False, True, False),
    ("imran.khan", "Imran", "Khan", "M", "9812345611", 58, "Sulfa drugs", "Heart condition", False, True, False),
    ("meera.joshi", "Meera", "Joshi", "F", "9812345612", 31, "", "", False, True, True),
]

COMPLAINTS = [
    ("Sharp pain in lower right molar when drinking cold water", "FILLING", "PAIN"),
    ("Bleeding gums while brushing for the past month", "SCALING", "CLEANING"),
    ("Routine six-monthly check-up", "CONSULT", "CHECKUP"),
    ("Broken filling on upper left premolar", "FILLING", "FILLING"),
    ("Severe throbbing pain, kept awake at night", "RCT", "PAIN"),
    ("Wants teeth whitened before a wedding", "WHITENING", "COSMETIC"),
    ("Swelling and pain around lower wisdom tooth", "EXTRACTION", "EMERGENCY"),
    ("Follow-up after root canal, crown fitting", "CROWN", "FOLLOW_UP"),
    ("Discussion about braces for crowded front teeth", "BRACES", "ORTHODONTIC"),
    ("Persistent bad breath despite brushing", "SCALING", "CLEANING"),
]

DIAGNOSES = {
    "FILLING": "Occlusal caries with dentine involvement. No pulpal exposure.",
    "SCALING": "Generalised chronic gingivitis with moderate supragingival calculus.",
    "CONSULT": "Oral cavity within normal limits. Mild staining noted; no active caries.",
    "RCT": "Irreversible pulpitis. Periapical radiolucency present on radiograph.",
    "WHITENING": "Extrinsic staining from tea and tobacco. Enamel intact.",
    "EXTRACTION": "Pericoronitis around partially erupted mandibular third molar.",
    "CROWN": "Root canal treatment complete; tooth prepared for full-coverage crown.",
    "BRACES": "Class I malocclusion with anterior crowding of 4 mm in the lower arch.",
}

MEDICINES = [
    ("Amoxicillin", "500 mg", "Three times daily after meals", "5 days", "Complete the full course."),
    ("Ibuprofen", "400 mg", "Twice daily after food", "3 days", "Stop if stomach discomfort occurs."),
    ("Paracetamol", "650 mg", "Every 8 hours if needed", "3 days", "Do not exceed 3 doses a day."),
    ("Chlorhexidine mouthwash", "10 ml", "Twice daily, do not swallow", "7 days", "Use 30 minutes after brushing."),
    ("Metronidazole", "400 mg", "Three times daily", "5 days", "Avoid alcohol during the course."),
]


class Command(BaseCommand):
    help = "Create a realistic demo clinic (users, appointments, treatments, bills)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete existing demo data (all non-superuser accounts) first.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        random.seed(20260921)

        if options["flush"]:
            self.stdout.write("Removing existing demo data...")
            User.objects.filter(is_superuser=False).delete()

        admin = self._create_admin()
        dentists = self._create_dentists()
        patients = self._create_patients()
        self._create_availability(dentists)
        appointments = self._create_appointments(patients, dentists)
        treatments = self._create_treatments(appointments)
        self._create_prescriptions(treatments)
        self._create_bills(treatments, admin)
        self._create_history(patients)
        self._create_ai_activity(patients)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Demo clinic ready."))
        self.stdout.write("")
        self.stdout.write("  Sign in at /accounts/login/ -- password for everyone: %s" % DEFAULT_PASSWORD)
        self.stdout.write("")
        self.stdout.write("    Administrator : clinicadmin")
        self.stdout.write("    Dentist       : anita.rao   (also vikram.shah, priya.nair, rahul.mehta)")
        self.stdout.write("    Patient       : arjun.patel (and 11 more, see the patient list)")
        self.stdout.write("")

    # --- Users -------------------------------------------------------------

    def _create_admin(self):
        admin, created = User.objects.get_or_create(
            username="clinicadmin",
            defaults={
                "first_name": "Clinic",
                "last_name": "Administrator",
                "email": "admin@smiledental.example",
                "role": Role.ADMIN,
                "is_staff": True,
                "phone": "9876543210",
            },
        )
        if created:
            admin.set_password(DEFAULT_PASSWORD)
            admin.save()
        self.stdout.write("Administrator: %s" % admin.username)
        return admin

    def _create_dentists(self):
        dentists = []
        for username, first, last, spec, qual, years, fee, reg in DENTISTS:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": first,
                    "last_name": last,
                    "email": "%s@smiledental.example" % username,
                    "role": Role.DENTIST,
                    "phone": "98765%05d" % random.randint(0, 99999),
                },
            )
            if created:
                user.set_password(DEFAULT_PASSWORD)
                user.save()

            profile, _ = DentistProfile.objects.get_or_create(
                user=user,
                defaults={
                    "registration_number": reg,
                    "specialization": spec,
                    "qualification": qual,
                    "experience_years": years,
                    "consultation_fee": Decimal(fee),
                    "slot_duration_minutes": 30,
                    "bio": "%s with %s years of clinical experience in %s."
                    % (qual, years, spec.lower()),
                },
            )
            dentists.append(profile)
        self.stdout.write("Dentists: %s" % len(dentists))
        return dentists

    def _create_patients(self):
        patients = []
        today = timezone.localdate()
        for (username, first, last, gender, phone, age, allergies,
             conditions, smoker, brushes, flosses) in PATIENTS:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": first,
                    "last_name": last,
                    "email": "%s@example.com" % username,
                    "role": Role.PATIENT,
                    "phone": phone,
                    "date_of_birth": today - timedelta(days=age * 365 + random.randint(0, 300)),
                    "address": "%s, Pune, Maharashtra" % random.choice(
                        ["Kothrud", "Viman Nagar", "Baner", "Hadapsar", "Aundh"]
                    ),
                },
            )
            if created:
                user.set_password(DEFAULT_PASSWORD)
                user.save()

            profile, _ = PatientProfile.objects.get_or_create(
                user=user,
                defaults={
                    "gender": gender,
                    "blood_group": random.choice(["A+", "B+", "O+", "AB+", "O-"]),
                    "allergies": allergies,
                    "chronic_conditions": conditions,
                    "current_medications": "Metformin 500 mg twice daily"
                    if "diabet" in conditions.lower()
                    else "",
                    "is_smoker": smoker,
                    "brushes_twice_daily": brushes,
                    "flosses_daily": flosses,
                    "emergency_contact_name": "%s (family)" % random.choice(
                        ["Ramesh", "Sunita", "Amit", "Kavita"]
                    ),
                    "emergency_contact_phone": "98%08d" % random.randint(0, 99999999),
                    "last_dental_visit": today - timedelta(days=random.randint(30, 500)),
                },
            )
            patients.append(profile)
        self.stdout.write("Patients: %s" % len(patients))
        return patients

    def _create_availability(self, dentists):
        created = 0
        for index, dentist in enumerate(dentists):
            # Weekday mornings + afternoons, Saturday mornings only.
            for weekday in range(0, 5):
                blocks = [(time(9, 30), time(13, 0)), (time(16, 0), time(19, 30))]
                if index % 2 and weekday in (1, 3):
                    blocks = [(time(10, 0), time(14, 0))]
                for start, end in blocks:
                    _, made = DentistAvailability.objects.get_or_create(
                        dentist=dentist, weekday=weekday, start_time=start,
                        defaults={"end_time": end},
                    )
                    created += int(made)
            _, made = DentistAvailability.objects.get_or_create(
                dentist=dentist, weekday=5, start_time=time(10, 0),
                defaults={"end_time": time(14, 0)},
            )
            created += int(made)
        self.stdout.write("Availability blocks: %s" % created)

    # --- Clinical activity -------------------------------------------------

    def _create_appointments(self, patients, dentists):
        if Appointment.objects.exists():
            self.stdout.write("Appointments already present, skipping.")
            return list(Appointment.objects.select_related("patient__user", "dentist__user"))

        appointments = []
        tz = timezone.get_current_timezone()
        today = timezone.localdate()

        # Past appointments (mostly completed) over the last 90 days.
        for offset in range(90, 0, -2):
            day = today - timedelta(days=offset)
            if day.weekday() == 6:
                continue
            for _ in range(random.randint(0, 2)):
                patient = random.choice(patients)
                dentist = random.choice(dentists)
                hour = random.choice([10, 11, 12, 17, 18])
                minute = random.choice([0, 30])
                when = timezone.make_aware(
                    datetime.combine(day, time(hour, minute)), tz
                )
                if Appointment.objects.filter(
                    dentist=dentist, scheduled_for=when
                ).exists():
                    continue
                complaint, _procedure, reason = random.choice(COMPLAINTS)
                status = random.choices(
                    [
                        AppointmentStatus.COMPLETED,
                        AppointmentStatus.CANCELLED,
                        AppointmentStatus.NO_SHOW,
                    ],
                    weights=[85, 10, 5],
                )[0]
                appointments.append(
                    Appointment.objects.create(
                        patient=patient,
                        dentist=dentist,
                        scheduled_for=when,
                        duration_minutes=dentist.slot_duration_minutes,
                        reason=reason,
                        symptoms=complaint,
                        status=status,
                    )
                )

        # Upcoming appointments over the next 20 days.
        for offset in range(0, 20):
            day = today + timedelta(days=offset)
            if day.weekday() == 6:
                continue
            for _ in range(random.randint(0, 2)):
                patient = random.choice(patients)
                dentist = random.choice(dentists)
                hour = random.choice([10, 11, 17, 18])
                minute = random.choice([0, 30])
                when = timezone.make_aware(
                    datetime.combine(day, time(hour, minute)), tz
                )
                if when <= timezone.now():
                    continue
                if Appointment.objects.filter(
                    dentist=dentist,
                    scheduled_for=when,
                    status__in=["PENDING", "CONFIRMED"],
                ).exists():
                    continue
                complaint, _procedure, reason = random.choice(COMPLAINTS)
                appointments.append(
                    Appointment.objects.create(
                        patient=patient,
                        dentist=dentist,
                        scheduled_for=when,
                        duration_minutes=dentist.slot_duration_minutes,
                        reason=reason,
                        symptoms=complaint,
                        status=random.choices(
                            [AppointmentStatus.CONFIRMED, AppointmentStatus.PENDING],
                            weights=[70, 30],
                        )[0],
                    )
                )

        self.stdout.write("Appointments: %s" % len(appointments))
        return appointments

    def _create_treatments(self, appointments):
        if Treatment.objects.exists():
            self.stdout.write("Treatments already present, skipping.")
            return list(Treatment.objects.select_related("patient__user", "dentist__user"))

        treatments = []
        completed = [
            appointment
            for appointment in appointments
            if appointment.status == AppointmentStatus.COMPLETED
        ]
        for appointment in completed:
            complaint, procedure, _reason = random.choice(COMPLAINTS)
            cost = {
                "CONSULT": 500, "SCALING": 1500, "FILLING": 2200, "RCT": 6500,
                "CROWN": 8000, "EXTRACTION": 2500, "WHITENING": 7000, "BRACES": 45000,
            }.get(procedure, 1000)

            treatment_date = timezone.localtime(appointment.scheduled_for).date()
            follow_up = None
            instructions = ""
            if procedure in ("RCT", "EXTRACTION", "CROWN", "BRACES"):
                follow_up = treatment_date + timedelta(days=random.choice([7, 14, 21]))
                instructions = {
                    "RCT": "Return for crown preparation. Avoid chewing on that side.",
                    "EXTRACTION": "Review healing of the socket and remove sutures.",
                    "CROWN": "Cementation of the permanent crown.",
                    "BRACES": "Routine adjustment of the archwire.",
                }[procedure]

            treatment = Treatment.objects.create(
                patient=appointment.patient,
                dentist=appointment.dentist,
                appointment=appointment,
                treatment_date=treatment_date,
                chief_complaint=appointment.symptoms or complaint,
                diagnosis=DIAGNOSES.get(procedure, "Clinical examination completed."),
                procedure=procedure,
                tooth_region=random.choice(["UR", "UL", "LL", "LR", "FM"]),
                tooth_numbers=random.choice(["16", "26, 27", "36", "46", ""]),
                treatment_notes="Local anaesthetic given. Patient tolerated the procedure well."
                if procedure not in ("CONSULT",)
                else "Oral hygiene instruction reinforced.",
                cost=Decimal(cost),
                follow_up_date=follow_up,
                follow_up_instructions=instructions,
            )
            treatments.append(treatment)

        self.stdout.write("Treatments: %s" % len(treatments))
        return treatments

    def _create_prescriptions(self, treatments):
        if Prescription.objects.exists():
            self.stdout.write("Prescriptions already present, skipping.")
            return

        count = 0
        for treatment in treatments:
            if treatment.procedure not in ("RCT", "EXTRACTION", "SCALING"):
                continue
            prescription = Prescription.objects.create(
                patient=treatment.patient,
                dentist=treatment.dentist,
                treatment=treatment,
                issued_on=treatment.treatment_date,
                advice="Soft diet for 48 hours. Rinse with warm salt water from tomorrow. "
                       "Contact the clinic if pain or swelling increases.",
            )
            for name, dosage, frequency, duration, note in random.sample(MEDICINES, 2):
                PrescriptionItem.objects.create(
                    prescription=prescription,
                    medicine_name=name,
                    dosage=dosage,
                    frequency=frequency,
                    duration=duration,
                    instructions=note,
                )
            count += 1
        self.stdout.write("Prescriptions: %s" % count)

    def _create_bills(self, treatments, admin):
        if Bill.objects.exists():
            self.stdout.write("Bills already present, skipping.")
            return

        count = 0
        for treatment in treatments:
            bill = Bill.objects.create(
                patient=treatment.patient,
                appointment=treatment.appointment,
                treatment=treatment,
                issued_on=treatment.treatment_date,
                due_date=treatment.treatment_date + timedelta(days=15),
                discount=Decimal(random.choice([0, 0, 0, 100, 250])),
                tax_percent=Decimal("0"),
                created_by=admin,
            )
            BillItem.objects.create(
                bill=bill,
                description="Consultation",
                quantity=1,
                unit_price=treatment.dentist.consultation_fee,
            )
            if treatment.cost:
                BillItem.objects.create(
                    bill=bill,
                    description=treatment.get_procedure_display(),
                    quantity=1,
                    unit_price=treatment.cost,
                )

            roll = random.random()
            if roll < 0.65:
                Payment.objects.create(
                    bill=bill,
                    amount=bill.total,
                    method=random.choice(
                        [PaymentMethod.CASH, PaymentMethod.UPI, PaymentMethod.CARD]
                    ),
                    paid_on=treatment.treatment_date,
                    recorded_by=admin,
                )
            elif roll < 0.85:
                Payment.objects.create(
                    bill=bill,
                    amount=(bill.total / 2).quantize(Decimal("0.01")),
                    method=PaymentMethod.UPI,
                    paid_on=treatment.treatment_date,
                    recorded_by=admin,
                )
            bill.recalculate_status()
            count += 1
        self.stdout.write("Bills: %s" % count)

    def _create_history(self, patients):
        if DentalHistoryEntry.objects.exists():
            return
        samples = [
            ("MEDICAL", "Type 2 diabetes", "Diagnosed 2019, managed with metformin."),
            ("DENTAL", "Orthodontic treatment", "Fixed braces 2012-2014, retainer since."),
            ("SURGERY", "Wisdom tooth removal", "Lower left third molar removed 2021."),
            ("HABIT", "Night grinding", "Reported by partner; wear facets noted."),
            ("ALLERGY", "Penicillin allergy", "Rash reported in childhood. Use alternatives."),
        ]
        count = 0
        for patient in patients:
            for category, title, description in random.sample(samples, random.randint(1, 3)):
                DentalHistoryEntry.objects.create(
                    patient=patient,
                    category=category,
                    title=title,
                    description=description,
                    recorded_on=timezone.localdate() - timedelta(days=random.randint(30, 900)),
                )
                count += 1
        self.stdout.write("History entries: %s" % count)

    def _create_ai_activity(self, patients):
        """Seed a few symptom assessments and a chat thread using the rule engine."""
        if SymptomAnalysis.objects.exists():
            return

        scenarios = [
            {
                "symptoms": ["sensitivity"],
                "description": "Pain when drinking cold water on the left side.",
                "pain_level": 3, "duration": "weeks",
            },
            {
                "symptoms": ["tooth_pain", "swelling"],
                "description": "Throbbing pain with swelling on my cheek since yesterday.",
                "pain_level": 8, "duration": "days", "has_swelling": True, "has_fever": True,
            },
            {
                "symptoms": ["gum_bleeding", "bad_breath"],
                "description": "Gums bleed every time I brush and my breath smells.",
                "pain_level": 1, "duration": "months",
            },
            {
                "symptoms": ["jaw_pain"],
                "description": "My jaw clicks in the morning and aches by evening.",
                "pain_level": 4, "duration": "weeks",
            },
        ]

        for patient, scenario in zip(random.sample(patients, len(scenarios)), scenarios):
            payload = {
                "symptoms": scenario["symptoms"],
                "description": scenario["description"],
                "pain_level": scenario["pain_level"],
                "duration": scenario["duration"],
                "has_swelling": scenario.get("has_swelling", False),
                "has_fever": scenario.get("has_fever", False),
                "difficulty_swallowing": False,
            }
            data = rule_engine.analyze_symptoms(payload)
            SymptomAnalysis.objects.create(
                user=patient.user,
                patient=patient,
                symptoms=payload["symptoms"],
                description=payload["description"],
                pain_level=payload["pain_level"],
                duration=payload["duration"],
                has_swelling=payload["has_swelling"],
                has_fever=payload["has_fever"],
                urgency=data["urgency"],
                summary=data["summary"],
                possible_areas=data["possible_areas"],
                self_care_advice=data["self_care_advice"],
                red_flags=data["red_flags"],
                recommended_within=data["recommended_within"],
                suggested_reason=data["suggested_reason"],
                provider=data["provider"],
                is_fallback=True,
            )

        demo_patient = patients[0]
        conversation = Conversation.objects.create(
            user=demo_patient.user, title="Why are my teeth sensitive?"
        )
        for question in [
            "Why are my teeth sensitive to cold?",
            "How often should I floss?",
        ]:
            AIMessage.objects.create(
                conversation=conversation, role=MessageRole.USER, content=question
            )
            AIMessage.objects.create(
                conversation=conversation,
                role=MessageRole.ASSISTANT,
                content=rule_engine.answer_question(question),
                provider=rule_engine.PROVIDER_NAME,
                is_fallback=True,
            )

        self.stdout.write("AI activity: %s assessments, 1 chat thread" % len(scenarios))
