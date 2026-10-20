import { useEffect, useState } from "react";
import { prefsApi } from "../api/client.js";
import { useI18n } from "../i18n/index.jsx";

/** A disclosure, never a UI cap or an automatic change to chosen leverage. */
export function LeverageAdvisory({ mode, leverage }) {
  const { t } = useI18n();
  const [recommended, setRecommended] = useState(mode === "demo" ? 10 : null);
  useEffect(() => {
    let alive = true;
    setRecommended(mode === "demo" ? 10 : null);
    if (mode === "real") prefsApi.myLimits().then((limits) => {
      if (alive) setRecommended(limits.max_leverage);
    }).catch(() => {});
    return () => { alive = false; };
  }, [mode]);
  return <div role="note" className="sp-risk-advisory mt-4">
    <strong>{t("leverage_advisory_title")}</strong>
    <p>{Number(leverage) > recommended && recommended != null
      ? `${leverage}× / ${recommended}× — ` : ""}{t("leverage_advisory_detail")}</p>
  </div>;
}
