import React, { useState } from 'react';
import { useCountUp, useScrollDriver } from './hooks';
import { CHANGE_SCENARIOS } from './data';
/*
  Propagation runs outward from the change, so it borrows the product's outbound
  tone rather than inventing a landing-page colour. Imported, never redeclared.
*/
import { EDGE_TONE } from '../interactive/graph/edgeSemantics';

/* ─────────────────────────────────────────────────────────────────────────────
 * ChangeSurface — chapter 04.
 *
 * The consequence of the graph. One continuous path runs from the changed
 * symbol to the entry point it reaches, lit a stage at a time. The spine grows
 * from a CSS custom property written by the scroll driver, so scrolling costs no
 * React renders; only the lit-stage index is stateful.
 *
 * What this section deliberately does *not* claim: the chapter used to lead with
 * a "BLAST RADIUS RISK 84 / 100" score and a red HIGH severity badge. Neither is
 * measured — no backend produces them, and the thresholds behind the severity
 * were invented for the illustration. Structural propagation is the honest
 * story, so the readout now reports what the chain actually contains: how many
 * files and symbols it reaches, and how deep it runs.
 * ────────────────────────────────────────────────────────────────────────── */

/** Longest chain in the set, so every scenario maps onto the same stage count. */
const MAX_STAGES = Math.max(...CHANGE_SCENARIOS.map((s) => s.chain.length));

