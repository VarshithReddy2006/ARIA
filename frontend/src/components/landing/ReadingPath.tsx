import React from 'react';
import { useScrollDriver } from './hooks';
import { READING_PATH } from './data';

/* ─────────────────────────────────────────────────────────────────────────────
 * ReadingPath — chapter 06.
 *
 * A centrality-ranked sequence, and the reason the ranking exists.
 *
 * The rows are a fixed-height list: emphasis is carried entirely by colour and
 * weight, never by size or padding, so advancing the active item cannot shift
 * anything below it. The commentary for the active step lives in the rail on the
 * left instead of expanding inline, which is what used to cause the jump.
 * ────────────────────────────────────────────────────────────────────────── */

export const ReadingPath: React.FC = () => {
  const { ref, step } = useScrollDriver<HTMLDivElement>({
    from: 0.16,
    to: 0.72,
    steps: READING_PATH.length,
  });

  const active = READING_PATH[step];
  const totalMinutes = READING_PATH.reduce((sum, s) => sum + s.minutes, 0);

  return (
    <div ref={ref} className="grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-12">
      {/* ── Rail: why the order exists, and where we are in it ───────────── */}
      <div className="lg:col-span-4 lg:sticky lg:top-24 lg:self-start">
        <div className="p-6 rounded-2xl bg-gradient-to-b from-[#0D1220]/90 to-[#070A12]/95 border border-white/[0.08] shadow-[0_16px_36px_rgba(0,0,0,0.6)] backdrop-blur-2xl">
          <div className="flex items-center gap-2 mb-3">
            <span className="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.6)] animate-pulse" />
            <span className="mono-label text-emerald-400 font-bold text-[10px] tracking-[0.2em] uppercase">ARCHITECTURAL ONBOARDING</span>
          </div>

          <p className="text-[13px] text-[#94A3B8] leading-relaxed">
            Start where the architecture says the code matters most — not at the top of the
            alphabet.
          </p>

          <div className="mt-6 pt-5 border-t border-white/[0.07] flex items-baseline justify-between">
            <div className="flex items-baseline gap-1.5">
              <span className="font-mono text-4xl text-white font-bold tabular-nums leading-none">
                {String(step + 1).padStart(2, '0')}
              </span>
              <span className="font-mono text-xs text-[#64748B]">/ {String(READING_PATH.length).padStart(2, '0')}</span>
            </div>
            <span className="px-2.5 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-[10px] font-mono text-emerald-300 font-semibold">
              ~{totalMinutes} MIN TOTAL
            </span>
          </div>

          {/* Progress rail — height driven by --p */}
          <div className="mt-4 h-[3px] w-full bg-white/[0.07] rounded-full relative overflow-hidden">
            <span
              className="absolute left-0 top-0 h-full w-full origin-left bg-gradient-to-r from-emerald-500 via-indigo-500 to-sky-400 shadow-[0_0_8px_rgba(52,211,153,0.5)]"
              style={{ transform: 'scaleX(var(--p, 0))' }}
              aria-hidden="true"
            />
          </div>

          {/* Commentary for the active step */}
          <div className="mt-6 pt-5 border-t border-white/[0.07] min-h-[6.5rem]" aria-live="polite">
            <span className="mono-label text-emerald-400 font-semibold block mb-2 text-[11px]">{active.role}</span>
            <p className="text-[13px] text-[#F1F5F9] leading-relaxed">{active.note}</p>
            <div className="mt-3 flex items-center gap-2 text-[10px] font-mono text-[#94A3B8]">
              <span className="text-white font-semibold">PAGERANK {active.rank.toFixed(2)}</span>
              <span className="text-white/20">·</span>
              <span className="text-emerald-300 font-semibold">~{active.minutes} MIN READ</span>
            </div>
          </div>

          <p className="mono-label mt-4 text-[9px] text-[#64748B]" style={{ letterSpacing: '0.2em' }}>
            ILLUSTRATIVE RANKING
          </p>
        </div>
      </div>

      {/* ── The route ──────────────────────────────────────────────────────── */}
      <ol className="lg:col-span-8 space-y-1">
        {READING_PATH.map((s, i) => {
          const isActive = i === step;
          const isPast = i < step;
          const isReached = i <= step;
          const isLast = i === READING_PATH.length - 1;

          return (
            <li
              key={s.index}
              className={`relative border border-transparent transition-all duration-300 rounded-xl ${
                isActive
                  ? 'bg-gradient-to-r from-indigo-500/[0.08] to-emerald-500/[0.04] border-indigo-500/20 shadow-[0_4px_20px_rgba(0,0,0,0.3)]'
                  : 'hover:bg-white/[0.02]'
              }`}
            >
              <div
                className="relative flex items-center gap-4 sm:gap-6 py-4 sm:py-5 px-4"
                style={{
                  opacity: isActive ? 1 : isPast ? 0.85 : 0.70,
                  transition: 'opacity 600ms cubic-bezier(0.16,1,0.3,1)',
                }}
              >
                {/* Route: the resting path */}
                {!isLast && (
                  <span
                    className="absolute left-[20px] top-1/2 bottom-0 w-px bg-white/[0.08]"
                    aria-hidden="true"
                  />
                )}
                {/* Route: the travelled segment */}
                {!isLast && (
                  <span
                    className={`route-seg absolute left-[20px] top-1/2 bottom-0 w-px ${
                      isPast ? 'is-lit' : ''
                    }`}
                    style={{ background: isPast ? 'linear-gradient(180deg, #34D399, #818CF8)' : 'rgba(94,106,210,0.4)' }}
                    aria-hidden="true"
                  />
                )}

                {/* Stop marker on the route */}
                <span
                  className="relative z-10 shrink-0 h-3 w-3 rounded-full border ring-4 ring-[#050608]"
                  style={{
                    borderColor: isReached ? '#34D399' : 'rgba(255,255,255,0.18)',
                    backgroundColor: isActive ? '#34D399' : isPast ? '#0D1220' : '#050608',
                    boxShadow: isActive ? '0 0 14px 3px rgba(52,211,153,0.7)' : 'none',
                    transition:
                      'background-color 500ms ease, border-color 500ms ease, box-shadow 500ms ease',
                  }}
                  aria-hidden="true"
                />

                <span
                  className={`font-mono text-xs tabular-nums shrink-0 transition-colors duration-300 ${
                    isActive ? 'text-emerald-400 font-bold' : 'text-[#64748B]'
                  }`}
                >
                  {s.index}
                </span>

                <div className="min-w-0 flex-1">
                  <p
                    className={`font-mono text-[13px] sm:text-[14px] leading-snug transition-colors duration-300 ${
                      isActive ? 'text-white font-semibold' : 'text-[#CBD5E1]'
                    }`}
                    style={{
                      wordBreak: 'break-word',
                      overflowWrap: 'anywhere',
                    }}
                  >
                    {s.path.includes('/') ? (
                      <>
                        <span className="text-[#64748B]">{s.path.slice(0, spanPathCut(s.path))}</span>
                        <span className={isActive ? 'text-white font-bold' : 'text-[#E2E8F0]'}>{s.path.slice(spanPathCut(s.path))}</span>
                      </>
                    ) : (
                      s.path
                    )}
                  </p>
                  <div className="mono-label mt-1.5 flex items-center gap-2.5 text-[10px]">
                    <span className={isActive ? 'text-indigo-300 font-medium' : 'text-[#64748B]'}>{s.role}</span>
                    <span className="text-white/20">·</span>
                    <span
                      className={`font-mono ${isActive ? 'text-emerald-400 font-semibold' : 'text-[#64748B]'}`}
                    >
                      ~{s.minutes} MIN
                    </span>
                  </div>
                </div>

                <div className="shrink-0 w-16 sm:w-28 text-right">
                  <span
                    className={`font-mono text-xs sm:text-sm tabular-nums transition-colors duration-300 ${
                      isActive ? 'text-emerald-300 font-bold' : 'text-[#64748B]'
                    }`}
                  >
                    {s.rank.toFixed(2)}
                  </span>
                  <span
                    className="mt-1.5 hidden sm:block h-[3px] w-full bg-white/[0.06] rounded-full overflow-hidden"
                    aria-hidden="true"
                  >
                    <span
                      className={`block h-full origin-left rounded-full transition-colors duration-500 ${
                        isActive ? 'bg-gradient-to-r from-indigo-500 to-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.5)]' : 'bg-white/20'
                      }`}
                      style={{
                        transform: `scaleX(${s.rank})`,
                        transition: 'transform 900ms cubic-bezier(0.16,1,0.3,1)',
                      }}
                    />
                  </span>
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
};

function spanPathCut(path: string): number {
  return path.lastIndexOf('/') + 1;
}

export default ReadingPath;
