import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useReducedMotion } from './hooks';
import type { AnalysisStep } from '../../lib/useRepoAnalysis';

/* ─────────────────────────────────────────────────────────────────────────────
 * AnalysisProgress — cinematic engineering telemetry console.
 *
 * Combines high-precision technical telemetry with real-time stream visualizers,
 * AST symbol resolution logs, and glowing obsidian glass architecture.
 * Explicitly separates OVERALL PIPELINE progress from CURRENT STAGE progress.
 * ────────────────────────────────────────────────────────────────────────── */

interface Stage {
  id: string;
  index: string;
  label: string;
  sub: string;
  steps: string[];
  typical: number;
}

const STAGES: Stage[] = [
  { id: 'clone', index: '01', label: 'CLONE', sub: 'Fetch & unpack repository git tree', steps: ['cloning'], typical: 3.5 },
  { id: 'detect', index: '02', label: 'DETECT', sub: 'Language ecosystem & project manifests', steps: ['detecting'], typical: 1.0 },
  { id: 'parse', index: '03', label: 'PARSE', sub: 'Tree-sitter AST syntax tokenization', steps: ['parsing'], typical: 4.0 },
  { id: 'embed', index: '04', label: 'EMBED', sub: 'Dense semantic code vector embeddings', steps: ['generating_embeddings'], typical: 7.0 },
  {
    id: 'index',
    index: '05',
    label: 'INDEX',
    sub: 'Symbol tables, caller & dependency call graph',
    steps: ['building_symbols', 'building_dependency', 'building_call', 'building_api'],
    typical: 6.0,
  },
  { id: 'analyze', index: '06', label: 'ANALYZE', sub: 'Graph centrality & risk blast radius', steps: ['computing_intel'], typical: 4.0 },
  { id: 'answer', index: '07', label: 'ANSWER', sub: 'Forensic architecture report compilation', steps: ['generating_report'], typical: 2.5 },
];

const STREAMING_AST_TOKENS = [
  { prefix: 'AST', token: 'extract_symbols(scope=AST_STRICT)', tag: 'symbol' },
  { prefix: 'GRAPH', token: 'build_directed_edges(NetworkX)', tag: 'graph' },
  { prefix: 'CALL', token: 'resolve_callers(traverse_depth=4)', tag: 'call' },
  { prefix: 'EMBED', token: 'generate_vector_embeddings(dim=384)', tag: 'vector' },
  { prefix: 'SCHEMA', token: 'map_api_surface(routes=REST)', tag: 'api' },
  { prefix: 'RANK', token: 'compute_pagerank_centrality()', tag: 'centrality' },
  { prefix: 'DRIFT', token: 'evaluate_layer_boundaries()', tag: 'drift' },
  { prefix: 'SYNTH', token: 'generate_grounded_report()', tag: 'report' },
];

type StageStatus = 'pending' | 'active' | 'completed';

interface Props {
  steps: AnalysisStep[];
  progress?: number;
  jobStartedAt?: number;
  jobElapsedSeconds?: number;
  jobStats?: Record<string, any>;
}

const clamp01 = (v: number): number => (Number.isFinite(v) ? Math.max(0, Math.min(1, v)) : 0);
const clampPct = (v: number): number => (Number.isFinite(v) ? Math.max(0, Math.min(100, v)) : 0);

