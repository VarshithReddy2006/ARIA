import React, { useEffect, useRef } from 'react';

type DonutTone = 'success' | 'warn' | 'danger' | 'primary' | 'info' | 'glass-indigo';

interface SVGDonutProps {
  /** 0–100 score value */
  value: number;
  /** Outer diameter in px (default: 128) */
  size?: number;
  /** Ring thickness in px (default: 10) */
  strokeWidth?: number;
  tone?: DonutTone;
  /** Label rendered in the centre */
  label?: React.ReactNode;
  className?: string;
}

const toneStroke: Record<DonutTone, string> = {
  success:        'var(--success)',
  warn:           'var(--warn)',
  danger:         'var(--danger)',
  primary:        'var(--primary)',
  info:           'var(--info)',
  'glass-indigo': 'url(#svg-donut-glass-indigo)',
};

/**
 * SVG-based circular progress ring that animates stroke-dashoffset on mount.
 * Correctly encodes the score value as a filled arc — unlike the CSS-border trick.
 *
 * Apply class `.svg-donut-ring` for reduced-motion opt-out.
 */
export const SVGDonut: React.FC<SVGDonutProps> = ({
  value,
  size = 128,
  strokeWidth = 10,
  tone = 'primary',
  label,
  className = '',
}) => {
  const circleRef = useRef<SVGCircleElement>(null);
  const clampedValue = Math.min(100, Math.max(0, value));
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const targetDash = (clampedValue / 100) * circumference;
  const gapDash = circumference - targetDash;
  const centre = size / 2;

  const prefersReduced =
    typeof window !== 'undefined'
      ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
      : false;

  useEffect(() => {
    const el = circleRef.current;
    if (!el || prefersReduced) return;

    // Start from 0
    el.style.strokeDashoffset = String(circumference);
    el.style.transition = 'none';

    // Force a reflow so the initial state is painted before animating
    void el.getBoundingClientRect();

    el.style.transition = `stroke-dashoffset 800ms var(--ease-spring, cubic-bezier(0.16,1,0.3,1))`;
    el.style.strokeDashoffset = String(gapDash > 0 ? circumference - targetDash : 0);
  }, [value, circumference, targetDash, gapDash, prefersReduced]);

  return (
    <div className={`relative inline-flex items-center justify-center ${className}`} style={{ width: size, height: size }}>
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        role="img"
        aria-label={`${clampedValue} out of 100`}
        className="rotate-[-90deg] overflow-visible"
      >
        <defs>
          <linearGradient id="svg-donut-glass-indigo" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#545DC4" />
            <stop offset="50%" stopColor="#6B74D9" />
            <stop offset="100%" stopColor="#7C86E8" />
          </linearGradient>
          <filter id="svg-donut-glass-glow" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="0" stdDeviation="3" floodColor="#6B74D9" floodOpacity="0.22" />
          </filter>
        </defs>
        {/* Track ring */}
        <circle
          cx={centre}
          cy={centre}
          r={radius}
          fill="none"
          stroke="#1F1F23"
          strokeWidth={strokeWidth}
        />
        {/* Progress ring */}
        <circle
          ref={circleRef}
          cx={centre}
          cy={centre}
          r={radius}
          fill="none"
          stroke={toneStroke[tone]}
          filter={tone === 'glass-indigo' ? 'url(#svg-donut-glass-glow)' : undefined}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={`${targetDash} ${circumference - targetDash}`}
          strokeDashoffset={prefersReduced ? 0 : circumference}
          className="svg-donut-ring"
        />
      </svg>
      {/* Centre label */}
      {label && (
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          {label}
        </div>
      )}
    </div>
  );
};

export default SVGDonut;
