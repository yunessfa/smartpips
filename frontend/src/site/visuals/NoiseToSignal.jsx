import { useEffect, useRef } from "react";
import { useReducedMotion } from "framer-motion";
import { useOnScreen } from "../motion.jsx";

/**
 * Section 3 visual: raw market noise resolving into structured intelligence.
 *
 * The left canvas paints genuine chaos — hundreds of unweighted ticks with no
 * hierarchy. As it crosses the divider, the same data is redrawn as a single
 * clean line with discrete marked levels. The point of the section is made by
 * the picture, not by the copy: same feed, different reading.
 */

const GOLD = "240,185,11";

function mulberry32(seed) {
  let a = seed;
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function NoiseCanvas({ className = "" }) {
  const canvasRef = useRef(null);
  const reduced = useReducedMotion();
  const { ref: gateRef, visible } = useOnScreen("160px");

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const ctx = canvas.getContext("2d");
    if (!ctx) return undefined;

    let w = 0;
    let h = 0;
    let raf = 0;
    let ticks = [];

    function seed() {
      const rnd = mulberry32(4242);
      const count = w < 500 ? 190 : 340;
      ticks = Array.from({ length: count }, () => ({
        x: rnd(),
        y: rnd(),
        v: 0.2 + rnd() * 0.8,
        drift: (rnd() - 0.5) * 0.0016,
        phase: rnd() * Math.PI * 2,
      }));
    }

    function resize() {
      const rect = canvas.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = rect.width;
      h = rect.height;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      seed();
    }

    function draw(t) {
      ctx.clearRect(0, 0, w, h);

      // Unweighted ticks: every print looks exactly as important as the next,
      // which is precisely the problem being illustrated.
      for (const p of ticks) {
        p.y += p.drift;
        if (p.y < 0) p.y += 1;
        if (p.y > 1) p.y -= 1;
        const flicker = 0.35 + 0.65 * Math.abs(Math.sin(t * 0.002 + p.phase));
        const x = p.x * w;
        const y = p.y * h;
        ctx.fillStyle = `rgba(132,142,156,${0.09 + flicker * 0.22 * p.v})`;
        ctx.fillRect(x, y, 1.6, 1.6);
      }

      // A few louder spikes — the ones that bait a trader into reacting.
      for (let i = 0; i < 26; i += 1) {
        const seedX = (i * 37) % 100 / 100;
        const wob = Math.sin(t * 0.0013 + i) * 0.5 + 0.5;
        const x = seedX * w;
        const len = 8 + wob * 26;
        const y = h * 0.5 + Math.sin(i * 2.3 + t * 0.0009) * h * 0.34;
        ctx.strokeStyle = `rgba(132,142,156,${0.06 + wob * 0.1})`;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(x, y - len / 2);
        ctx.lineTo(x, y + len / 2);
        ctx.stroke();
      }
    }

    function frame(now) {
      draw(now);
      raf = requestAnimationFrame(frame);
    }

    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);

    if (reduced) draw(0);
    else if (visible) raf = requestAnimationFrame(frame);

    return () => { cancelAnimationFrame(raf); ro.disconnect(); };
  }, [visible, reduced]);

  return (
    <div ref={gateRef} className={`relative ${className}`}>
      <canvas ref={canvasRef} className="h-full w-full" aria-hidden />
    </div>
  );
}

/**
 * The resolved side: the same feed reduced to one clean reading with the
 * levels that actually matter marked on it.
 */
export function SignalCanvas({ className = "" }) {
  const canvasRef = useRef(null);
  const reduced = useReducedMotion();
  const { ref: gateRef, visible } = useOnScreen("160px");

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const ctx = canvas.getContext("2d");
    if (!ctx) return undefined;

    let w = 0;
    let h = 0;
    let raf = 0;
    let path = [];

    function seed() {
      const rnd = mulberry32(99);
      const n = 60;
      let v = 0.5;
      path = Array.from({ length: n }, (_, i) => {
        v += (rnd() - 0.46) * 0.06;
        v = Math.max(0.16, Math.min(0.86, v));
        return { x: i / (n - 1), y: v };
      });
    }

    function resize() {
      const rect = canvas.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = rect.width;
      h = rect.height;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      seed();
    }

    function draw(t) {
      ctx.clearRect(0, 0, w, h);
      const pad = 14;
      const iw = w - pad * 2;
      const ih = h - pad * 2;
      const X = (p) => pad + p.x * iw;
      const Y = (p) => pad + (1 - p.y) * ih;

      // Area fill under the resolved line.
      const g = ctx.createLinearGradient(0, pad, 0, pad + ih);
      g.addColorStop(0, `rgba(${GOLD},0.16)`);
      g.addColorStop(1, `rgba(${GOLD},0)`);
      ctx.beginPath();
      ctx.moveTo(X(path[0]), pad + ih);
      for (const p of path) ctx.lineTo(X(p), Y(p));
      ctx.lineTo(X(path[path.length - 1]), pad + ih);
      ctx.closePath();
      ctx.fillStyle = g;
      ctx.fill();

      // The line itself.
      ctx.beginPath();
      path.forEach((p, i) => (i ? ctx.lineTo(X(p), Y(p)) : ctx.moveTo(X(p), Y(p))));
      ctx.strokeStyle = `rgba(${GOLD},0.9)`;
      ctx.lineWidth = 1.6;
      ctx.lineJoin = "round";
      ctx.stroke();

      // A scanning head that runs the line, marking levels as it passes.
      const prog = ((t * 0.00022) % 1);
      const idx = prog * (path.length - 1);
      const i0 = Math.floor(idx);
      const i1 = Math.min(path.length - 1, i0 + 1);
      const f = idx - i0;
      const cx = X(path[i0]) + (X(path[i1]) - X(path[i0])) * f;
      const cy = Y(path[i0]) + (Y(path[i1]) - Y(path[i0])) * f;

      ctx.strokeStyle = `rgba(${GOLD},0.18)`;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(cx, pad);
      ctx.lineTo(cx, pad + ih);
      ctx.stroke();

      ctx.fillStyle = `rgba(${GOLD},1)`;
      ctx.shadowBlur = 14;
      ctx.shadowColor = `rgba(${GOLD},0.8)`;
      ctx.beginPath();
      ctx.arc(cx, cy, 3.2, 0, Math.PI * 2);
      ctx.fill();
      ctx.shadowBlur = 0;

      // Fixed structural levels — the output of the reading.
      for (const lv of [0.72, 0.3]) {
        const y = pad + (1 - lv) * ih;
        ctx.strokeStyle = "rgba(255,255,255,0.12)";
        ctx.setLineDash([3, 5]);
        ctx.beginPath();
        ctx.moveTo(pad, y);
        ctx.lineTo(pad + iw, y);
        ctx.stroke();
        ctx.setLineDash([]);
      }
    }

    function frame(now) { draw(now); raf = requestAnimationFrame(frame); }

    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);
    if (reduced) draw(0);
    else if (visible) raf = requestAnimationFrame(frame);

    return () => { cancelAnimationFrame(raf); ro.disconnect(); };
  }, [visible, reduced]);

  return (
    <div ref={gateRef} className={`relative ${className}`}>
      <canvas ref={canvasRef} className="h-full w-full" aria-hidden />
    </div>
  );
}
