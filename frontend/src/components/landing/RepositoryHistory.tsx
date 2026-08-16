import React from 'react';
import { useMediaQuery, useScrollDriver } from './hooks';
import {
  HISTORY_ERAS,
  HISTORY_SUMMARY,
  REPOSITORY_HISTORY,
  type HistorySpan,
} from './data';

/* ─────────────────────────────────────────────────────────────────────────────
 * RepositoryHistory — chapter 05.
 *
 * The chapter where the page gains time. Every other chapter describes what the
 * repository *is*; this one describes how it *changed*.
 *
 * Time runs left to right. Each module occupies the span it was actually being
 * worked on, and luminance carries churn — how much of the module was rewritten
 * across that span. A hotspot is the intersection of the two things the rest of
 * the page has already established: high churn landing on a structurally central
 * module.
 *
 * Nothing here animates as though commits were arriving. Spans are drawn as the
 * chapter is read, once, and then rest: the reveal is discovery, not activity.
 * Scroll drives the axis through --p; only the coarse row index is stateful.
 * ────────────────────────────────────────────────────────────────────────── */

/** Churn → resting luminance. Deliberately narrow: nothing here reaches neon. */
function churnTone(churn: number, lit: boolean): string {
  const alpha = (0.22 + churn * 0.68) * (lit ? 1 : 0.16);
  return `rgba(129, 140, 248, ${alpha.toFixed(3)})`;
}

interface RowProps {
  span: HistorySpan;
  index: number;
  lit: boolean;
  active: boolean;
}

const HistoryRow: React.FC<RowProps> = ({ span, index, lit, active }) => {
  const left = span.from * 100;
  const width = Math.max(2, (span.to - span.from) * 100);

  return (
    <li
      className="hair-t last:border-b last:border-white/[0.055]"
      aria-current={active ? 'true' : undefined}
    >
      <div
        className="grid grid-cols-[1fr] sm:grid-cols-[minmax(0,15rem)_minmax(0,1fr)_4.5rem]
                   items-center gap-y-2.5 sm:gap-x-6 py-4 sm:py-5"
        style={{
          opacity: lit ? 1 : 0.3,
          transition: 'opacity 700ms cubic-bezier(0.16,1,0.3,1)',
        }}
      >
        {/* Module */}
        <div className="min-w-0">
          <p
            className="font-mono text-[12px] sm:text-[13px] leading-snug transition-colors duration-500"
            style={{
              color: active ? '#ffffff' : lit ? 'var(--text)' : 'var(--text-subtle)',
              fontWeight: active ? 600 : 400,
              wordBreak: 'break-word',
              overflowWrap: 'anywhere',
            }}
          >
            {span.path.includes('/') ? (
              <>
                <span className="text-text-subtle/70">{span.path.slice(0, span.path.lastIndexOf('/') + 1)}</span>
                <span>{span.path.slice(span.path.lastIndexOf('/') + 1)}</span>
              </>
            ) : (
              span.path
            )}
          </p>
          <span className="mono-label block mt-1.5">{span.role}</span>
        </div>

        {/*
          The span across the window. `era-field` draws the same minor divisions
          as the axis behind the track, so a span is read against measured time
          rather than floating in the row.
        */}
        <div className="era-field relative h-5 flex items-center min-w-0">
          {/* Resting track, so an inactive module still reads as present */}
          <span
            className="absolute left-0 right-0 h-px bg-white/[0.045]"
            aria-hidden="true"
          />

          <span
            className="absolute h-[2px]"
            style={{ left: `${left}%`, width: `${width}%` }}
            aria-hidden="true"
          >
            <span
              className="churn-bar block w-full"
              style={
                {
                  backgroundColor: churnTone(span.churn, lit),
                  transform: `scaleX(${lit ? 1 : 0})`,
                  '--reveal-delay': `${index * 90}ms`,
                } as React.CSSProperties
              }
            />
          </span>

          {/*
            Hotspot marker, at the end of the span — where change is still
            landing. Settles once, then rests; it never pulses.
          */}
          {span.hotspot && lit && (
            <span
              key={`hot-${span.path}`}
              className="hotspot absolute h-2 w-2 -translate-x-1/2 rounded-full"
              style={
                {
                  left: `${span.to * 100}%`,
                  background: 'rgba(143,155,245,0.9)',
                  boxShadow: '0 0 12px 2px rgba(94,106,210,0.5)',
                  '--reveal-delay': `${index * 90 + 320}ms`,
                } as React.CSSProperties
              }
              aria-hidden="true"
            />
          )}
        </div>

        {/* Commits */}
        <span
          className="font-mono text-[13px] tabular-nums sm:text-right transition-colors duration-500"
          style={{ color: active ? 'var(--primary)' : lit ? 'var(--text)' : 'var(--text-subtle)' }}
        >
          {span.commits}
        </span>
      </div>
    </li>
  );
};

