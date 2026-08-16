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
            opacity: resolved ? 1 : 0.16,
            transform: resolved ? 'none' : 'translateY(10px)',
            transition:
              'opacity 700ms cubic-bezier(0.16,1,0.3,1), transform 700ms cubic-bezier(0.16,1,0.3,1)',
          }}
        >
          <span className="mono-label block mb-4">AFFECTED SURFACE</span>
          <div className="flex items-end gap-3">
            <span className="font-mono text-4xl sm:text-5xl font-bold tabular-nums leading-none text-text">
              {Math.round(filesValue)}
            </span>
            <span className="mono-detail pb-1.5">files reached</span>
          </div>

          {/* Reach across the chain, drawn once the chain is complete. */}
          <div className="mt-4 h-[3px] w-full bg-white/[0.06] overflow-hidden">
            <div
              className="h-full origin-left"
              style={{
                backgroundColor: EDGE_TONE.outgoing,
                transform: `scaleX(${resolved ? 1 : 0})`,
                transition: 'transform 1000ms cubic-bezier(0.16,1,0.3,1)',
              }}
            />
          </div>

          <dl className="mt-6 grid grid-cols-3 gap-4">
            {[
              { k: 'DEPTH', v: scenario.depth },
              { k: 'SYMBOLS', v: scenario.symbols },
              { k: 'HOPS', v: scenario.chain.length },
            ].map((m) => (
              <div key={m.k}>
                <dt className="mono-label mb-1.5">{m.k}</dt>
                <dd className="font-mono text-lg text-text tabular-nums">{m.v}</dd>
              </div>
            ))}
          </dl>

          {/* Current propagation state, so the rail and the chain stay in step. */}
          <p className="mono-label mt-6" style={{ letterSpacing: '0.2em' }}>
            STATE · {currentStage}
          </p>

          {/* Matches the disclosure wording used by chapters 02 and 03. */}
          <p className="mono-label mt-2" style={{ letterSpacing: '0.2em' }}>
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
                background: '#5e6ad2',
                boxShadow: '0 0 8px 2px rgba(94,106,210,0.6)',
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
                  opacity: isLit ? 1 : 0.22,
                  transform: isLit ? 'none' : 'translateY(10px)',
                  transition:
                    'opacity 700ms cubic-bezier(0.16,1,0.3,1), transform 700ms cubic-bezier(0.16,1,0.3,1)',
                }}
              >
                <span
                  className={`absolute -left-11 sm:-left-14 top-0 flex h-7 w-7 sm:h-9 sm:w-9 items-center justify-center
                              rounded-full border font-mono text-[10px] transition-colors duration-500 ${isLit
                      ? 'border-primary/60 bg-primary/12 text-primary'
                      : 'border-white/10 bg-canvas text-text-subtle'
                    }`}
                  aria-hidden="true"
                >
                  {/*
                    The stage that has just been reached emits one ring, which
                    dissipates. Keyed on the stage index so it fires once per
                    advance rather than looping — the change arriving here, not a
                    process running here.
                  */}
                  {!reduced && i === lit - 1 && (
                    <span
                      key={`${scenario.id}-wake-${i}`}
                      className="stage-wake absolute inset-0 rounded-full border border-primary/50"
                    />
                  )}
                  {String(i + 1).padStart(2, '0')}
                </span>

                {/*
                  Direction, stated on the spine. The chain previously ran as a
                  plain vertical rule, which showed sequence but not causality —
                  a reader could not tell propagation from a numbered list.
                */}
                {i > 0 && (
                  <span
                    className="absolute -left-[30px] sm:-left-[38px] -top-5 font-mono text-[11px] leading-none"
                    style={{
                      color: isLit ? EDGE_TONE.outgoing : 'rgba(255,255,255,0.12)',
                      transition: 'color 500ms ease',
                    }}
                    aria-hidden="true"
                  >
                    ▼
                  </span>
                )}

                {/*
                  The stage name only. The index is already on the marker beside
                  it, and repeating it in the "01 — " form made every propagation
                  step look like a chapter marker competing with the real one at
                  the top of the section.
                */}
                <span className="mono-label block mb-2.5">{stage.stage}</span>

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
          <p className="display-3 text-text">A change is never isolated.</p>
          <p className="mono-detail mt-3 max-w-xl">
            Traced through the call graph before the merge — not inferred from the diff text.
            Before you merge, ARIA can show how far a change travels.
          </p>
        </div>
      </div>
    </div>
  );
};

export default ChangeSurface;
