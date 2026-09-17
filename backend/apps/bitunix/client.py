"""Bitunix FUTURES REST client (https://fapi.bitunix.com).

Signing — verified against the official docs (api-docs/futures/common/sign.html):
  digest = SHA256( nonce + timestamp + api_key + queryParams + body )
  sign   = SHA256( digest + secret_key )
where
  * nonce      = random 32-char string
  * timestamp  = milliseconds
  * queryParams= query params sorted ascending by key, concatenated as
                 key1value1key2value2...  (NO '=' or '&')
  * body       = the raw compact JSON string for POSTs, "" for GETs
Headers: api-key, sign, nonce, timestamp, Content-Type: application/json.
Success envelope: {"code": 0, "data": ..., "msg": "Success"}.

qty for orders is in BASE COIN (e.g. BTC), NOT contracts — stated explicitly
in the official place_order doc. This removes the size-unit ambiguity that
blocked the LBank futures integration.

Endpoints implemented below are taken from the official docs index
(api-docs/futures/...): market/kline, market/tickers, market/depth,
market/funding_rate, market/trading_pairs, account, position/get_pending_positions,
position/get_history_positions, trade/place_order, trade/cancel_orders,
trade/get_pending_orders, trade/get_history_orders, trade/flash_close_position,
account/change_leverage, account/change_margin_mode, tpsl/position/place_order.
"""
import hashlib
import json
import random
import string
import time

import requests
from django.conf import settings


class BitunixError(Exception):
    """Raised with Bitunix's own code/message so callers can show it."""


def _nonce(n=32):
    return "".join(random.choices(string.ascii_letters + string.digits, k=n))


def _query_concat(params):
    """Query params sorted ascending by key, concatenated key+value with no
    separators — exactly as the signing doc specifies."""
    if not params:
        return ""
    return "".join(f"{k}{params[k]}" for k in sorted(params))


def sign_request(api_key, secret_key, params=None, body_json="", nonce=None, timestamp=None):
    """Return (headers, nonce, timestamp). Pure function -> unit-testable."""
    nonce = nonce or _nonce()
    timestamp = timestamp or str(int(time.time() * 1000))
    digest_input = f"{nonce}{timestamp}{api_key}{_query_concat(params)}{body_json}"
    digest = hashlib.sha256(digest_input.encode()).hexdigest()
    sign = hashlib.sha256((digest + secret_key).encode()).hexdigest()
    return {
        "api-key": api_key,
        "sign": sign,
        "nonce": nonce,
        "timestamp": timestamp,
        "Content-Type": "application/json",
    }, nonce, timestamp