export const RepositoryHistory: React.FC = () => {
  /* Mobile recomposes rather than shrinks: fewer modules, same argument. */
  const compact = useMediaQuery('(max-width: 639px)');
  const spans = compact ? REPOSITORY_HISTORY.filter((s) => s.compact) : REPOSITORY_HISTORY;

  const { ref, step } = useScrollDriver<HTMLDivElement>({
    from: 0.16,
    to: 0.7,
    steps: spans.length,
  });

  const active = spans[Math.min(step, spans.length - 1)];
  const lit = step + 1;

  return (
    <div ref={ref} className="grid grid-cols-1 lg:grid-cols-12 gap-10 lg:gap-14">
      {/* ── Rail: what the temporal reading adds ─────────────────────────── */}
      <div className="lg:col-span-4 lg:sticky lg:top-24 lg:self-start">
        <p className="text-[13px] text-text-muted leading-relaxed max-w-sm">
          Structure tells you how the repository is arranged. History tells you which parts of it
          are still moving.
        </p>

        <dl className="mt-9 grid grid-cols-3 gap-4">
          {[
            { k: 'COMMITS', v: HISTORY_SUMMARY.commits.toLocaleString() },
            { k: 'MODULES', v: String(HISTORY_SUMMARY.files) },
            { k: 'HOTSPOTS', v: String(HISTORY_SUMMARY.hotspots) },
          ].map((m) => (
            <div key={m.k}>
              <dt className="mono-label mb-1.5">{m.k}</dt>
              <dd className="font-mono text-lg text-text tabular-nums">{m.v}</dd>
            </div>
          ))}
        </dl>

        {/*
          Commentary for the module currently in the reading. Height is reserved
          so advancing never reflows the rail or the rows beside it.
        */}
        <div className="mt-9 min-h-[7rem]" aria-live="polite">
          <span className="mono-label mono-label-accent block mb-3">{active.role}</span>
          <p className="text-[13px] text-text leading-relaxed max-w-sm">{active.note}</p>
          <p className="mono-detail mt-3" style={{ fontSize: 10 }}>
            {active.commits} COMMITS · {Math.round(active.churn * 100)}% REWRITTEN
            {active.hotspot ? ' · HOTSPOT' : ''}
          </p>
        </div>

        <p className="mono-label mt-2" style={{ letterSpacing: '0.2em' }}>
          ILLUSTRATIVE · ARIA&apos;S OWN REPOSITORY
        </p>
      </div>

      {/* ── The window ───────────────────────────────────────────────────── */}
      <div className="lg:col-span-8 min-w-0">
        {/*
          Axis. Labels describe the window; the rule draws with the scroll.
          The padding lines the axis up with the span column of the rows below:
          15rem module column + 1.5rem gap on the left, 4.5rem commit column +
          1.5rem gap on the right. Kept as literals — `calc()` inside a Tailwind
          arbitrary value needs escaped whitespace and fails silently without it.
        */}
        <div className="sm:pl-[16.5rem] sm:pr-[6rem]">
          <div className="flex items-baseline justify-between mb-2.5">
            {HISTORY_ERAS.map((era) => (
              <span key={era} className="mono-label tabular-nums">
                {era}
              </span>
            ))}
          </div>
          <div className="era-axis" aria-hidden="true" />
          {/* Minor divisions, so a span is read against a measured window. */}
          <div className="era-ticks" aria-hidden="true" />
        </div>

        <ol className="mt-1">
          {spans.map((span, i) => (
            <HistoryRow
              key={span.path}
              span={span}
              index={i}
              lit={i < lit}
              active={i === Math.min(step, spans.length - 1)}
            />
          ))}
        </ol>

        {/* Accessible equivalent of the temporal chart. */}
        <p className="sr-only">
          Change history across {HISTORY_ERAS[0]} to {HISTORY_ERAS[HISTORY_ERAS.length - 1]}, for{' '}
          {spans.length} modules. Figures are illustrative, drawn from ARIA&apos;s own repository.
        </p>
        <ul className="sr-only">
          {spans.map((s) => (
            <li key={s.path}>
              {s.path} — {s.role}, {s.commits} commits, {Math.round(s.churn * 100)} percent
              rewritten{s.hotspot ? ', architectural hotspot' : ''}. {s.note}
            </li>
          ))}
        </ul>

        <p className="display-3 text-text mt-12 sm:mt-14">
          ARIA understands not only what the repository is,
          <br className="hidden sm:block" />
          <span className="display-dim"> but how it changes.</span>
        </p>
      </div>
    </div>
  );
};

export default RepositoryHistory;
