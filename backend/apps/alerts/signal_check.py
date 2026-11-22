"""User-scoped alerts from the same guarded decision pipeline as the scalp API."""
import hashlib
import logging
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from .push import broadcast, vapid_configured

log = logging.getLogger('smartpips.alerts')


def _limit_note(decision):
    plan = decision.get('entry_plan') or {}
    if plan.get('type') != 'limit':
        return ''
    minutes = plan.get('valid_for_minutes')
    source = 'trend pullback, ' if decision.get('signal_source') == 'playbook' else ''
    return (f"LIMIT ({source}valid ~{minutes} min) " if minutes else f"LIMIT ({source}pullback) ")


def _alert_mode(user):
    """'safe' follows the user's own playbook strategy; 'trend' is the playbook alone."""
    if not getattr(settings, 'ALERTS_VALIDATED_ONLY', True):
        return 'safe'
    from apps.strategy.config_models import Strategy
    strategy = Strategy.objects.filter(user=user, is_active=True, archived=False).first()
    version = strategy.current_version() if strategy else None
    return 'safe' if version and (version.risk or {}).get('signal_source') == 'playbook' else 'trend'


def _same_setup_alerted(user, symbol, timeframe, signal, decision):
    """A playbook limit stays valid for N bars: flicker inside that window is one setup."""
    if decision.get('signal_source') != 'playbook':
        return False
    from apps.strategy.trend_pullback import LIMIT_VALID_BARS, TF_SECONDS
    from .models import Notification
    since = timezone.now() - timedelta(seconds=LIMIT_VALID_BARS * TF_SECONDS.get(timeframe, 300))
    return Notification.objects.filter(
        user=user, category='signal', symbol=symbol, created__gte=since,
        meta__timeframe=timeframe, meta__signal=signal,
        meta__strategy_version_id=decision.get('strategy_version_id')).exists()


def _breakeven_note(decision):
    be = (decision.get('exit_plan') or {}).get('breakeven')
    return f" · at {be['trigger_price']} move SL to {be['stop_price']}" if be else ''


