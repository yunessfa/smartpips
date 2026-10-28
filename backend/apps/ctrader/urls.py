from django.urls import path

from .views import connect, callback, use_account, use_manual, status_view

urlpatterns = [
    path("connect/", connect, name="ctrader-connect"),
    path("callback/", callback, name="ctrader-callback"),
    path("use/<int:account_id>/", use_account, name="ctrader-use"),
    path("use_manual/", use_manual, name="ctrader-use-manual"),
    path("status/", status_view, name="ctrader-status"),
]
