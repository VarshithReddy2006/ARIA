/**
 * Shared presentation primitives for the two PR instruments.
 *
 * PR Risk and PR Drift ask different questions but are built from the same
 * parts: a command workspace, a compact waiting state, a PR identity readout,
 * section heads and evidence rows. These live here so the two surfaces stay
 * siblings instead of drifting into separate dialects.
 *
 * Presentation only — no fetching, no derivation, no scoring.
 */

import React from 'react';
import { ArrowRight } from 'lucide-react';

/**
 * The command workspace: analysis input beside its diagnostics.
 *
 * One coordinated surface rather than two cards — a single vertical hairline
 * divides them at desktop width and they stack below `lg`. 65/35 per spec, with
 * the gap shrinking before either side loses readable content.
 */
export const CommandWorkspace: React.FC<{
  input: React.ReactNode;
  diagnostics: React.ReactNode;
}> = ({ input, diagnostics }) => (
  <div
    className="grid grid-cols-1 gap-y-9 items-start min-w-0
               lg:grid-cols-[minmax(0,65fr)_minmax(0,35fr)] lg:gap-x-8 xl:gap-x-10"
  >
    <div className="min-w-0">{input}</div>
    <div className="min-w-0 lg:pl-8 xl:pl-10 lg:border-l lg:border-white/[0.055]">
      {diagnostics}
    </div>
  </div>
);

/**
 * Compact waiting state. Occupies roughly the rhythm of the command surface
 * rather than a viewport-sized rectangle, and names the pipeline it is waiting
 * to run so the empty state still teaches the model.
 */
export const WaitingState: React.FC<{
  label: string;
  pipeline: string;
  children: React.ReactNode;
}> = ({ label, pipeline, children }) => (
  <div className="min-w-0">
    <span className="mono-label block mb-3">{label}</span>
    <p className="mono-detail mb-4" style={{ fontSize: 10, letterSpacing: '0.16em' }}>
      {pipeline}
    </p>
    <p className="text-[13px] text-text-muted leading-relaxed max-w-lg">{children}</p>
  </div>
);

/**
 * PR identity. The number is the indigo anchor, the state sits beside it, and
 * the subject line carries the weight — no decorative container.
 */
export const PRIdentity: React.FC<{
  prNumber: number;
  state?: string;
  stateTone?: string;
  /** The readable subject: a PR title on Risk, the repository on Drift. */
  subject: React.ReactNode;
  metadata: React.ReactNode;
  action?: React.ReactNode;
}> = ({ prNumber, state, stateTone = 'text-text-muted', subject, metadata, action }) => (
  <header className="min-w-0">
    <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
      <div className="min-w-0">
        <div className="flex items-baseline gap-4 flex-wrap">
          <span className="font-mono text-[19px] font-semibold text-primary tabular-nums">
            #{prNumber}
          </span>
          {state && (
            <span className={`font-mono text-[10px] uppercase tracking-[0.16em] ${stateTone}`}>
              {state}
            </span>
          )}
        </div>
        <div className="mt-2 min-w-0">{subject}</div>
        <p className="mono-detail mt-2.5" style={{ fontSize: 10, letterSpacing: '0.14em' }}>
          {metadata}
        </p>
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  </header>
);

/** A section head with an optional right-aligned criterion or count. */
export const SectionHead: React.FC<{
  id: string;
  title: string;
  accent?: boolean;
  aside?: React.ReactNode;
}> = ({ id, title, accent = false, aside }) => (
  <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1 pb-3 hair-b">
    <h3 id={id} className={`mono-label ${accent ? 'mono-label-accent' : ''}`}>
      {title}
    </h3>
    {aside && <span className="shrink-0">{aside}</span>}
  </div>
);

/**
 * A label with a hairline leader running to its value — the readout shape used
 * by both diagnostics panels and the metric strips.
 */
export const LeaderRow: React.FC<{
  label: string;
  children: React.ReactNode;
  first?: boolean;
}> = ({ label, children, first = false }) => (
  <div
    className={`flex items-baseline gap-3 py-2.5 min-w-0 ${
      first ? '' : 'border-t border-white/[0.055]'
    }`}
  >
    <dt className="mono-label shrink-0">{label}</dt>
    <span className="flex-1 h-px bg-white/[0.05] min-w-[1rem]" aria-hidden="true" />
    <dd className="shrink-0 text-right min-w-0">{children}</dd>
  </div>
);

/** Quiet mono status text. Semantic colour is the caller's decision. */
export const StatusText: React.FC<{ tone?: string; children: React.ReactNode }> = ({
  tone = 'text-text',
  children,
}) => (
  <span className={`font-mono text-[11px] uppercase tracking-[0.14em] ${tone}`}>{children}</span>
);

/** An arrowed quiet action, matching the language used across the workspace. */
export const InstrumentAction: React.FC<{
  onClick?: () => void;
  href?: string;
  ariaLabel?: string;
  children: React.ReactNode;
}> = ({ onClick, href, ariaLabel, children }) => {
  const content = (
    <>
      {children}
      <ArrowRight className="h-2.5 w-2.5 arrow ml-1" aria-hidden="true" />
    </>
  );

  if (href) {
    return (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="api-action link-arrow"
        aria-label={ariaLabel}
      >
        {content}
      </a>
    );
  }
  return (
    <button type="button" onClick={onClick} className="api-action link-arrow" aria-label={ariaLabel}>
      {content}
    </button>
  );
};

/**
 * A zero/non-zero change row for a matrix: the count carries semantic colour
 * only when something actually changed, so empty rows stay quiet instead of
 * competing with real findings.
 */
export const MatrixRow: React.FC<{
  label: string;
  count: number;
  /** Tone applied only when `count > 0`. */
  tone?: string;
  /** Shown when the count is zero. */
  quietEvidence: string;
  /** Shown when the count is non-zero. */
  children?: React.ReactNode;
}> = ({ label, count, tone = 'text-text', quietEvidence, children }) => {
  const active = count > 0;

  return (
    <li className="api-row py-3 border-t border-white/[0.055] last:border-b last:border-white/[0.055] min-w-0">
      <div className="grid grid-cols-[minmax(0,1fr)_auto] sm:grid-cols-[minmax(0,34fr)_auto_minmax(0,58fr)] gap-x-5 gap-y-1.5 items-baseline min-w-0">
        <span className="mono-label min-w-0">{label}</span>
        <span
          className={`font-mono text-[13px] tabular-nums text-right ${
            active ? tone : 'text-text-subtle'
          }`}
        >
          {count}
        </span>
        <span className="col-span-2 sm:col-span-1 min-w-0">
          {active ? (
            children
          ) : (
            <span className="text-[12px] text-text-subtle leading-relaxed">{quietEvidence}</span>
          )}
        </span>
      </div>
    </li>
  );
};
