"""LBank REST API clients — SPOT (real account) and FUTURES/CONTRACT.

Signing (both APIs) follows LBank's documented v2/v1 process for HmacSHA256:
sort every request param (incl. api_key, signature_method, timestamp, echostr)
-> MD5 the "k=v&k=v" string as UPPERCASE hex -> HMAC-SHA256 that digest with
the secret key -> LOWERCASE hex. A 32-char secret is an HMAC shared secret
(RSA private keys are long PKCS8/PEM blobs), so these clients sign with
HmacSHA256.

Two separate services:
  * SPOT     -> https://api.lbkex.com , content-type x-www-form-urlencoded,
               auth params travel in the POST body.
  * FUTURES  -> https://lbkperp.lbank.com , content-type application/json,
               timestamp/signature_method/echostr ALSO travel as HTTP headers
               and must match the signed values.

IMPORTANT (real money): LBank documents only the PUBLIC futures endpoints
(market data). The private futures trading endpoints (open/close position,
set leverage) are not published in a verifiable form, so futures ORDER
placement is intentionally NOT implemented here — it raises rather than guess
a leveraged real-money request. Futures market data and (best-effort) account
read are wired up.
"""
import hashlib
import hmac
import json
import random
import string
import time
from datetime import datetime, timedelta

import requests
from django.conf import settings


class LBankError(Exception):
    """Raised with LBank's own error code/message so the caller can show it."""


# ----------------------------------------------------------------------------
# shared signing helpers
# ----------------------------------------------------------------------------
def _echostr(length=35):
    return "".join(random.choices(string.ascii_letters + string.digits, k=length))


def _prepared_str(params):
    """sorted 'k=v&k=v' -> MD5 hex UPPERCASE (LBank's 'preparedStr')."""
    query_string = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    return hashlib.md5(query_string.encode()).hexdigest().upper()


def _hmac_sha256(prepared_str, secret_key):
    """HMAC-SHA256(preparedStr, secret) -> LOWERCASE hex. The final HMAC MUST
    be lowercase; returning it uppercase is what caused the 10007 'Invalid
    signature'."""
    return hmac.new(secret_key.encode(), prepared_str.encode(), hashlib.sha256).hexdigest()


# Spot order status codes -> human labels (docs: orders_info_history.do)
_ORDER_STATUS = {
    -1: "cancelled",
    0: "unfilled",
    1: "partially_filled",
    2: "filled",
    3: "partially_filled_cancelled",
    4: "cancelling",
}


def _num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


