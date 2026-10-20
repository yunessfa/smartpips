"""
cTrader bridge — a long-running service that connects to the cTrader Open API and:
  - authenticates the application + the trading account
  - resolves the gold/silver symbol IDs
  - subscribes to live spot quotes  -> stores into MT5Quote
  - periodically pulls 5m/15m candles -> stores into MT5Candles (engine reads these)
  - pulls account info -> stores into MT5Account
  - polls the MT5Order queue and sends real orders with SL/TP, then acks them

Run it as its own process (NOT inside gunicorn):

    python manage.py ctrader_bridge

Keep it alive with systemd (see deploy/smartpips-ctrader.service).

You must first connect via OAuth (visit /api/ctrader/connect/) so a CTraderToken
row exists with an access_token and account_id.
"""
import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

# canonical symbol -> our internal name
TF_TO_PERIOD = {"5m": "M5", "15m": "M15"}


class Command(BaseCommand):
    help = "Run the cTrader Open API bridge (live data + trade execution)."

    def handle(self, *args, **options):
        try:
            from ctrader_open_api import Client, Protobuf, TcpProtocol, EndPoints
            from ctrader_open_api.messages.OpenApiCommonMessages_pb2 import (
                ProtoHeartbeatEvent,
            )
            from ctrader_open_api.messages.OpenApiMessages_pb2 import (
                ProtoOAApplicationAuthReq, ProtoOAAccountAuthReq,
                ProtoOASymbolsListReq, ProtoOASubscribeSpotsReq,
                ProtoOAGetTrendbarsReq, ProtoOATraderReq, ProtoOANewOrderReq,
                ProtoOASpotEvent,
            )
            # account-list request has had two names across lib versions
            try:
                from ctrader_open_api.messages.OpenApiMessages_pb2 import (
                    ProtoOAGetAccountListByAccessTokenReq as _AcctListReq)
            except ImportError:
                from ctrader_open_api.messages.OpenApiMessages_pb2 import (
                    ProtoOAGetAccountsByAccessTokenReq as _AcctListReq)
            from ctrader_open_api.messages.OpenApiModelMessages_pb2 import (
                ProtoOATrendbarPeriod, ProtoOAOrderType, ProtoOATradeSide,
            )
            from twisted.internet import reactor, task
        except ImportError as exc:
            self.stderr.write(f"ctrader-open-api not installed or import failed: {exc}")
            self.stderr.write("Run: pip install ctrader-open-api")
            return

        from apps.ctrader.models import CTraderToken
        from apps.mt5.models import MT5Account, MT5Quote, MT5Candles, MT5Order

        token = CTraderToken.objects.filter(id=1).first()
        if not token or not token.is_valid():
            self.stderr.write("No valid cTrader token/account yet. "
                              "Visit /api/ctrader/connect/ to authorize. Waiting...")
            # Don't hammer systemd with restarts — wait and re-check for a token.
            for _ in range(60):  # up to ~5 minutes, then let systemd restart us
                time.sleep(5)
                token = CTraderToken.objects.filter(id=1).first()
                if token and token.is_valid():
                    self.stdout.write("Token found, connecting...")
                    break
            else:
                return

        host = (EndPoints.PROTOBUF_LIVE_HOST
                if "live" in settings.CTRADER_HOST else EndPoints.PROTOBUF_DEMO_HOST)
        client = Client(host, EndPoints.PROTOBUF_PORT, TcpProtocol)

        state = {
            "account_id": int(token.account_id),
            "wanted_login": int(token.account_id),  # the platform login we picked
            "access_token": token.access_token,
            "symbol_ids": {},          # canonical -> symbolId
            "symbol_names": {settings.CTRADER_GOLD_SYMBOL.upper(): "XAUUSD",
                             settings.CTRADER_SILVER_SYMBOL.upper(): "XAGUSD"},
            "digits": {},
        }

        # ----- helpers to persist into the shared MT5 tables -----
        def save_quote(canonical, bid, ask):
            MT5Quote.objects.update_or_create(
                symbol=canonical,
                defaults={"bid": bid, "ask": ask, "spread": round(ask - bid, 5)})

        # remember the last mid-price per symbol to classify tick direction
        _last_mid = {}

        def save_tick(canonical, bid, ask):
            """Store a tick and classify aggressor side from mid-price movement,
            so the engine can compute REAL order-flow delta for metals."""
            from apps.mt5.models import MT5Tick
            mid = (bid + ask) / 2.0
            prev = _last_mid.get(canonical)
            direction = 0
            if prev is not None:
                direction = 1 if mid > prev else -1 if mid < prev else 0
            _last_mid[canonical] = mid
            MT5Tick.objects.create(symbol=canonical, bid=bid, ask=ask,
                                   tick_dir=direction)
            # keep only the most recent ~600 ticks per symbol (rolling buffer)
            if MT5Tick.objects.filter(symbol=canonical).count() > 700:
                old_ids = list(MT5Tick.objects.filter(symbol=canonical)
                               .order_by("-ts").values_list("id", flat=True)[600:])
                if old_ids:
                    MT5Tick.objects.filter(id__in=old_ids).delete()

        def save_account(trader):
            # cTrader sends money in cents; some builds use balanceInCents.
            raw = getattr(trader, "balance", 0) or getattr(trader, "balanceInCents", 0)
            bal = raw / 100.0
            self.stdout.write(f"trader balance raw={raw} -> {bal} "
                              f"login={getattr(trader,'traderLogin','?')}")
            MT5Account.objects.update_or_create(
                login=str(state.get("wanted_login") or state["account_id"]),
                defaults={
                    "broker": "cTrader", "currency": "USD",
                    "balance": bal, "equity": bal,
                    "leverage": getattr(trader, "leverageInCents", 0) // 100,
                    "gold_symbol": settings.CTRADER_GOLD_SYMBOL,
                    "silver_symbol": settings.CTRADER_SILVER_SYMBOL,
                })

        def save_candles(canonical, timeframe, bars):
            rows = []
            for b in bars:
                low = b.low / 100000.0
                rows.append({
                    "time": b.utcTimestampInMinutes * 60,
                    "open": (low + b.deltaOpen / 100000.0),
                    "high": (low + b.deltaHigh / 100000.0),
                    "low": low,
                    "close": (low + b.deltaClose / 100000.0),
                    "volume": b.volume,
                })
            if rows:
                MT5Candles.objects.update_or_create(
                    symbol=canonical, timeframe=timeframe, defaults={"candles": rows})

        # ----- protobuf request senders -----
        def send(msg):
            return client.send(msg)

        def on_app_auth(_):
            # Ask cTrader which accounts this token can access. The number you see
            # in the platform (traderLogin, e.g. 9046893) is NOT the same as the
            # ctidTraderAccountId the API needs — so we resolve it here.
            req = _AcctListReq()
            req.accessToken = state["access_token"]
            send(req)

        def do_account_auth(ctid):
            state["account_id"] = ctid
            req = ProtoOAAccountAuthReq()
            req.ctidTraderAccountId = ctid
            req.accessToken = state["access_token"]
            send(req)

        def on_account_auth(_):
            # got account auth -> list symbols
            req = ProtoOASymbolsListReq()
            req.ctidTraderAccountId = state["account_id"]
            send(req)
            # also pull trader (account) info periodically
            task.LoopingCall(pull_trader).start(15, now=True)
            task.LoopingCall(pull_candles).start(20, now=False)
            task.LoopingCall(poll_orders).start(5, now=False)

        def pull_trader():
            req = ProtoOATraderReq()
            req.ctidTraderAccountId = state["account_id"]
            send(req)

        def pull_candles():
            for canonical, tf in (("XAUUSD", "5m"), ("XAUUSD", "15m"), ("XAUUSD", "1h"),
                                  ("XAGUSD", "5m"), ("XAGUSD", "15m")):
                sid = state["symbol_ids"].get(canonical)
                if not sid:
                    continue
                req = ProtoOAGetTrendbarsReq()
                req.ctidTraderAccountId = state["account_id"]
                req.symbolId = sid
                period_map = {"5m": ProtoOATrendbarPeriod.M5,
                              "15m": ProtoOATrendbarPeriod.M15,
                              "1h": ProtoOATrendbarPeriod.H1}
                req.period = period_map.get(tf, ProtoOATrendbarPeriod.M5)
                now_min = int(time.time() // 60)
                back = 60 * 24 * 5 if tf == "1h" else 60 * 24  # more history for 1h
                req.fromTimestamp = (now_min - back) * 60000
                req.toTimestamp = now_min * 60000
                send(req)

        def poll_orders():
            pending = list(MT5Order.objects.filter(status="pending").order_by("created")[:10])
            for o in pending:
                sid = state["symbol_ids"].get(o.symbol)
                if not sid:
                    o.status = "error"; o.message = "symbol not resolved"; o.save()
                    continue
                req = ProtoOANewOrderReq()
                req.ctidTraderAccountId = state["account_id"]
                req.symbolId = sid
                req.orderType = ProtoOAOrderType.MARKET
                req.tradeSide = (ProtoOATradeSide.BUY if o.action == "buy"
                                 else ProtoOATradeSide.SELL)
                req.volume = int(max(o.volume, 0.01) * 100)  # cTrader volume in units/100
                if o.stop_loss:
                    req.stopLoss = float(o.stop_loss)
                if o.take_profit:
                    req.takeProfit = float(o.take_profit)
                send(req)
                o.status = "filled"; o.message = "sent to cTrader"; o.save()

        # ----- inbound message router -----
        def on_message(_, message):
            payload = Protobuf.extract(message)
            name = type(payload).__name__
            # trace every inbound message name so we can see what cTrader sends
            self.stdout.write(f"« {name}")
            # surface any explicit error from cTrader (e.g. bad secret, bad token)
            if name in ("ProtoOAErrorRes", "ProtoErrorRes"):
                code = getattr(payload, "errorCode", "?")
                desc = getattr(payload, "description", "")
                self.stderr.write(f"cTrader ERROR: {code} — {desc}")
                return
            if name == "ProtoOAApplicationAuthRes":
                self.stdout.write("app authenticated ✓")
                on_app_auth(payload)
            elif name in ("ProtoOAGetAccountListByAccessTokenRes",
                          "ProtoOAGetAccountsByAccessTokenRes"):
                # find the account whose login matches what the admin picked;
                # otherwise use the first one. Use its ctidTraderAccountId.
                accounts = list(payload.ctidTraderAccount)
                if not accounts:
                    self.stderr.write("no trading accounts on this token")
                    return
                want_login = state.get("wanted_login")
                chosen = None
                for acc in accounts:
                    self.stdout.write(f"  account: login={getattr(acc,'traderLogin','?')} "
                                      f"ctid={acc.ctidTraderAccountId} "
                                      f"live={getattr(acc,'isLive',False)}")
                    if want_login and str(getattr(acc, "traderLogin", "")) == str(want_login):
                        chosen = acc
                if chosen is None:
                    chosen = accounts[0]
                self.stdout.write(f"using ctidTraderAccountId={chosen.ctidTraderAccountId} "
                                  f"(login {getattr(chosen,'traderLogin','?')})")
                do_account_auth(chosen.ctidTraderAccountId)
            elif name == "ProtoOAAccountAuthRes":
                on_account_auth(payload)
            elif name == "ProtoOASymbolsListRes":
                for s in payload.symbol:
                    nm = s.symbolName.upper()
                    canonical = state["symbol_names"].get(nm)
                    if canonical:
                        state["symbol_ids"][canonical] = s.symbolId
                # subscribe to spot quotes for resolved symbols
                if state["symbol_ids"]:
                    req = ProtoOASubscribeSpotsReq()
                    req.ctidTraderAccountId = state["account_id"]
                    for sid in state["symbol_ids"].values():
                        req.symbolId.append(sid)
                    send(req)
                    self.stdout.write(f"resolved symbols: {state['symbol_ids']}")
            elif name == "ProtoOASpotEvent":
                # map symbolId back to canonical
                inv = {v: k for k, v in state["symbol_ids"].items()}
                canonical = inv.get(payload.symbolId)
                if canonical and payload.bid and payload.ask:
                    bid_p, ask_p = payload.bid / 100000.0, payload.ask / 100000.0
                    save_quote(canonical, bid_p, ask_p)
                    save_tick(canonical, bid_p, ask_p)
            elif name == "ProtoOAGetTrendbarsRes":
                inv = {v: k for k, v in state["symbol_ids"].items()}
                canonical = inv.get(payload.symbolId)
                tf_map = {ProtoOATrendbarPeriod.M5: "5m",
                          ProtoOATrendbarPeriod.M15: "15m",
                          ProtoOATrendbarPeriod.H1: "1h"}
                tf = tf_map.get(payload.period, "5m")
                if canonical:
                    save_candles(canonical, tf, payload.trendbar)
            elif name == "ProtoOATraderRes":
                save_account(payload.trader)

        def on_connected(_):
            self.stdout.write("cTrader connected, authenticating app...")
            req = ProtoOAApplicationAuthReq()
            req.clientId = settings.CTRADER_CLIENT_ID
            req.clientSecret = settings.CTRADER_CLIENT_SECRET
            send(req)

        def on_disconnected(_, reason):
            self.stderr.write(f"cTrader disconnected: {reason}")

        client.setConnectedCallback(on_connected)
        client.setDisconnectedCallback(on_disconnected)
        client.setMessageReceivedCallback(on_message)

        self.stdout.write(f"Starting cTrader bridge on {host} for account {state['account_id']}...")
        client.startService()
        reactor.run()
