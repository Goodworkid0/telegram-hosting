/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  safelist: [
    { pattern: /from-(primary|neon|cyan|amber|red|purple)-500/ },
    { pattern: /via-(primary|neon|cyan|amber|red|purple)-500/ },
    { pattern: /to-(primary|neon|cyan|amber|red|purple)-500/ },
    { pattern: /border-(primary|neon|cyan|amber|red|purple)-500/ },
    { pattern: /from-accent-purple/ },
    { pattern: /via-accent-purple/ },
    { pattern: /to-accent-purple/ },
  ],
  theme: {
    extend: {
      colors: {
        // Omniscient cyan — the all-seeing primary
        primary: {
          50: '#e0fcff',
          100: '#b0f7ff',
          200: '#7af0ff',
          300: '#40e8ff',
          400: '#00dfff',
          500: '#00c8e6',  // Main cyan
          600: '#00a3bf',
          700: '#007f99',
          800: '#005c73',
          900: '#003a4d',
        },
        // Matrix green — the hack
        neon: {
          50: '#e4ffe6',
          100: '#b3ffb8',
          200: '#7fff88',
          300: '#4dff5a',
          400: '#26ff33',
          500: '#00e60a',  // Matrix green
          600: '#00b808',
          700: '#008a06',
          800: '#005c04',
          900: '#002e02',
        },
        // True blacks with subtle blue tint — the void
        dark: {
          50: '#f0f4f8',
          100: '#d9e2ec',
          200: '#bcccdc',
          300: '#9fb3c8',
          400: '#829ab1',
          500: '#627d98',
          600: '#486581',
          700: '#334e68',
          800: '#102a43',   // Card surfaces
          900: '#061525',   // Elevated surfaces
          950: '#010812',   // Root background (near-black)
        },
        accent: {
          purple: '#b44dff',
          cyan: '#00ffff',
        }
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        display: ['JetBrains Mono', 'Fira Code', 'monospace'],
        mono: ['JetBrains Mono', 'Fira Code', 'ui-monospace', 'monospace'],
      },
      boxShadow: {
        'neon-cyan': '0 0 15px rgba(0, 200, 230, 0.3), 0 0 40px rgba(0, 200, 230, 0.1), inset 0 0 15px rgba(0, 200, 230, 0.05)',
        'neon-green': '0 0 15px rgba(0, 230, 10, 0.3), 0 0 40px rgba(0, 230, 10, 0.1), inset 0 0 15px rgba(0, 230, 10, 0.05)',
      },
    },
  },
  plugins: [],
}
