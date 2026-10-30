import { useEffect, useState } from "react";

// Every price chart (Scalp analysis chart, TradingView chart, dashboard and
// Bitunix position charts) gets the SAME explicit height: 80% of the visible
// screen height, written into the chart div in pixels. Percent heights inside
// flex/overflow layouts collapse, so the value is computed, not "80%".
export const CHART_VIEWPORT_RATIO = 0.8;
export const CHART_MIN_HEIGHT = 320;

function pick() {
  if (typeof window === "undefined") return 600;
  return Math.max(CHART_MIN_HEIGHT, Math.round(window.innerHeight * CHART_VIEWPORT_RATIO));
}

export function useChartHeight() {
  const [h, setH] = useState(pick);
  useEffect(() => {
    let t = null;
    const on = () => { clearTimeout(t); t = setTimeout(() => setH(pick()), 150); };
    window.addEventListener("resize", on);
    return () => { clearTimeout(t); window.removeEventListener("resize", on); };
  }, []);
  return h;
}
