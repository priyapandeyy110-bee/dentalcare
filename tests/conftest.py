from datetime import time, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from accounts.models import DentistProfile, PatientProfile, Role, User
from aiassistant.models import SymptomAnalysis, UrgencyLevel
from appointments.models import Appointment, AppointmentStatus, DentistAvailability
from billing.models import Bill, BillItem
from records.models import Treatment

PASSWORD = "test-pass-123"


@pytest.fixture
def admin_user(db):
    user = User.objects.create_user(
        username="admin1", password=PASSWORD, role=Role.ADMIN,
        first_name="Ada", last_name="Admin", email="admin@example.com",
    )
    return user


@pytest.fixture
def dentist_user(db):
    return User.objects.create_user(
        username="dentist1", password=PASSWORD, role=Role.DENTIST,
        first_name="Dina", last_name="Dentist", email="dentist@example.com",
    )


@pytest.fixture
def dentist(dentist_user):
    profile = DentistProfile.objects.create(
        user=dentist_user,
        registration_number="REG-TEST-1",
        specialization="General Dentistry",
        consultation_fee=Decimal("500"),
        slot_duration_minutes=30,
    )
    # Working hours every day so slot tests are not weekday-dependent.
    for weekday in range(7):
        DentistAvailability.objects.create(
            dentist=profile, weekday=weekday,
            start_time=time(9, 0), end_time=time(17, 0),
        )
    return profile


@pytest.fixture
def patient_user(db):
    return User.objects.create_user(
        username="patient1", password=PASSWORD, role=Role.PATIENT,
        first_name="Pat", last_name="Patient", email="patient@example.com",
    )


@pytest.fixture
def patient(patient_user):
    return PatientProfile.objects.create(
        user=patient_user, gender="F", allergies="Penicillin"
    )


@pytest.fixture
def admin_client_(client, admin_user):
    client.force_login(admin_user)
    return client


@pytest.fixture
def dentist_client(client, dentist):
    client.force_login(dentist.user)
    return client


@pytest.fixture
def patient_client(client, patient):
    client.force_login(patient.user)
    return client


@pytest.fixture
def appointment(patient, dentist):
    when = (timezone.localtime() + timedelta(days=2)).replace(
        hour=10, minute=0, second=0, microsecond=0
    )
    return Appointment.objects.create(
        patient=patient, dentist=dentist, scheduled_for=when,
        reason="CHECKUP", status=AppointmentStatus.CONFIRMED,
        symptoms="Routine check",
    )


@pytest.fixture
def treatment(patient, dentist, appointment):
    return Treatment.objects.create(
        patient=patient, dentist=dentist, appointment=appointment,
        diagnosis="Occlusal caries on 16.", procedure="FILLING",
        cost=Decimal("2200"),
    )


@pytest.fixture
def bill(patient, treatment):
    bill = Bill.objects.create(patient=patient, treatment=treatment)
    BillItem.objects.create(
        bill=bill, description="Composite filling", quantity=1,
        unit_price=Decimal("2200"),
    )
    return bill


@pytest.fixture
def analysis(patient):
    return SymptomAnalysis.objects.create(
        user=patient.user, patient=patient,
        symptoms=["tooth_pain"], description="Aching lower molar.",
        pain_level=6, duration="days",
        urgency=UrgencyLevel.SOON, summary="Persistent pain needs examining.",
        possible_areas=["Tooth decay"], self_care_advice=["Rinse with salt water."],
        red_flags=[], recommended_within="Within 2 to 3 days",
        suggested_reason="PAIN", provider="rule-engine", is_fallback=True,
    )
