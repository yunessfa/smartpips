"""Shared DRF permission classes.

Background
----------
Several models in this project are *global system configuration* rather than
per-user data: AIProvider, Indicator, TelegramChannel and Source. They are
read by machinery that has no user context at all --- for example
``apps.chat.services`` builds the assistant prompt from
``Indicator.objects.filter(is_active=True)`` and ``apps.strategy.services``
reads every active TelegramChannel. The ``seed`` management command creates
them as shared defaults.

That design is fine, but their viewsets were left on the project default of
``IsAuthenticated`` with no further scoping, which meant *any* signed-in user
could mutate configuration that affects *every* user. The sharpest edge was
AIProvider: ``api_key`` is write-only so keys could not be read back, but a
non-admin could still point ``base_url`` at a host they control and activate
it, silently routing every user's assistant traffic --- and prompt content ---
through themselves.

The fix keeps the global semantics (no user foreign keys, no changes to the
consumers or the seed command) and restricts *writes* to staff.
"""

from rest_framework import permissions


class IsAdminOrReadOnly(permissions.BasePermission):
    """Any authenticated user may read; only staff/superusers may write.

    Applied to shared-configuration viewsets. Non-safe methods cover the
    custom POST actions too (``activate``, ``test``, ``preview``), which is
    intended --- activating a provider or firing an outbound request on the
    server's behalf is an administrative act.
    """

    message = "Only an administrator can change this setting."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(user.is_staff or user.is_superuser)
