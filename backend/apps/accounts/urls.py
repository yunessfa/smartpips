from django.urls import path
from .views import (
    login_view, register_view, logout_view, me_view,
    admin_users, admin_user_detail, admin_user_reset,
    public_config_view, system_settings_view,
)

urlpatterns = [
    path("login/", login_view, name="login"),
    path("register/", register_view, name="register"),
    path("logout/", logout_view, name="logout"),
    path("me/", me_view, name="me"),
    # Anonymous: tells /register whether sign-ups are open.
    path("config/", public_config_view, name="public-config"),
    # Staff read / super-admin write of the system switches.
    path("settings/", system_settings_view, name="system-settings"),
    path("users/", admin_users, name="admin-users"),
    path("users/<int:user_id>/", admin_user_detail, name="admin-user-detail"),
    # Super-admin only: wipe this user's data so they start from scratch.
    path("users/<int:user_id>/reset/", admin_user_reset, name="admin-user-reset"),
]