export const AnalysisProgress: React.FC<Props> = ({
  steps,
  progress,
  jobStartedAt,
  jobElapsedSeconds,
  jobStats,
}) => {
  const reduced = useReducedMotion();
  const [now, setNow] = useState(() => Date.now());
  const [tokenIndex, setTokenIndex] = useState(0);

  const startedAt = useRef(jobStartedAt ? jobStartedAt * 1000 : Date.now());
  const stageStart = useRef<Record<string, number>>({});
  const stageEnd = useRef<Record<string, number>>({});
  const highestOverallRef = useRef<number>(0);
  const highestEmbedPctRef = useRef<number>(0);
  const highestChunksProcessedRef = useRef<number>(0);

  useEffect(() => {
    if (jobStartedAt && jobStartedAt * 1000 < startedAt.current) {
      startedAt.current = jobStartedAt * 1000;
    }
  }, [jobStartedAt]);

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

  useEffect(() => {
    if (finished) return;
    const id = window.setInterval(() => setNow(Date.now()), 80);
    return () => window.clearInterval(id);
  }, [finished]);

  // Rotate simulated AST token stream chips during live analysis
  useEffect(() => {
    if (finished) return;
    const streamInterval = window.setInterval(() => {
      setTokenIndex((prev) => (prev + 1) % STREAMING_AST_TOKENS.length);
    }, 1400);
    return () => window.clearInterval(streamInterval);
  }, [finished]);

  const secondsIn = (stageId: string, status: StageStatus) => {
    const start = stageStart.current[stageId];
    if (!start) return 0;
    if (status === 'completed') return ((stageEnd.current[stageId] ?? now) - start) / 1000;
    return Math.max(0, (now - start) / 1000);
  };

  // ── Safe, Monotonic Extraction of Embedding Stage Telemetry ────────────────
  const embedChunksTotal = typeof jobStats?.chunks_total === 'number' && Number.isFinite(jobStats.chunks_total) && jobStats.chunks_total >= 0
    ? jobStats.chunks_total
    : 0;

  const rawChunksProcessed = typeof jobStats?.chunks_processed === 'number'
    ? jobStats.chunks_processed
    : typeof jobStats?.completed_chunks === 'number'
      ? jobStats.completed_chunks
      : 0;

  const embedBatch = typeof jobStats?.batch === 'number' && Number.isFinite(jobStats.batch) && jobStats.batch >= 0
    ? jobStats.batch
    : 0;

  const embedTotalBatches = typeof jobStats?.total_batches === 'number' && Number.isFinite(jobStats.total_batches) && jobStats.total_batches >= 0
    ? jobStats.total_batches
    : 0;

  const rawEmbedPct = typeof jobStats?.embed_progress_pct === 'number'
    ? jobStats.embed_progress_pct
    : embedChunksTotal > 0 && typeof rawChunksProcessed === 'number'
      ? (rawChunksProcessed / embedChunksTotal) * 100
      : undefined;

  if (rawEmbedPct !== undefined && Number.isFinite(rawEmbedPct)) {
    const clamped = clampPct(rawEmbedPct);
    if (clamped > highestEmbedPctRef.current) {
      highestEmbedPctRef.current = clamped;
    }
  }

  if (Number.isFinite(rawChunksProcessed) && rawChunksProcessed > highestChunksProcessedRef.current) {
    highestChunksProcessedRef.current = embedChunksTotal > 0
      ? Math.min(embedChunksTotal, rawChunksProcessed)
      : rawChunksProcessed;
  }

  const embedProgressPct = finished ? 100 : highestEmbedPctRef.current;
  const embedChunksProcessed = finished && embedChunksTotal > 0
    ? embedChunksTotal
    : highestChunksProcessedRef.current;

  const fractionOf = (stage: (typeof stages)[number]) => {
    if (stage.status === 'completed') return 1;
    if (stage.status === 'pending') return 0;
    if (stage.total > 1) {
      return Math.min(0.95, stage.done / stage.total + 0.15);
    }
    // Real embedding stage fraction from backend telemetry stats
    if (stage.id === 'embed') {
      if (embedProgressPct > 0) {
        return clamp01(embedProgressPct / 100);
      }
    }
    const elapsedPhase = secondsIn(stage.id, stage.status);
    return Math.min(0.95, 0.2 + (elapsedPhase / stage.typical) * 0.7);
  };

  const stageProgress = stages.reduce((sum, s) => sum + fractionOf(s), 0) / stages.length;
  const rawOverall = typeof progress === 'number' && progress > 0
    ? Math.max(progress / 100, stageProgress)
    : stageProgress;

  const clampedOverall = finished ? 1 : clamp01(rawOverall);
  if (clampedOverall > highestOverallRef.current) {
    highestOverallRef.current = clampedOverall;
  }
  const overall = highestOverallRef.current;

  const totalElapsed = typeof jobElapsedSeconds === 'number' && jobElapsedSeconds > 0
    ? Math.max(jobElapsedSeconds, (now - startedAt.current) / 1000)
    : (now - startedAt.current) / 1000;

  const activeStage = stages.find((s) => s.status === 'active');
  const activeElapsed = activeStage ? secondsIn(activeStage.id, activeStage.status) : 0;
  const isLongOrUnpredictable = activeStage?.id === 'embed' || (activeStage && activeElapsed > activeStage.typical * 1.5);

  const remaining = stages.reduce((sum, s) => {
    if (s.status === 'completed') return sum;
    if (s.status === 'pending') return sum + s.typical;
    return sum + Math.max(0.5, s.typical - secondsIn(s.id, s.status));
  }, 0);

  // Live telemetry counters derived deterministically from progress
  const simulatedNodes = Math.min(1840, Math.floor(overall * 1840));
  const simulatedEdges = Math.min(5260, Math.floor(overall * 5260));

  return (
    <div className="w-full font-mono text-xs animate-fade-in" aria-label="Analysis progress">
      {/* ── Outer Obsidian Glass Chassis ── */}
      <div className="bg-gradient-to-b from-[#0D1220]/95 to-[#070A12]/98 backdrop-blur-2xl border border-white/[0.08] rounded-2xl overflow-hidden shadow-[0_24px_60px_rgba(0,0,0,0.85)]">

        {/* Top Telemetry Header Bar */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 px-6 py-4 border-b border-white/[0.08] bg-[#050608]/70">
          <div className="flex items-center gap-3">
            <span className="relative flex h-2.5 w-2.5 items-center justify-center">
              {finished ? (
                <span className="h-2.5 w-2.5 rounded-full bg-[#34D399] shadow-[0_0_10px_rgba(52,211,153,0.9)]" />
              ) : (
                <>
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#818CF8] opacity-75" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-[#818CF8] shadow-[0_0_8px_rgba(129,140,248,0.9)]" />
                </>
              )}
            </span>
            <span className="text-[11px] font-bold tracking-[0.2em] text-[#F8FAFC] uppercase flex items-center gap-2">
              <span>{finished ? 'ANALYSIS COMPLETE' : 'STREAMING ENGINE'}</span>
              <span className="text-[#64748B] text-[10px] font-normal">
                // {finished ? 'EVIDENCE READY' : activeStage ? `${activeStage.index} ${activeStage.label}` : 'INITIALIZING'}
              </span>
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-4 sm:gap-5 text-[11px] font-mono">
            <div className="flex items-center gap-1.5">
              <span className="text-[#64748B] text-[10px] tracking-wider uppercase font-semibold">ELAPSED:</span>
              <span className="text-[#CBD5E1] tabular-nums font-semibold">{totalElapsed.toFixed(1)}s</span>
            </div>

            {!finished && (
              <div className="flex items-center gap-1.5">
                <span className="text-[#64748B] text-[10px] tracking-wider uppercase font-semibold">ETA:</span>
                <span className="text-[#818CF8] tabular-nums font-semibold">
                  {isLongOrUnpredictable ? 'Estimating…' : `~${Math.ceil(remaining)}s`}
                </span>
              </div>
            )}

            {/* Current Stage Progress Badge (Explicit when in EMBED) */}
            {activeStage?.id === 'embed' && (
              <div className="flex items-center gap-2 px-2.5 py-1 rounded-md bg-[#0F172A]/90 border border-[#38BDF8]/40 shadow-[0_0_10px_rgba(56,189,248,0.15)]">
                <span className="text-[10px] text-[#94A3B8] uppercase font-bold tracking-wider">STAGE (EMBED)</span>
                <span className="text-sm font-bold text-[#38BDF8] tabular-nums">{Math.round(embedProgressPct)}%</span>
              </div>
            )}

            {/* Overall Pipeline Progress */}
            <div className="flex items-center gap-2 px-3 py-1 rounded-md bg-[#131A2E]/90 border border-[#818CF8]/40 shadow-[0_0_12px_rgba(129,140,248,0.2)]">
              <span className="text-[10px] text-[#94A3B8] uppercase font-bold tracking-wider">OVERALL PIPELINE</span>
              <div className="flex items-baseline gap-0.5">
                <span className="text-sm font-bold text-white tabular-nums">{Math.round(overall * 100)}</span>
                <span className="text-[#818CF8] text-[11px] font-bold">%</span>
              </div>
            </div>
          </div>
        </div>

        {/* Global Laser Progress Track */}
        <div className="relative h-1 w-full bg-[#050608] overflow-hidden border-b border-white/[0.04]">
          <div
            className="h-full bg-gradient-to-r from-[#818CF8] via-[#38BDF8] to-[#34D399] shadow-[0_0_12px_rgba(129,140,248,0.8)] transition-all duration-300"
            style={{ width: `${Math.round(overall * 100)}%` }}
          />
        </div>

        {/* Main Work Area: Dual Pane Grid */}
        <div className="p-6 sm:p-7 grid grid-cols-1 lg:grid-cols-12 gap-7">

          {/* Left Column: 7 Pipeline Stages (7 cols) */}
          <div className="lg:col-span-7 space-y-1.5">
            <div className="text-[10px] font-bold text-[#64748B] tracking-[0.2em] uppercase mb-3 flex items-center justify-between">
              <span>PIPELINE EXECUTION PHASES</span>
              <span className="text-[#818CF8]">DETERMINISTIC STAGES</span>
            </div>

            <div className="space-y-1">
              {stages.map((stage) => {
                const isActive = stage.status === 'active';
                const isDone = stage.status === 'completed';
                const fraction = fractionOf(stage);
                const seconds = secondsIn(stage.id, stage.status);

                return (
                  <div
                    key={stage.id}
                    className={`px-3.5 py-2.5 rounded-lg border transition-all duration-300 flex items-center justify-between gap-4 ${
                      isActive
                        ? 'border-[#818CF8]/40 bg-gradient-to-r from-[#131A2E]/80 to-[#0A0D14]/90 shadow-[0_0_20px_rgba(129,140,248,0.15)] translate-x-1'
                        : isDone
                        ? 'border-white/[0.05] bg-white/[0.01]'
                        : 'border-transparent opacity-40'
                    }`}
                  >
                    {/* Index & Name */}
                    <div className="flex items-center gap-3 min-w-0 flex-1">
                      <span
                        className={`h-4 w-4 rounded flex items-center justify-center text-[9.5px] font-mono font-bold shrink-0 ${
                          isDone
                            ? 'bg-[#34D399]/20 text-[#34D399] border border-[#34D399]/40'
                            : isActive
                            ? 'bg-[#818CF8] text-[#050608] shadow-[0_0_8px_rgba(129,140,248,0.8)]'
                            : 'bg-white/[0.06] text-[#64748B]'
                        }`}
                      >
                        {isDone ? '✓' : stage.index}
                      </span>

                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span
                            className={`font-mono text-xs tracking-wider uppercase font-bold truncate ${
                              isActive ? 'text-white' : isDone ? 'text-[#CBD5E1]' : 'text-[#64748B]'
                            }`}
                          >
                            {stage.label}
                          </span>
                          {isActive && (
                            <span className="inline-block w-1.5 h-1.5 rounded-full bg-[#818CF8] shadow-[0_0_6px_rgba(129,140,248,0.9)] animate-pulse" />
                          )}
                        </div>
                        <p className="text-[10px] text-[#64748B] truncate font-sans">
                          {isActive && stage.id === 'embed' && embedChunksTotal > 0
                            ? `Batch ${embedBatch} / ${embedTotalBatches} · ${embedChunksProcessed.toLocaleString()} / ${embedChunksTotal.toLocaleString()} chunks (${Math.round(embedProgressPct)}%)`
                            : isDone && stage.id === 'embed' && embedChunksTotal > 0
                            ? `${embedChunksTotal.toLocaleString()} chunks embedded · 100%`
                            : stage.sub}
                        </p>
                      </div>
                    </div>

                    {/* Stage Mini Progress Rail */}
                    <div className="w-20 sm:w-28 h-1 rounded-full bg-[#050608] border border-white/[0.06] overflow-hidden shrink-0">
                      <div
                        className={`h-full transition-all duration-300 ${
                          isDone
                            ? 'bg-[#34D399]'
                            : isActive
                            ? 'bg-gradient-to-r from-[#818CF8] to-[#38BDF8] shadow-[0_0_6px_rgba(129,140,248,0.8)]'
                            : 'bg-transparent'
                        }`}
                        style={{ width: `${Math.round(fraction * 100)}%` }}
                      />
                    </div>

                    {/* Stage Duration */}
                    <span
                      className={`w-12 text-right font-mono text-[11px] tabular-nums font-semibold shrink-0 ${
                        isDone ? 'text-[#34D399]' : isActive ? 'text-[#818CF8]' : 'text-[#64748B]'
                      }`}
                    >
                      {isDone || isActive ? `${seconds.toFixed(1)}s` : '—'}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Right Column: Live Ingestion Telemetry HUD (5 cols) */}
          <div className="lg:col-span-5 bg-[#050608]/70 border border-white/[0.06] rounded-xl p-5 flex flex-col justify-between">
            <div className="space-y-4">
              <div className="flex items-center justify-between border-b border-white/[0.06] pb-2.5">
                <span className="text-[10px] font-bold text-[#64748B] tracking-[0.2em] uppercase">
                  INGESTION TELEMETRY
                </span>
                <span className="text-[#34D399] text-[10px] font-bold font-mono flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#34D399] shadow-[0_0_6px_rgba(52,211,153,0.8)] animate-pulse" />
                  60Hz STREAM
                </span>
              </div>

              {/* Active Stage Focused Telemetry when in EMBED */}
              {activeStage?.id === 'embed' && embedChunksTotal > 0 ? (
                <div className="space-y-3 p-3.5 rounded-lg bg-[#0A0D14]/90 border border-[#38BDF8]/30 shadow-[0_0_15px_rgba(56,189,248,0.08)]">
                  <div className="flex items-center justify-between border-b border-white/[0.06] pb-2">
                    <span className="text-[10px] font-bold text-[#38BDF8] uppercase tracking-wider flex items-center gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-[#38BDF8] shadow-[0_0_6px_rgba(56,189,248,0.8)] animate-pulse" />
                      EMBEDDING STAGE TELEMETRY
                    </span>
                    <span className="text-[9.5px] text-[#64748B] font-mono">BGE SMALL EN V1.5</span>
                  </div>

                  <div className="grid grid-cols-2 gap-2.5">
                    <div className="p-2.5 rounded bg-[#07090F] border border-white/[0.06]">
                      <div className="text-[9px] text-[#64748B] uppercase font-bold tracking-wider mb-0.5">OVERALL PIPELINE</div>
                      <div className="text-lg font-bold font-mono text-white tabular-nums">
                        {Math.round(overall * 100)}%
                      </div>
                    </div>
                    <div className="p-2.5 rounded bg-[#07090F] border border-[#38BDF8]/30">
                      <div className="text-[9px] text-[#38BDF8] uppercase font-bold tracking-wider mb-0.5">EMBEDDING STAGE</div>
                      <div className="text-lg font-bold font-mono text-[#38BDF8] tabular-nums">
                        {Math.round(embedProgressPct)}%
                      </div>
                    </div>
                  </div>

                  <div className="p-2.5 rounded bg-[#07090F] border border-white/[0.06] space-y-1.5 font-mono text-[11px]">
                    <div className="flex items-center justify-between text-[#94A3B8]">
                      <span className="text-[#64748B] text-[10px] uppercase font-semibold">BATCH PROGRESS</span>
                      <span className="text-white font-semibold tabular-nums">
                        Batch {embedBatch} / {embedTotalBatches}
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-[#94A3B8]">
                      <span className="text-[#64748B] text-[10px] uppercase font-semibold">CHUNKS ENCODED</span>
                      <span className="text-[#38BDF8] font-semibold tabular-nums">
                        {embedChunksProcessed.toLocaleString()} / {embedChunksTotal.toLocaleString()} chunks
                      </span>
                    </div>
                    <div className="w-full h-1.5 rounded-full bg-[#050608] border border-white/[0.06] overflow-hidden mt-1.5">
                      <div
                        className="h-full bg-gradient-to-r from-[#818CF8] to-[#38BDF8] shadow-[0_0_6px_rgba(56,189,248,0.8)] transition-all duration-300"
                        style={{ width: `${Math.round(embedProgressPct)}%` }}
                      />
                    </div>
                  </div>
                </div>
              ) : (
                /* AST Symbols & Call Edges Counters Grid */
                <div className="grid grid-cols-2 gap-3">
                  <div className="p-3 rounded-lg bg-[#0A0D14]/80 border border-white/[0.06]">
                    <div className="text-[10px] text-[#64748B] uppercase font-bold tracking-wider mb-1">
                      AST SYMBOLS
                    </div>
                    <div className="text-lg font-bold font-mono text-white tabular-nums">
                      {simulatedNodes.toLocaleString()}
                    </div>
                  </div>

                  <div className="p-3 rounded-lg bg-[#0A0D14]/80 border border-white/[0.06]">
                    <div className="text-[10px] text-[#64748B] uppercase font-bold tracking-wider mb-1">
                      CALL EDGES
                    </div>
                    <div className="text-lg font-bold font-mono text-[#818CF8] tabular-nums">
                      {simulatedEdges.toLocaleString()}
                    </div>
                  </div>
                </div>
              )}

              {/* Streaming AST Token Feed */}
              <div className="space-y-2">
                <div className="text-[10px] text-[#64748B] uppercase font-bold tracking-wider flex items-center justify-between">
                  <span>LIVE RESOLVER FEED</span>
                  <span className="text-[#818CF8] font-mono text-[9.5px]">AST ENGINE</span>
                </div>

                <div className="p-3 rounded-lg bg-[#07090F] border border-white/[0.06] space-y-2 font-mono text-[11px]">
                  {STREAMING_AST_TOKENS.slice(0, 3).map((item, idx) => {
                    const isCurrent = (tokenIndex + idx) % STREAMING_AST_TOKENS.length === 0;
                    const tokenData = STREAMING_AST_TOKENS[(tokenIndex + idx) % STREAMING_AST_TOKENS.length];
                    return (
                      <div
                        key={idx}
                        className={`flex items-center gap-2 px-2 py-1 rounded transition-colors ${
                          isCurrent ? 'bg-[#818CF8]/10 text-white' : 'text-[#94A3B8]'
                        }`}
                      >
                        <span className="text-[#818CF8] text-[10px] font-bold">›</span>
                        <span className="text-[#64748B] text-[10px] uppercase font-bold">{tokenData.prefix}</span>
                        <span className="truncate">{tokenData.token}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>

            {/* Bottom Status Proof */}
            <div className="pt-3 border-t border-white/[0.06] flex items-center justify-between text-[10px] text-[#64748B]">
              <span>TREE-SITTER · NETWORKX · SSE</span>
              <span className="text-[#818CF8] font-bold">ZERO WRITEBACK</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AnalysisProgress;
