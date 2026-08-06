/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './src/**/*.{astro,html,js,jsx,md,mdx,svelte,ts,tsx,vue}',
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        canvas: '#010102',
        surface: {
          1: '#111114',
          2: '#17181c',
          3: '#1e1f24',
        },
        border: {
          DEFAULT: '#23252a',
          strong: '#2f3138',
          subtle: '#1a1c20',
        },
        text: {
          DEFAULT: '#f7f8f8',
          muted: '#9ca3af',
          subtle: '#80848e',
        },
        primary: {
          DEFAULT: '#5e6ad2',
          hover: '#4d5ac0',
          soft: 'rgba(94,106,210,0.10)',
          ring: 'rgba(94,106,210,0.35)',
          foreground: '#f7f8f8',
        },
        card: {
          DEFAULT: '#111114',
          hover: '#17181c',
          foreground: '#f7f8f8',
        },
        popover: {
          DEFAULT: '#17181c',
          foreground: '#f7f8f8',
        },
        // semantic tokens — use these instead of raw emerald/red/orange/blue
        success: {
          DEFAULT: '#10b981',
          soft: 'rgba(16,185,129,0.10)',
        },
        warn: {
          DEFAULT: '#f59e0b',
          soft: 'rgba(245,158,11,0.10)',
        },
        danger: {
          DEFAULT: '#ef4444',
          soft: 'rgba(239,68,68,0.10)',
        },
        info: {
          DEFAULT: '#3b82f6',
          soft: 'rgba(59,130,246,0.10)',
        },
        // back-compat shims for invented slate stops used by older Phase-2 code
        slate: {
          850: '#172033',
          750: '#2a374b',
          650: '#475569',
          550: '#64748b',
        },
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      animation: {
        'pulse-slow': 'pulse 4s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'spin-slow': 'spin 4s linear infinite',
      },
      boxShadow: {
        card: '0 1px 0 rgba(255,255,255,0.03) inset, 0 1px 2px rgba(0,0,0,0.5)',
        ring: '0 0 0 1px rgba(94,106,210,0.55), 0 0 0 4px rgba(94,106,210,0.18)',
      },
    },
  },
  plugins: [],
}