# ============================================================================
# SPOT
# ============================================================================
class LBankClient:
    """LBank SPOT (real account). Endpoints verified against LBank API v2 docs
    (https://www.lbank.com/docs/index.html)."""

    def __init__(self, api_key=None, secret_key=None, base_url=None):
        # .strip() guards against a trailing space/newline from a copy-paste
        # into .env — that alone breaks every signature.
        self.api_key = (api_key or settings.LBANK_API_KEY or "").strip()
        self.secret_key = (secret_key or settings.LBANK_SECRET_KEY or "").strip()
        self.base_url = (base_url or settings.LBANK_BASE_URL).rstrip("/")

    @property
    def configured(self):
        return bool(self.api_key and self.secret_key)

    # ---- internals ----
    def _signed_params(self, extra=None):
        params = {
            "api_key": self.api_key,
            "signature_method": "HmacSHA256",
            "timestamp": str(int(time.time() * 1000)),
            "echostr": _echostr(),
        }
        if extra:
            params.update({k: v for k, v in extra.items() if v is not None})
        params["sign"] = _hmac_sha256(_prepared_str(params), self.secret_key)
        return params

    def _post(self, path, extra=None):
        if not self.configured:
            raise LBankError("LBank API key/secret not configured (.env).")
        params = self._signed_params(extra)
        try:
            r = requests.post(f"{self.base_url}{path}", data=params, timeout=15)
        except requests.RequestException as exc:
            raise LBankError(f"could not reach LBank: {exc}") from exc
        try:
            data = r.json()
        except ValueError:
            raise LBankError(f"non-JSON response (HTTP {r.status_code}): {r.text[:300]}")
        # LBank error convention: {"result": "false", "error_code": N, ...}
        if isinstance(data, dict) and str(data.get("result")).lower() == "false":
            raise LBankError(f"LBank error {data.get('error_code')}: {data.get('msg', data)}")
        return data

    # ---- account ----
    def account_info(self):
        """Clean spot balances via /v2/supplement/user_info_account.do.

        Returns a normalized dict:
          {uid, canTrade, canWithdraw, canDeposit,
           balances: [{asset, free, locked, total}]}  (non-zero only, sorted)
        """
        raw = self._post("/v2/supplement/user_info_account.do")
        data = raw.get("data", {}) if isinstance(raw, dict) else {}
        balances = []
        for b in data.get("balances", []) or []:
            free = _num(b.get("free"))
            locked = _num(b.get("locked"))
            total = free + locked
            if total <= 0:
                continue
            balances.append({
                "asset": (b.get("asset") or "").upper(),
                "free": free,
                "locked": locked,
                "total": total,
            })
        balances.sort(key=lambda x: x["total"], reverse=True)
        return {
            "uid": data.get("uid"),
            "canTrade": data.get("canTrade"),
            "canWithdraw": data.get("canWithdraw"),
            "canDeposit": data.get("canDeposit"),
            "balances": balances,
        }

    # kept for backward-compat; test_connection / old callers use this.
    def balance(self):
        return self.account_info()

    def wallet_currencies(self):
        """Per-coin deposit/withdrawal + multi-chain info
        (/v2/supplement/user_info.do). Returns LBank's raw 'data' list."""
        raw = self._post("/v2/supplement/user_info.do")
        return raw.get("data", []) if isinstance(raw, dict) else []

    # ---- orders / trades ----
    def order_history(self, symbol, current_page=1, page_length=100, status=None):
        """All orders for a symbol via /v2/spot/trade/orders_info_history.do.

        NOTE: no status filter by default (LBank then returns cancelled +
        fully-filled orders). The previous code hard-coded status=-1, which
        silently returned ONLY cancelled orders.
        """
        extra = {
            "symbol": symbol,
            "current_page": current_page,
            "page_length": page_length,
        }
        if status is not None:
            extra["status"] = status
        raw = self._post("/v2/spot/trade/orders_info_history.do", extra)
        return self._normalize_orders(raw)

    def open_orders(self, symbol, current_page=1, page_length=100):
        """Current pending orders via /v2/supplement/orders_info_no_deal.do."""
        raw = self._post("/v2/supplement/orders_info_no_deal.do", {
            "symbol": symbol, "current_page": current_page, "page_length": page_length,
        })
        return self._normalize_orders(raw)

    def order_info(self, symbol, order_id):
        """Single order via /v2/spot/trade/orders_info.do."""
        raw = self._post("/v2/spot/trade/orders_info.do", {
            "symbol": symbol, "orderId": order_id,
        })
        data = raw.get("data") if isinstance(raw, dict) else None
        return self._order_row(data) if isinstance(data, dict) else None

    def transaction_history(self, symbol, start_time=None, end_time=None, limit=100):
        """Actual executed fills via /v2/supplement/transaction_history.do.

        This is the true "past trades" list (price/qty/fee per fill), not the
        order log. Time format is yyyy-MM-dd (UTC+8); the query window LBank
        allows is max 2 days, so we default to yesterday->today.
        """
        if not start_time:
            start_time = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
        if not end_time:
            end_time = datetime.utcnow().strftime("%Y-%m-%d")
        raw = self._post("/v2/supplement/transaction_history.do", {
            "symbol": symbol, "startTime": start_time, "endTime": end_time, "limit": limit,
        })
        rows = raw.get("data", []) if isinstance(raw, dict) else []
        trades = []
        for tr in rows or []:
            trades.append({
                "symbol": tr.get("symbol"),
                "orderId": tr.get("orderId"),
                "tradeId": tr.get("id"),
                "price": _num(tr.get("price")),
                "qty": _num(tr.get("qty")),
                "quoteQty": _num(tr.get("quoteQty")),
                "commission": _num(tr.get("commission")),
                "side": "buy" if tr.get("isBuyer") else "sell",
                "role": "maker" if tr.get("isMaker") else "taker",
                "time": tr.get("time"),
            })
        trades.sort(key=lambda x: x.get("time") or 0, reverse=True)
        return trades

    @staticmethod
    def _order_row(o):
        status = o.get("status")
        try:
            status_int = int(status)
        except (TypeError, ValueError):
            status_int = None
        return {
            "orderId": o.get("orderId"),
            "clientOrderId": o.get("clientOrderId"),
            "symbol": o.get("symbol"),
            "type": o.get("type"),
            "price": _num(o.get("price")),
            "origQty": _num(o.get("origQty")),
            "executedQty": _num(o.get("executedQty")),
            "cummulativeQuoteQty": _num(o.get("cummulativeQuoteQty")),
            "status": status_int,
            "status_label": _ORDER_STATUS.get(status_int, str(status)),
            "time": o.get("time"),
            "updateTime": o.get("updateTime"),
        }

    def _normalize_orders(self, raw):
        data = raw.get("data", {}) if isinstance(raw, dict) else {}
        orders = data.get("orders", []) if isinstance(data, dict) else []
        rows = [self._order_row(o) for o in (orders or [])]
        rows.sort(key=lambda x: x.get("time") or 0, reverse=True)
        return {
            "total": data.get("total") if isinstance(data, dict) else None,
            "current_page": data.get("current_page") if isinstance(data, dict) else None,
            "orders": rows,
        }

    # ---- trading (real money) ----
    def place_order(self, symbol, order_type, price, amount, custom_id=None):
        """POST /v2/supplement/create_order.do.
        order_type: buy | sell | buy_market | sell_market | buy_maker |
                    sell_maker | buy_ioc | sell_ioc | buy_fok | sell_fok.
        Market rules: buy_market -> price is the QUOTE amount to spend;
                      sell_market -> amount is the BASE quantity to sell.
        """
        return self._post("/v2/supplement/create_order.do", {
            "symbol": symbol, "type": order_type, "price": price,
            "amount": amount, "custom_id": custom_id,
        })

    def cancel_order(self, symbol, order_id):
        """POST /v2/supplement/cancel_order.do. Param is 'orderId' (the old
        code sent 'order_id', which LBank ignores)."""
        return self._post("/v2/supplement/cancel_order.do", {
            "symbol": symbol, "orderId": order_id,
        })

    def test_connection(self):
        """Cheapest signed call that proves keys + signing work."""
        return self.account_info()

    # ---- diagnostics ----
    def diagnostics(self):
        """SAFE debug info — never the secret itself."""
        def mask(s):
            if not s:
                return None
            if len(s) <= 8:
                return "*" * len(s)
            return f"{s[:4]}…{s[-4:]} (len {len(s)})"

        looks_like_rsa = ("BEGIN" in (self.secret_key or "") or len(self.secret_key or "") > 100)
        return {
            "api_key_preview": mask(self.api_key),
            "secret_key_preview": mask(self.secret_key),
            "base_url": self.base_url,
            "sign_method": "HmacSHA256",
            "secret_key_looks_like_rsa": looks_like_rsa,
        }


