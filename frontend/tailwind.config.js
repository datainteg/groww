/** @type {import('tailwindcss').Config} */
import { uiPlugin } from './src/styles/ui.plugin.js'

export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        dark: {
          950: '#050810',
          900: '#0a0f1a',
          850: '#0f1629',
          800: '#141c2e',
          700: '#1e2a42',
          600: '#2d3b55',
          500: '#475569',
          400: '#64748b',
          300: '#94a3b8',
          200: '#cbd5e1',
          100: '#e2e8f0',
        },
        // Groww-style green brand palette
        primary: {
          50: '#e6fbf5',
          100: '#c4f5e6',
          200: '#8fead0',
          300: '#54dbb6',
          400: '#1fc99b',
          500: '#00d09c',
          600: '#00b386',
          700: '#00936e',
          800: '#007355',
          900: '#005c44',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
    },
  },
  plugins: [uiPlugin],
}