def evaluate_and_alert(symbol, timeframe):
    """Notify once per user's final-signal transition and strategy version.

    Safe mode, completed candles, selected strategy, news and user risk gates
    come from decide(). No user-independent base signal can authorize a push.
    Internal notifications work without VAPID. No trading orders are placed.
    """
    from apps.strategy.decision import decide
    from .gating import watchers, trade_alerts_muted, loss_limit_state
    from .models import UserSignalState
    from .notify import notify

    symbol = symbol.strip().upper()
    sent = 0
    for user in watchers(symbol):
        try:
            mode = _alert_mode(user)
            decision = decide(symbol, timeframe=timeframe, user=user, mode=mode)
            signal = decision.get('signal', 'wait')
            score = int(decision.get('score') or 0)
            why = _wait_reason(decision) if signal not in ('buy', 'sell') else ''
            # A below-threshold or muted setup is WAIT for this recipient, not
            # an emitted signal. Eligibility changes can then produce a fresh alert.
            eligible = any(u.pk == user.pk for u in watchers(symbol, score=score, timeframe=timeframe))
            blocked = trade_alerts_muted(user)
            if signal in ('buy', 'sell') and not eligible:
                why = f'score {score} below your minimum for this symbol'
            if blocked:
                reason = (loss_limit_state(user).get('reason') or 'daily risk guard')
                if signal in ('buy', 'sell'):
                    why = f"muted: {reason}"
                announce_mute(user, reason)
            if not eligible or blocked:
                signal = 'wait'
            context = hashlib.sha256(
                f"{decision.get('strategy_id')}:{decision.get('strategy_version_id')}:{mode}".encode()
            ).hexdigest()
            note = None
            with transaction.atomic():
                state, _ = UserSignalState.objects.get_or_create(
                    user=user, symbol=symbol, timeframe=timeframe)
                state = UserSignalState.objects.select_for_update().get(pk=state.pk)
                changed = signal in ('buy', 'sell') and (
                    signal != state.last_signal or context != state.context)
                if changed and _same_setup_alerted(user, symbol, timeframe, signal, decision):
                    changed = False
                if changed:
                    word = signal.upper()
                    payload = {
                        'title': f'SmartPips · {symbol} {timeframe}',
                        'body': (f"{word} setup (score {score}, R:R {decision.get('risk_reward')}). "
                                 f"{_limit_note(decision)}"
                                 f"Entry {decision.get('entry')} · SL {decision.get('stop_loss')} "
                                 f"· TP {decision.get('take_profit')}{_breakeven_note(decision)}"),
                        'url': f'/app/scalp?symbol={symbol}&tf={timeframe}&quick=1',
                        'symbol': symbol, 'timeframe': timeframe, 'signal': signal,
                        'entry': decision.get('entry'), 'sl': decision.get('stop_loss'),
                        'tp': decision.get('take_profit'), 'score': score,
                        'strategy_id': decision.get('strategy_id'),
                        'strategy_version_id': decision.get('strategy_version_id'),
                        'strategy_name': decision.get('strategy_name'), 'mode': mode,
                        'generated_at': decision.get('generated_at'),
                    }
                    note = notify(user, title=payload['title'], body=payload['body'],
                                  category='signal', level='success' if signal == 'buy' else 'danger',
                                  url=payload['url'], symbol=symbol, meta=payload, push=False)
                    # Risk can change between decide() and notify(). Never latch
                    # a signal which was suppressed by the final notification gate.
                    if note is None:
                        signal = 'wait'
                if signal in ('buy', 'sell') and not changed:
                    why = f'{signal.upper()} still active — already notified'
                elif note is not None:
                    why = f'notified: {signal.upper()}'
                state.last_signal = signal
                state.last_score = score
                state.context = context
                state.last_checked = timezone.now()
                state.last_reason = (why or '')[:200]
                state.save(update_fields=['last_signal', 'last_score', 'context', 'updated',
                                          'last_checked', 'last_reason'])
            if note is not None:
                if vapid_configured():
                    try:
                        sent += broadcast({**payload, 'notificationId': note.pk}, users=[user]) or 0
                    except Exception:
                        log.exception('push failed; internal notification %s remains stored', note.pk)
                log.info('%s %s user_id=%s final=%s strategy=%s notification=%s',
                         symbol, timeframe, user.pk, signal, decision.get('strategy_id'), note.pk)
        except Exception:
            # A bad strategy/account/provider for one user cannot leak or stop
            # notifications for other users. Failed decisions never send a push.
            log.exception('signal evaluation failed: %s %s user_id=%s', symbol, timeframe, user.pk)
    return sent


def _wait_reason(decision):
    """One short, human-readable reason why this pass produced no signal."""
    reasons = decision.get('wait_reasons') or []
    if reasons:
        return str(reasons[0].get('message') or reasons[0].get('code') or '')[:200]
    return str(decision.get('reason') or 'no setup')[:200]


def announce_mute(user, reason):
    """Tell the user ONCE per UTC day that trade alerts are paused, and why.

    The mute itself already existed; it was silent, so a paused day looked like
    a broken notification system."""
    from .models import Notification
    from .notify import notify
    start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    if Notification.objects.filter(user=user, created__gte=start,
                                   meta__kind='alerts_muted').exists():
        return None
    return notify(user, title='هشدار سیگنال‌ها امروز متوقف شد',
                  body=(f'دلیل: {reason}. هشدارهای ورود تا پایان امروز (UTC) ارسال نمی‌شوند؛ '
                        'هشدارهای ریسک و پوزیشن همچنان فعال‌اند.'),
                  category='risk', level='warning', url='/app/notifications',
                  meta={'kind': 'alerts_muted', 'reason': reason}, force=True)
