/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}"
  ],
  theme: {
    extend: {
      colors: {
        agentBlue: "#3b82f6",
        agentGreen: "#10b981",
        agentDark: "#0f172a"
      }
    }
  },
  plugins: []
}