export const ChangeSurface: React.FC = () => {
  const [scenarioId, setScenarioId] = useState(CHANGE_SCENARIOS[0].id);
  const { ref, step, reduced } = useScrollDriver<HTMLDivElement>({
    from: 0.2,
    to: 0.66,
    steps: MAX_STAGES,
  });

  const scenario = CHANGE_SCENARIOS.find((s) => s.id === scenarioId) ?? CHANGE_SCENARIOS[0];

  const lit = Math.min(scenario.chain.length, step + 1);
  /*
    Order matters: the reader watches the change travel, and only then is told
    how far it went. Interpretation that arrives before the propagation turns the
    section into a dashboard with an animation attached, so the read-out stays
    dormant until the chain has fully resolved.
  */
  const resolved = lit >= scenario.chain.length;
  /** A real count from the scenario: how many files the chain reaches. */
  const filesValue = useCountUp(scenario.files, resolved);
  /** Name of the propagation state currently lit. */
  const currentStage = scenario.chain[Math.max(0, lit - 1)]?.stage ?? scenario.chain[0].stage;

  return (
    <div ref={ref} className="grid grid-cols-1 lg:grid-cols-12 gap-10 lg:gap-14">
      {/* ── Left rail: scenario switch + risk read-out ────────────────────── */}
      <div className="lg:col-span-4 flex flex-col gap-9 lg:sticky lg:top-24 lg:self-start">
        <div>
          <span className="mono-label block mb-4">SIMULATE A DIFF</span>
          <div className="flex flex-col">
            {CHANGE_SCENARIOS.map((s) => {
              const isActive = s.id === scenario.id;
              return (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => setScenarioId(s.id)}
                  aria-pressed={isActive}
                  className={`group lumen-button text-left py-3.5 px-2 -mx-2 rounded hair-t last:border-b last:border-white/[0.055]
                              focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary
                              ${isActive ? 'text-text' : 'text-text-subtle hover:text-text-muted'}`}
                >
                  <span className="flex items-center gap-3">
                    <span
                      className={`h-1 w-1 rounded-full transition-transform duration-300 ${isActive ? 'bg-primary scale-150' : 'bg-white/20'
                        }`}
                      aria-hidden="true"
                    />
                    <span className="font-mono text-xs break-all">
                      {s.symbol.replace('()', '')}
                    </span>
                  </span>
                  <span className="mono-detail block mt-1.5 pl-4" style={{ fontSize: 10 }}>
                    {s.file}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/*
          Affected surface — the telemetry, read after the propagation. The
          headline is a count of what the chain reaches, not a score of how bad it
          is: the difference between reporting structure and predicting outcomes.
        */}
        <div
          style={{
            opacity: resolved ? 1 : 0.85,
            transform: resolved ? 'none' : 'translateY(6px)',
            transition:
              'opacity 700ms cubic-bezier(0.16,1,0.3,1), transform 700ms cubic-bezier(0.16,1,0.3,1)',
          }}
          className="p-6 rounded-xl border border-white/[0.08] bg-gradient-to-b from-[#0D1220]/95 to-[#070A12]/98 backdrop-blur-2xl shadow-2xl"
        >
          {/* DIFF != IMPACT distinction */}
          <div className="flex items-center justify-between pb-3 mb-4 border-b border-white/[0.08]">
            <span className="mono-label font-bold flex items-center gap-1.5" style={{ color: EDGE_TONE.outgoing }}>
              <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: EDGE_TONE.outgoing, boxShadow: `0 0 6px ${EDGE_TONE.outgoing}cc` }}></span>
              DIFF ≠ IMPACT
            </span>
            <span className="mono-label text-[10px] text-[#34D399] font-bold px-2 py-0.5 rounded bg-[#34D399]/10 border border-[#34D399]/30">CALL GRAPH PROVEN</span>
          </div>

          <span className="mono-label block mb-2 text-[#94A3B8] font-bold">AFFECTED SURFACE</span>
          <div className="flex items-baseline gap-2.5">
            <span className="font-mono text-5xl sm:text-6xl font-extrabold tabular-nums leading-none text-[#F8FAFC] tracking-tight">
              {Math.round(filesValue)}
            </span>
            <span className="font-mono text-xs text-[#CBD5E1] uppercase tracking-wider font-bold">files reached</span>
          </div>

          {/* Reach across the chain, drawn once the chain is complete. */}
          <div className="mt-4 h-[3px] w-full bg-white/[0.06] overflow-hidden rounded-full">
            <div
              className="h-full origin-left bg-gradient-to-r from-primary to-[#34D399]"
              style={{
                transform: `scaleX(${resolved ? 1 : 0})`,
                transition: 'transform 1000ms cubic-bezier(0.16,1,0.3,1)',
                boxShadow: '0 0 10px rgba(129,140,248,0.6)',
              }}
            />
          </div>

          <dl className="mt-5 grid grid-cols-3 gap-3 pt-4 border-t border-white/[0.08]">
            {[
              { k: 'DEPTH', v: scenario.depth },
              { k: 'SYMBOLS', v: scenario.symbols },
              { k: 'HOPS', v: scenario.chain.length },
            ].map((m) => (
              <div key={m.k} className="p-2.5 rounded-lg bg-[#0A0D14] border border-white/[0.06] text-center">
                <dt className="mono-label mb-1 text-[9.5px] text-[#94A3B8] font-bold">{m.k}</dt>
                <dd className="font-mono text-base font-bold text-[#F8FAFC] tabular-nums">{m.v}</dd>
              </div>
            ))}
          </dl>

          {/* Current propagation state, so the rail and the chain stay in step. */}
          <p className="mono-label mt-4 text-[10px] text-[#CBD5E1]" style={{ letterSpacing: '0.18em' }}>
            STATE · <span className="font-bold" style={{ color: EDGE_TONE.outgoing }}>{currentStage}</span>
          </p>

          {/* Matches the disclosure wording used by chapters 02 and 03. */}
          <p className="mono-label mt-1 text-[9px] text-[#64748B]" style={{ letterSpacing: '0.18em' }}>
            ILLUSTRATIVE · ARIA&apos;S OWN REPOSITORY
          </p>
        </div>
      </div>

      {/* ── Right: one continuous propagation path ────────────────────────── */}
      <div className="lg:col-span-8">
        <ol className="relative pl-11 sm:pl-14">
          {/* Static spine */}
          <span
            className="absolute left-[13px] sm:left-[17px] top-2 bottom-10 w-px bg-white/[0.07]"
            aria-hidden="true"
          />
          {/* Growing spine — height comes from --p, written outside React */}
          <span
            className="change-spine absolute left-[13px] sm:left-[17px] top-2 w-px"
            aria-hidden="true"
          />
          {/* Traveling Signal Dot */}
          {step > 0 && (
            <span
              className="absolute left-[13px] sm:left-[17px] top-2"
              style={{
                top: 'calc(var(--p, 0) * 100% + 8px)',
                width: '4px',
                height: '4px',
                borderRadius: '50%',
                background: '#737DFF',
                boxShadow: '0 0 8px 2px rgba(115,125,255,0.6)',
                transform: 'translateX(-1.5px)',
              }}
              aria-hidden="true"
            />
          )}

          {scenario.chain.map((stage, i) => {
            const isLit = i < lit;
            const isHead = i === 0;

            return (
              <li
                key={`${scenario.id}-${i}`}
                className="relative pb-10 sm:pb-12 last:pb-0"
                style={{
                  opacity: isLit ? 1 : 0.78,
                  transform: isLit ? 'none' : 'translateY(4px)',
                  transition:
                    'opacity 700ms cubic-bezier(0.16,1,0.3,1), transform 700ms cubic-bezier(0.16,1,0.3,1)',
                }}
              >
                <span
                  className={`absolute -left-11 sm:-left-14 top-0 flex h-7 w-7 sm:h-9 sm:w-9 items-center justify-center
                              rounded-full border font-mono text-[10px] transition-colors duration-500 ${isLit
                      ? 'border-primary/60 bg-primary/12 text-primary font-semibold'
                      : 'border-white/10 bg-canvas text-text-subtle'
                    }`}
                  aria-hidden="true"
                >
                  {!reduced && i === lit - 1 && (
                    <span
                      key={`${scenario.id}-wake-${i}`}
                      className="stage-wake absolute inset-0 rounded-full border border-primary/50"
                    />
                  )}
                  {String(i + 1).padStart(2, '0')}
                </span>

                {i > 0 && (
                  <span
                    className="absolute -left-[30px] sm:-left-[38px] -top-5 font-mono text-[11px] leading-none"
                    style={{
                      color: isLit ? '#737DFF' : 'rgba(255,255,255,0.12)',
                      transition: 'color 500ms ease',
                    }}
                    aria-hidden="true"
                  >
                    ▼
                  </span>
                )}

                <span className="mono-label block mb-2.5 text-text-secondary font-semibold">{stage.stage}</span>

                <p
                  className={`font-mono break-all leading-snug ${isHead
                      ? 'text-base sm:text-xl text-text font-semibold'
                      : 'text-sm sm:text-base text-text'
                    }`}
                >
                  {stage.target}
                </p>

                <p className="mt-2.5 text-[13px] text-text-muted leading-relaxed max-w-xl">
                  {stage.detail}
                </p>
              </li>
            );
          })}
        </ol>

        {/* The point of the section, then the bridge onward. */}
        <div className="mt-12 hair-t pt-6">
          <p className="display-3 text-text font-bold">A change is never isolated.</p>
          <p className="story-lead mt-3 text-[14px] text-text-secondary max-w-xl">
            Traced through the <span className="text-primary font-semibold">call graph</span> before the merge — not inferred from the diff text.
          </p>
        </div>
      </div>
    </div>
  );
};

export default ChangeSurface;
