import React, { useState, useEffect, useRef } from 'react';

export interface Scenario {
  id: string;
  title: string;
  description: string;
  category: string;
  targetSymbols: Array<{ name: string; type: string; file: string }>;
  diffLines: Array<{ text: string; type: 'add' | 'del' | 'context' }>;
  directFiles: Array<{ name: string; role: string; callers: number }>;
  downstreamFiles: Array<{ name: string; depth: number }>;
  testImpact: {
    status: string;
    description: string;
    tone: 'emerald' | 'amber' | 'rose' | 'muted';
  };
  blastRadius: {
    size: 'XS' | 'S' | 'M' | 'L' | 'XL';
    label: string;
    tone: 'emerald' | 'amber' | 'rose';
  };
  confidence: number;
  recommendedAction: string;
  rationale: string;
  directRoute: string;
}

export const SCENARIOS: Scenario[] = [
  {
    id: 'sqlite-timeout',
    title: 'Fix SQLite timeout handling',
    description: 'Add exponential backoff and lock retry to SQLite store connector during concurrent ingest.',
    category: 'STORAGE · DRIVER',
    targetSymbols: [
      { name: 'connect_with_retry', type: 'function', file: 'backend/storage/sqlite.py' },
      { name: 'SQLiteTimeoutError', type: 'class', file: 'backend/storage/exceptions.py' },
      { name: 'DEFAULT_BUSY_TIMEOUT', type: 'constant', file: 'backend/storage/sqlite.py' },
    ],
    diffLines: [
      { text: '- timeout = DEFAULT_TIMEOUT', type: 'del' },
      { text: '+ timeout = calculate_exponential_backoff(attempt, max_retries)', type: 'add' },
      { text: '+ retry_on_exception(SQLiteTimeoutError)', type: 'add' },
    ],
    directFiles: [
      { name: 'backend/storage/sqlite.py', role: 'Modified connector & retry loop', callers: 4 },
      { name: 'backend/storage/exceptions.py', role: 'Exported error definition', callers: 2 },
    ],
    downstreamFiles: [],
    testImpact: {
      status: 'UNKNOWN',
      description: 'No direct unit tests recorded for retry backoff behavior.',
      tone: 'amber',
    },
    blastRadius: {
      size: 'XS',
      label: 'Minimal isolated footprint (2 files reached, 0 downstream cascade)',
      tone: 'emerald',
    },
    confidence: 69,
    recommendedAction: 'STANDARD REVIEW + TEST',
    rationale: 'Call graph proves change is fully quarantined within the storage adapter layer.',
    directRoute: '/impact',
  },
  {
    id: 'vector-retry',
    title: 'Add vector fallback retry',
    description: 'Fallback to dense CPU cosine index if remote embedding service times out.',
    category: 'INDEXING · EMBEDDINGS',
    targetSymbols: [
      { name: 'embed_with_fallback', type: 'function', file: 'backend/embeddings/service.py' },
      { name: 'VectorStoreClient', type: 'class', file: 'backend/embeddings/store.py' },
    ],
    diffLines: [
      { text: '- vectors = await remote_client.embed(batch)', type: 'del' },
      { text: '+ try: vectors = await remote_client.embed(batch)', type: 'add' },
      { text: '+ except TimeoutError: vectors = local_dense_index.embed(batch)', type: 'add' },
    ],
    directFiles: [
      { name: 'backend/embeddings/service.py', role: 'Fallback handler', callers: 6 },
      { name: 'backend/embeddings/store.py', role: 'Index switch', callers: 5 },
      { name: 'backend/embeddings/fallback_index.py', role: 'Local store', callers: 2 },
    ],
    downstreamFiles: [
      { name: 'backend/api/retrieval.py', depth: 2 },
      { name: 'backend/indexer/pipeline.py', depth: 2 },
      { name: 'backend/chat/rag_pipeline.py', depth: 3 },
    ],
    testImpact: {
      status: 'COVERED (3/3)',
      description: 'Regression tests present in tests/test_embeddings_fallback.py',
      tone: 'emerald',
    },
    blastRadius: {
      size: 'S',
      label: 'Moderate localized reach (3 files direct, 3 downstream modules)',
      tone: 'emerald',
    },
    confidence: 84,
    recommendedAction: 'FAST-TRACK REVIEW',
    rationale: 'Downstream call sites consume unified abstract interface without schema change.',
    directRoute: '/impact',
  },
  {
    id: 'ast-cache',
    title: 'Refactor AST parser cache',
    description: 'Change symbol extraction serialization format and in-memory cache key scheme.',
    category: 'PARSING · CORE',
    targetSymbols: [
      { name: 'extract_symbols', type: 'function', file: 'backend/parser/ast_engine.py' },
      { name: 'SymbolIndexCache', type: 'class', file: 'backend/parser/cache.py' },
      { name: 'CacheKeyTuple', type: 'type', file: 'backend/parser/types.py' },
    ],
    diffLines: [
      { text: '- cache_key = f"{filepath}:{mtime}"', type: 'del' },
      { text: '+ cache_key = CacheKeyTuple(file_hash=sha256, flags=AST_STRICT)', type: 'add' },
      { text: '+ return SymbolIndexCache.get_or_compute(cache_key, extract_symbols)', type: 'add' },
    ],
    directFiles: [
      { name: 'backend/parser/ast_engine.py', role: 'Core parser invocation', callers: 12 },
      { name: 'backend/parser/cache.py', role: 'Cache store implementation', callers: 8 },
      { name: 'backend/parser/types.py', role: 'Shared data definitions', callers: 19 },
    ],
    downstreamFiles: [
      { name: 'backend/indexer/call_graph.py', depth: 2 },
      { name: 'backend/indexer/dependency_graph.py', depth: 2 },
      { name: 'backend/analysis/drift.py', depth: 3 },
      { name: 'backend/analysis/risk.py', depth: 3 },
      { name: 'backend/analysis/dead_code.py', depth: 3 },
      { name: 'backend/api/routes.py', depth: 4 },
    ],
    testImpact: {
      status: 'PARTIAL (2/7 SUITES)',
      description: 'Call graph indexers require full end-to-end integration validation.',
      tone: 'rose',
    },
    blastRadius: {
      size: 'L',
      label: 'High blast radius (3 core files, 6 downstream analyzer pipelines)',
      tone: 'amber',
    },
    confidence: 52,
    recommendedAction: 'DEEP REGRESSION TEST REQUIRED',
    rationale: 'Central AST cache changes alter return shape for 6 downstream analysis engines.',
    directRoute: '/risk',
  },
];

