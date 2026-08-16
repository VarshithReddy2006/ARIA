import React from 'react';
import { useRevealed } from './useReveal';

interface SectionSeamProps {
  /** Names the transition, e.g. "ARCHITECTURE SIGNAL → STRUCTURE". */
  label: string;
  className?: string;
}

/**
 * The seam between two major groups on the Analysis page.
 *
 * Same idea as the landing page's SectionBridge, dialled down for an
 * instrument: a mono label and a hairline that draws itself as the seam scrolls
 * into view, with measured breathing space either side. It replaces the
 * anonymous gap that made consecutive groups read as unrelated slabs.
 */
export const SectionSeam: React.FC<SectionSeamProps> = ({ label, className = '' }) => {
  const [ref, revealed] = useRevealed<HTMLDivElement>();

  return (
    <div
      ref={ref}
      className={`seam pt-12 pb-6 sm:pt-14 sm:pb-7 ${revealed ? 'is-revealed' : ''} ${className}`}
      role="presentation"
      aria-hidden="true"
    >
      <span
        className="mono-label whitespace-nowrap"
        style={{
          opacity: revealed ? 1 : 0,
          transition: 'opacity 700ms cubic-bezier(0.16,1,0.3,1)',
        }}
      >
        {label}
      </span>
    </div>
  );
};

export default SectionSeam;
