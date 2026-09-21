"""End-to-end smoke tests: every page renders for every role."""

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


PUBLIC_PAGES = [
    ("core:home", {}),
    ("accounts:login", {}),
    ("accounts:signup", {}),
    ("aiassistant:faq", {}),
    ("accounts:dentist_list", {}),
]

SHARED_PAGES = [
    ("core:dashboard", {}),
    ("appointments:list", {}),
    ("appointments:book", {}),
    ("records:treatment_list", {}),
    ("records:prescription_list", {}),
    ("billing:list", {}),
    ("aiassistant:chat", {}),
    ("aiassistant:symptom_checker", {}),
    ("aiassistant:symptom_history", {}),
    ("notifications:list", {}),
    ("accounts:profile", {}),
]

STAFF_PAGES = [
    ("accounts:patient_list", {}),
    ("appointments:schedule", {}),
    ("appointments:availability", {}),
]

ADMIN_ONLY_PAGES = [
    ("core:reports", {}),
    ("accounts:staff_list", {}),
    ("accounts:patient_create", {}),
    ("accounts:staff_create", {}),
    ("aiassistant:ai_logs", {}),
]


@pytest.mark.parametrize("name,kwargs", PUBLIC_PAGES)
def test_public_pages_render(client, name, kwargs):
    response = client.get(reverse(name, kwargs=kwargs))
    assert response.status_code == 200


@pytest.mark.parametrize("name,kwargs", SHARED_PAGES)
def test_shared_pages_render_for_patient(patient_client, name, kwargs):
    response = patient_client.get(reverse(name, kwargs=kwargs))
    assert response.status_code == 200, "%s failed for patient" % name


@pytest.mark.parametrize("name,kwargs", SHARED_PAGES + STAFF_PAGES)
def test_pages_render_for_dentist(dentist_client, name, kwargs):
    response = dentist_client.get(reverse(name, kwargs=kwargs))
    assert response.status_code == 200, "%s failed for dentist" % name


@pytest.mark.parametrize("name,kwargs", SHARED_PAGES + STAFF_PAGES + ADMIN_ONLY_PAGES)
def test_pages_render_for_admin(admin_client_, dentist, name, kwargs):
    # `dentist` is required: the schedule and availability pages need at least
    # one dentist on record before an administrator can open them.
    response = admin_client_.get(reverse(name, kwargs=kwargs))
    assert response.status_code == 200, "%s failed for admin" % name


def test_anonymous_is_redirected_to_login(client):
    response = client.get(reverse("core:dashboard"))
    assert response.status_code == 302
    assert "/accounts/login/" in response["Location"]


def test_patient_cannot_open_admin_pages(patient_client):
    for name in ["core:reports", "accounts:staff_list", "aiassistant:ai_logs"]:
        response = patient_client.get(reverse(name))
        assert response.status_code == 403, "%s was not blocked" % name


def test_patient_cannot_open_patient_directory(patient_client):
    response = patient_client.get(reverse("accounts:patient_list"))
    assert response.status_code == 403


def test_detail_pages_render(admin_client_, appointment, treatment, bill, analysis):
    pages = [
        reverse("appointments:detail", args=[appointment.pk]),
        reverse("records:treatment_detail", args=[treatment.pk]),
        reverse("billing:detail", args=[bill.pk]),
        reverse("billing:invoice_print", args=[bill.pk]),
        reverse("aiassistant:symptom_detail", args=[analysis.pk]),
        reverse("accounts:patient_detail", args=[appointment.patient.pk]),
        reverse("records:clinical_briefing", args=[appointment.patient.pk]),
        reverse("aiassistant:care_plan_for", args=[appointment.patient.pk]),
    ]
    for url in pages:
        response = admin_client_.get(url)
        assert response.status_code == 200, "%s failed" % url


def test_reports_period_filters(admin_client_):
    for period in ["week", "month", "year", "all"]:
        response = admin_client_.get(reverse("core:reports"), {"period": period})
        assert response.status_code == 200
