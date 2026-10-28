"""Read-only previews; NEVER repair incomplete historical records automatically."""
import json
from django.core.management.base import BaseCommand
from apps.trades.models import Trade


class Command(BaseCommand):
    help = "Print accounting/provenance issues. Read-only, no apply mode."

    def add_arguments(self, parser):
        parser.add_argument("--user-id", type=int)

    def handle(self, *args, **opts):
        qs = Trade.objects.filter(status="closed")
        if opts["user_id"]:
            qs = qs.filter(user_id=opts["user_id"])
        issues = []
        for t in qs.iterator():
            reasons = []
            if t.source == "bitunix_real" and not t.execution_verified:
                reasons.append("exchange_fill_unverified")
            if t.realized_pnl and t.remaining_pct > 0:
                reasons.append("legacy_partial_exit_review_required")
            if not t.strategy_name or not t.timeframe:
                reasons.append("entry_attribution_incomplete_do_not_infer")
            if not t.costs_verified:
                reasons.append("net_pnl_unknown")
            if reasons:
                issues.append({"id": t.pk, "source": t.source, "reported_pnl": t.pnl,
                               "issues": reasons})
        self.stdout.write(json.dumps({"read_only": True, "issues": issues}, ensure_ascii=False))