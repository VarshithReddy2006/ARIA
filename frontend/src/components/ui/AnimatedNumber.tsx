import React, { useEffect, useRef, useState } from 'react';
import { observeOnce } from './useReveal';

interface AnimatedNumberProps {
  /** Target value to count up to */
  value: number;
  /** Duration in ms (default: 800) */
  duration?: number;
  /** Decimal places to show (default: 0) */
  decimals?: number;
  /** Optional suffix appended after the number (e.g. "%" or "ms") */
  suffix?: string;
  /** Optional prefix prepended before the number (e.g. "$") */
  prefix?: string;
  /**
   * Wait until the number scrolls into view before counting. Without this a
   * metric below the fold finishes animating before it is ever seen.
   */
  startOnView?: boolean;
  className?: string;
}

/**
 * Counts from 0 to `value` on mount using a requestAnimationFrame loop.
 * Respects `prefers-reduced-motion` — renders the final value immediately.
 * Apply the `.animated-number` class to get reduced-motion opt-out from CSS.
 */
export const AnimatedNumber: React.FC<AnimatedNumberProps> = ({
  value,
  duration = 800,
  decimals = 0,
  suffix = '',
  prefix = '',
  startOnView = false,
  className = '',
}) => {
  const [display, setDisplay] = useState(0);
  const rafRef = useRef<number | null>(null);
  const startTimeRef = useRef<number | null>(null);
  const spanRef = useRef<HTMLSpanElement>(null);
  const [armed, setArmed] = useState(!startOnView);
  const prefersReduced =
    typeof window !== 'undefined'
      ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
      : false;

  // Arm the count-up when the digits reach the viewport.
  useEffect(() => {
    if (!startOnView || armed) return;
    const el = spanRef.current;
    if (!el) return;
    if (prefersReduced) {
      setArmed(true);
      return;
    }
    return observeOnce(el, () => setArmed(true));
  }, [startOnView, armed, prefersReduced]);

  useEffect(() => {
    if (!armed) return;
    if (prefersReduced) {
      setDisplay(value);
      return;
    }

    startTimeRef.current = null;

    const step = (timestamp: number) => {
      if (startTimeRef.current === null) startTimeRef.current = timestamp;
      const elapsed = timestamp - startTimeRef.current;
      const progress = Math.min(elapsed / duration, 1);
      // Expo-out easing: matches --ease-spring feel
      const eased = 1 - Math.pow(1 - progress, 4);
      setDisplay(value * eased);
      if (progress < 1) {
        rafRef.current = requestAnimationFrame(step);
      } else {
        setDisplay(value);
      }
    };

    rafRef.current = requestAnimationFrame(step);
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
  }, [value, duration, prefersReduced, armed]);

  const formatted = decimals === 0
    ? Math.round(display).toLocaleString()
    : display.toFixed(decimals);

  return (
    <span
      ref={spanRef}
      className={`animated-number tabular-nums ${className}`}
      aria-label={`${prefix}${value}${suffix}`}
    >
      {prefix}{formatted}{suffix}
    </span>
  );
};

export default AnimatedNumber;
