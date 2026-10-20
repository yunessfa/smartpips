// Empty historical context stays empty; valid zero scores must not disappear.
export function journalContext(tr) {
  return {
    strategy_name: tr.strategy_name || "",
    strategy_version: tr.strategy_version ?? "",
    timeframe: tr.timeframe || "",
    confidence: tr.confidence ?? "",
    exit_reason: tr.exit_reason || "",
    fees_paid: tr.fees_paid ?? "",
    funding_paid: tr.funding_paid ?? "",
    net_pnl: tr.net_pnl ?? "",
    pnl_basis: tr.pnl_basis || "unknown",
    execution_verified: tr.execution_verified ? "verified" : "unverified",
  };
}