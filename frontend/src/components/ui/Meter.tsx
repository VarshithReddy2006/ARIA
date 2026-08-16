import React from 'react';
import { useRevealed } from './useReveal';

interface MeterProps {
  /** 0–1. Values outside the range are clamped. */
  value: number;
  /** Tailwind background class for the fill, e.g. `bg-success`. */
  barClassName?: string;
  /** Extra classes for the track (width caps, thickness overrides). */
  className?: string;
  /** Delay before the fill grows, for staggering a stack of meters. */
  delay?: number;
  /** Exposed to assistive tech; omit when an adjacent value already says it. */
  label?: string;
}

/**
 * A single-line meter that grows from zero when it scrolls into view.
 *
 * Previously these were rendered at their final width, so the fill never
 * animated. Driving the fill from a reveal makes the value read as measured
 * rather than merely drawn — and it stays a `transform`, so it composites.
 */
export const Meter: React.FC<MeterProps> = ({
  value,
  barClassName = 'bg-primary',
  className = '',
  delay = 0,
  label,
}) => {
  const [ref, revealed] = useRevealed<HTMLDivElement>();
  const clamped = Math.min(1, Math.max(0, Number.isFinite(value) ? value : 0));

  return (
    <div
      ref={ref}
      className={`meter ${className}`}
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      <span
        className={barClassName}
        style={{
          transform: `scaleX(${revealed ? clamped : 0})`,
          transitionDelay: `${delay}ms`,
        }}
      />
    </div>
  );
};

export default Meter;
