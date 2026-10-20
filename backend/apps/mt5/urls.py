from django.urls import path

from .views import (
    bridge_push, bridge_pending_orders, bridge_ack_order,
    account_view, place_order, my_orders,
)

urlpatterns = [
    # EA bridge (shared-secret)
    path("push/", bridge_push, name="mt5-push"),
    path("orders/pending/", bridge_pending_orders, name="mt5-pending"),
    path("orders/<int:order_id>/ack/", bridge_ack_order, name="mt5-ack"),
    # frontend (user token)
    path("account/", account_view, name="mt5-account"),
    path("order/", place_order, name="mt5-order"),
    path("orders/", my_orders, name="mt5-my-orders"),
]
