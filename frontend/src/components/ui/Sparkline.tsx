import React, { useId, useMemo } from 'react';

type SparkTone = 'primary' | 'success' | 'warn' | 'danger' | 'info' | 'neutral';

interface SparklineProps {
  /** Series to plot. Fewer than 2 points renders nothing. */
  data: number[];
  width?: number;
  height?: number;
  tone?: SparkTone;
  /** Fills the area beneath the line with a soft gradient */
  area?: boolean;
  strokeWidth?: number;
  className?: string;
  /** Accessible description; omit to mark the graphic decorative */
  ariaLabel?: string;
}

const toneStroke: Record<SparkTone, string> = {
  primary: 'var(--primary)',
  success: 'var(--success)',
  warn:    'var(--warn)',
  danger:  'var(--danger)',
  info:    'var(--info)',
  neutral: 'var(--text-subtle)',
};

/**
 * Dependency-free inline SVG sparkline.
 *
 * Purely decorative by default — it carries no numeric meaning that isn't
 * already stated in the card's value and hint text, so it is hidden from
 * assistive technology unless an `ariaLabel` is supplied.
 */
export const Sparkline: React.FC<SparklineProps> = ({
  data,
  width = 64,
  height = 20,
  tone = 'primary',
  area = true,
  strokeWidth = 1.5,
  className = '',
  ariaLabel,
}) => {
  const gradientId = useId();

  const geometry = useMemo(() => {
    const points = (data ?? []).filter((n) => Number.isFinite(n));
    if (points.length < 2) return null;

    const min = Math.min(...points);
    const max = Math.max(...points);
    const span = max - min || 1;

    // Inset by half the stroke so the line never clips at the edges.
    const pad = strokeWidth / 2;
    const usableWidth = width - pad * 2;
    const usableHeight = height - pad * 2;

    const coords = points.map((value, index) => {
      const x = pad + (index / (points.length - 1)) * usableWidth;
      const y = pad + (1 - (value - min) / span) * usableHeight;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    });

    const line = `M${coords.join(' L')}`;
    const fill = `${line} L${(width - pad).toFixed(2)},${(height - pad).toFixed(2)} L${pad.toFixed(2)},${(height - pad).toFixed(2)} Z`;

    return { line, fill };
  }, [data, width, height, strokeWidth]);

  if (!geometry) return null;

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={`overflow-visible ${className}`}
      role={ariaLabel ? 'img' : 'presentation'}
      aria-label={ariaLabel}
      aria-hidden={ariaLabel ? undefined : true}
      focusable="false"
    >
      {area && (
        <>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={toneStroke[tone]} stopOpacity="0.28" />
              <stop offset="100%" stopColor={toneStroke[tone]} stopOpacity="0" />
            </linearGradient>
          </defs>
          <path d={geometry.fill} fill={`url(#${gradientId})`} stroke="none" />
        </>
      )}
      <path
        d={geometry.line}
        fill="none"
        stroke={toneStroke[tone]}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
};

export default Sparkline;
