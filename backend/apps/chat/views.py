from rest_framework import viewsets, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.ai.models import AIProvider
from apps.ai.providers import chat_completion, AIClientError

from .models import Conversation, Message
from .serializers import (
    ConversationSerializer,
    ConversationListSerializer,
    MessageSerializer,
)
from .services import build_system_prompt, parse_assistant_reply
from .scalp import build_explanation_prompt, parse_explanation, engine_explanation


class ConversationViewSet(viewsets.ModelViewSet):
    """Conversations are scoped to the logged-in user."""

    def get_queryset(self):
        return Conversation.objects.filter(user=self.request.user)

    def get_serializer_class(self):
        if self.action == "list":
            return ConversationListSerializer
        return ConversationSerializer


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def chat(request):
    """Main chat endpoint.

    Body: { "conversation_id": <int|null>, "message": "<text>" }
    """
    user_text = (request.data.get("message") or "").strip()
    if not user_text:
        return Response(
            {"error": "Message is empty."}, status=status.HTTP_400_BAD_REQUEST
        )

    live_prices = request.data.get("live_prices") or {}

    # Figure out exactly which instrument(s) the user is asking about, and inject
    # ONLY those live prices (plus gold/silver as the app's focus). Dumping a whole
    # crypto basket every time made weak models answer about the wrong asset.
    focus_symbols = []
    try:
        from apps.market.quotes_resolver import live_prices as resolve_prices
        import re as _re

        NAMES = {"BITCOIN": "BTCUSDT", "BTC": "BTCUSDT", "ETHEREUM": "ETHUSDT",
                 "ETH": "ETHUSDT", "SOLANA": "SOLUSDT", "SOL": "SOLUSDT",
                 "BNB": "BNBUSDT", "XRP": "XRPUSDT", "RIPPLE": "XRPUSDT",
                 "GOLD": "XAUUSD", "TALA": "XAUUSD", "طلا": "XAUUSD",
                 "SILVER": "XAGUSD", "نقره": "XAGUSD"}
        text = user_text.upper()
        mentioned = set()
        for tok in _re.findall(r"[A-Z0-9]{3,15}", text):
            if tok.endswith(("USDT", "USDC")) or tok in {"XAUUSD", "XAGUSD"}:
                mentioned.add(tok)
        for name, pair in NAMES.items():
            if name.upper() in text or name in user_text:  # catch Persian names too
                mentioned.add(pair)

        focus_symbols = sorted(mentioned)
        # Inject mentioned symbols; if none mentioned, give gold/silver as defaults.
        need = focus_symbols or ["XAUUSD", "XAGUSD"]
        need = [s for s in need if s.upper() not in {k.upper() for k in live_prices}]
        resolved = resolve_prices(need)
        for k, v in resolved.items():
            live_prices.setdefault(k, v)
    except Exception:
        pass

    # If the user is asking about gold/silver, run the Decision Engine so the AI can
    # explain the ACTUAL live signal ("why buy?", "why is the stop here?") instead
    # of guessing. The engine decides; the AI only explains.
    engine_context = ""
    try:
        focus = [s for s in (focus_symbols or []) if s.upper() in ("XAUUSD", "XAGUSD")]
        if focus:
            from apps.strategy.decision import decide
            lines = []
            for sym in focus[:2]:
                d = decide(sym, "5m", user=request.user)
                if d.get("data_quality") != "none":
                    g = d.get("grade", {})
                    lines.append(
                        f"{sym}: signal={d.get('signal')} grade={g.get('grade')} "
                        f"score={d.get('score')} entry={d.get('entry')} "
                        f"SL={d.get('stop_loss')} TP={d.get('take_profit')} "
                        f"session={(d.get('session') or {}).get('name')} "
                        f"reason={d.get('reason')}")
            if lines:
                engine_context = ("\n\nLIVE ENGINE DECISION (you EXPLAIN this, never "
                                  "override it):\n" + "\n".join(lines))
    except Exception:
        pass

    provider = AIProvider.objects.filter(is_active=True).first()
    if provider is None:
        return Response(
            {"error": "No active AI provider. Configure one on the AI page."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    conversation_id = request.data.get("conversation_id")
    if conversation_id:
        conversation = Conversation.objects.filter(
            pk=conversation_id, user=request.user
        ).first()
        if conversation is None:
            return Response(
                {"error": "Conversation not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
    else:
        title = user_text[:60] + ("…" if len(user_text) > 60 else "")
        conversation = Conversation.objects.create(user=request.user, title=title)

    Message.objects.create(conversation=conversation, role="user", content=user_text)

    system = build_system_prompt(request.user, live_prices)
    if engine_context:
        system = system + engine_context
    if focus_symbols:
        system += (
            "\n\n================  FOCUS  ================\n"
            f"The user's CURRENT question is about: {', '.join(focus_symbols)}. "
            "Answer ONLY about this/these instrument(s). Do NOT switch to or quote a "
            "different asset (e.g. don't talk about Bitcoin when asked about gold). "
            "Use the matching value from the LIVE PRICES block above."
        )
    messages = [{"role": "system", "content": system}]
    # Only the last 8 messages, so an old topic doesn't drag the answer off-track.
    history = list(conversation.messages.all())
    for msg in history[-8:]:
        messages.append({"role": msg.role, "content": msg.content})

    try:
        raw_reply = chat_completion(provider, messages)
    except AIClientError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

    parsed = parse_assistant_reply(raw_reply)
    assistant_message = Message.objects.create(
        conversation=conversation,
        role="assistant",
        content=parsed.get("reply", ""),
        recommendations=parsed.get("recommendations", []),
        news_used=parsed.get("news_used", []),
    )
    conversation.save()  # bump updated_at

    return Response(
        {
            "conversation_id": conversation.id,
            "message": MessageSerializer(assistant_message).data,
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def scalp_signal(request):
    """Scalp signal for gold/silver. The Python strategy engine DECIDES; the AI only
    explains. Body: { symbol, price, timeframe, tick_series?: [..] }"""
    symbol = (request.data.get("symbol") or "XAUUSD").upper()
    from apps.market.crypto_symbols import SUPPORTED_CRYPTO
    _allowed = {"XAUUSD", "XAGUSD"} | SUPPORTED_CRYPTO
    if symbol.replace(":PERP", "") not in _allowed:
        return Response({"error": "Unsupported symbol."},
                        status=status.HTTP_400_BAD_REQUEST)

    price = request.data.get("price")
    if not price:
        return Response({"error": "No live price provided."},
                        status=status.HTTP_400_BAD_REQUEST)

    timeframe = request.data.get("timeframe") or "5m"
    import math
    try:
        price = float(price)
        if not math.isfinite(price) or price <= 0:
            raise ValueError
        for field in ("balance", "risk_pct"):
            value = request.data.get(field)
            if value is not None and (not math.isfinite(float(value)) or float(value) <= 0):
                raise ValueError
    except (TypeError, ValueError):
        return Response({"error": "Price, balance and risk must be positive finite numbers."}, status=400)
    if timeframe not in ("1m", "5m", "15m", "1h", "4h"):
        return Response({"error": "Unsupported timeframe."}, status=400)

    # The central Decision Engine runs the WHOLE pipeline (data -> structure ->
    # liquidity -> order-flow -> session -> score -> news guard -> risk sizing).
    from apps.strategy.decision import decide

    decision = decide(symbol, timeframe, user=request.user,
                      tick_series=request.data.get("tick_series"),
                      live_price=float(price),
                      balance=request.data.get("balance"),
                      risk_pct=request.data.get("risk_pct"),
                      mode=request.data.get("mode") or "safe")

    decision["symbol"] = symbol
    decision["timeframe"] = timeframe
    import secrets
    decision["decision_id"] = secrets.token_hex(12)
    decision["summary"], decision["explanation"] = engine_explanation(symbol, timeframe, decision)
    decision["explanation_source"] = "engine"
    decision["ai_explanation_status"] = "not_requested"

    # Compatibility field only: raw strength, NOT a calibrated win probability.
    try:
        from apps.trades.journal import calibrated_confidence
        g = (decision.get("grade") or {}).get("grade")
        raw_conf = decision.get("score") or 0
        decision["confidence_calibrated"] = calibrated_confidence(
            request.user, g, raw_conf)
    except Exception:
        pass

    # FAST PATH (explain=false): the engine's decision is computed in
    # milliseconds; the AI explanation call is the slow part (seconds). For
    # auto-refresh polling the frontend sets explain=false to get the signal
    # immediately — the user can still request the written explanation with a
    # normal (explain=true) call. This is the "signal arrives late" fix.
    if request.data.get("explain", True) in (False, "false", "0", 0):
        if request.data.get("prepare_explanation") is True:
            from django.core import signing
            decision["explanation_token"] = signing.dumps(
                {"user_id": request.user.pk, "decision": dict(decision)},
                salt="smartpips.scalp.explanation", compress=True)
        return Response(decision)

    decision.update(_optional_ai_explanation(decision, request.user))
    return Response(decision)


def _optional_ai_explanation(decision, user):
    """AI adds commentary, never replaces factual engine explanation/levels."""
    result = {"ai_explanation": "", "ai_summary": "", "ai_explanation_status": "disabled"}
    try:
        provider = AIProvider.objects.filter(is_active=True).first()
        if provider is not None:
            from apps.trades.profile import profile_for_prompt
            raw = chat_completion(
                provider,
                build_explanation_prompt(decision["symbol"], decision["timeframe"],
                                         decision, profile_for_prompt(user)),
                timeout=20,
            )
            summary, explanation = parse_explanation(raw)
            if not explanation.strip():
                result["ai_explanation_status"] = "empty"
            else:
                result.update(ai_summary=summary, ai_explanation=explanation,
                              ai_explanation_status="ok")
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Optional scalp explanation failed")
        result["ai_explanation_status"] = "unavailable"
    return result


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def scalp_explanation(request):
    """Explain a signed, user-bound decision. Never run the strategy again."""
    from django.core import signing
    token = request.data.get("explanation_token")
    if not isinstance(token, str) or len(token) > 120000:
        return Response({"error": "Invalid analysis snapshot."}, status=400)
    try:
        payload = signing.loads(token, salt="smartpips.scalp.explanation", max_age=120)
    except signing.BadSignature:
        return Response({"error": "Analysis snapshot expired or invalid. Request a new analysis."}, status=400)
    if payload.get("user_id") != request.user.pk:
        return Response({"error": "Analysis belongs to another user."}, status=403)
    decision = payload["decision"]
    result = _optional_ai_explanation(decision, request.user)
    return Response({"decision_id": decision["decision_id"], **result})
