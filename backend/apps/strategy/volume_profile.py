"""OHLCV-distributed profile estimate, NOT trade-at-price/order-book volume."""
import math


def volume_profile(candles, bins=48, value_fraction=0.70):
    bars = [c for c in candles[-200:] if all(
        isinstance(c.get(k), (int, float)) and math.isfinite(c[k])
        for k in ("low", "high", "volume")) and c["volume"] > 0 and c["high"] >= c["low"]]
    if len(bars) < 20:
        return None
    low, high = min(c["low"] for c in bars), max(c["high"] for c in bars)
    if high <= low:
        return None
    step = (high - low) / bins
    volumes = [0.0] * bins
    for c in bars:
        first = max(0, min(bins - 1, int((c["low"] - low) / step)))
        last = max(first, min(bins - 1, int((c["high"] - low) / step)))
        share = c["volume"] / (last - first + 1)
        for index in range(first, last + 1):
            volumes[index] += share
    poc = max(range(bins), key=volumes.__getitem__)
    left = right = poc
    included = volumes[poc]
    target = sum(volumes) * value_fraction
    while included < target and (left > 0 or right < bins - 1):
        if right < bins - 1 and (left == 0 or volumes[right + 1] >= volumes[left - 1]):
            right += 1
            included += volumes[right]
        else:
            left -= 1
            included += volumes[left]
    return {"poc": low + (poc + 0.5) * step,
            "val": low + left * step, "vah": low + (right + 1) * step,
            "method": "OHLCV uniform-range approximation", "bars": len(bars),
            "value_fraction": value_fraction}