class BitunixClient:
    BASE = "https://fapi.bitunix.com"

    def __init__(self, api_key=None, secret_key=None, base_url=None):
        self.api_key = (api_key or getattr(settings, "BITUNIX_API_KEY", "") or "").strip()
        self.secret_key = (secret_key or getattr(settings, "BITUNIX_SECRET_KEY", "") or "").strip()
        self.base_url = (base_url or getattr(settings, "BITUNIX_BASE_URL", self.BASE)).rstrip("/")

    @property
    def configured(self):
        return bool(self.api_key and self.secret_key)

    # ------------------------------------------------------------ plumbing --
    def _request(self, method, path, params=None, body=None, auth=False):
        params = {k: v for k, v in (params or {}).items() if v is not None}
        body_json = json.dumps(body, separators=(",", ":")) if body is not None else ""
        headers = {"Content-Type": "application/json"}
        if auth:
            if not self.configured:
                raise BitunixError("BITUNIX_API_KEY / BITUNIX_SECRET_KEY not set in .env")
            headers, _, _ = sign_request(self.api_key, self.secret_key, params, body_json)
        try:
            r = requests.request(method, f"{self.base_url}{path}", params=params,
                                 data=body_json if body is not None else None,
                                 headers=headers, timeout=15)
        except requests.RequestException as exc:
            raise BitunixError(f"could not reach Bitunix: {exc}") from exc
        try:
            data = r.json()
        except ValueError:
            raise BitunixError(f"non-JSON response (HTTP {r.status_code}): {r.text[:200]}")
        if isinstance(data, dict) and data.get("code") not in (0, "0", None):
            raise BitunixError(f"Bitunix error {data.get('code')}: {data.get('msg', data)}")
        return data.get("data", data) if isinstance(data, dict) else data

    def _get(self, path, params=None, auth=False):
        return self._request("GET", path, params=params, auth=auth)

    def _post(self, path, body=None):
        return self._request("POST", path, body=body or {}, auth=True)

    # -------------------------------------------------------- public market --
    def klines(self, symbol, interval="5m", limit=200, kline_type="LAST_PRICE",
               end_time=None):
        """Real OHLCV from Bitunix's own market — feeds the signal engine so
        signal and execution share one venue. Single page, max 200 bars."""
        params = {
            "symbol": symbol.upper(), "interval": interval,
            "limit": min(int(limit), 200), "type": kline_type,
        }
        if end_time is not None:
            params["endTime"] = int(end_time)
        rows = self._get("/api/v1/futures/market/kline", params) or []
        out = []
        for k in rows:
            try:
                out.append({
                    "time": int(int(k["time"]) // 1000),
                    "open": float(k["open"]), "high": float(k["high"]),
                    "low": float(k["low"]), "close": float(k["close"]),
                    "volume": float(k.get("baseVol") or k.get("volume") or 0),
                })
            except (KeyError, TypeError, ValueError):
                continue
        out.sort(key=lambda c: c["time"])
        return out

    def klines_paginated(self, symbol, interval="5m", limit=200, kline_type="LAST_PRICE"):
        """Fetch up to `limit` bars by paging backwards with endTime — the
        exchange caps each request at 200, which silently starved the 500-bar
        backtest window until this existed."""
        out = self.klines(symbol, interval, min(limit, 200), kline_type)
        pages = 1
        while len(out) < limit and out and pages < 6:
            oldest_ms = out[0]["time"] * 1000 - 1
            older = self.klines(symbol, interval, 200, kline_type, end_time=oldest_ms)
            older = [c for c in older if c["time"] < out[0]["time"]]
            if not older:
                break
            out = older + out
            pages += 1
        # dedupe by time, keep chronological order
        seen, dedup = set(), []
        for c in out:
            if c["time"] not in seen:
                seen.add(c["time"])
                dedup.append(c)
        return dedup[-limit:]

    def tickers(self, symbols=None):
        params = {"symbols": ",".join(s.upper() for s in symbols)} if symbols else None
        return self._get("/api/v1/futures/market/tickers", params) or []

    def last_price(self, symbol):
        rows = self.tickers([symbol])
        for t in rows:
            if (t.get("symbol") or "").upper() == symbol.upper():
                for key in ("lastPrice", "last", "close"):
                    if t.get(key) is not None:
                        return float(t[key])
        return None

    def mark_prices(self, symbols):
        """symbol -> mark price map.

        Bitunix's `position/get_pending_positions` response carries NO mark
        price, which is exactly why the REAL positions tab rendered "—" under
        Mark while demo (which computes it locally) was fine. We join the
        number in from the public tickers feed instead, falling back to index
        / last price when a pair has no separate mark.
        """
        syms = sorted({(s or "").upper().replace(":PERP", "") for s in symbols if s})
        if not syms:
            return {}
        try:
            rows = self.tickers(syms)
        except BitunixError:
            rows = []
        out = {}
        for t in rows or []:
            if not isinstance(t, dict):
                continue
            sym = (t.get("symbol") or "").upper()
            if not sym:
                continue
            for key in ("markPrice", "indexPrice", "lastPrice", "last", "close"):
                v = t.get(key)
                if v in (None, ""):
                    continue
                try:
                    out[sym] = float(v)
                except (TypeError, ValueError):
                    continue
                break
        return out

    def depth(self, symbol, limit=15):
        d = self._get("/api/v1/futures/market/depth",
                      {"symbol": symbol.upper(), "limit": str(limit)}) or {}
        def side(rows):
            out = []
            for r in rows or []:
                try:
                    out.append({"price": float(r[0]), "qty": float(r[1])})
                except (TypeError, ValueError, IndexError):
                    continue
            return out
        return {"asks": side(d.get("asks")), "bids": side(d.get("bids"))}

    def funding_rate(self, symbol):
        return self._get("/api/v1/futures/market/funding_rate", {"symbol": symbol.upper()})

    def trading_pairs(self, symbols=None):
        params = {"symbols": ",".join(s.upper() for s in symbols)} if symbols else None
        return self._get("/api/v1/futures/market/trading_pairs", params) or []

    # ------------------------------------------------------------- account --
    def account(self, margin_coin="USDT"):
        return self._get("/api/v1/futures/account", {"marginCoin": margin_coin}, auth=True)

    def pending_positions(self, symbol=None):
        return self._get("/api/v1/futures/position/get_pending_positions",
                         {"symbol": symbol.upper() if symbol else None}, auth=True) or []

    def history_positions(self, symbol=None, limit=20):
        return self._get("/api/v1/futures/position/get_history_positions",
                         {"symbol": symbol.upper() if symbol else None,
                          "limit": str(limit)}, auth=True) or []

    def pending_orders(self, symbol=None):
        return self._get("/api/v1/futures/trade/get_pending_orders",
                         {"symbol": symbol.upper() if symbol else None}, auth=True) or []

    def history_orders(self, symbol=None, limit=20):
        return self._get("/api/v1/futures/trade/get_history_orders",
                         {"symbol": symbol.upper() if symbol else None,
                          "limit": str(limit)}, auth=True) or []

    def change_leverage(self, symbol, leverage, margin_coin="USDT"):
        return self._post("/api/v1/futures/account/change_leverage", {
            "symbol": symbol.upper(), "marginCoin": margin_coin, "leverage": int(leverage)})

    def change_margin_mode(self, symbol, margin_mode="ISOLATION", margin_coin="USDT"):
        if margin_mode not in ("ISOLATION", "CROSS"):
            raise BitunixError("margin_mode must be ISOLATION or CROSS")
        return self._post("/api/v1/futures/account/change_margin_mode", {
            "symbol": symbol.upper(), "marginCoin": margin_coin, "marginMode": margin_mode})

    # -------------------------------------------------------------- trading --
    def place_order(self, symbol, side, qty, order_type="MARKET", price=None,
                    trade_side="OPEN", effect="GTC", reduce_only=False,
                    tp_price=None, sl_price=None, client_id=None):
        """POST trade/place_order. qty is BASE COIN amount (per official doc).
        side: BUY|SELL; order_type: LIMIT|MARKET; TP/SL ride on the SAME
        request (tpPrice/slPrice, MARK_PRICE trigger, MARKET execution) so
        protection lives on the exchange from the first moment."""
        side = side.upper()
        order_type = order_type.upper()
        if side not in ("BUY", "SELL"):
            raise BitunixError("side must be BUY or SELL")
        if order_type not in ("LIMIT", "MARKET"):
            raise BitunixError("orderType must be LIMIT or MARKET")
        if order_type == "LIMIT" and price is None:
            raise BitunixError("LIMIT order requires price")
        body = {
            "symbol": symbol.upper(),
            "qty": str(qty),
            "side": side,
            "tradeSide": trade_side,
            "orderType": order_type,
            "effect": effect,
            "reduceOnly": bool(reduce_only),
            "clientId": client_id or f"sp{int(time.time()*1000)}",
        }
        if price is not None:
            body["price"] = str(price)
        if tp_price is not None:
            body.update({"tpPrice": str(tp_price), "tpStopType": "MARK_PRICE",
                         "tpOrderType": "MARKET"})
        if sl_price is not None:
            body.update({"slPrice": str(sl_price), "slStopType": "MARK_PRICE",
                         "slOrderType": "MARKET"})
        return self._post("/api/v1/futures/trade/place_order", body)

    def cancel_orders(self, symbol, order_ids):
        return self._post("/api/v1/futures/trade/cancel_orders", {
            "symbol": symbol.upper(),
            "orderList": [{"orderId": str(o)} for o in order_ids]})

    def flash_close_position(self, position_id):
        """Close a position at market immediately (official flash close)."""
        return self._post("/api/v1/futures/trade/flash_close_position",
                          {"positionId": str(position_id)})

    def place_position_tpsl(self, symbol, position_id, tp_price=None, sl_price=None):
        body = {"symbol": symbol.upper(), "positionId": str(position_id)}
        if tp_price is not None:
            body.update({"tpPrice": str(tp_price), "tpStopType": "MARK_PRICE"})
        if sl_price is not None:
            body.update({"slPrice": str(sl_price), "slStopType": "MARK_PRICE"})
        return self._post("/api/v1/futures/tpsl/position/place_order", body)

    # ---------------------------------------------------------- diagnostics --
    def diagnostics(self):
        def mask(s):
            if not s:
                return None
            return f"{s[:4]}…{s[-4:]} (len {len(s)})" if len(s) > 8 else "*" * len(s)
        return {"api_key_preview": mask(self.api_key),
                "secret_key_preview": mask(self.secret_key),
                "base_url": self.base_url}

    def self_test(self):
        """Safe, read-only end-to-end checks (NO orders). Each step reports
        ok/fail so the panel can show exactly where a problem is."""
        steps = []
        def run(name, fn):
            try:
                out = fn()
                steps.append({"step": name, "ok": True,
                              "detail": (str(out)[:120] if out is not None else "ok")})
            except Exception as exc:  # noqa: BLE001 — report, don't crash
                steps.append({"step": name, "ok": False, "detail": str(exc)[:200]})
        run("public: tickers(BTCUSDT)", lambda: self.last_price("BTCUSDT"))
        run("public: klines(BTCUSDT,5m)", lambda: len(self.klines("BTCUSDT", "5m", 5)))
        run("public: depth(BTCUSDT)", lambda: len(self.depth("BTCUSDT", 5)["bids"]))
        if self.configured:
            run("private: account(USDT)", lambda: bool(self.account()))
            run("private: pending_positions", lambda: len(self.pending_positions()))
            run("private: pending_orders", lambda: len(self.pending_orders()))
        else:
            steps.append({"step": "private", "ok": False,
                          "detail": "keys not configured in .env"})
        return {"ok": all(s["ok"] for s in steps), "steps": steps}
