import { useEffect, useRef, useState } from 'react';

/* ─────────────────────────────────────────────────────────────────────────────
 * Scroll + motion primitives for the landing story.
 *
 * Design rule: scroll position drives animation through requestAnimationFrame
 * and direct style writes. IntersectionObserver only answers "is this section
 * on screen?" — it never drives progress, and React state is never updated on
 * a per-frame basis.
 * ────────────────────────────────────────────────────────────────────────── */

const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)';

function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || !window.matchMedia) return false;
  return window.matchMedia(REDUCED_MOTION_QUERY).matches;
}

/** Reactive `prefers-reduced-motion`. False during SSR. */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    const mql = window.matchMedia(REDUCED_MOTION_QUERY);
    setReduced(mql.matches);
    const onChange = (e: MediaQueryListEvent) => setReduced(e.matches);
    mql.addEventListener('change', onChange);
    return () => mql.removeEventListener('change', onChange);
  }, []);

  return reduced;
}

/** Reactive media query, used to curate visuals for small screens. */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false);

  useEffect(() => {
    const mql = window.matchMedia(query);
    setMatches(mql.matches);
    const onChange = (e: MediaQueryListEvent) => setMatches(e.matches);
    mql.addEventListener('change', onChange);
    return () => mql.removeEventListener('change', onChange);
  }, [query]);

  return matches;
}

/** True once the element has entered the viewport. Never flips back. */
export function useInView<T extends Element>(
  options: IntersectionObserverInit = { threshold: 0.25 }
): [React.RefObject<T>, boolean] {
  const ref = useRef<T>(null);
  const [inView, setInView] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (typeof IntersectionObserver === 'undefined') {
      setInView(true);
      return;
    }
    const io = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        setInView(true);
        io.disconnect();
      }
    }, options);
    io.observe(el);
    return () => io.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return [ref, inView];
}

export interface ScrollDriverOptions {
  /**
   * Slice of the element's viewport travel that maps to progress 0→1.
   * Travel is measured from "element top at viewport bottom" (0) to
   * "element bottom at viewport top" (1).
   */
  from?: number;
  to?: number;
  /** Number of discrete stages to report through `step`. */
  steps?: number;
  /** CSS custom property updated on the element every frame. */
  cssVar?: string;
  /**
   * Per-frame hook for imperative writes. Runs inside rAF; must not call
   * setState. Receives eased progress and the element.
   */
  onFrame?: (progress: number, el: HTMLElement) => void;
}

export interface ScrollDriver<T> {
  ref: React.RefObject<T>;
  /** Discrete stage index — the only value that triggers a re-render. */
  step: number;
  /** True once the section has been on screen at least once. */
  entered: boolean;
  reduced: boolean;
}

/**
 * Drives a section from scroll position.
 *
 * The rAF loop only runs while the element intersects the viewport, so
 * off-screen sections cost nothing. Continuous values are published as a CSS
 * custom property (and through `onFrame`) rather than as React state; only the
 * coarse `step` index is stateful, so a five-stage section re-renders five
 * times instead of once per frame.
 *
 * Under reduced motion the final state is applied once and no loop starts.
 */
export function useScrollDriver<T extends HTMLElement>(
  options: ScrollDriverOptions = {}
): ScrollDriver<T> {
  const { from = 0, to = 1, steps = 1, cssVar = '--p', onFrame } = options;

  const ref = useRef<T>(null);
  const [step, setStep] = useState(0);
  const [entered, setEntered] = useState(false);
  const reduced = useReducedMotion();

  // Keep the latest callback without restarting the loop.
  const frameCb = useRef(onFrame);
  frameCb.current = onFrame;

  const stepRef = useRef(0);
  const rafRef = useRef(0);
  const visibleRef = useRef(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const applyReducedState = () => {
      el.style.setProperty(cssVar, '1');
      frameCb.current?.(1, el);
      stepRef.current = steps - 1;
      setStep(steps - 1);
      setEntered(true);
    };

    if (reduced) {
      applyReducedState();
      return;
    }

    const measure = () => {
      const rect = el.getBoundingClientRect();
      const vh = window.innerHeight || 1;
      const span = rect.height + vh;
      const travelled = vh - rect.top;
      const raw = span > 0 ? travelled / span : 0;

      // Remap the useful slice of travel onto 0→1.
      const denom = to - from || 1;
      const p = Math.min(1, Math.max(0, (raw - from) / denom));

      el.style.setProperty(cssVar, p.toFixed(4));
      frameCb.current?.(p, el);

      const nextStep = Math.min(steps - 1, Math.max(0, Math.floor(p * steps)));
      if (nextStep !== stepRef.current) {
        stepRef.current = nextStep;
        setStep(nextStep);
      }
    };

    const loop = () => {
      measure();
      rafRef.current = visibleRef.current ? requestAnimationFrame(loop) : 0;
    };

    const start = () => {
      if (rafRef.current) return;
      rafRef.current = requestAnimationFrame(loop);
    };

    const stop = () => {
      if (!rafRef.current) return;
      cancelAnimationFrame(rafRef.current);
      rafRef.current = 0;
    };

    if (typeof IntersectionObserver === 'undefined') {
      visibleRef.current = true;
      setEntered(true);
      start();
      return () => stop();
    }

    const io = new IntersectionObserver(
      ([entry]) => {
        visibleRef.current = entry.isIntersecting;
        if (entry.isIntersecting) {
          setEntered(true);
          start();
        } else {
          // Settle on the boundary state so a section skipped past still reads
          // correctly, then stop burning frames.
          measure();
          stop();
        }
      },
      { rootMargin: '10% 0px' }
    );

    io.observe(el);

    // Pause with the tab.
    const onVisibility = () => {
      if (document.hidden) stop();
      else if (visibleRef.current) start();
    };
    document.addEventListener('visibilitychange', onVisibility);

    return () => {
      io.disconnect();
      document.removeEventListener('visibilitychange', onVisibility);
      stop();
    };
  }, [reduced, from, to, steps, cssVar]);

  return { ref, step, entered, reduced };
}

/** Counts up to `value` once `active` becomes true. */
export function useCountUp(value: number, active: boolean, duration = 1100): number {
  const [display, setDisplay] = useState(0);

  useEffect(() => {
    if (!active) return;
    if (prefersReducedMotion()) {
      setDisplay(value);
      return;
    }

    let raf = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      // easeOutExpo — fast settle, no bounce
      const eased = t === 1 ? 1 : 1 - Math.pow(2, -10 * t);
      setDisplay(value * eased);
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, active, duration]);

  return display;
}

/**
 * Reveals a sequence of items one after another once `active` is true.
 * Returns how many items are currently revealed.
 */
export function useSequence(total: number, active: boolean, stepMs = 520): number {
  const [count, setCount] = useState(0);

  useEffect(() => {
    if (!active) return;
    if (prefersReducedMotion()) {
      setCount(total);
      return;
    }
    let cancelled = false;
    let i = 0;
    const advance = () => {
      if (cancelled) return;
      i += 1;
      setCount(i);
      if (i < total) window.setTimeout(advance, stepMs);
    };
    const first = window.setTimeout(advance, 260);
    return () => {
      cancelled = true;
      window.clearTimeout(first);
    };
  }, [total, active, stepMs]);

  return count;
}

/** Clamped linear map of `p` onto a sub-range. */
export function phase(p: number, from: number, to: number): number {
  return Math.min(1, Math.max(0, (p - from) / (to - from)));
}

export const easeOutCubic = (t: number): number => 1 - Math.pow(1 - t, 3);
