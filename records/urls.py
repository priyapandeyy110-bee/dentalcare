from django.urls import path

from . import views

app_name = "records"

urlpatterns = [
    path("treatments/", views.treatment_list, name="treatment_list"),
    path("treatments/<int:pk>/", views.treatment_detail, name="treatment_detail"),
    path("treatments/<int:pk>/edit/", views.treatment_edit, name="treatment_edit"),
    path(
        "patients/<int:patient_id>/treatments/new/",
        views.treatment_create,
        name="treatment_create",
    ),
    path("prescriptions/", views.prescription_list, name="prescription_list"),
    path(
        "prescriptions/<int:pk>/",
        views.prescription_detail,
        name="prescription_detail",
    ),
    path(
        "patients/<int:patient_id>/prescriptions/new/",
        views.prescription_create,
        name="prescription_create",
    ),
    path(
        "patients/<int:patient_id>/history/new/",
        views.history_create,
        name="history_create",
    ),
    path("history/<int:pk>/delete/", views.history_delete, name="history_delete"),
    path(
        "patients/<int:patient_id>/briefing/",
        views.clinical_briefing,
        name="clinical_briefing",
    ),
]
