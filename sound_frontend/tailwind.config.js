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
          primary: '#00ff88',
          secondary: '#00d4ff',
          grid: '#1a3a52',
          background: '#0a1628',
          surface: '#0f1e35',
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