const STEPS = [
  { id: 'change', label: 'CHANGE SCENARIO' },
  { id: 'symbols', label: 'TARGET SYMBOLS' },
  { id: 'impact', label: 'DIRECT & DOWNSTREAM' },
  { id: 'tests', label: 'TEST IMPACT' },
  { id: 'decision', label: 'RISK & DECISION' },
];

export default function ProductDemo() {
  const [activeScenarioId, setActiveScenarioId] = useState<string>('sqlite-timeout');
  const [activeStep, setActiveStep] = useState<number>(0);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [isScanning, setIsScanning] = useState<boolean>(false);
  const [tiltStyle, setTiltStyle] = useState<{ transform: string; boxShadow: string }>({
    transform: 'perspective(1200px) rotateX(0deg) rotateY(0deg)',
    boxShadow: '0 24px 60px rgba(0,0,0,0.8)',
  });

  const timerRef = useRef<number | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const hasTriggeredRef = useRef<boolean>(false);

  const scenario = SCENARIOS.find((s) => s.id === activeScenarioId) || SCENARIOS[0];

  // Viewport entry auto-trigger
  useEffect(() => {
    const el = containerRef.current;
    if (!el || typeof IntersectionObserver === 'undefined') return;

    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduced) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !hasTriggeredRef.current) {
          hasTriggeredRef.current = true;
          setIsPlaying(true);
        }
      },
      { threshold: 0.3 }
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Auto-play progression when enabled
  useEffect(() => {
    if (!isPlaying) {
      if (timerRef.current) clearInterval(timerRef.current);
      return;
    }

    timerRef.current = window.setInterval(() => {
      setActiveStep((prev) => {
        if (prev >= STEPS.length - 1) {
          setIsPlaying(false);
          return prev;
        }
        return prev + 1;
      });
    }, 2400);

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [isPlaying]);

  const handleScenarioChange = (id: string) => {
    setActiveScenarioId(id);
    setActiveStep(0);
    setIsPlaying(false);
    setIsScanning(true);
    setTimeout(() => {
      setIsScanning(false);
    }, 600);
  };

  const handleStepClick = (index: number) => {
    setActiveStep(index);
    setIsPlaying(false);
  };

  // Interactive 3D Card Mouse Move Physics
  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const card = cardRef.current;
    if (!card) return;
    const rect = card.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const centerX = rect.width / 2;
    const centerY = rect.height / 2;
    const rotateX = ((y - centerY) / centerY) * -4;
    const rotateY = ((x - centerX) / centerX) * 4;

    setTiltStyle({
      transform: `perspective(1200px) rotateX(${rotateX.toFixed(2)}deg) rotateY(${rotateY.toFixed(2)}deg)`,
      boxShadow: `${-rotateY * 2}px ${rotateX * 2 + 25}px 60px rgba(0,0,0,0.85), 0 0 35px rgba(99, 102, 241, 0.15)`,
    });
  };

  const handleMouseLeave = () => {
    setTiltStyle({
      transform: 'perspective(1200px) rotateX(0deg) rotateY(0deg)',
      boxShadow: '0 24px 60px rgba(0,0,0,0.8)',
    });
  };

  return (
    <div ref={containerRef} className="w-full font-mono text-xs">
      {/* Top Bar / Mode Selector */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-4 mb-5 border-b border-white/[0.08]">
        <div className="flex items-center gap-2.5">
          <span className="inline-block w-2.5 h-2.5 rounded-full bg-indigo-400 shadow-[0_0_8px_rgba(129,140,248,0.8)] animate-pulse" />
          <span className="text-[#F8FAFC] tracking-[0.16em] uppercase font-bold text-[11px]">
            SIMULATED INVESTIGATION PIPELINE
          </span>
          <span className="text-[#64748B] text-[10px] hidden sm:inline ml-1">
            · REAL-TIME GRAPH DETERMINISM
          </span>
        </div>

        {/* Clean Scenario Selector */}
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[#64748B] text-[10px] tracking-wider uppercase font-semibold">PRESETS:</span>
          {SCENARIOS.map((s) => {
            const isSelected = s.id === scenario.id;
            return (
              <button
                key={s.id}
                onClick={() => handleScenarioChange(s.id)}
                className={`px-3.5 py-1.5 rounded-lg text-[11px] uppercase tracking-wider transition-all duration-200 border font-semibold ${
                  isSelected
                    ? 'border-indigo-500 bg-indigo-500/20 text-white shadow-[0_0_16px_rgba(99,102,241,0.35)]'
                    : 'border-white/[0.08] bg-[#050608]/80 text-[#94A3B8] hover:text-[#F8FAFC] hover:border-white/[0.18]'
                }`}
              >
                {s.title.split(' ')[1] || s.title}
              </button>
            );
          })}
        </div>
      </div>

      {/* Main Console Surface with 3D Tilt and Holographic Scan */}
      <div
        ref={cardRef}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
        style={tiltStyle}
        className="tilt-card relative bg-gradient-to-b from-[#0D1220]/95 to-[#070A12]/98 backdrop-blur-2xl border border-white/[0.08] rounded-2xl overflow-hidden"
      >
        {/* Animated Laser Scanning Line */}
        {isScanning && <div className="laser-scanner-beam z-30" />}

        {/* Step Navigation Rail */}
        <div className="grid grid-cols-2 sm:grid-cols-5 border-b border-white/[0.08] bg-[#050608]/60">
          {STEPS.map((step, idx) => {
            const isActive = activeStep === idx;
            const isPassed = activeStep > idx;
            return (
              <button
                key={step.id}
                onClick={() => handleStepClick(idx)}
                className={`py-3 px-3.5 text-left transition-all duration-200 border-r border-white/[0.06] last:border-r-0 relative ${
                  isActive
                    ? 'bg-indigo-500/[0.08] text-[#F8FAFC]'
                    : isPassed
                    ? 'text-[#CBD5E1] hover:bg-white/[0.02]'
                    : 'text-[#64748B] hover:text-[#CBD5E1]'
                }`}
              >
                <div className="flex items-center gap-2 mb-0.5">
                  <span
                    className={`inline-flex items-center justify-center w-4 h-4 text-[9px] font-bold rounded-full ${
                      isActive
                        ? 'bg-indigo-400 text-[#050608] shadow-[0_0_8px_rgba(129,140,248,0.8)]'
                        : isPassed
                        ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                        : 'bg-white/[0.06] text-[#64748B]'
                    }`}
                  >
                    {isPassed ? '✓' : idx + 1}
                  </span>
                  <span className="text-[10px] tracking-wider uppercase font-semibold truncate">
                    {step.label}
                  </span>
                </div>
                {isActive && (
                  <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-gradient-to-r from-indigo-500 to-sky-400 shadow-[0_0_8px_rgba(129,140,248,0.8)]" />
                )}
              </button>
            );
          })}
        </div>

        {/* Console Workspace Area */}
        <div className="p-5 sm:p-7 grid grid-cols-1 lg:grid-cols-12 gap-6 min-h-[400px]">
          {/* Left Column: Active Stage Content (7 cols) */}
          <div className="lg:col-span-7 flex flex-col justify-between">
            <div>
              {/* Header Badge */}
              <div className="flex items-center justify-between mb-4 pb-2 border-b border-white/[0.06]">
                <span className="text-[11px] tracking-[0.2em] uppercase font-bold flex items-center gap-2 text-indigo-400">
                  <span className="w-1.5 h-1.5 rounded-full bg-indigo-400" />
                  STAGE {activeStep + 1}/{STEPS.length} · {STEPS[activeStep].label}
                </span>
                <span className="px-2 py-0.5 rounded text-[10px] border bg-white/[0.05] text-[#94A3B8] border-white/[0.05]">
                  {scenario.category}
                </span>
              </div>

              {/* Stage Specific Panels */}
              {activeStep === 0 && (
                <div className="space-y-4 animate-fade-in">
                  <div>
                    <h4 className="text-base sm:text-lg font-bold tracking-tight text-white mb-1.5">
                      {scenario.title}
                    </h4>
                    <p className="text-[13px] text-[#CBD5E1] leading-relaxed">
                      {scenario.description}
                    </p>
                  </div>
                  <div className="p-4 rounded-xl bg-[#050608]/80 border border-white/[0.06]">
                    <div className="text-[#64748B] text-[10px] uppercase tracking-wider mb-2.5 font-bold flex items-center justify-between">
                      <span>SYNTAX DIFF CLUSTER</span>
                      <span className="text-indigo-400">AST NODES (LEXICAL PARSE)</span>
                    </div>
                    <div className="space-y-1.5 font-mono text-[12px]">
                      {scenario.diffLines.map((line, idx) => (
                        <div
                          key={idx}
                          className={`px-2 py-1 rounded truncate ${
                            line.type === 'del'
                              ? 'text-[#FF758F] bg-[#FF758F]/10'
                              : line.type === 'add'
                              ? 'text-[#34D399] bg-[#34D399]/10'
                              : 'text-[#94A3B8]'
                          }`}
                        >
                          {line.text}
                        </div>
                      ))}
                    </div>
                  </div>
                  <p className="text-[#94A3B8] text-[11px] leading-normal">
                    ARIA detects modified syntax tokens directly from the AST diff without relying solely on raw text patches.
                  </p>
                </div>
              )}

              {activeStep === 1 && (
                <div className="space-y-3 animate-fade-in">
                  <div className="text-[#94A3B8] text-[11px] font-semibold mb-2">
                    EXTRACTED REPOSITORAL SYMBOLS IN CHANGED SCOPE:
                  </div>
                  <div className="space-y-2">
                    {scenario.targetSymbols.map((sym, i) => (
                      <div
                        key={i}
                        className="p-3 rounded-xl bg-[#050608]/80 border border-white/[0.06] flex items-center justify-between hover:border-indigo-500/40 transition-colors"
                      >
                        <div className="flex items-center gap-2.5">
                          <span className="px-2 py-0.5 rounded text-[10px] uppercase font-bold border bg-indigo-500/20 text-indigo-300 border-indigo-500/30">
                            {sym.type}
                          </span>
                          <span className="text-white font-bold text-[12px]">{sym.name}</span>
                        </div>
                        <span className="text-[#64748B] text-[11px] font-mono">{sym.file}</span>
                      </div>
                    ))}
                  </div>
                  <div className="text-[#64748B] text-[11px] pt-1">
                    Symbol nodes resolved against ARIA's global AST symbol table.
                  </div>
                </div>
              )}

              {activeStep === 2 && (
                <div className="space-y-4 animate-fade-in">
                  <div>
                    <div className="text-[#64748B] text-[10px] uppercase tracking-wider mb-2 font-bold flex items-center justify-between">
                      <span>DIRECTLY MODIFIED FILES ({scenario.directFiles.length})</span>
                      <span className="text-emerald-400">ORIGIN NODES</span>
                    </div>
                    <div className="space-y-2 mb-4">
                      {scenario.directFiles.map((file, i) => (
                        <div
                          key={i}
                          className="p-3 rounded-xl bg-[#050608]/80 border border-white/[0.06] flex items-center justify-between"
                        >
                          <div>
                            <div className="text-white font-semibold text-[12px]">{file.name}</div>
                            <div className="text-[#64748B] text-[10px] mt-0.5">{file.role}</div>
                          </div>
                          <span className="text-emerald-400 text-[11px] tabular-nums font-semibold px-2 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/20">
                            {file.callers} direct callers
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div>
                    <div className="text-[#64748B] text-[10px] uppercase tracking-wider mb-2 font-bold flex items-center justify-between">
                      <span>DOWNSTREAM CASCADE REACHED ({scenario.downstreamFiles.length})</span>
                      <span className="text-indigo-400">CALL GRAPH TRAVERSAL</span>
                    </div>
                    {scenario.downstreamFiles.length === 0 ? (
                      <div className="p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-[11px] flex items-center gap-2">
                        <span className="font-bold">✓</span>
                        <span>0 downstream files affected. Impact stops cleanly at adapter boundary.</span>
                      </div>
                    ) : (
                      <div className="space-y-1.5">
                        {scenario.downstreamFiles.map((down, i) => (
                          <div
                            key={i}
                            className="p-2.5 rounded-lg bg-[#050608]/80 border border-white/[0.05] flex items-center justify-between text-[11px]"
                          >
                            <span className="text-[#CBD5E1]">{down.name}</span>
                            <span className="text-indigo-400 font-mono font-semibold">Depth {down.depth}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {activeStep === 3 && (
                <div className="space-y-4 animate-fade-in">
                  <div className="p-4 rounded-xl bg-[#050608]/80 border border-white/[0.06] space-y-3">
                    <div className="flex items-center justify-between border-b border-white/[0.06] pb-2.5">
                      <span className="text-[#94A3B8] uppercase tracking-wider text-[10px] font-bold">
                        TEST IMPACT STATUS
                      </span>
                      <span
                        className={`px-2.5 py-0.5 rounded-full text-[10px] uppercase font-bold tracking-wider ${
                          scenario.testImpact.tone === 'emerald'
                            ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40'
                            : scenario.testImpact.tone === 'amber'
                            ? 'bg-amber-500/20 text-amber-400 border border-amber-500/40'
                            : 'bg-rose-500/20 text-rose-400 border border-rose-500/40'
                        }`}
                      >
                        {scenario.testImpact.status}
                      </span>
                    </div>
                    <p className="text-[13px] text-[#F8FAFC] leading-relaxed">
                      {scenario.testImpact.description}
                    </p>
                  </div>
                  <div className="p-3.5 rounded-xl border border-white/[0.06] bg-[#050608]/60 space-y-1.5">
                    <div className="text-[#64748B] text-[10px] uppercase tracking-wider font-bold">
                      EPISTEMIC INTEGRITY PRINCIPLE
                    </div>
                    <p className="text-[#94A3B8] text-[11px] leading-normal">
                      ARIA refuses to fabricate confidence: if test suites do not exercise the specific changed call path, the status remains explicitly <span className="text-amber-400 font-bold">UNKNOWN</span> rather than guessed.
                    </p>
                  </div>
                </div>
              )}

              {activeStep === 4 && (
                <div className="space-y-4 animate-fade-in">
                  <div className="grid grid-cols-2 gap-3.5">
                    <div className="p-4 rounded-xl bg-[#050608]/80 border border-white/[0.06]">
                      <div className="text-[#64748B] text-[10px] uppercase tracking-wider mb-1 font-bold">
                        BLAST RADIUS
                      </div>
                      <div
                        className={`text-2xl font-bold font-mono ${
                          scenario.blastRadius.tone === 'emerald'
                            ? 'text-emerald-400'
                            : scenario.blastRadius.tone === 'amber'
                            ? 'text-amber-400'
                            : 'text-rose-400'
                        }`}
                      >
                        {scenario.blastRadius.size}
                      </div>
                      <div className="text-[10px] text-[#94A3B8] mt-1 truncate">
                        {scenario.blastRadius.label}
                      </div>
                    </div>

                    <div className="p-4 rounded-xl bg-[#050608]/80 border border-white/[0.06]">
                      <div className="text-[#64748B] text-[10px] uppercase tracking-wider mb-1 font-bold">
                        CONFIDENCE
                      </div>
                      <div className="text-2xl font-bold font-mono text-indigo-400">
                        {scenario.confidence}%
                      </div>
                      <div className="text-[10px] text-[#94A3B8] mt-1">
                        Based on graph depth & proof
                      </div>
                    </div>
                  </div>

                  <div className="p-4 rounded-xl border space-y-1 bg-indigo-500/10 border-indigo-500/30">
                    <div className="text-[10px] uppercase tracking-wider font-bold text-indigo-300">
                      RECOMMENDED ACTION
                    </div>
                    <div className="text-[13px] font-bold text-white">
                      {scenario.recommendedAction}
                    </div>
                    <div className="text-[11px] text-[#CBD5E1] pt-1">
                      {scenario.rationale}
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Stepper Controls */}
            <div className="flex flex-wrap items-center justify-between gap-3 pt-4 mt-6 border-t border-white/[0.06]">
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setIsPlaying(!isPlaying)}
                  className={`px-3.5 py-1.5 rounded-lg text-[11px] uppercase tracking-wider font-semibold border transition-all ${
                    isPlaying
                      ? 'border-emerald-500/50 bg-emerald-500/20 text-emerald-400 shadow-[0_0_12px_rgba(52,211,153,0.3)]'
                      : 'border-white/[0.08] bg-[#050608] text-[#CBD5E1] hover:border-indigo-500/40'
                  }`}
                >
                  {isPlaying ? '⏸ PAUSE PIPELINE' : '▶ AUTO-PLAY PIPELINE'}
                </button>

                <button
                  onClick={() => {
                    setIsScanning(true);
                    setTimeout(() => setIsScanning(false), 1000);
                  }}
                  className="px-3 py-1.5 rounded-lg text-[11px] border border-white/[0.08] bg-[#050608] text-[#94A3B8] hover:text-white hover:border-white/[0.2] transition-colors"
                >
                  ⚡ RE-SCAN AST
                </button>
              </div>

              <div className="flex items-center gap-2">
                <button
                  disabled={activeStep === 0}
                  onClick={() => handleStepClick(Math.max(0, activeStep - 1))}
                  className="px-3 py-1.5 rounded-lg text-[11px] border border-white/[0.08] bg-[#050608] text-[#CBD5E1] disabled:opacity-40 disabled:cursor-not-allowed hover:border-white/[0.2]"
                >
                  ← PREV
                </button>
                <button
                  disabled={activeStep === STEPS.length - 1}
                  onClick={() => handleStepClick(Math.min(STEPS.length - 1, activeStep + 1))}
                  className="px-3.5 py-1.5 rounded-lg text-[11px] border border-indigo-500/50 bg-indigo-500/20 text-white font-semibold disabled:opacity-40 disabled:cursor-not-allowed hover:bg-indigo-500/30 shadow-[0_0_12px_rgba(99,102,241,0.25)]"
                >
                  NEXT →
                </button>
              </div>
            </div>
          </div>

          {/* Right Column: Mini Architectural Synthesis Visualizer (5 cols) */}
          <div className="lg:col-span-5 bg-[#050608]/70 border border-white/[0.06] rounded-xl p-5 flex flex-col justify-between">
            <div>
              <div className="text-[#64748B] text-[10px] uppercase tracking-wider mb-4 flex items-center justify-between border-b border-white/[0.06] pb-2.5 font-bold">
                <span>EVIDENCE SYNTHESIS</span>
                <span className="text-indigo-400 font-bold">TOPOLOGY ENGINE</span>
              </div>

              {/* Node Schematic */}
              <div className="space-y-3 py-1">
                <div className="p-2.5 rounded-lg border border-indigo-500/40 bg-indigo-500/10 text-white flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-indigo-400 shadow-[0_0_6px_rgba(129,140,248,0.8)]" />
                    <span className="font-bold text-[11px]">CHANGE ORIGIN</span>
                  </div>
                  <span className="text-[10px] font-semibold text-indigo-300">
                    Δ ast_diff
                  </span>
                </div>

                <div className="flex justify-center">
                  <div className="w-px h-3 bg-white/[0.1]" />
                </div>

                <div
                  className={`p-2.5 rounded-lg border transition-all duration-300 ${
                    activeStep >= 1
                      ? 'border-emerald-500/40 bg-emerald-500/10 text-white'
                      : 'border-white/[0.06] bg-[#050608] text-[#64748B]'
                  } flex items-center justify-between`}
                >
                  <div className="flex items-center gap-2">
                    <span
                      className={`w-2 h-2 rounded-full ${
                        activeStep >= 1 ? 'bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.8)]' : 'bg-white/20'
                      }`}
                    />
                    <span className="font-semibold text-[11px]">TARGET SYMBOLS</span>
                  </div>
                  <span className="text-[10px] tabular-nums font-mono">
                    {scenario.targetSymbols.length} resolved
                  </span>
                </div>

                <div className="flex justify-center">
                  <div className="w-px h-3 bg-white/[0.1]" />
                </div>

                <div
                  className={`p-2.5 rounded-lg border transition-all duration-300 ${
                    activeStep >= 2
                      ? 'border-sky-500/40 bg-sky-500/10 text-white'
                      : 'border-white/[0.06] bg-[#050608] text-[#64748B]'
                  } flex items-center justify-between`}
                >
                  <div className="flex items-center gap-2">
                    <span
                      className={`w-2 h-2 rounded-full ${
                        activeStep >= 2 ? 'bg-sky-400 shadow-[0_0_6px_rgba(56,189,248,0.8)]' : 'bg-white/20'
                      }`}
                    />
                    <span className="font-semibold text-[11px]">AFFECTED REACH</span>
                  </div>
                  <span className="text-[10px] tabular-nums font-mono">
                    {scenario.directFiles.length + scenario.downstreamFiles.length} files
                  </span>
                </div>

                <div className="flex justify-center">
                  <div className="w-px h-3 bg-white/[0.1]" />
                </div>

                <div
                  className={`p-2.5 rounded-lg border transition-all duration-300 ${
                    activeStep >= 4
                      ? 'border-amber-500/40 bg-amber-500/10 text-white'
                      : 'border-white/[0.06] bg-[#050608] text-[#64748B]'
                  } flex items-center justify-between`}
                >
                  <div className="flex items-center gap-2">
                    <span
                      className={`w-2 h-2 rounded-full ${
                        activeStep >= 4
                          ? 'bg-amber-400 shadow-[0_0_6px_rgba(252,211,77,0.8)]'
                          : 'bg-white/20'
                      }`}
                    />
                    <span className="font-semibold text-[11px]">VERIFIED DECISION</span>
                  </div>
                  <span className="text-[10px] font-bold font-mono text-amber-400">
                    {scenario.blastRadius.size} · {scenario.confidence}%
                  </span>
                </div>
              </div>
            </div>

            {/* Bottom Actions & Proof Deep Link */}
            <div className="pt-4 border-t border-white/[0.06] space-y-3">
              <a
                href={scenario.directRoute}
                className="w-full py-2 px-3 rounded-lg bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] hover:border-indigo-500/40 text-[#CBD5E1] hover:text-white flex items-center justify-between transition-all group"
              >
                <span className="text-[11px] font-semibold">Open Live Studio Lens</span>
                <span className="text-indigo-400 group-hover:translate-x-0.5 transition-transform">→</span>
              </a>
              <div className="text-[#64748B] text-[10px] leading-relaxed">
                "ARIA traces the relationship graph before the merge — not inferred from raw diff text."
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
