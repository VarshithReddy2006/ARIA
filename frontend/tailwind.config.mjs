/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './src/**/*.{astro,html,js,jsx,md,mdx,svelte,ts,tsx,vue}',
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        canvas: '#020204',
        'canvas-subtle': '#050609',
        surface: {
          1: '#08090d',
          2: '#0d0e14',
          3: '#13141c',
        },
        border: {
          DEFAULT: 'rgba(255, 255, 255, 0.06)',
          strong: 'rgba(255, 255, 255, 0.12)',
          subtle: 'rgba(255, 255, 255, 0.035)',
          dim: 'rgba(255, 255, 255, 0.02)',
        },
        text: {
          DEFAULT: '#ededed',
          muted: '#8e939e',
          subtle: '#525660',
        },
        primary: {
          DEFAULT: '#5e6ad2',
          hover: '#4d5ac0',
          soft: 'rgba(94, 106, 210, 0.08)',
          ring: 'rgba(94, 106, 210, 0.35)',
          foreground: '#f7f8f8',
        },
        card: {
          DEFAULT: '#08090d',
          hover: '#0d0e14',
          foreground: '#ededed',
        },
        popover: {
          DEFAULT: '#0d0e14',
          foreground: '#ededed',
        },
        success: {
          DEFAULT: '#10b981',
          soft: 'rgba(16, 185, 129, 0.08)',
        },
        warn: {
          DEFAULT: '#f59e0b',
          soft: 'rgba(245, 158, 11, 0.08)',
        },
        danger: {
          DEFAULT: '#ef4444',
          soft: 'rgba(239, 68, 68, 0.08)',
        },
        info: {
          DEFAULT: '#3b82f6',
          soft: 'rgba(59, 130, 246, 0.08)',
        },
        slate: {
          850: '#172033',
          750: '#2a374b',
          650: '#475569',
          550: '#64748b',
        },
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'sans-serif'],
        display: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'ui-monospace', 'monospace'],
      },
      fontSize: {
        'hero-sm': ['2.75rem', { lineHeight: '1.02', letterSpacing: '-0.035em', fontWeight: '800' }],
        'hero-md': ['4rem', { lineHeight: '1.01', letterSpacing: '-0.04em', fontWeight: '800' }],
        'hero-lg': ['5.5rem', { lineHeight: '0.98', letterSpacing: '-0.045em', fontWeight: '800' }],
        'hero-xl': ['7rem', { lineHeight: '0.96', letterSpacing: '-0.05em', fontWeight: '800' }],
        'editorial-1': ['2.25rem', { lineHeight: '1.1', letterSpacing: '-0.035em', fontWeight: '700' }],
        'editorial-2': ['3.25rem', { lineHeight: '1.05', letterSpacing: '-0.04em', fontWeight: '700' }],
      },
      spacing: {
        'hero': '100vh',
        'section': '9rem',
        'section-lg': '14rem',
      },
      animation: {
        'pulse-slow': 'pulse 5s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'spin-slow': 'spin 6s linear infinite',
        'hero-fade-in': 'heroFadeIn 0.9s cubic-bezier(0.16, 1, 0.3, 1) both',
      },
      keyframes: {
        heroFadeIn: {
          '0%': { opacity: '0', transform: 'translateY(16px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      boxShadow: {
        card: '0 1px 0 rgba(255,255,255,0.02) inset, 0 1px 3px rgba(0,0,0,0.7)',
        ring: '0 0 0 1px rgba(94,106,210,0.55), 0 0 0 4px rgba(94,106,210,0.18)',
        raised: '0 4px 20px rgba(0,0,0,0.6), 0 1px 3px rgba(0,0,0,0.8)',
        float: '0 12px 40px rgba(0,0,0,0.7), 0 2px 8px rgba(0,0,0,0.6)',
        subtle: '0 0 0 1px rgba(255,255,255,0.04)',
      },
    },
  },
  plugins: [],
}
