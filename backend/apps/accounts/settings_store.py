"""Server-side system settings.

Why a model and not an env var or localStorage:

* The registration switch is a *security* control. Hiding the sign-up button in
  the frontend is cosmetic --- anyone can POST to /api/auth/register/ directly,
  so the flag has to be read by the registration endpoint itself.
* It has to be changeable at runtime by a super admin without a redeploy, which
  rules out settings.py / .env.
* It must survive restarts and be identical for every gunicorn worker, which
  rules out module-level globals and the local-memory cache.

The store is a tiny key/value table with JSON values, so future switches
("maintenance mode", "real trading globally paused") can be added without a
new model or migration each time.
"""

from django.db import models


class SystemSetting(models.Model):
    """One row per system-wide switch. Values are JSON so booleans stay booleans."""

    key = models.CharField(max_length=64, primary_key=True)
    value = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        "auth.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="system_settings_changed",
    )

    class Meta:
        ordering = ["key"]

    def __str__(self):
        return f"{self.key} = {self.value}"


# ---------------------------------------------------------------- accessors

REGISTRATION_ENABLED = "registration_enabled"

# Defaults are used when the row does not exist yet, so an existing deployment
# keeps behaving exactly as it did before this migration ran.
DEFAULTS = {
    REGISTRATION_ENABLED: True,
}


def get_setting(key, default=None):
    if default is None:
        default = DEFAULTS.get(key)
    try:
        row = SystemSetting.objects.filter(pk=key).first()
    except Exception:
        # Never let a missing table (e.g. during an initial migrate) break auth.
        return default
    if row is None:
        return default
    value = row.value
    # Values are stored as {"v": ...} so JSONField can hold scalars portably.
    if isinstance(value, dict) and "v" in value:
        return value["v"]
    return value


def set_setting(key, value, user=None):
    row, _ = SystemSetting.objects.update_or_create(
        pk=key,
        defaults={"value": {"v": value}, "updated_by": user},
    )
    return row


def registration_enabled():
    return bool(get_setting(REGISTRATION_ENABLED, True))


def public_settings():
    """The subset safe to expose to anonymous callers (the /register page)."""
    return {"registration_enabled": registration_enabled()}


def all_settings():
    """Everything an administrator can see and change."""
    return {key: get_setting(key) for key in DEFAULTS}
