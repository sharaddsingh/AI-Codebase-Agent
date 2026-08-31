import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        slate: {
          // Deep slate palette — slightly cooler than zinc, premium feel.
          base: "#0a0a0f",
          raised: "#11121a",
          panel: "#15172a",
          line: "#1f2236",
        },
        violet: {
          brand: "#7c5cff",
          "brand-soft": "#9b87ff",
        },
        cyan: {
          brand: "#22d3ee",
          "brand-soft": "#67e8f9",
        },
      },
      fontFamily: {
        sans: [
          "var(--font-inter)",
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
        mono: [
          "var(--font-jetbrains)",
          "JetBrains Mono",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Consolas",
          "Liberation Mono",
          "monospace",
        ],
      },
      borderRadius: {
        card: "14px",
        btn: "10px",
      },
      boxShadow: {
        card: "0 1px 0 0 rgba(255,255,255,0.04) inset, 0 8px 24px -12px rgba(0,0,0,0.6)",
        elevated:
          "0 24px 60px -24px rgba(124,92,255,0.35), 0 1px 0 0 rgba(255,255,255,0.05) inset",
        glow: "0 0 0 1px rgba(124,92,255,0.4), 0 0 24px -4px rgba(124,92,255,0.45)",
      },
      transitionTimingFunction: {
        layout: "cubic-bezier(0.2, 0.8, 0.2, 1)",
      },
      transitionDuration: {
        350: "350ms",
      },
      keyframes: {
        "fade-in": {
          from: { opacity: "0", transform: "translateY(2px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "chip-in": {
          from: { opacity: "0", transform: "scale(0.85)" },
          to: { opacity: "1", transform: "scale(1)" },
        },
        "rail-pop": {
          from: { opacity: "0", transform: "translateX(-6px)" },
          to: { opacity: "1", transform: "translateX(0)" },
        },
        "cube-spin": {
          from: { transform: "rotateX(-15deg) rotateY(0deg)" },
          to: { transform: "rotateX(-15deg) rotateY(360deg)" },
        },
        "plane-spin": {
          from: { transform: "rotateX(60deg) rotateZ(0deg)" },
          to: { transform: "rotateX(60deg) rotateZ(360deg)" },
        },
        sweep: {
          from: { transform: "rotate(0deg)" },
          to: { transform: "rotate(360deg)" },
        },
        "beam-flash": {
          "0%": { opacity: "0", transform: "scaleX(0)" },
          "20%": { opacity: "1" },
          "100%": { opacity: "0", transform: "scaleX(1)" },
        },
        "pulse-soft": {
          "0%,100%": { opacity: "0.55" },
          "50%": { opacity: "1" },
        },
        shimmer: {
          from: { backgroundPosition: "-200% 0" },
          to: { backgroundPosition: "200% 0" },
        },
      },
      animation: {
        "fade-in": "fade-in 350ms cubic-bezier(0.2, 0.8, 0.2, 1)",
        "chip-in": "chip-in 250ms cubic-bezier(0.2, 0.8, 0.2, 1)",
        "rail-pop": "rail-pop 350ms cubic-bezier(0.2, 0.8, 0.2, 1)",
        "cube-spin": "cube-spin 9s linear infinite",
        "plane-spin": "plane-spin 22s linear infinite",
        sweep: "sweep 8s linear infinite",
        "beam-flash": "beam-flash 1200ms cubic-bezier(0.2, 0.8, 0.2, 1)",
        "pulse-soft": "pulse-soft 2.4s ease-in-out infinite",
        shimmer: "shimmer 3s linear infinite",
      },
    },
  },
  plugins: [],
};

export default config;
