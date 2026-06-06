/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,jsx,ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        slate: {
          100: '#f1f5f9',
          400: '#cbd5e1',
          500: '#64748b',
          800: '#1e293b',
        },
      },
    },
  },
  plugins: [],
};