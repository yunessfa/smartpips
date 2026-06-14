from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import ExpiringToken


def _issue_token(user):
    ExpiringToken.objects.filter(user=user).delete()
    token = ExpiringToken.objects.create(user=user)
    from django.conf import settings
    return {
        "token": token.key,
        "username": user.username,
        "expires_in": settings.TOKEN_TTL_SECONDS,
        "expires_at": token.expires_at.isoformat(),
    }


@api_view(["POST"])
@permission_classes([AllowAny])
def login_view(request):
    username = (request.data.get("username") or "").strip()
    password = request.data.get("password") or ""
    user = authenticate(username=username, password=password)
    if user is None:
        return Response(
            {"error": "Invalid username or password."},
            status=status.HTTP_401_UNAUTHORIZED,
        )
    return Response(_issue_token(user))


@api_view(["POST"])
@permission_classes([AllowAny])
def register_view(request):
    username = (request.data.get("username") or "").strip()
    password = request.data.get("password") or ""
    if not username or not password:
        return Response(
            {"error": "Username and password are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if len(password) < 6:
        return Response(
            {"error": "Password must be at least 6 characters."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if User.objects.filter(username=username).exists():
        return Response(
            {"error": "That username is taken."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    user = User.objects.create_user(username=username, password=password)
    return Response(_issue_token(user), status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout_view(request):
    ExpiringToken.objects.filter(user=request.user).delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me_view(request):
    auth = request.auth
    return Response(
        {
            "username": request.user.username,
            "expires_at": auth.expires_at.isoformat() if auth else None,
        }
    )
