from django.urls import path

from . import views

app_name = "appointments"

urlpatterns = [
    path("", views.appointment_list, name="list"),
    path("book/", views.book, name="book"),
    path("slots/", views.slots_api, name="slots_api"),
    path("schedule/", views.schedule, name="schedule"),
    path("availability/", views.availability, name="availability"),
    path(
        "availability/<int:pk>/delete/",
        views.availability_delete,
        name="availability_delete",
    ),
    path("time-off/<int:pk>/delete/", views.time_off_delete, name="time_off_delete"),
    path("<int:pk>/", views.appointment_detail, name="detail"),
    path("<int:pk>/reschedule/", views.reschedule, name="reschedule"),
    path("<int:pk>/cancel/", views.cancel, name="cancel"),
]
