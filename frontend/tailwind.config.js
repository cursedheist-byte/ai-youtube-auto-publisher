/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#050505", surface: "#101010", surface2: "#171717", line: "#292929",
        paper: "#F7F7F5", muted: "#8F8F8F", signal: "#FFFFFF", good: "#B9F6CA", bad: "#FF8D8D",
      },
      fontFamily: { display: ["'Space Grotesk'", "sans-serif"], body: ["'Inter'", "sans-serif"] },
    },
  },
  plugins: [],
};
