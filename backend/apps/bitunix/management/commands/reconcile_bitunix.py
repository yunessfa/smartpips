"""Exchange-history preview only; immutable historical PnL is never overwritten."""
import json
import math
from django.core.management.base import BaseCommand, CommandError
from apps.bitunix.client import BitunixClient
from apps.trades.models import Trade


def preview(trade, payload, position_id):
    rows = payload.get("positionList", []) if isinstance(payload, dict) else payload
    matches = [r for r in rows if str(r.get("positionId")) == str(position_id)
               and r.get("symbol") == trade.symbol.replace(":PERP", "")
               and r.get("side") == ("LONG" if trade.direction == "long" else "SHORT")]
    if len(matches) != 1:
        raise ValueError("Expected one exact positionId/symbol/side match. No guessing.")
    row = matches[0]
    numbers = {}
    for field in ("entryPrice", "closePrice", "realizedPNL", "fee", "funding"):
        numbers[field] = float(row[field])
        if not math.isfinite(numbers[field]):
            raise ValueError("Incomplete/nonfinite exchange history.")
    if numbers["entryPrice"] <= 0 or numbers["closePrice"] <= 0:
        raise ValueError("Invalid exchange prices.")
    # Official docs establish gross realized PnL but not funding sign convention.
    # Preserve raw signed amounts: never guess a net result.
    return {"trade_id": trade.pk, "position_id": str(position_id), "read_only": True,
            "journal": {"reported_pnl":trade.pnl,"entry":trade.entry_price,"exit":trade.exit_price},
            "exchange_raw": numbers,
            "net_pnl": None, "warning": "Review position membership and funding/fee sign convention before any import.",
            "source_url":"https://www.bitunix.com/api-docs/futures/position/get_history_positions.html"}


class Command(BaseCommand):
    help = "Preview exact exchange position against one journal row. No apply mode, no orders."

    def add_arguments(self, p):
        p.add_argument("--user-id", type=int, required=True)
        p.add_argument("--trade-id", type=int, required=True)
        p.add_argument("--position-id", required=True)

    def handle(self, *args, **o):
        try:
            t = Trade.objects.get(pk=o["trade_id"], user_id=o["user_id"], source="bitunix_real")
            if t.external_position_id and t.external_position_id != o["position_id"]:
                raise ValueError("Stored position id differs.")
            payload = BitunixClient().history_position_exact(t.symbol.replace(":PERP",""), o["position_id"])
            self.stdout.write(json.dumps(preview(t,payload,o["position_id"])))
        except Exception as exc:
            raise CommandError(str(exc)) from exc