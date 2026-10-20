"""User-scoped alerts from the same guarded decision pipeline as the scalp API."""
import hashlib
import logging
from django.db import transaction
from .push import broadcast, vapid_configured

log = logging.getLogger('smartpips.alerts')


def evaluate_and_alert(symbol, timeframe):
    """Notify once per user's final-signal transition and strategy version.

    Safe mode, completed candles, selected strategy, news and user risk gates
    come from decide(). No user-independent base signal can authorize a push.
    Internal notifications work without VAPID. No trading orders are placed.
    """
    from apps.strategy.decision import decide
    from .gating import watchers, trade_alerts_muted
    from .models import UserSignalState
    from .notify import notify

    symbol = symbol.strip().upper()
    sent = 0
    for user in watchers(symbol):
        try:
            decision = decide(symbol, timeframe=timeframe, user=user, mode='safe')
            signal = decision.get('signal', 'wait')
            score = int(decision.get('score') or 0)
            # A below-threshold or muted setup is WAIT for this recipient, not
            # an emitted signal. Eligibility changes can then produce a fresh alert.
            eligible = any(u.pk == user.pk for u in watchers(symbol, score=score, timeframe=timeframe))
            if not eligible or trade_alerts_muted(user):
                signal = 'wait'
            context = hashlib.sha256(
                f"{decision.get('strategy_id')}:{decision.get('strategy_version_id')}:safe".encode()
            ).hexdigest()
            note = None
            with transaction.atomic():
                state, _ = UserSignalState.objects.get_or_create(
                    user=user, symbol=symbol, timeframe=timeframe)
                state = UserSignalState.objects.select_for_update().get(pk=state.pk)
                changed = signal in ('buy', 'sell') and (
                    signal != state.last_signal or context != state.context)
                if changed:
                    word = signal.upper()
                    payload = {
                        'title': f'SmartPips · {symbol} {timeframe}',
                        'body': (f"{word} setup (score {score}, R:R {decision.get('risk_reward')}). "
                                 f"Entry {decision.get('entry')} · SL {decision.get('stop_loss')} "
                                 f"· TP {decision.get('take_profit')}"),
                        'url': f'/app/scalp?symbol={symbol}&tf={timeframe}&quick=1',
                        'symbol': symbol, 'timeframe': timeframe, 'signal': signal,
                        'entry': decision.get('entry'), 'sl': decision.get('stop_loss'),
                        'tp': decision.get('take_profit'), 'score': score,
                        'strategy_id': decision.get('strategy_id'),
                        'strategy_version_id': decision.get('strategy_version_id'),
                        'strategy_name': decision.get('strategy_name'), 'mode': 'safe',
                        'generated_at': decision.get('generated_at'),
                    }
                    note = notify(user, title=payload['title'], body=payload['body'],
                                  category='signal', level='success' if signal == 'buy' else 'danger',
                                  url=payload['url'], symbol=symbol, meta=payload, push=False)
                    # Risk can change between decide() and notify(). Never latch
                    # a signal which was suppressed by the final notification gate.
                    if note is None:
                        signal = 'wait'
                state.last_signal = signal
                state.last_score = score
                state.context = context
                state.save(update_fields=['last_signal', 'last_score', 'context', 'updated'])
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
