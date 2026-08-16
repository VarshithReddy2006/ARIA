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
      <div className="flex items-center justify-between gap-4 mb-10 sm:mb-14">
        <span className="mono-label truncate" aria-live="polite">
          STAGE {active.step} · {active.title}
        </span>
        <span className="mono-label hidden sm:block shrink-0">
          ISOLATED ANALYZERS · DETERMINISTIC
        </span>
      </div>

      <div className="relative">
        {/* ── Horizontal track (md and up) ─────────────────────────────────── */}
        <span
          className="hidden md:block absolute left-0 right-0 top-[13px] h-px bg-white/[0.07]"
          aria-hidden="true"
        />
        <span
          className="pipeline-track-fill hidden md:block absolute left-0 right-0 top-[13px] h-px"
          aria-hidden="true"
        />
        {/* Travelling head */}
        <span
          className="pipeline-head hidden md:block absolute top-[13px] h-2 w-2 rounded-full bg-white"
          style={{ boxShadow: '0 0 12px 2px rgba(94,106,210,0.8)' }}
          aria-hidden="true"
        />

        {/* ── Vertical track (below md) ────────────────────────────────────── */}
        <span
          className="md:hidden absolute left-[13px] top-0 bottom-0 w-px bg-white/[0.07]"
          aria-hidden="true"
        />
        <span
          className="pipeline-track-fill-y md:hidden absolute left-[13px] top-0 bottom-0 w-px"
          aria-hidden="true"
        />
        <span
          className="pipeline-head-y md:hidden absolute left-[13px] h-2 w-2 rounded-full bg-white"
          style={{ boxShadow: '0 0 12px 2px rgba(94,106,210,0.8)' }}
          aria-hidden="true"
        />

        <ol className="grid grid-cols-1 md:grid-cols-5 gap-10 md:gap-6 relative">
          {PIPELINE_STAGES.map((stage, i) => {
            const isActive = i === step;
            const isReached = i <= step;

            return (
              <li key={stage.step} className="relative pl-11 md:pl-0">
                {/* Track node */}
                <span
                  className="absolute left-[9px] top-[9px] md:relative md:left-0 md:top-0 md:block md:mb-7 md:h-[27px]"
                  aria-hidden="true"
                >
                  <span className="relative block h-[7px] w-[7px] md:mt-[10px]">
                    {/*
                      Activation wave: the stage the travelling head has just
                      reached wakes once, and the ring dissipates outward toward
                      the next stage. Keyed on the stage index so it fires per
                      advance — computational, not a loop implying live execution.
                    */}
                    {!reduced && isActive && (
                      <span
                        key={`wake-${step}`}
                        className="stage-wake absolute -inset-[3px] rounded-full border border-primary/60"
                      />
                    )}
                    <span
                      className="block h-full w-full rounded-full"
                      style={{
                        background: isReached ? '#5e6ad2' : '#22242e',
                        outline: isReached ? 'none' : '1px solid rgba(255,255,255,0.12)',
                        transform: isActive ? 'scale(1.5)' : 'scale(1)',
                        transition:
                          'transform 400ms cubic-bezier(0.16,1,0.3,1), background-color 400ms ease',
                      }}
                    />
                  </span>
                </span>

                <div
                  style={{
                    opacity: isReached ? 1 : 0.4,
                    transition: 'opacity 600ms cubic-bezier(0.16,1,0.3,1)',
                  }}
                >
                  <span className={`mono-label block mb-3 ${isActive ? 'mono-label-accent' : ''}`}>
                    {stage.step}
                  </span>

                  <h3
                    className={`font-mono font-bold tracking-tight transition-colors duration-500 ${isReached ? 'text-text' : 'text-text-subtle'
                      }`}
                    style={{ fontSize: 'clamp(1.05rem, 1.8vw, 1.375rem)' }}
                  >
                    {stage.title}
                  </h3>

                  <p className="mt-2 mono-detail" style={{ fontSize: 10, letterSpacing: '0.14em' }}>
                    {stage.sub.toUpperCase()}
                  </p>

                  <p className="mt-4 text-[13px] leading-relaxed text-text-muted max-w-xs md:max-w-none">
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
