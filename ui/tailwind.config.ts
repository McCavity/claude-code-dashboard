import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        surface: "var(--surface)",
        "surface-2": "var(--surface-2)",
        border: "var(--border)",
        "border-glow": "var(--border-glow)",
        text: "var(--text)",
        "text-dim": "var(--text-dim)",
        "text-subtle": "var(--text-subtle)",
        "text-heading": "var(--text-heading)",
        warm: "var(--warm)",
        accent: {
          start: "var(--accent-start)",
          end: "var(--accent-end)",
        },
        good: "var(--good)",
        warn: "var(--warn)",
        bad: "var(--bad)",
        info: "var(--info)",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "ui-sans-serif", "-apple-system", "Segoe UI", "Helvetica", "Arial", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Menlo", "Monaco", "Consolas", "monospace"],
        display: ["Fraunces", "Libre Caslon Text", "ui-serif", "Georgia", "serif"],
      },
      letterSpacing: {
        kicker: "0.09em",
      },
      borderRadius: {
        sm: "2px",
        DEFAULT: "4px",
        md: "4px",
        lg: "8px",
        xl: "8px",
        "2xl": "8px",
      },
      boxShadow: {
        paper: "0 1px 0 rgba(27,58,92,.06), 0 2px 10px rgba(27,58,92,.18)",
        card: "0 1px 0 rgba(27,58,92,.10), 0 6px 24px rgba(27,58,92,.22)",
        floating: "0 8px 40px rgba(27,58,92,.36)",
      },
      keyframes: {
        "fade-in": {
          "0%": { opacity: "0", transform: "translateY(4px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "fade-in": "fade-in 320ms cubic-bezier(.2,.7,.2,1) both",
      },
      transitionTimingFunction: {
        "vuz-out": "cubic-bezier(.2,.7,.2,1)",
      },
    },
  },
  plugins: [],
} satisfies Config;
