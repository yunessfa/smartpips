/**
 * Is a displayed signal still actionable?
 *  - MARKET plans expire once price has run past max_chase_price (late entry).
 *  - LIMIT pullback plans are *meant* to sit away from price; they expire by
 *    time (limit_expiry_minutes) or when price already reached the stop side.
 */
export function signalExpired(ai, livePrice, now = Date.now()) {
  const tk = ai?.order_ticket || {};
  if (tk.order_type === "limit") {
    // A pullback LIMIT is not "late" because price is above it — that is the
    // point. It expires with time, or when price already broke the stop side.
    const ttl = (tk.limit_expiry_minutes || 0) * 60000;
    if (ttl && ai.generated_at && now - ai.generated_at > ttl) return true;
    const sl = ai.stop_loss;
    if (sl && livePrice) return ai.signal === "buy" ? livePrice <= sl : livePrice >= sl;
    return false;
  }
  const chase = tk.max_chase_price;
  if (!chase || !livePrice) return false;
  return ai.signal === "buy" ? livePrice > chase : livePrice < chase;
}
