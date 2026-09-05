import { useEffect, useRef } from "react";
import { useReducedMotion } from "framer-motion";
import { useOnScreen } from "../motion.jsx";

/**
 * Section 10 backdrop: a very quiet market visualization behind the final CTA.
 *
 * Deliberately restrained — opacity stays low and motion stays slow, because
 * anything louder would compete with the headline, which is the only thing
 * that matters at the bottom of the page. It reads as depth, not decoration.
 */

const GOLD = "240,185,11";

export function CTABackdrop({ className = "" }) {
  const canvasRef = useRef(null);
  const reduced = useReducedMotion();
  const { ref: gateRef, visible } = useOnScreen("200px");

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const ctx = canvas.getContext("2d");
    if (!ctx) return undefined;

    let w = 0;
    let h = 0;
    let raf = 0;
    let lines = [];

    function seed() {
      const count = w < 640 ? 5 : 9;
      lines = Array.from({ length: count }, (_, i) => ({
        offset: i / count,
        amp: 0.05 + ((i * 7) % 5) / 60,
        speed: 0.00008 + (i % 4) * 0.00004,
        phase: i * 1.7,
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
      const steps = w < 640 ? 26 : 46;

      for (const l of lines) {
        ctx.beginPath();
        for (let s = 0; s <= steps; s += 1) {
          const x = (s / steps) * w;
          const wave =
            Math.sin(s * 0.28 + t * l.speed * 1000 + l.phase) * l.amp +
            Math.sin(s * 0.11 - t * l.speed * 620 + l.phase) * l.amp * 0.6;
          const y = h * (0.2 + l.offset * 0.62) + wave * h;
          if (s === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.strokeStyle = `rgba(${GOLD},0.07)`;
        ctx.lineWidth = 1;
        ctx.stroke();
      }

      // A handful of slow-drifting nodes on the middle line for a little life.
      const nodeCount = w < 640 ? 3 : 6;
      for (let i = 0; i < nodeCount; i += 1) {
        const p = ((t * 0.000022) + i / nodeCount) % 1;
        const x = p * w;
        const y = h * 0.5 + Math.sin(p * 8 + i) * h * 0.12;
        const fade = Math.sin(p * Math.PI);
        ctx.fillStyle = `rgba(${GOLD},${0.22 * fade})`;
        ctx.beginPath();
        ctx.arc(x, y, 1.6, 0, Math.PI * 2);
        ctx.fill();
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
    <div ref={gateRef} className={`pointer-events-none absolute inset-0 ${className}`} aria-hidden>
      <canvas ref={canvasRef} className="h-full w-full" />
    </div>
  );
}

export default CTABackdrop;
