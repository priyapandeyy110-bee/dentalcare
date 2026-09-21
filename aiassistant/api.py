"""REST endpoints backing the live chat widget.

Session-authenticated and throttled (see REST_FRAMEWORK.DEFAULT_THROTTLE_RATES
in settings) so a single user cannot run up an API bill.
"""

from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.decorators import api_view, throttle_classes
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from accounts.models import PatientProfile

from .models import AIMessage, Conversation, MessageRole
from .services import assistant


class ChatRequestSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=2000, trim_whitespace=True)
    conversation_id = serializers.IntegerField(required=False, allow_null=True)

    def validate_message(self, value):
        if not value.strip():
            raise serializers.ValidationError("Type a question first.")
        return value.strip()


class AIMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIMessage
        fields = (
            "id", "role", "content", "provider", "is_fallback", "latency_ms",
            "created_at",
        )


class AIChatThrottle(ScopedRateThrottle):
    scope = "ai"


@api_view(["POST"])
@throttle_classes([AIChatThrottle])
def chat_api(request):
    """Send one message to the assistant and get the reply."""
    serializer = ChatRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    conversation_id = data.get("conversation_id")
    if conversation_id:
        conversation = get_object_or_404(
            Conversation, pk=conversation_id, user=request.user
        )
    else:
        conversation = Conversation.objects.create(user=request.user)

    user_message = AIMessage.objects.create(
        conversation=conversation, role=MessageRole.USER, content=data["message"]
    )

    if conversation.title == "New conversation":
        conversation.title = data["message"][:60]
        conversation.save(update_fields=["title"])

    history = list(
        conversation.messages.exclude(pk=user_message.pk)
        .values("role", "content")
        .order_by("-created_at", "-id")[:12]
    )
    history.reverse()

    patient = PatientProfile.objects.filter(user=request.user).first()
    result = assistant.chat(
        request.user, data["message"], history=history, patient=patient
    )

    reply = AIMessage.objects.create(
        conversation=conversation,
        role=MessageRole.ASSISTANT,
        content=result.content,
        provider=result.provider,
        model=result.model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        latency_ms=result.latency_ms,
        is_fallback=result.is_fallback,
    )
    conversation.touch()

    return Response(
        {
            "conversation_id": conversation.pk,
            "user_message": AIMessageSerializer(user_message).data,
            "reply": AIMessageSerializer(reply).data,
            "ai_live": assistant.ai_is_live(),
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
def conversation_api(request, pk):
    """Full transcript of one conversation."""
    conversation = get_object_or_404(Conversation, pk=pk, user=request.user)
    return Response({
        "id": conversation.pk,
        "title": conversation.title,
        "messages": AIMessageSerializer(conversation.messages.all(), many=True).data,
    })
