/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: '#0a0a0a',
        card: '#121212',
        line: '#292929',
        fg: '#ededed',
        muted: '#8c8c8c',
        hover: 'rgba(255,255,255,.04)',
        ok: '#4ade80',
        warn: '#fbbf24',
        bad: '#f87171',
      },
      fontFamily: {
        sans: ['"Geist Sans"', 'Geist', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"Geist Mono"', 'GeistMono', 'ui-monospace', 'monospace'],
      },
    },
  },
  plugins: [],
}
