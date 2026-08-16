import React from 'react';
import { useRevealed } from './useReveal';

interface RevealProps {
  children: React.ReactNode;
  /** Stagger in ms, for revealing siblings in sequence. */
  delay?: number;
  /** `rise` lifts into place, `fade` only changes opacity. */
  mode?: 'rise' | 'fade';
  /**
   * Entrance duration in ms. Defaults to 620 — the instrument resolves faster
   * than the landing story's 900ms so the page never feels slow to settle.
   */
  duration?: number;
  as?: 'div' | 'section' | 'header' | 'footer' | 'li';
  /** Forwarded so a revealed row can still be keyboard focusable. */
  tabIndex?: number;
  className?: string;
}

/**
 * Scroll reveal wrapper for the Analysis page.
 *
 * Reuses the landing page's `[data-reveal]` CSS so both surfaces share one
 * motion definition (including its reduced-motion opt-out) — this component
 * only decides *when* to add `is-revealed`.
 */
export const Reveal: React.FC<RevealProps> = ({
  children,
  delay = 0,
  mode = 'rise',
  duration = 620,
  as = 'div',
  tabIndex,
  className = '',
}) => {
  const [ref, revealed] = useRevealed<HTMLElement>();

  /*
    An explicit switch rather than a dynamic tag: a variable tag makes React
    intersect the props of every allowed element, and the `ref` types then
    conflict. Building the props once and choosing the element keeps this fully
    typed with no casts on the caller side.
  */
  const shared = {
    ref: ref as React.Ref<never>,
    tabIndex,
    'data-reveal': mode === 'fade' ? 'fade' : '',
    className: `${revealed ? 'is-revealed' : ''} ${className}`,
    style: {
      ['--reveal-delay' as string]: `${delay}ms`,
      ['--reveal-duration' as string]: `${duration}ms`,
    } as React.CSSProperties,
  };

  switch (as) {
    case 'section':
      return <section {...shared}>{children}</section>;
    case 'header':
      return <header {...shared}>{children}</header>;
    case 'footer':
      return <footer {...shared}>{children}</footer>;
    case 'li':
      return <li {...shared}>{children}</li>;
    default:
      return <div {...shared}>{children}</div>;
  }
};

export default Reveal;
