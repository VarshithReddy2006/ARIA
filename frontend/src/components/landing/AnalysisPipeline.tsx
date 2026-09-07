import React from 'react';
import { useScrollDriver } from './hooks';
import { PIPELINE_STAGES } from './data';

/* ─────────────────────────────────────────────────────────────────────────────
 * AnalysisPipeline — chapter 07.
 *
 * Five stages on one continuous track. A single point travels the track as the
 * visitor scrolls, activating each stage as it passes; the running description
 * below the track updates with it. Track fill and head position both come from
 * the --p custom property, so scrolling triggers no React work.
 *
 * The track rotates to vertical below md without changing any of the logic.
 * ────────────────────────────────────────────────────────────────────────── */

export const AnalysisPipeline: React.FC = () => {
  const { ref, step, reduced } = useScrollDriver<HTMLDivElement>({
    from: 0.2,
    to: 0.68,
    steps: PIPELINE_STAGES.length,
  });

  const active = PIPELINE_STAGES[step];

  return (
    <div ref={ref}>
      <div className="flex items-center justify-between gap-4 mb-8 sm:mb-12 p-3.5 rounded-xl bg-[#080B12]/80 border border-white/[0.06] backdrop-blur-xl">
        <div className="flex items-center gap-2.5">
          <span className="w-2 h-2 rounded-full bg-indigo-400 shadow-[0_0_8px_rgba(129,140,248,0.8)] animate-pulse" />
          <span className="font-mono text-xs font-bold text-white tracking-wider truncate" aria-live="polite">
            STAGE {active.step} · {active.title}
          </span>
        </div>
        <span className="mono-label text-[10px] text-indigo-300 hidden sm:block shrink-0 tracking-widest">
          ISOLATED ANALYZERS · DETERMINISTIC ENGINE
        </span>
      </div>

      <div className="relative">
        {/* ── Horizontal track (md and up) ─────────────────────────────────── */}
        <span
          className="hidden md:block absolute left-0 right-0 top-[18px] h-px bg-white/[0.08]"
          aria-hidden="true"
        />
        <span
          className="pipeline-track-fill hidden md:block absolute left-0 right-0 top-[18px] h-px"
          style={{ background: 'linear-gradient(90deg, #6366F1, #38BDF8)' }}
          aria-hidden="true"
        />
        {/* Travelling head */}
        <span
          className="pipeline-head hidden md:block absolute top-[18px] h-3 w-3 rounded-full bg-white ring-4 ring-[#050608]"
          style={{ boxShadow: '0 0 16px 4px rgba(129,140,248,0.9)' }}
          aria-hidden="true"
        />

        {/* ── Vertical track (below md) ────────────────────────────────────── */}
        <span
          className="md:hidden absolute left-[16px] top-0 bottom-0 w-px bg-white/[0.08]"
          aria-hidden="true"
        />
        <span
          className="pipeline-track-fill-y md:hidden absolute left-[16px] top-0 bottom-0 w-px"
          aria-hidden="true"
        />
        <span
          className="pipeline-head-y md:hidden absolute left-[16px] h-3 w-3 rounded-full bg-white ring-4 ring-[#050608]"
          style={{ boxShadow: '0 0 16px 4px rgba(129,140,248,0.9)' }}
          aria-hidden="true"
        />

        <ol className="grid grid-cols-1 md:grid-cols-5 gap-6 md:gap-4 relative">
          {PIPELINE_STAGES.map((stage, i) => {
            const isActive = i === step;
            const isReached = i <= step;

            return (
              <li key={stage.step} className="relative pl-12 md:pl-0">
                {/* Track node */}
                <span
                  className="absolute left-[10px] top-[14px] md:relative md:left-0 md:top-0 md:block md:mb-6 md:h-[36px]"
                  aria-hidden="true"
                >
                  <span className="relative block h-3 w-3 md:mt-[12px]">
                    {!reduced && isActive && (
                      <span
                        key={`wake-${step}`}
                        className="stage-wake absolute -inset-1.5 rounded-full border-2 border-indigo-400"
                        style={{ boxShadow: '0 0 12px rgba(129,140,248,0.6)' }}
                      />
                    )}
                    <span
                      className="block h-full w-full rounded-full ring-2 ring-[#050608]"
                      style={{
                        background: isReached ? '#818CF8' : '#1E293B',
                        boxShadow: isReached ? '0 0 10px rgba(129,140,248,0.6)' : 'none',
                        transform: isActive ? 'scale(1.3)' : 'scale(1)',
                        transition:
                          'transform 400ms cubic-bezier(0.16,1,0.3,1), background-color 400ms ease',
                      }}
                    />
                  </span>
                </span>

                <div
                  className={`p-5 rounded-2xl transition-all duration-300 border ${
                    isActive
                      ? 'bg-gradient-to-b from-[#0D1220] to-[#070A12] border-indigo-500/40 shadow-[0_12px_32px_rgba(99,102,241,0.15)]'
                      : isReached
                      ? 'bg-[#080B12]/80 border-white/[0.08]'
                      : 'bg-[#050608]/50 border-white/[0.04]'
                  }`}
                  style={{
                    opacity: isReached ? 1 : 0.65,
                    transition: 'opacity 600ms cubic-bezier(0.16,1,0.3,1)',
                  }}
                >
                  <div className="flex items-center justify-between mb-3">
                    <span className={`mono-label text-[10px] font-bold ${isActive ? 'text-indigo-400' : 'text-[#64748B]'}`}>
                      {stage.step}
                    </span>
                    {isActive && (
                      <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 shadow-[0_0_6px_rgba(129,140,248,0.9)] animate-pulse" />
                    )}
                  </div>

                  <h3
                    className={`font-mono font-bold tracking-tight transition-colors duration-300 ${
                      isActive ? 'text-white' : isReached ? 'text-[#F1F5F9]' : 'text-[#94A3B8]'
                    }`}
                    style={{ fontSize: 'clamp(0.95rem, 1.4vw, 1.15rem)' }}
                  >
                    {stage.title}
                  </h3>

                  <p className="mt-1.5 font-mono text-[10px] tracking-wider text-indigo-300/80 font-semibold uppercase">
                    {stage.sub}
                  </p>

                  <p className="mt-3 text-[12px] leading-relaxed text-[#94A3B8]">
                    {stage.detail}
                  </p>
                </div>
              </li>
            );
          })}
        </ol>
      </div>
    </div>
  );
};

export default AnalysisPipeline;
