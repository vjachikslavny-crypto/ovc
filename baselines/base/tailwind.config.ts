import type { Config } from "tailwindcss";
import typography from "@tailwindcss/typography";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
    "./server/**/*.{ts,tsx}",
    "./styles/**/*.{ts,tsx}",
    "./scripts/**/*.{ts,tsx}"
  ],
  theme: {
    extend: {
      colors: {
        background: "rgb(249 250 251)",
        foreground: "rgb(17 24 39)",
        muted: "rgb(229 231 235)"
      }
    }
  },
  plugins: [typography]
};

export default config;
