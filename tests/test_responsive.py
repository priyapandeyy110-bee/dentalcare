"""Mobile layout guards.

Data tables are unreadable at phone width unless every cell carries its own
label, so these tests fail if a table is added without the stacking markup.
"""

import re

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db

TABLE_RE = re.compile(r"<table\b[^>]*>.*?</table>", re.S)
TD_RE = re.compile(r"<td\b([^>]*)>")


def tables_in(html):
    return TABLE_RE.findall(html)


def assert_tables_are_stacked(html, where):
    found = tables_in(html)
    assert found, "%s rendered no table to check" % where

    for table in found:
        classes = re.match(r"<table\b([^>]*)>", table).group(1)
        assert "table-stack" in classes or "table-form-stack" in classes, (
            "%s has a table with no mobile stacking class" % where
        )

        body = re.search(r"<tbody\b.*?</tbody>", table, re.S)
        if not body:
            continue

        for attrs in TD_RE.findall(body.group(0)):
            labelled = "data-label" in attrs
            full_width = "colspan" in attrs
            actions = "stack-actions" in attrs
            assert labelled or full_width or actions, (
                "%s has a cell with no data-label, colspan or stack-actions: <td%s>"
                % (where, attrs[:70])
            )


LIST_PAGES = [
    "appointments:list",
    "accounts:patient_list",
    "accounts:staff_list",
    "billing:list",
    "records:treatment_list",
    "records:prescription_list",
    "aiassistant:ai_logs",
    "aiassistant:symptom_history",
    "core:reports",
    "core:dashboard",
    "appointments:schedule",
    "appointments:availability",
]


@pytest.mark.parametrize("name", LIST_PAGES)
def test_list_tables_stack_on_mobile(admin_client_, dentist, name):
    response = admin_client_.get(reverse(name))
    assert response.status_code == 200
    assert_tables_are_stacked(response.content.decode(), name)


def test_detail_tables_stack_on_mobile(admin_client_, bill, treatment, appointment):
    pages = {
        "bill detail": reverse("billing:detail", args=[bill.pk]),
        "invoice print": reverse("billing:invoice_print", args=[bill.pk]),
        "patient detail": reverse("accounts:patient_detail", args=[bill.patient.pk]),
    }
    for where, url in pages.items():
        response = admin_client_.get(url)
        assert response.status_code == 200
        assert_tables_are_stacked(response.content.decode(), where)


def test_formset_tables_stack_on_mobile(admin_client_, dentist, patient):
    pages = {
        "invoice form": reverse("billing:create", args=[patient.pk]),
        "prescription form": reverse("records:prescription_create", args=[patient.pk]),
    }
    for where, url in pages.items():
        response = admin_client_.get(url)
        assert response.status_code == 200
        html = response.content.decode()
        assert "table-form-stack" in html, "%s is not stacked" % where
        assert_tables_are_stacked(html, where)


def test_every_page_declares_the_viewport(admin_client_):
    from django.test import Client

    anonymous = Client()
    for response in [
        anonymous.get(reverse("core:home")),
        anonymous.get(reverse("accounts:login")),
        admin_client_.get(reverse("core:dashboard")),
    ]:
        assert b'name="viewport"' in response.content
        assert b"width=device-width" in response.content


def test_navbar_keeps_notifications_reachable_on_mobile(admin_client_):
    """The bell sits outside the collapsed menu so it stays one tap away."""
    html = admin_client_.get(reverse("core:dashboard")).content.decode()
    outside = html.split('id="mainNav"')[0]
    assert "bi-bell" in outside, "the bell is only inside the collapsed menu"
    assert "d-lg-none" in outside
    assert "navbar-brand-text" in outside, "brand has no truncation hook"


def test_header_actions_are_marked_for_full_width(admin_client_):
    html = admin_client_.get(reverse("core:dashboard")).content.decode()
    assert "page-actions" in html


def test_stylesheet_carries_the_mobile_layer():
    """The rules live in app.css, so guard the pieces the templates rely on."""
    css = open("static/css/app.css", encoding="utf-8").read()

    for rule in [
        ".table-stack",
        ".table-form-stack",
        ".page-actions",
        ".chat-quick-links",
        ".btn-group-wrap",
        ".navbar-brand-text",
    ]:
        assert rule in css, "app.css is missing %s" % rule

    # Phone rules must not apply to paper.
    assert "@media screen and (max-width: 767.98px)" in css
    assert "@media (max-width:" not in css, "a mobile query is not scoped to screen"

    # Inputs under 16px make iOS zoom on focus.
    assert "font-size: 16px" in css
