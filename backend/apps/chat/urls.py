from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import ConversationViewSet, chat

router = DefaultRouter()
router.register("conversations", ConversationViewSet, basename="conversation")

urlpatterns = [
    path("send/", chat, name="chat-send"),
] + router.urls
