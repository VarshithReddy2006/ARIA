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

/** Churn → resting luminance with vibrant gradient tone */
function churnTone(churn: number, lit: boolean): string {
  const alpha = (0.35 + churn * 0.65) * (lit ? 1 : 0.25);
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
      className={`border-t border-white/[0.06] transition-all duration-300 ${
        active ? 'bg-indigo-500/[0.04] sm:rounded-lg px-2 -mx-2' : ''
      }`}
      aria-current={active ? 'true' : undefined}
    >
      <div
        className="grid grid-cols-[1fr] sm:grid-cols-[minmax(0,15rem)_minmax(0,1fr)_4.5rem]
                   items-center gap-y-2.5 sm:gap-x-6 py-3.5 sm:py-4"
        style={{
          opacity: lit ? 1 : 0.75,
          transition: 'opacity 700ms cubic-bezier(0.16,1,0.3,1)',
        }}
      >
        {/* Module */}
        <div className="min-w-0">
          <p
            className="font-mono text-[12px] sm:text-[13px] leading-snug transition-colors duration-300"
            style={{
              color: active ? '#ffffff' : lit ? '#F1F5F9' : '#94A3B8',
              fontWeight: active ? 600 : 400,
              wordBreak: 'break-word',
              overflowWrap: 'anywhere',
            }}
          >
            {span.path.includes('/') ? (
              <>
                <span className="text-[#64748B]">{span.path.slice(0, span.path.lastIndexOf('/') + 1)}</span>
                <span className={active ? 'text-indigo-300 font-semibold' : 'text-[#E2E8F0]'}>{span.path.slice(span.path.lastIndexOf('/') + 1)}</span>
              </>
            ) : (
              span.path
            )}
          </p>
          <span className={`mono-label block mt-1 text-[10px] ${active ? 'text-indigo-400' : 'text-[#64748B]'}`}>{span.role}</span>
        </div>

        {/*
          The span across the window. `era-field` draws the same minor divisions
          as the axis behind the track.
        */}
        <div className="era-field relative h-6 flex items-center min-w-0">
          {/* Resting track */}
          <span
            className="absolute left-0 right-0 h-px bg-white/[0.08]"
            aria-hidden="true"
          />

          <span
            className="absolute h-[3px] rounded-full overflow-hidden"
            style={{ left: `${left}%`, width: `${width}%` }}
            aria-hidden="true"
          >
            <span
              className="churn-bar block w-full h-full rounded-full shadow-[0_0_8px_rgba(129,140,248,0.3)]"
              style={
                {
                  background: lit ? `linear-gradient(90deg, rgba(99,102,241,0.7), rgba(129,140,248,1))` : churnTone(span.churn, lit),
                  transform: `scaleX(${lit ? 1 : 0})`,
                  '--reveal-delay': `${index * 90}ms`,
                } as React.CSSProperties
              }
            />
          </span>

          {/* Hotspot marker */}
          {span.hotspot && lit && (
            <span
              key={`hot-${span.path}`}
              className="hotspot absolute h-2.5 w-2.5 -translate-x-1/2 rounded-full ring-2 ring-[#050608]"
              style={
                {
                  left: `${span.to * 100}%`,
                  background: '#818CF8',
                  boxShadow: '0 0 14px 3px rgba(129,140,248,0.75)',
                  '--reveal-delay': `${index * 90 + 320}ms`,
                } as React.CSSProperties
              }
              aria-hidden="true"
            />
          )}
        </div>

        {/* Commits */}
        <span
          className="font-mono text-[12px] sm:text-[13px] tabular-nums sm:text-right transition-colors duration-300"
          style={{ color: active ? '#818CF8' : lit ? '#CBD5E1' : '#64748B', fontWeight: active ? 600 : 400 }}
        >
          {span.commits} <span className="text-[10px] text-[#64748B] sm:hidden">commits</span>
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
    <div ref={ref} className="grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-12">
      {/* ── Rail: what the temporal reading adds ─────────────────────────── */}
      <div className="lg:col-span-4 lg:sticky lg:top-24 lg:self-start">
        <div className="p-6 rounded-2xl bg-gradient-to-b from-[#0D1220]/90 to-[#070A12]/95 border border-white/[0.08] shadow-[0_16px_36px_rgba(0,0,0,0.6)] backdrop-blur-2xl">
          <div className="flex items-center gap-2 mb-3">
            <span className="w-2 h-2 rounded-full bg-indigo-400 shadow-[0_0_8px_rgba(129,140,248,0.6)]" />
            <span className="font-mono text-[10px] tracking-[0.2em] uppercase text-indigo-300 font-bold">TEMPORAL TELEMETRY</span>
          </div>

          <p className="text-[13px] text-[#94A3B8] leading-relaxed">
            Structure tells you how the repository is arranged. History tells you which parts of it
            are still moving.
          </p>

          <dl className="mt-6 pt-5 border-t border-white/[0.07] grid grid-cols-3 gap-3">
            {[
              { k: 'COMMITS', v: HISTORY_SUMMARY.commits.toLocaleString(), c: 'text-indigo-400' },
              { k: 'MODULES', v: String(HISTORY_SUMMARY.files), c: 'text-sky-400' },
              { k: 'HOTSPOTS', v: String(HISTORY_SUMMARY.hotspots), c: 'text-emerald-400' },
            ].map((m) => (
              <div key={m.k} className="p-2.5 rounded-lg bg-[#050608]/60 border border-white/[0.04]">
                <dt className="mono-label mb-1 text-[9px] text-[#64748B]">{m.k}</dt>
                <dd className={`font-mono text-base font-bold tabular-nums ${m.c}`}>{m.v}</dd>
              </div>
            ))}
          </dl>

          {/* Commentary for the module currently in the reading */}
          <div className="mt-6 pt-5 border-t border-white/[0.07] min-h-[6.5rem]" aria-live="polite">
            <div className="flex items-center justify-between mb-2">
              <span className="mono-label text-indigo-400 font-semibold">{active.role}</span>
              {active.hotspot && (
                <span className="px-2 py-0.5 rounded-full bg-indigo-500/20 border border-indigo-500/40 text-[9px] font-mono text-indigo-300 font-semibold">
                  HOTSPOT
                </span>
              )}
            </div>
            <p className="text-[13px] text-[#F1F5F9] leading-relaxed">{active.note}</p>
            <div className="mt-3 flex items-center gap-2 text-[10px] font-mono text-[#94A3B8]">
              <span className="text-white font-semibold">{active.commits} COMMITS</span>
              <span className="text-white/20">·</span>
              <span className="text-indigo-300 font-semibold">{Math.round(active.churn * 100)}% REWRITTEN</span>
            </div>
          </div>

          <p className="mono-label mt-4 text-[9px] text-[#64748B]" style={{ letterSpacing: '0.2em' }}>
            ILLUSTRATIVE · ARIA&apos;S OWN REPOSITORY
          </p>
        </div>
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
