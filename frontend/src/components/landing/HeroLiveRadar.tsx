import React, { useState, useEffect } from 'react';

interface RepoPreset {
  id: string;
  name: string;
  lang: string;
  nodes: number;
  edges: number;
  topSymbol: string;
  riskScore: string;
  throughput: string;
}

const PRESETS: RepoPreset[] = [
  {
    id: 'fastapi',
    name: 'fastapi/fastapi',
    lang: 'Python',
    nodes: 1284,
    edges: 4890,
    topSymbol: 'FastAPI.add_api_route()',
    riskScore: 'LOW · 12%',
    throughput: '48.2k tokens/s',
  },
  {
    id: 'flask',
    name: 'pallets/flask',
    lang: 'Python',
    nodes: 842,
    edges: 2640,
    topSymbol: 'Flask.wsgi_app()',
    riskScore: 'LOW · 8%',
    throughput: '39.5k tokens/s',
  },
  {
    id: 'sqlmodel',
    name: 'tiangolo/sqlmodel',
    lang: 'Python',
    nodes: 620,
    edges: 1980,
    topSymbol: 'SQLModelMetaclass',
    riskScore: 'MED · 24%',
    throughput: '41.0k tokens/s',
  },
  {
    id: 'aria',
    name: 'aria/core',
    lang: 'TypeScript + Python',
    nodes: 1560,
    edges: 6210,
    topSymbol: 'Orchestrator.audit_graph()',
    riskScore: 'VERIFIED · 0%',
    throughput: '56.8k tokens/s',
  },
];

export const HeroLiveRadar: React.FC = () => {
  const [selectedRepo, setSelectedRepo] = useState<RepoPreset>(PRESETS[0]);
  const [scanPulse, setScanPulse] = useState(0);
  const [streamingTokens, setStreamingTokens] = useState<string[]>([]);

  useEffect(() => {
    const interval = setInterval(() => {
      setScanPulse((prev) => (prev + 1) % 100);
    }, 120);

    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const tokens = [
      `AST::${selectedRepo.topSymbol}`,
      `EDGE::RESOLVE(${selectedRepo.edges})`,
      `PAGERANK::RANK_TOPOLOGY`,
      `CALL_GRAPH::EXTRACT`,
    ];
    setStreamingTokens(tokens);
  }, [selectedRepo]);

  return (
    <div className="w-full max-w-xl rounded-2xl bg-gradient-to-b from-[#0D1220]/90 to-[#070A12]/95 border border-white/[0.08] p-4 sm:p-5 shadow-[0_20px_50px_rgba(0,0,0,0.8)] backdrop-blur-2xl font-mono text-xs">
      {/* HUD Header */}
      <div className="flex items-center justify-between gap-2 pb-3 border-b border-white/[0.08] mb-3.5">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)] animate-pulse" />
          <span className="text-[10.5px] font-bold tracking-[0.2em] text-emerald-300 uppercase">
            LIVE REPOSITORY RADAR
          </span>
        </div>
        <span className="text-[9px] text-[#64748B] tracking-wider uppercase">
          FREQ: 60Hz · ACTIVE
        </span>
      </div>

      {/* Preset Switcher */}
      <div className="flex items-center gap-1.5 flex-wrap mb-4">
        {PRESETS.map((p) => {
          const isSelected = p.id === selectedRepo.id;
          return (
            <button
              key={p.id}
              onClick={() => setSelectedRepo(p)}
              className={`px-2.5 py-1 rounded-lg text-[10px] tracking-wider transition-all duration-200 border font-semibold ${
                isSelected
                  ? 'border-indigo-500/70 bg-indigo-500/20 text-white shadow-[0_0_12px_rgba(99,102,241,0.3)]'
                  : 'border-white/[0.06] bg-[#050608]/70 text-[#94A3B8] hover:text-white hover:border-white/[0.15]'
              }`}
            >
              {p.name.split('/')[1]}
            </button>
          );
        })}
      </div>

      {/* Live Graph Radar Metrics Grid */}
      <div className="grid grid-cols-3 gap-2.5 mb-4">
        <div className="p-2.5 rounded-xl bg-[#050608]/70 border border-white/[0.05]">
          <div className="text-[9px] text-[#64748B] uppercase tracking-wider mb-1">NODES</div>
          <div className="text-sm font-bold text-white tabular-nums">{selectedRepo.nodes.toLocaleString()}</div>
        </div>

        <div className="p-2.5 rounded-xl bg-[#050608]/70 border border-white/[0.05]">
          <div className="text-[9px] text-[#64748B] uppercase tracking-wider mb-1">CALL EDGES</div>
          <div className="text-sm font-bold text-indigo-400 tabular-nums">{selectedRepo.edges.toLocaleString()}</div>
        </div>

        <div className="p-2.5 rounded-xl bg-[#050608]/70 border border-white/[0.05]">
          <div className="text-[9px] text-[#64748B] uppercase tracking-wider mb-1">THROUGHPUT</div>
          <div className="text-sm font-bold text-sky-400 tabular-nums">{selectedRepo.throughput}</div>
        </div>
      </div>

      {/* Live Streaming AST Stream */}
      <div className="p-2.5 rounded-xl bg-[#050608]/80 border border-white/[0.06] mb-4">
        <div className="flex items-center justify-between mb-2">
          <span className="text-[9px] font-bold text-[#64748B] tracking-wider uppercase">
            AST STREAMING PIPELINE
          </span>
          <span className="text-[9px] text-indigo-400 font-semibold">{selectedRepo.lang}</span>
        </div>
        <div className="flex items-center gap-1.5 flex-wrap">
          {streamingTokens.map((tok, idx) => (
            <span
              key={idx}
              className="px-2 py-0.5 rounded text-[9px] bg-indigo-500/10 border border-indigo-500/20 text-indigo-300 font-mono"
            >
              {tok}
            </span>
          ))}
        </div>
      </div>

      {/* Quick Launch CTA */}
      <a
        href={`/analysis?repo=${selectedRepo.name}`}
        className="w-full py-2.5 rounded-xl flex items-center justify-center gap-2 bg-gradient-to-r from-indigo-600/90 to-indigo-500/90 hover:from-indigo-500 hover:to-indigo-400 text-white font-bold tracking-wider uppercase text-[11px] shadow-[0_0_20px_rgba(99,102,241,0.35)] transition-all duration-200 hover:-translate-y-0.5"
      >
        <span>LAUNCH FULL CODEBASE AUDIT</span>
        <span>→</span>
      </a>
    </div>
  );
};

export default HeroLiveRadar;
