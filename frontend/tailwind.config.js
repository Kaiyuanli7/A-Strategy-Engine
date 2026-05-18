/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: {
          50: '#f6f7f9',
          100: '#eceef2',
          200: '#cfd4dd',
          400: '#7a8294',
          600: '#3f4757',
          800: '#1f2530',
          900: '#11151c',
        },
        accent: {
          green: '#16a34a',
          red: '#dc2626',
          blue: '#2563eb',
        },
      },
      fontFamily: {
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
    },
  },
  plugins: [],
}
