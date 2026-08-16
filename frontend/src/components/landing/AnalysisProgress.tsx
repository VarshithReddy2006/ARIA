import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useReducedMotion } from './hooks';
import type { AnalysisStep } from '../../lib/useRepoAnalysis';

/* ─────────────────────────────────────────────────────────────────────────────
 * AnalysisProgress — the live pipeline, in the story's own language.
 *
 * This is the same deterministic pipeline chapter 07 describes, now running for
 * real: one continuous track, a point that travels it, stages that light in
 * sequence, hairline rules and monospace metadata. No rounded cards, no block
 * characters, no strikethrough.
 *
 * The ten SSE statuses are grouped into seven stages, listed in the order the
 * backend emits them so a later stage can never complete before an earlier one.
 * ────────────────────────────────────────────────────────────────────────── */

interface Stage {
  id: string;
  index: string;
  label: string;
  sub: string;
  /** SSE status ids that make up this stage. */
  steps: string[];
  /** Rough duration in seconds, used only to estimate time remaining. */
  typical: number;
}

const STAGES: Stage[] = [
  { id: 'clone', index: '01', label: 'CLONE', sub: 'Target repository', steps: ['cloning'], typical: 3.5 },
  { id: 'detect', index: '02', label: 'DETECT', sub: 'Ecosystem & stacks', steps: ['detecting'], typical: 1.0 },
  { id: 'parse', index: '03', label: 'PARSE', sub: 'Source files', steps: ['parsing'], typical: 4.0 },
  { id: 'embed', index: '04', label: 'EMBED', sub: 'Vector index', steps: ['generating_embeddings'], typical: 7.0 },
  {
    id: 'index',
    index: '05',
    label: 'INDEX',
    sub: 'Symbols, dependencies & calls',
    steps: ['building_symbols', 'building_dependency', 'building_call', 'building_api'],
    typical: 6.0,
  },
  { id: 'analyze', index: '06', label: 'ANALYZE', sub: 'Graph intelligence', steps: ['computing_intel'], typical: 4.0 },
  { id: 'answer', index: '07', label: 'ANSWER', sub: 'Report generation', steps: ['generating_report'], typical: 2.5 },
];

type StageStatus = 'pending' | 'active' | 'completed';

interface Props {
  steps: AnalysisStep[];
}

