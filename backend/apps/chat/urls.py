from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import ConversationViewSet, chat, scalp_signal, scalp_explanation

router = DefaultRouter()
router.register("conversations", ConversationViewSet, basename="conversation")

urlpatterns = [
    path("send/", chat, name="chat-send"),
    path("scalp/", scalp_signal, name="chat-scalp"),
    path("scalp/explain/", scalp_explanation, name="chat-scalp-explain"),
] + router.urls
