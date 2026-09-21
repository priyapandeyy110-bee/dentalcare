from django.urls import path

from . import views

app_name = "billing"

urlpatterns = [
    path("", views.bill_list, name="list"),
    path("<int:pk>/", views.bill_detail, name="detail"),
    path("<int:pk>/edit/", views.bill_edit, name="edit"),
    path("<int:pk>/cancel/", views.bill_cancel, name="cancel"),
    path("<int:pk>/print/", views.invoice_print, name="invoice_print"),
    path("patients/<int:patient_id>/new/", views.bill_create, name="create"),
]
