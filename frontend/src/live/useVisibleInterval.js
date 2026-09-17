import { useEffect, useRef } from "react";

/**
 * setInterval that automatically pauses when the browser tab is hidden and
 * when `enabled` is false. This is the single biggest lever against request
 * flooding: a backgrounded tab (or a disabled market) stops polling entirely
 * instead of hammering the server every second forever.
 *
 * Runs `fn` once immediately on (re)enable, then every `ms`.
 */
export function useVisibleInterval(fn, ms, enabled = true) {
  const saved = useRef(fn);
  useEffect(() => { saved.current = fn; }, [fn]);

  useEffect(() => {
    if (!enabled) return undefined;
    let timer = null;

    const start = () => {
      if (timer != null) return;
      saved.current();                       // fire immediately
      timer = setInterval(() => saved.current(), ms);
    };
    const stop = () => { if (timer != null) { clearInterval(timer); timer = null; } };

    const onVis = () => (document.hidden ? stop() : start());
    if (!document.hidden) start();
    document.addEventListener("visibilitychange", onVis);
    return () => { stop(); document.removeEventListener("visibilitychange", onVis); };
  }, [ms, enabled]);
}
