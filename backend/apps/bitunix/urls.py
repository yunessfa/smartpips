from django.urls import path

from .views import (
    status_view, self_test_view, account_view, positions_view, orders_view,
    place_order_view, close_position_view, cancel_orders_view,
    leverage_view, margin_mode_view, depth_view, ticker_view, klines_view,
)

urlpatterns = [
    path("status/", status_view),
    path("self_test/", self_test_view),
    path("account/", account_view),
    path("positions/", positions_view),
    path("orders/", orders_view),
    path("order/", place_order_view),
    path("close/", close_position_view),
    path("cancel/", cancel_orders_view),
    path("leverage/", leverage_view),
    path("margin_mode/", margin_mode_view),
    path("depth/", depth_view),
    path("ticker/", ticker_view),
    path("klines/", klines_view),
]
