/** @type {import('tailwindcss').Config} */
const c = (v) => `rgb(var(${v}) / <alpha-value>)`;

export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["'IBM Plex Sans'", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["'IBM Plex Mono'", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      colors: {
        term: {
          bg: c("--c-bg"),
          panel: c("--c-panel"),
          panel2: c("--c-panel2"),
          border: c("--c-border"),
          grid: c("--c-grid"),
          text: c("--c-text"),
          muted: c("--c-muted"),
          up: c("--c-up"),
          down: c("--c-down"),
          accent: c("--c-accent"),
        },
      },
      boxShadow: {
        panel: "0 1px 0 0 rgba(255,255,255,0.02) inset, 0 10px 30px -20px rgba(0,0,0,0.55)",
      },
    },
  },
  plugins: [],
}
