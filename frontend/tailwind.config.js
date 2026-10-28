/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // Quiet Terminal palette: low-noise surfaces and restrained signal colours.
        ink: {
          950: "#07090C",   // public-site void (deeper than the panel bg)
          900: "#080A0C",   // page background
          800: "#0D1116",   // raised surface
          700: "#11171D",   // card
          600: "#1B242D",   // hover / inset
          500: "#303C48",   // border
          400: "#43515F",   // emphasised border
        },
        mist: { 100: "#EAECEF", 300: "#B7BDC6", 400: "#B0BAC6", 500: "#A2ADBA" },
        gold: { DEFAULT: "#D4B47B", soft: "#E2C793" },   // warm gold brand accent
        up: "#65BD98",
        down: "#E08B92",
        info: "#5B8DEF",

        // ---------------------------------------------------------------
        // Public-site palette. Namespaced under `sp` so the trading panel's
        // semantic aliases remain separate from the internal terminal surfaces.
        // ---------------------------------------------------------------
        sp: {
          // 2026-10 "bolder dark": graphite instead of near-black, so cards and
          // borders are actually visible and sections separate without glow.
          void: "#0A0C10",   // hero / CTA background
          base: "#0E1116",   // page background
          deep: "#12161C",   // alternating section background
          s1: "#161B22",     // lowest raised surface
          s2: "#1A2029",     // card
          s3: "#222935",     // hover / inset
          line: "#2A323E",   // border (visible, not a hairline ghost)
          edge: "#3A4453",   // emphasised border

          // Text ramp. t1 is reserved for headlines and must stay near-white:
          // the previous build used a mid grey for the hero, which is the
          // single biggest reason it read as weak.
          t1: "#FFFFFF",
          t2: "#E4E7EC",
          t3: "#B4BCC8",
          t4: "#8E97A5",

          pos: "#00C896",
          neg: "#F0445C",
        },
        // Signal gold. `bright` is the interaction/active state.
        // Bullion gold: saturated, the one loud colour on the public site.
        signal: { DEFAULT: "#F5B731", bright: "#FFC84A", soft: "#FFE2A0" },
      },
      fontFamily: {
        sans: ["Inter", "Vazirmatn", "system-ui", "sans-serif"],
        fa: ["Vazirmatn", "Inter", "system-ui", "sans-serif"],
        mono: ["'JetBrains Mono'", "Vazirmatn", "ui-monospace", "monospace"],
      },
      // Display scale for the public site only. The panel keeps Tailwind's
      // defaults, so nothing in the dashboard shifts.
      fontSize: {
        // Weight 700 (not 600) and tighter leading: headlines must dominate
        // the composition rather than politely coexist with body copy.
        "display-xs": ["1.75rem", { lineHeight: "1.15", letterSpacing: "-0.02em", fontWeight: "700" }],
        "display-sm": ["2.25rem", { lineHeight: "1.08", letterSpacing: "-0.025em", fontWeight: "700" }],
        "display-md": ["3.5rem", { lineHeight: "1.02", letterSpacing: "-0.03em", fontWeight: "800" }],
        "display-lg": ["4.75rem", { lineHeight: "0.98", letterSpacing: "-0.035em", fontWeight: "800" }],
        "display-xl": ["6.25rem", { lineHeight: "0.94", letterSpacing: "-0.04em", fontWeight: "800" }],
      },
      maxWidth: {
        site: "1440px",     // outer shell
        content: "1280px",  // text + standard grids
      },
      boxShadow: {
        panel: "0 1px 0 0 rgba(255,255,255,0.02) inset",
        glow: "0 0 0 1px rgba(240,185,11,0.18), 0 0 40px -8px rgba(240,185,11,0.28)",
        "glow-sm": "0 0 24px -6px rgba(240,185,11,0.35)",
        lift: "0 32px 64px -24px rgba(0,0,0,0.85)",
        mockup: "0 60px 120px -40px rgba(0,0,0,0.9), 0 0 80px -40px rgba(240,185,11,0.25)",
      },
      keyframes: {
        float: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-10px)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "200% 0" },
          "100%": { backgroundPosition: "-200% 0" },
        },
        "pulse-ring": {
          "0%": { transform: "scale(0.9)", opacity: "0.7" },
          "100%": { transform: "scale(1.8)", opacity: "0" },
        },
      },
      animation: {
        float: "float 6s ease-in-out infinite",
        shimmer: "shimmer 3s linear infinite",
        "pulse-ring": "pulse-ring 2.4s ease-out infinite",
      },
    },
  },
  plugins: [],
};
