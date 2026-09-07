/**
 * ARIA Master Semantic Color Tokens — Dark Engineering Glass System
 * Single source of truth for frontend components.
 */

export const ARIA_THEME = {
  bg: {
    canvas: '#050608',
    surface: '#090B0F',
    elevated: '#0D1015',
    interactive: '#11141B',
    inset: '#080A0D',
  },
  border: {
    default: '#202631',
    hairline: '#202631',
    elevated: '#2A313C',
    interactive: '#343C4A',
  },
  text: {
    primary: '#F5F7FA',
    secondary: '#B8BEC9',
    tertiary: '#858D9A',
    muted: '#626A77',
  },
  indigo: {
    primary: '#7C83FF',
    hover: '#9AA0FF',
    active: '#636BEF',
    deep: '#4E56C7',
    glass: 'rgba(124, 131, 255, 0.10)',
    border: 'rgba(124, 131, 255, 0.38)',
    glow: '0 0 24px rgba(124, 131, 255, 0.08)',
  },
  amber: {
    primary: '#F0B429',
    secondary: '#D89A24',
    deep: '#8E6416',
    glass: 'rgba(240, 180, 41, 0.10)',
    border: 'rgba(240, 180, 41, 0.38)',
    innerHighlight: 'rgba(240, 180, 41, 0.08)',
    glow: '0 0 22px rgba(240, 180, 41, 0.07)',
  },
  green: {
    primary: '#35D6A3',
    hover: '#52E6B5',
    deep: '#168565',
    glass: 'rgba(53, 214, 163, 0.09)',
    border: 'rgba(53, 214, 163, 0.34)',
    glow: '0 0 20px rgba(53, 214, 163, 0.06)',
  },
  red: {
    primary: '#F27781',
    hover: '#FF8D96',
    deep: '#A84852',
    glass: 'rgba(242, 119, 129, 0.09)',
    border: 'rgba(242, 119, 129, 0.34)',
    glow: '0 0 20px rgba(242, 119, 129, 0.05)',
  },
  violet: {
    primary: '#A58CFF',
    hover: '#B9A6FF',
    deep: '#6252B5',
    glass: 'rgba(165, 140, 255, 0.09)',
    border: 'rgba(165, 140, 255, 0.30)',
  },
  cyan: {
    primary: '#4CC9E8',
    deep: '#287E94',
    glass: 'rgba(76, 201, 232, 0.08)',
    border: 'rgba(76, 201, 232, 0.28)',
  },
} as const;

export default ARIA_THEME;
