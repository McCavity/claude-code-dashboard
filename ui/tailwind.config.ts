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
      },
      letterSpacing: {
        kicker: "0.14em",
      },
      borderRadius: {
        xl: "14px",
        "2xl": "16px",
      },
      boxShadow: {
        card: "0 1px 0 rgba(255,255,255,0.04) inset, 0 8px 24px rgba(0,0,0,0.35)",
        glow: "0 0 0 1px rgba(77,124,255,0.25), 0 12px 40px rgba(77,124,255,0.18)",
      },
      backgroundImage: {
        "gradient-accent": "linear-gradient(135deg, var(--accent-start), var(--accent-end))",
        "radial-glow":
          "radial-gradient(circle at 20% 10%, rgba(77,124,255,0.10), transparent 40%), radial-gradient(circle at 85% 80%, rgba(139,92,246,0.08), transparent 45%)",
      },
      keyframes: {
        "fade-in": {
          "0%": { opacity: "0", transform: "translateY(4px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "fade-in": "fade-in 320ms ease-out both",
      },
    },
  },
  plugins: [],
} satisfies Config;
