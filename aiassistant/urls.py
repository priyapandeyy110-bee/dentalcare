from django.urls import path

from . import api, views

app_name = "aiassistant"

urlpatterns = [
    path("", views.chat, name="chat"),
    path("new/", views.chat_new, name="chat_new"),
    path("c/<int:conversation_id>/", views.chat, name="chat_detail"),
    path("c/<int:conversation_id>/delete/", views.chat_delete, name="chat_delete"),
    path("symptom-checker/", views.symptom_checker, name="symptom_checker"),
    path("symptom-checker/history/", views.symptom_history, name="symptom_history"),
    path("symptom-checker/<int:pk>/", views.symptom_detail, name="symptom_detail"),
    path(
        "symptom-checker/<int:pk>/reviewed/",
        views.symptom_mark_reviewed,
        name="symptom_mark_reviewed",
    ),
    path("care-plan/", views.care_plan, name="care_plan"),
    path("care-plan/<int:patient_id>/", views.care_plan, name="care_plan_for"),
    path("faq/", views.faq, name="faq"),
    path("logs/", views.ai_logs, name="ai_logs"),
    # JSON API used by the chat widget
    path("api/chat/", api.chat_api, name="api_chat"),
    path("api/conversations/<int:pk>/", api.conversation_api, name="api_conversation"),
]