export const AnalysisProgress: React.FC<Props> = ({ steps }) => {
  const reduced = useReducedMotion();
  const [now, setNow] = useState(() => Date.now());

  const startedAt = useRef(Date.now());
  const stageStart = useRef<Record<string, number>>({});
  const stageEnd = useRef<Record<string, number>>({});

  /** Roll the ten step statuses up into seven stage statuses. */
  const stages = useMemo(
    () =>
      STAGES.map((stage) => {
        const statuses = stage.steps.map(
          (id) => steps.find((s) => s.id === id)?.status ?? 'pending'
        );

        let status: StageStatus = 'pending';
        if (statuses.every((s) => s === 'completed')) status = 'completed';
        else if (statuses.some((s) => s === 'active' || s === 'completed')) status = 'active';

        const done = statuses.filter((s) => s === 'completed').length;
        return { ...stage, status, done, total: stage.steps.length };
      }),
    [steps]
  );

  // Record when each stage began and ended so durations are real, not guessed.
  useEffect(() => {
    stages.forEach((stage) => {
      if (stage.status === 'active' && !stageStart.current[stage.id]) {
        stageStart.current[stage.id] = Date.now();
      }
      if (stage.status === 'completed') {
        if (!stageStart.current[stage.id]) stageStart.current[stage.id] = Date.now();
        if (!stageEnd.current[stage.id]) stageEnd.current[stage.id] = Date.now();
      }
    });
  }, [stages]);

  const finished = stages.every((s) => s.status === 'completed');

  // A single clock drives every elapsed read-out. Stops once the run finishes.
  useEffect(() => {
    if (finished) return;
    const id = window.setInterval(() => setNow(Date.now()), 120);
    return () => window.clearInterval(id);
  }, [finished]);

  const secondsIn = (stageId: string, status: StageStatus) => {
    const start = stageStart.current[stageId];
    if (!start) return 0;
    if (status === 'completed') return ((stageEnd.current[stageId] ?? now) - start) / 1000;
    return (now - start) / 1000;
  };

  /** Fractional completion of a stage, for its own rail. */
  const fractionOf = (stage: (typeof stages)[number]) => {
    if (stage.status === 'completed') return 1;
    if (stage.status === 'pending') return 0;
    if (stage.total > 1) {
      // Multi-step stages report real sub-step progress.
      return Math.min(0.92, stage.done / stage.total + 0.12);
    }
    const elapsed = secondsIn(stage.id, stage.status);
    return Math.min(0.92, (elapsed / stage.typical) * 0.8);
  };

  const overall = stages.reduce((sum, s) => sum + fractionOf(s), 0) / stages.length;
  const elapsed = (now - startedAt.current) / 1000;

  const remaining = stages.reduce((sum, s) => {
    if (s.status === 'completed') return sum;
    if (s.status === 'pending') return sum + s.typical;
    return sum + Math.max(0.2, s.typical - secondsIn(s.id, s.status));
  }, 0);

  const activeStage = stages.find((s) => s.status === 'active');

  return (
    <section className="w-full" aria-label="Analysis progress">
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
        <div className="flex items-center gap-2.5 min-w-0">
          <span
            className={`h-1.5 w-1.5 shrink-0 rounded-full ${
              finished ? 'bg-success' : 'bg-primary status-dot'
            }`}
            aria-hidden="true"
          />
          <span className="mono-label truncate">
            {finished ? 'PIPELINE COMPLETE' : `RUNNING · ${activeStage?.label ?? 'CLONE'}`}
          </span>
        </div>

        <div className="flex items-baseline gap-5 shrink-0">
          <span className="mono-detail" style={{ fontSize: 10 }}>
            ELAPSED{' '}
            <span className="text-text tabular-nums">{elapsed.toFixed(1)}s</span>
          </span>
          {!finished && (
            <span className="mono-detail" style={{ fontSize: 10 }}>
              REMAINING{' '}
              <span className="text-primary tabular-nums">~{Math.ceil(remaining)}s</span>
            </span>
          )}
          <span className="font-mono text-xl sm:text-2xl text-text tabular-nums leading-none">
            {Math.round(overall * 100)}
            <span className="text-text-subtle text-sm">%</span>
          </span>
        </div>
      </div>

      {/* ── Continuous track, mirroring the pipeline chapter ───────────────── */}
      <div className="relative mt-5 h-px w-full bg-white/[0.08]">
        <span
          className="absolute left-0 top-0 h-full w-full origin-left"
          style={{
            transform: `scaleX(${overall})`,
            background: 'linear-gradient(90deg, rgba(94,106,210,0.4), #8f9bf5)',
            transition: reduced ? 'none' : 'transform 400ms cubic-bezier(0.16,1,0.3,1)',
          }}
          aria-hidden="true"
        />
        {!finished && !reduced && (
          <span
            className="absolute top-0 h-1.5 w-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white"
            style={{
              left: `${overall * 100}%`,
              boxShadow: '0 0 12px 2px rgba(94,106,210,0.8)',
              transition: 'left 400ms cubic-bezier(0.16,1,0.3,1)',
            }}
            aria-hidden="true"
          />
        )}
      </div>

      {/* ── Stages ─────────────────────────────────────────────────────────── */}
      <ol className="mt-2" aria-live="polite">
        {stages.map((stage, i) => {
          const isActive = stage.status === 'active';
          const isDone = stage.status === 'completed';
          const fraction = fractionOf(stage);
          const seconds = secondsIn(stage.id, stage.status);

          return (
            <li
              key={stage.id}
              className="hair-t last:border-b last:border-white/[0.055]"
              style={{
                opacity: isDone ? 0.55 : isActive ? 1 : 0.4,
                transition: reduced ? 'none' : 'opacity 500ms ease',
                animation: reduced
                  ? undefined
                  : `fade-up 420ms cubic-bezier(0.16,1,0.3,1) ${i * 60}ms both`,
              }}
            >
              <div className="flex items-center gap-4 sm:gap-6 py-3.5">
                {/* Stage marker */}
                <span className="shrink-0 flex items-center gap-3 w-[3.25rem] sm:w-[4.5rem]">
                  <span
                    className={`h-1.5 w-1.5 rounded-full shrink-0 ${
                      isDone ? 'bg-success' : isActive ? 'bg-primary status-dot' : 'bg-white/20'
                    }`}
                    aria-hidden="true"
                  />
                  <span
                    className={`font-mono text-[11px] tabular-nums ${
                      isActive ? 'text-primary' : 'text-text-subtle'
                    }`}
                  >
                    {stage.index}
                  </span>
                </span>

                {/* Name + sub */}
                <span className="min-w-0 flex-1">
                  <span
                    className={`block font-mono text-[13px] tracking-[0.08em] ${
                      isActive ? 'text-text font-semibold' : isDone ? 'text-text-muted' : 'text-text-subtle'
                    }`}
                  >
                    {stage.label}
                  </span>
                  <span className="mono-detail hidden sm:block mt-1" style={{ fontSize: 10 }}>
                    {stage.sub}
                  </span>
                </span>

                {/* Per-stage rail, replacing the old block-character bar */}
                <span
                  className="hidden sm:block shrink-0 w-24 lg:w-40 h-px bg-white/[0.08] relative"
                  aria-hidden="true"
                >
                  <span
                    className={`absolute inset-0 origin-left ${isDone ? 'bg-success/60' : 'bg-primary'}`}
                    style={{
                      transform: `scaleX(${fraction})`,
                      transition: reduced ? 'none' : 'transform 400ms cubic-bezier(0.16,1,0.3,1)',
                    }}
                  />
                </span>

                {/* Duration */}
                <span
                  className={`shrink-0 w-14 text-right font-mono text-[11px] tabular-nums ${
                    isDone ? 'text-success' : isActive ? 'text-primary' : 'text-text-subtle'
                  }`}
                >
                  {isDone || isActive ? `${seconds.toFixed(1)}s` : '—'}
                </span>
              </div>
            </li>
          );
        })}
      </ol>

      <p className="mono-detail mt-5" style={{ fontSize: 10, letterSpacing: '0.16em' }}>
        DETERMINISTIC AST PARSER · NETWORKX TOPOLOGY · ZERO WRITEBACK
      </p>
    </section>
  );
};

export default AnalysisProgress;
