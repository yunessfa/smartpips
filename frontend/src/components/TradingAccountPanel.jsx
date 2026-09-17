import { useState } from "react";
import { PositionsPanel } from "./PositionsPanel.jsx";
import { BitunixMiniPanel } from "./BitunixMiniPanel.jsx";
import { useI18n } from "../i18n/index.jsx";

/**
 * Two trading-account modes, switched with a simple tab:
 *   - "demo": the app's own in-app paper-trading journal (existing Trade model)
 *   - "bitunix": the user's Bitunix futures account — its own demo/real
 *     switch inside, real balance and real positions. (LBank tab removed.)
 */
export function TradingAccountPanel({ balance, defaultInitial = null, refreshKey }) {
  const { t } = useI18n();
  const [mode, setMode] = useState(() => {
    const saved = localStorage.getItem("sp_account_mode");
    return saved === "lbank" ? "bitunix" : (saved || "demo"); // migrate old choice
  });

  function switchMode(m) { setMode(m); localStorage.setItem("sp_account_mode", m); }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-1 bg-ink-800 rounded-lg p-0.5 w-fit">
        {[["demo", `🧪 ${t("mode_demo")}`], ["bitunix", `⚡ ${t("mode_bitunix")}`]].map(([m, label]) => (
          <button key={m} onClick={() => switchMode(m)}
            className={`text-xs px-3 py-1.5 rounded-md transition ${
              mode === m ? "bg-ink-600 text-mist-100 font-medium" : "text-mist-500 hover:text-mist-300"
            }`}>
            {label}
          </button>
        ))}
      </div>

      {mode === "demo"
        ? <PositionsPanel balance={balance} defaultInitial={defaultInitial} refreshKey={refreshKey} />
        : <BitunixMiniPanel refreshKey={refreshKey} demoBalance={balance ? Number(balance) : undefined} />}
    </div>
  );
}
