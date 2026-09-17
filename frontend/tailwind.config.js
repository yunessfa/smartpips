/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // Exchange-dark palette (Binance-family values), tuned for OLED phones.
        ink: {
          950: "#07090C",   // public-site void (deeper than the panel bg)
          900: "#0B0E11",   // page background
          800: "#12161C",   // raised surface
          700: "#181D25",   // card
          600: "#222831",   // hover / inset
          500: "#2B3139",   // border
          400: "#39414C",   // emphasised border
        },
        mist: { 100: "#EAECEF", 300: "#B7BDC6", 500: "#848E9C" },
        gold: { DEFAULT: "#F0B90B", soft: "#FCD535" },   // brand accent (Binance yellow family)
        up: "#0ECB81",
        down: "#F6465A",
        info: "#5B8DEF",

        // ---------------------------------------------------------------
        // Public-site palette. Namespaced under `sp` so the trading panel's
        // existing ink/mist/gold tokens keep their exact values and nothing
        // in the dashboard shifts by a single pixel or hex digit.
        // ---------------------------------------------------------------
        sp: {
          void: "#050607",   // deepest background, used behind the hero
          base: "#080A0D",   // page background
          deep: "#0B0E11",   // alternating section background
          s1: "#0E1115",     // lowest raised surface
          s2: "#12161C",     // card
          s3: "#171C22",     // hover / inset
          line: "#1C2229",   // hairline border
          edge: "#262E38",   // emphasised border

          // Text ramp. t1 is reserved for headlines and must stay near-white:
          // the previous build used a mid grey for the hero, which is the
          // single biggest reason it read as weak.
          t1: "#F3F4F6",
          t2: "#D1D5DB",
          t3: "#9CA3AF",
          t4: "#6B7280",

          pos: "#00C896",
          neg: "#F0445C",
        },
        // Signal gold. `bright` is the interaction/active state.
        signal: { DEFAULT: "#F0B90B", bright: "#F5B800", soft: "#FFD45A" },
      },
      fontFamily: {
        sans: ["Inter", "Vazirmatn", "system-ui", "sans-serif"],
        fa: ["Vazirmatn", "Inter", "system-ui", "sans-serif"],
        mono: ["'JetBrains Mono'", "ui-monospace", "monospace"],
      },
      // Display scale for the public site only. The panel keeps Tailwind's
      // defaults, so nothing in the dashboard shifts.
      fontSize: {
        // Weight 700 (not 600) and tighter leading: headlines must dominate
        // the composition rather than politely coexist with body copy.
        "display-xs": ["1.75rem", { lineHeight: "1.15", letterSpacing: "-0.02em", fontWeight: "700" }],
        "display-sm": ["2.25rem", { lineHeight: "1.08", letterSpacing: "-0.025em", fontWeight: "700" }],
        "display-md": ["3.25rem", { lineHeight: "1.02", letterSpacing: "-0.03em", fontWeight: "700" }],
        "display-lg": ["4.25rem", { lineHeight: "0.98", letterSpacing: "-0.035em", fontWeight: "700" }],
        "display-xl": ["5.75rem", { lineHeight: "0.94", letterSpacing: "-0.04em", fontWeight: "700" }],
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
