from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.DentalLoginView.as_view(), name="login"),
    path("logout/", views.DentalLogoutView.as_view(), name="logout"),
    path("signup/", views.signup, name="signup"),
    path("profile/", views.profile, name="profile"),
    path("password/", views.DentalPasswordChangeView.as_view(), name="password_change"),
    path(
        "password/done/",
        views.DentalPasswordChangeDoneView.as_view(),
        name="password_change_done",
    ),
    path("patients/", views.patient_list, name="patient_list"),
    path("patients/new/", views.patient_create, name="patient_create"),
    path("patients/<int:pk>/", views.patient_detail, name="patient_detail"),
    path("dentists/", views.dentist_list, name="dentist_list"),
    path("dentists/<int:pk>/", views.dentist_detail, name="dentist_detail"),
    path("staff/", views.staff_list, name="staff_list"),
    path("staff/new/", views.staff_create, name="staff_create"),
    path(
        "staff/<int:user_id>/dentist-profile/",
        views.dentist_profile_edit,
        name="dentist_profile_edit",
    ),
    path("staff/<int:user_id>/toggle/", views.toggle_user_active, name="toggle_user_active"),
]
