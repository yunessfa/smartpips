import { useEffect, useState } from "react";

// One height for every price chart on the site (Scalp analysis chart,
// TradingView chart, dashboard and Bitunix position charts) so they line up.
export const CHART_HEIGHT_DESKTOP = 460;
export const CHART_HEIGHT_MOBILE = 360;

function pick() {
  if (typeof window === "undefined") return CHART_HEIGHT_DESKTOP;
  return window.innerWidth < 640 ? CHART_HEIGHT_MOBILE : CHART_HEIGHT_DESKTOP;
}

export function useChartHeight() {
  const [h, setH] = useState(pick);
  useEffect(() => {
    const on = () => setH(pick());
    window.addEventListener("resize", on);
    return () => window.removeEventListener("resize", on);
  }, []);
  return h;
}
