// Display-only translations: never decide whether an order is allowed here.
const number = value => Number.isFinite(Number(value)) ? Number(value).toFixed(2) : "—";
export function formatOrderWarning(warning, isRTL = false) {
  if (warning.code === "leverage_above_recommended") return isRTL
    ? `اهرم ${warning.leverage}× بالاتر از پیشنهاد ${warning.recommended_max}× است؛ این هشدار مانع سفارش نیست.`
    : `Leverage ${warning.leverage}× exceeds the ${warning.recommended_max}× recommendation; this warning does not block the order.`;
  if (["demo_trade_risk_cap", "demo_total_stop_risk_cap"].includes(warning.code)) {
    const total = warning.code === "demo_total_stop_risk_cap";
    const label = isRTL ? (total ? "مجموع ریسک باز دمو" : "زیان تخمینی این معامله تا استاپ") : (total ? "Total open demo stop risk" : "Estimated demo stop loss");
    return isRTL
      ? `${label}: ${number(warning.estimated_risk_usdt)} USDT؛ بالاتر از پیشنهاد ${warning.recommended_max_pct}٪ موجودی. فقط هشدار است و مانع سفارش نیست. زیان واقعی ممکن است بیشتر باشد.`
      : `${label}: ${number(warning.estimated_risk_usdt)} USDT; above the ${warning.recommended_max_pct}% balance recommendation. Warning only, not an order block. Actual losses may be higher.`;
  }
  return warning.message || warning.code || "";
}
const errors = {
  demo_daily_loss_cap: ["سقف زیان روزانه دمو رسیده است؛ امروز سفارش جدید مجاز نیست.", "Demo daily loss limit reached; new orders are blocked today."],
  demo_open_position_cap: ["تعداد پوزیشن‌های باز دمو به سقف مجاز رسیده است.", "Demo open-position limit reached."],
  demo_available_margin: ["موجودی آزاد دمو برای مارجین این سفارش کافی نیست.", "Insufficient free demo margin."],
  existing_demo_stop_missing_or_invalid: ["استاپ یکی از پوزیشن‌های باز دمو وجود ندارد یا معتبر نیست؛ ابتدا آن را اصلاح کنید.", "An existing demo position has a missing or invalid stop; correct it first."],
  invalid_stop_side: ["استاپ در سمت نادرست قیمت ورود است.", "Stop is on the wrong side of entry."],
  demo_balance_and_valid_stop_required: ["موجودی معتبر و استاپ معتبر برای سفارش دمو لازم است.", "A valid demo balance and stop are required."],
  stop_too_close_to_or_beyond_estimated_liquidation: ["استاپ به لیکوییدشدن تخمینی بسیار نزدیک است یا از آن عبور می‌کند؛ اهرم یا فاصله استاپ را اصلاح کنید.", "Stop is too close to or beyond estimated liquidation; adjust leverage or stop distance."],
};
export function formatOrderError(message, isRTL = false) {
  return String(message || "").split(";").map(code => {
    const key = code.trim();
    // A stale backend may still reject these: do not claim it accepted the order.
    if (["demo_trade_risk_cap", "demo_total_stop_risk_cap"].includes(key)) return isRTL
      ? "نسخه فعلی سرور هنوز سقف ریسک دمو را مسدود می‌کند؛ به‌روزرسانی بک‌اند لازم است."
      : "The current server still blocks demo risk budgets; update the backend.";
    return errors[key]?.[isRTL ? 0 : 1] || key;
  }).join(isRTL ? " ؛ " : "; ");
}
