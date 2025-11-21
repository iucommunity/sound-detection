/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        radar: {
          primary: '#00d9ff',
          secondary: '#7c3aed',
          accent: '#a855f7',
          warning: '#f59e0b',
          grid: '#1e3a5f',
          background: '#0a0e1a',
          surface: '#0f172a',
          glow: '#00d9ff',
          neon: '#00f0ff',
          purple: '#8b5cf6',
        },
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'radar-sweep': 'radar-sweep 2s ease-out infinite',
      },
      keyframes: {
        'radar-sweep': {
          '0%': {
            transform: 'scale(0)',
            opacity: '1',
          },
          '100%': {
            transform: 'scale(1)',
            opacity: '0',
          },
        },
      },
    },
  },
  plugins: [],
};

