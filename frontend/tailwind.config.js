/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#050505", surface: "#0D0D0D", surface2: "#141414", line: "#262626",
        paper: "#F7F7F5", muted: "#9A9A9A", signal: "#FFFFFF",
        accent: "#FF0033", good: "#4ADE80", bad: "#F87171", warn: "#FBBF24",
      },
      fontFamily: { display: ["'Space Grotesk'", "sans-serif"], body: ["'Inter'", "sans-serif"] },
      borderRadius: { card: "20px", panel: "28px", btn: "14px" },
      boxShadow: {
        glow: "0 0 0 1px rgba(255,255,255,.06), 0 24px 80px rgba(0,0,0,.55)",
        accent: "0 8px 30px rgba(255,0,51,.25)",
      },
    },
  },
  plugins: [],
};
