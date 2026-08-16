import React from 'react';
import { Reveal } from './Reveal';

export interface MetricEntry {
  label: string;
  value: React.ReactNode;
  /** One short line of context — a count, a list, a duration. */
  detail?: React.ReactNode;
  /** Second, quieter line. */
  note?: React.ReactNode;
  tone?: 'default' | 'success' | 'warn' | 'danger' | 'primary';
  /** Makes the cell a button — used where a metric maps to a tab. */
  onClick?: () => void;
  /** Accessible name for the interactive form of the cell. */
  actionLabel?: string;
}

interface MetricMatrixProps {
  entries: MetricEntry[];
  className?: string;
}

const TONE: Record<NonNullable<MetricEntry['tone']>, string> = {
  default: 'text-text',
  success: 'text-success',
  warn: 'text-warn',
  danger: 'text-danger',
  primary: 'text-primary',
};

/**
 * A compact structural read-out.
 *
 * Replaces a row of bordered metric cards with a single matrix separated by
 * hairlines: two columns on mobile, three on tablet, one row of five at lg.
 * `min-w-0` on every cell plus `truncate`/`break-words` on the text means long
 * language lists or directory counts shrink instead of widening the page.
 */
export const MetricMatrix: React.FC<MetricMatrixProps> = ({ entries, className = '' }) => (
  <dl
    className={`grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5
                border-t border-white/[0.055] ${className}`}
  >
    {entries.map((entry, index) => {
      const tone = TONE[entry.tone ?? 'default'];

      const body = (
        <>
          <dt className="mono-label mb-2.5">{entry.label}</dt>
          <dd>
            <span className={`readout-value block ${tone}`}>{entry.value}</span>
            {entry.detail && (
              <span className="mono-detail block mt-2 truncate" style={{ fontSize: 10 }}>
                {entry.detail}
              </span>
            )}
            {entry.note && (
              <span
                className="block mt-1 text-text-subtle truncate"
                style={{ fontSize: 10, fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
              >
                {entry.note}
              </span>
            )}
          </dd>
        </>
      );

      const cell =
        'min-w-0 px-4 sm:px-5 py-5 border-b border-white/[0.055] ' +
        // Vertical separators, suppressed at the start of each wrapped row.
        'border-l border-white/[0.055] [&:nth-child(2n+1)]:border-l-0 ' +
        'md:[&:nth-child(2n+1)]:border-l md:[&:nth-child(3n+1)]:border-l-0 ' +
        'lg:[&:nth-child(3n+1)]:border-l lg:[&:nth-child(5n+1)]:border-l-0';

      // Cells resolve left to right as the matrix enters view.
      const delay = index * 70;

      if (entry.onClick) {
        return (
          <Reveal key={entry.label} delay={delay} className={cell}>
            <button
              type="button"
              onClick={entry.onClick}
              aria-label={entry.actionLabel ?? `${entry.label}: open related view`}
              className="group text-left w-full min-w-0 focus-visible:outline-none
                         focus-visible:shadow-ring"
            >
              <span className="block transition-opacity duration-200 group-hover:opacity-80">
                {body}
              </span>
            </button>
          </Reveal>
        );
      }

      return (
        <Reveal key={entry.label} delay={delay} className={cell}>
          {body}
        </Reveal>
      );
    })}
  </dl>
);

export default MetricMatrix;
