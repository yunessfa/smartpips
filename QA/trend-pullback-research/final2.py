import json
from final import go, row
for tf in ("1h", "15m", "5m"):
    row(f"{tf} TP as market(taker+slip)", go(tf, tp_taker=True))
    row(f"{tf} TP taker + through 0.02%", go(tf, tp_taker=True, pen=0.0002))
