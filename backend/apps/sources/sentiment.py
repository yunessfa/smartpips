"""
A cheap, dependency-free sentiment scorer for news headlines. It approximates the
"sentiment layer" idea (a fine-tuned FinLLM/GNN is out of scope for this app) using
a small finance lexicon. Good enough to give the assistant a directional bias hint.
"""
import re

BULLISH = {
    "surge", "surges", "soar", "soars", "rally", "rallies", "gain", "gains",
    "bullish", "breakout", "record", "high", "highs", "adoption", "upgrade",
    "inflow", "inflows", "approval", "approved", "buy", "buying", "accumulate",
    "support", "rebound", "recover", "recovery", "boom", "spike", "jump", "jumps",
    "optimism", "green", "moon", "pump", "uptrend", "demand", "etf",
}
BEARISH = {
    "crash", "crashes", "plunge", "plunges", "dump", "dumps", "bearish", "selloff",
    "sell-off", "hack", "hacked", "exploit", "ban", "banned", "lawsuit", "sue",
    "outflow", "outflows", "liquidation", "liquidations", "fear", "downgrade",
    "fall", "falls", "drop", "drops", "slump", "tumble", "tumbles", "fraud",
    "scam", "warning", "risk", "decline", "weak", "red", "downtrend", "fud",
    "correction", "bearmarket", "recession",
}

_WORD_RE = re.compile(r"[a-zA-Z]+")


def score_text(text: str) -> int:
    bull = bear = 0
    for w in _WORD_RE.findall((text or "").lower()):
        if w in BULLISH:
            bull += 1
        elif w in BEARISH:
            bear += 1
    return bull - bear


def score_news(items) -> dict:
    """Return an aggregate sentiment over a list of news dicts (title/summary)."""
    if not items:
        return {"label": "neutral", "score": 0.0, "bullish": 0, "bearish": 0}
    bull = bear = 0
    for n in items:
        s = score_text(f"{n.get('title', '')} {n.get('summary', '')}")
        if s > 0:
            bull += 1
        elif s < 0:
            bear += 1
    total = bull + bear
    score = round((bull - bear) / total, 2) if total else 0.0
    if score > 0.15:
        label = "bullish"
    elif score < -0.15:
        label = "bearish"
    else:
        label = "neutral"
    return {"label": label, "score": score, "bullish": bull, "bearish": bear}


def fear_greed():
    """Crypto Fear & Greed index (alternative.me, free, no key). Returns dict or None."""
    import requests
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=6)
        r.raise_for_status()
        d = r.json()["data"][0]
        return {"value": int(d["value"]), "label": d["value_classification"]}
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError):
        return None
