import { useEffect, useRef, useState } from 'react';

/* ─────────────────────────────────────────────────────────────────────────────
 * Shared reveal observer.
 *
 * The Analysis page reveals dozens of elements — group headings, insight rows,
 * meters, digits. Giving each its own IntersectionObserver would allocate
 * dozens of observers; instead every consumer registers with one module-level
 * observer that unobserves each target as soon as it fires.
 *
 * Reveals are one-shot by design: scrolling back up never replays them, so the
 * page settles instead of flickering.
 * ────────────────────────────────────────────────────────────────────────── */

type Callback = () => void;

const callbacks = new Map<Element, Callback>();
let observer: IntersectionObserver | null = null;

function ensureObserver(): IntersectionObserver | null {
  if (observer) return observer;
  if (typeof IntersectionObserver === 'undefined') return null;

  observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        const cb = callbacks.get(entry.target);
        if (!cb) return;
        callbacks.delete(entry.target);
        observer?.unobserve(entry.target);
        cb();
      });
    },
    // Fire a little before the element is fully in view so motion has already
    // begun by the time the reader's eye arrives.
    { threshold: 0.12, rootMargin: '0px 0px -5% 0px' }
  );

  return observer;
}

export function observeOnce(el: Element, cb: Callback): () => void {
  const io = ensureObserver();
  if (!io) {
    // No observer support: show the resolved state immediately.
    cb();
    return () => {};
  }
  callbacks.set(el, cb);
  io.observe(el);
  return () => {
    callbacks.delete(el);
    io.unobserve(el);
  };
}

export function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || !window.matchMedia) return false;
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/**
 * True once the element has scrolled into view. Resolves immediately when the
 * visitor prefers reduced motion, so nothing waits on a scroll that will never
 * be animated.
 */
export function useRevealed<T extends Element>(): [React.RefObject<T>, boolean] {
  const ref = useRef<T>(null);
  const [revealed, setRevealed] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (prefersReducedMotion()) {
      setRevealed(true);
      return;
    }
    return observeOnce(el, () => setRevealed(true));
  }, []);

  return [ref, revealed];
}

export { Reveal } from './Reveal.tsx';
