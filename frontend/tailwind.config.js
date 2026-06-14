/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          900: "#0B0E14", 800: "#10141E", 700: "#141925",
          600: "#1B2231", 500: "#222A3A",
        },
        mist: { 100: "#E6E9F0", 300: "#AEB6C7", 500: "#8A93A6" },
        gold: { DEFAULT: "#E0A82E", soft: "#F4C95D" },
        up: "#2FBF9B",
        down: "#F0616D",
        info: "#5B8DEF",
      },
      fontFamily: {
        sans: ["Inter", "Vazirmatn", "system-ui", "sans-serif"],
        fa: ["Vazirmatn", "Inter", "system-ui", "sans-serif"],
        mono: ["'JetBrains Mono'", "ui-monospace", "monospace"],
      },
      boxShadow: {
        panel: "0 1px 0 0 rgba(255,255,255,0.03) inset, 0 8px 24px -12px rgba(0,0,0,0.6)",
      },
    },
  },
  plugins: [],
};
