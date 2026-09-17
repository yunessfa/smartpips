from django.urls import path

from .views import (
    status_view, balance_view, orders_view, open_orders_view, trades_view,
    place_order_view, cancel_order_view, debug_signatures_view,
    futures_market_view, futures_account_view, futures_orderbook_view,
)

urlpatterns = [
    # spot
    path("status/", status_view, name="lbank-status"),
    path("balance/", balance_view, name="lbank-balance"),
    path("orders/", orders_view, name="lbank-orders"),
    path("open_orders/", open_orders_view, name="lbank-open-orders"),
    path("trades/", trades_view, name="lbank-trades"),
    path("order/", place_order_view, name="lbank-place-order"),
    path("cancel/", cancel_order_view, name="lbank-cancel-order"),
    path("debug_signatures/", debug_signatures_view, name="lbank-debug-signatures"),
    # futures
    path("futures/market/", futures_market_view, name="lbank-futures-market"),
    path("futures/account/", futures_account_view, name="lbank-futures-account"),
    path("futures/orderbook/", futures_orderbook_view, name="lbank-futures-orderbook"),
]
