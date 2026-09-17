from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .models import ExpiringToken


class ExpiringTokenAuthentication(TokenAuthentication):
    """Token auth that rejects (and deletes) tokens older than the TTL."""

    model = ExpiringToken

    def authenticate_credentials(self, key):
        try:
            token = self.model.objects.select_related("user").get(key=key)
        except self.model.DoesNotExist:
            raise AuthenticationFailed("Invalid token.")

        if not token.user.is_active:
            raise AuthenticationFailed("User inactive or deleted.")

        if token.is_expired:
            token.delete()
            raise AuthenticationFailed("Token expired. Please log in again.")

        return (token.user, token)