# ============================================================================
# FUTURES / CONTRACT
# ============================================================================
class LBankFuturesClient:
    """LBank CONTRACT (perpetual futures) API — https://lbkperp.lbank.com.

    Public market data + best-effort read-only account. Order placement is
    intentionally not implemented (see module docstring). Endpoints verified
    against https://www.lbank.com/docs/contract.html:
      pub/getTime, pub/instrument, pub/marketData, pub/marketOrder, prv/account
    """

    PUBLIC = "/cfd/openApi/v1/pub"
    PRIVATE = "/cfd/openApi/v1/prv"

    def __init__(self, api_key=None, secret_key=None, base_url=None, product_group="SwapU"):
        self.api_key = (api_key or getattr(settings, "LBANK_API_KEY", "") or "").strip()
        self.secret_key = (secret_key or getattr(settings, "LBANK_SECRET_KEY", "") or "").strip()
        self.base_url = (base_url or getattr(settings, "LBANK_FUTURES_BASE_URL",
                                             "https://lbkperp.lbank.com")).rstrip("/")
        self.product_group = product_group  # SwapU = USDT-margined perpetual

    @property
    def configured(self):
        return bool(self.api_key and self.secret_key)

    # ---- public (no auth) ----
    def _get_public(self, path, params=None):
        try:
            r = requests.get(f"{self.base_url}{path}", params=params or {}, timeout=15)
            data = r.json()
        except requests.RequestException as exc:
            raise LBankError(f"could not reach LBank futures: {exc}") from exc
        except ValueError:
            raise LBankError(f"futures non-JSON response (HTTP {r.status_code})")
        self._raise_on_error(data)
        return data

    def get_time(self):
        return self._get_public(f"{self.PUBLIC}/getTime")

    def instruments(self):
        """Contract spec list (min/max size, tick, default leverage, ...)."""
        raw = self._get_public(f"{self.PUBLIC}/instrument",
                               {"productGroup": self.product_group})
        return raw.get("data", raw) if isinstance(raw, dict) else raw

    def market_data(self):
        """Ticker list for all contracts: last/mark price, funding, 24h."""
        raw = self._get_public(f"{self.PUBLIC}/marketData",
                               {"productGroup": self.product_group})
        rows = raw.get("data", raw) if isinstance(raw, dict) else raw
        out = []
        for m in rows or []:
            out.append({
                "symbol": m.get("symbol"),
                "last": _num(m.get("lastPrice")),
                "mark": _num(m.get("markedPrice")),
                "open": _num(m.get("openPrice")),
                "high": _num(m.get("highestPrice")),
                "low": _num(m.get("lowestPrice")),
                "volume": _num(m.get("volume")),
                "turnover": _num(m.get("turnover")),
                "fundingRate": _num(m.get("prePositionFeeRate")),
            })
        return out

    def order_book(self, symbol, depth=10):
        raw = self._get_public(f"{self.PUBLIC}/marketOrder",
                               {"symbol": symbol, "depth": depth})
        return raw.get("data", raw) if isinstance(raw, dict) else raw

    # ---- private (signed, read-only) ----
    def _signed_get(self, path, extra=None):
        if not self.configured:
            raise LBankError("LBank futures API key/secret not configured (.env).")
        ts = str(int(time.time() * 1000))
        echo = _echostr()
        params = {
            "api_key": self.api_key,
            "signature_method": "HmacSHA256",
            "timestamp": ts,
            "echostr": echo,
        }
        if extra:
            params.update({k: v for k, v in extra.items() if v is not None})
        params["sign"] = _hmac_sha256(_prepared_str(params), self.secret_key)
        # Futures also requires these three in the HTTP headers, matching sign.
        headers = {
            "Content-Type": "application/json",
            "timestamp": ts,
            "signature_method": "HmacSHA256",
            "echostr": echo,
        }
        try:
            r = requests.get(f"{self.base_url}{path}", params=params,
                             headers=headers, timeout=15)
            data = r.json()
        except requests.RequestException as exc:
            raise LBankError(f"could not reach LBank futures: {exc}") from exc
        except ValueError:
            raise LBankError(f"futures non-JSON response (HTTP {r.status_code})")
        self._raise_on_error(data)
        return data

    def account(self, asset="USDT"):
        """Read futures account (margin/balance) via prv/account.
        Response schema isn't fully published, so we return LBank's raw 'data'
        untouched rather than guess field names."""
        raw = self._signed_get(f"{self.PRIVATE}/account",
                               {"asset": asset, "productGroup": self.product_group})
        return raw.get("data", raw) if isinstance(raw, dict) else raw

    def test_connection(self):
        return self.account()

    # ---- trading: deliberately unavailable ----
    def place_order(self, *args, **kwargs):
        raise LBankError(
            "Futures order placement is not enabled: LBank does not publish a "
            "verifiable private contract-trading endpoint, and this app will "
            "not send a leveraged real-money order built on guesswork. Provide "
            "the official private futures docs to enable it."
        )

    close_position = place_order
    set_leverage = place_order

    # ---- error handling ----
    @staticmethod
    def _raise_on_error(data):
        if not isinstance(data, dict):
            return
        # success envelope: {result, error_code, msg, data, success}
        ok = data.get("success")
        code = data.get("error_code")
        if ok is False or (code not in (0, "0", None) and str(data.get("result")).lower() == "false"):
            raise LBankError(f"LBank futures error {code}: {data.get('msg', data)}")
