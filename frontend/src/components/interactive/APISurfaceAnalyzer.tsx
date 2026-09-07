/**
 * APISurfaceAnalyzer — Production-Grade 10/10 Contract Intelligence Pass
 *
 * Core Principle:
 * FILE GRAPH = ARCHITECTURE / SPATIAL (“How is this repository organized?”)
 * CALL GRAPH = EXECUTION / TEMPORAL (“What happens when the software runs?”)
 * API SURFACE = CONTRACT / EXPOSURE (“What does this system expose, who uses it, and what happens if it changes?”)
 *
 * Information Architecture:
 * 1. EXECUTIVE CONTRACT BRIEFING
 * 2. KEY CONTRACT METRICS
 * 3. KEY INVESTIGATION TARGETS (Start Here)
 * 4. EXPOSURE SUMMARY & CONTRACT HEALTH
 * 5. PRIMARY NAVIGATION & SUBORDINATE FILTERS
 * 6. CONTRACT INVENTORY (Routes, Public, Internal, Issues)
 * 7. SELECTED CONTRACT & IMPACT INSPECTOR
 */

import React, { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import { apiUrl, extractErrorMessage } from '../../lib/api';
import { Button } from '../ui/Button';
import { EmptyState } from '../ui/EmptyState';
import { SkeletonCard, SkeletonGroup } from '../ui/Skeleton';
import { FilePath } from '../ui/FilePath';
import { Meter } from '../ui/Meter';
import {
  Globe, Lock, AlertTriangle, Route, RefreshCw,
  Search, X, ChevronDown, ChevronUp, Zap, Info, CheckCircle2,
  LayoutList, ArrowRight, ArrowLeft, ExternalLink, Sparkles,
  ShieldAlert, ShieldCheck, Copy, Check, Filter, Layers, Code2,
  Activity, Play, FileCode, CheckCircle, ArrowDown, CornerDownRight,
  TrendingUp, Terminal, Workflow,
} from 'lucide-react';
import {
  computeApiExposureSignals,
  extractHttpRoutes,
  sortRoutes,
  extractContractSchemaDetails,
  simulateContractChangeImpact,
  generateApiQuestions,
  generateWhyApiMatters,
  deriveDecisionPath,
  groupSymbolsByModule,
  shortSymbolName,
  deriveApiEvidenceLevel,
  deriveContractType,
  parseHttpRoute,
} from './api/apiSurfaceIntelligence';
import type {
  ClassifiedSymbol,
  APISurfaceStats,
  HttpRouteInfo,
  StartHereCard,
  DecisionPathStep,
  ApiExposureSignals,
  ContractSchemaDetails,
  ContractChangeSimulation,
  ModuleSymbolGroup,
  RouteSortMode,
  ApiEvidenceLevel,
  ContractType,
} from './api/apiSurfaceIntelligence';

// ── Types ─────────────────────────────────────────────────────────────────

interface Props { repoName: string; }
type ViewId = 'overview' | 'routes' | 'public' | 'internal' | 'issues';
type SecondaryFilter = 'all' | 'high_impact' | 'no_internal_callers' | 'deprecated';

// ── HTTP Method Restrained Palette ──────────────────────────────────────────
// HTTP method is a protocol category, NOT a health/success state.
// Restrained neutral styling for standard methods; rose exclusively for destructive DELETE.
const METHOD_ACCENT: Record<string, { color: string; border: string; bg: string }> = {
  GET:     { color: '#A1A1AA', border: 'border-white/[0.085]', bg: 'bg-[rgba(14,14,18,0.72)] text-[#F4F4F5]' },
  POST:    { color: '#A1A1AA', border: 'border-white/[0.085]', bg: 'bg-[rgba(14,14,18,0.72)] text-[#F4F4F5]' },
  PUT:     { color: '#A1A1AA', border: 'border-white/[0.085]', bg: 'bg-[rgba(14,14,18,0.72)] text-[#F4F4F5]' },
  PATCH:   { color: '#A1A1AA', border: 'border-white/[0.085]', bg: 'bg-[rgba(14,14,18,0.72)] text-[#F4F4F5]' },
  DELETE:  { color: '#F87171', border: 'border-[#F87171]/40', bg: 'bg-[#F87171]/10 text-[#F87171]' },
  HEAD:    { color: '#71717A', border: 'border-white/[0.055]', bg: 'bg-[rgba(14,14,18,0.5)] text-[#A1A1AA]' },
  OPTIONS: { color: '#71717A', border: 'border-white/[0.055]', bg: 'bg-[rgba(14,14,18,0.5)] text-[#A1A1AA]' },
  ROUTE:   { color: '#A1A1AA', border: 'border-white/[0.085]', bg: 'bg-[rgba(14,14,18,0.72)] text-[#F4F4F5]' },
};

function methodTagStyle(m: string) {
  return METHOD_ACCENT[m.toUpperCase()] || METHOD_ACCENT.ROUTE;
}

// ── Evidence Badge Helper ──────────────────────────────────────────────────
function getEvidenceBadgeClass(evidence: ApiEvidenceLevel) {
  switch (evidence) {
    case 'VERIFIED':
      return 'text-[#34D399] bg-[#34D399]/10 border-[#34D399]/30';
    case 'STRONGLY INFERRED':
      return 'text-[#6B74D9] bg-[#6B74D9]/10 border-[#6B74D9]/30';
    case 'INFERRED':
      return 'text-[#94A3B8] bg-white/[0.03] border-white/[0.08]';
    default:
      return 'text-[#F4B942] bg-[#F4B942]/10 border-[#F4B942]/30';
  }
}

// ── Decision Path Ribbon ───────────────────────────────────────────────────

const DecisionPathRibbon: React.FC<{ steps: DecisionPathStep[] }> = ({ steps }) => {
  return (
    <div className="p-2.5 bg-[#08080A] border border-[#1F1F23] rounded-lg space-y-1.5 font-mono select-none">
      <span className="text-[8px] font-bold text-zinc-500 uppercase tracking-widest block">
        Decision Path
      </span>
      <div className="flex items-center gap-1.5 overflow-x-auto text-[9px] pb-1">
        {steps.map((step, idx) => (
          <React.Fragment key={step.label}>
            <div className={`p-1.5 rounded border shrink-0 min-w-[85px] ${
              step.tone === 'danger'
                ? 'bg-rose-950/30 border-rose-500/40 text-rose-300'
                : step.tone === 'warning'
                  ? 'bg-amber-950/30 border-amber-500/40 text-amber-300'
                  : step.tone === 'success'
                    ? 'bg-emerald-950/30 border-emerald-500/40 text-emerald-300'
                    : step.tone === 'accent'
                      ? 'bg-indigo-950/30 border-indigo-500/40 text-indigo-300'
                      : 'bg-[#0D0D10] border-[#1F1F23] text-zinc-300'
            }`}>
              <div className="text-[7px] text-zinc-500 uppercase font-bold">{step.label}</div>
              <div className="font-bold truncate">{step.value}</div>
              {step.subValue && <div className="text-[7px] text-zinc-400 truncate opacity-80">{step.subValue}</div>}
            </div>
            {idx < steps.length - 1 && (
              <span className="text-zinc-600 text-xs shrink-0">→</span>
            )}
          </React.Fragment>
        ))}
      </div>
    </div>
  );
};

// ── Contract & Impact Inspector Drawer ─────────────────────────────────────

interface InspectorProps {
  symbol: ClassifiedSymbol;
  routeInfo?: HttpRouteInfo;
  allSymbols: ClassifiedSymbol[];
  repoName: string;
  onClose: () => void;
  onSelectSymbol: (sym: ClassifiedSymbol) => void;
}

const ApiContractInspector: React.FC<InspectorProps> = ({
  symbol,
  routeInfo,
  allSymbols,
  repoName,
  onClose,
  onSelectSymbol,
}) => {
  const [copied, setCopied] = useState(false);
  const [showSim, setShowSim] = useState(false);

  const evidence = useMemo(() => deriveApiEvidenceLevel(symbol), [symbol]);
  const schema = useMemo(() => extractContractSchemaDetails(symbol), [symbol]);
  const sim = useMemo(() => simulateContractChangeImpact(symbol, allSymbols), [symbol, allSymbols]);
  const questions = useMemo(() => generateApiQuestions(symbol, routeInfo), [symbol, routeInfo]);
  const whyItMatters = useMemo(() => generateWhyApiMatters(symbol, routeInfo), [symbol, routeInfo]);
  const decisionPath = useMemo(() => deriveDecisionPath(symbol, routeInfo, sim), [symbol, routeInfo, sim]);

  const handleCopy = useCallback(() => {
    if (typeof navigator !== 'undefined' && navigator.clipboard) {
      navigator.clipboard.writeText(routeInfo ? `${routeInfo.method} ${routeInfo.path}` : symbol.qualified);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }
  }, [routeInfo, symbol]);

  const handleAskAria = useCallback((promptText?: string) => {
    const p =
      promptText ||
      `Explain the API contract for \`${symbol.qualified}\` in \`${symbol.file_path}\`. What is its schema, who uses it, and what breaks if it changes?`;
    window.dispatchEvent(
      new CustomEvent('aria-open-chat', {
        detail: {
          prompt: p,
          repository: repoName,
          file: symbol.file_path,
          symbol: symbol.qualified,
          route: routeInfo?.path,
          method: routeInfo?.method,
          handler: symbol.name,
          callers: symbol.fan_in,
          evidence,
          intent: 'contract_inquiry',
        },
      })
    );
  }, [repoName, symbol, routeInfo, evidence]);

  const handleOpenFileGraph = useCallback(() => {
    window.dispatchEvent(
      new CustomEvent('aria-open-graph', {
        detail: { path: symbol.file_path, file: symbol.file_path },
      })
    );
  }, [symbol]);

  const handleOpenImpact = useCallback(() => {
    window.dispatchEvent(
      new CustomEvent('aria-open-impact', {
        detail: { file: symbol.file_path, symbol: symbol.qualified },
      })
    );
  }, [symbol]);

  const handleOpenCallGraph = useCallback(() => {
    window.dispatchEvent(
      new CustomEvent('aria-navigate-tab', {
        detail: { tab: 'call_graph', file: symbol.file_path, symbol: symbol.qualified },
      })
    );
  }, [symbol]);

  const riskTone =
    sim.riskRating === 'Critical'
      ? 'text-rose-400 border-rose-500/40 bg-rose-950/30'
      : sim.riskRating === 'High'
        ? 'text-orange-400 border-orange-500/40 bg-orange-950/30'
        : sim.riskRating === 'Medium'
          ? 'text-amber-400 border-amber-500/40 bg-amber-950/30'
          : 'text-emerald-400 border-emerald-500/40 bg-emerald-950/30';

  return (
    <aside
      className="w-84 sm:w-96 shrink-0 border-l border-[#1F1F23] bg-[#08080A]/95 flex flex-col overflow-hidden font-mono z-20 shadow-2xl animate-in fade-in slide-in-from-right-2 duration-200"
      aria-label="API Contract Inspector"
    >
      {/* Header */}
      <div className="p-4 border-b border-[#1F1F23] bg-[#08080A] shrink-0 space-y-2 select-none">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-[9px] font-bold text-indigo-400 uppercase tracking-wider flex items-center gap-1">
              <Route className="h-3 w-3 text-indigo-400" /> API Contract
            </span>
            <span className={`text-[8px] font-bold border px-1.5 py-0.5 rounded uppercase ${getEvidenceBadgeClass(evidence)}`}>
              [{evidence}]
            </span>
            <span className="text-[8px] font-bold text-zinc-400 bg-[#0D0D10] border border-[#1F1F23] px-1.5 py-0.5 rounded uppercase">
              {schema.contractType}
            </span>
          </div>
          <button
            onClick={onClose}
            className="text-zinc-400 hover:text-zinc-100 rounded p-1"
            aria-label="Close panel"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex items-center gap-2">
          {routeInfo ? (
            <div className="flex items-baseline gap-2 min-w-0">
              <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded border uppercase shrink-0 ${methodTagStyle(routeInfo.method).bg} ${methodTagStyle(routeInfo.method).border}`}>
                {routeInfo.method}
              </span>
              <h3 className="text-xs font-semibold text-zinc-100 truncate block font-mono" title={routeInfo.path}>
                {routeInfo.path}
              </h3>
            </div>
          ) : (
            <h3 className="text-xs font-semibold text-zinc-100 truncate block font-mono" title={symbol.qualified}>
              {shortSymbolName(symbol.qualified)}()
            </h3>
          )}
          <button
            onClick={handleCopy}
            className="text-zinc-500 hover:text-zinc-200 p-0.5 rounded ml-auto shrink-0"
            title="Copy identifier"
          >
            {copied ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
          </button>
        </div>

        <span className="text-[9px] text-zinc-500 truncate block" title={symbol.file_path}>
          {symbol.file_path}:{symbol.line_number}
        </span>
      </div>

      {/* Inspector Body */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 text-xs">
        {/* Interactive Decision Path */}
        <DecisionPathRibbon steps={decisionPath} />

        {/* WHAT IS THIS? */}
        <div className="p-3 bg-[#0D0D10] border border-[#1F1F23] rounded-lg space-y-1">
          <span className="text-[9px] font-bold text-zinc-400 uppercase tracking-wider block">
            What Is This?
          </span>
          <p className="text-[11px] text-zinc-300 leading-relaxed font-sans">
            {whyItMatters}
          </p>
        </div>

        {/* CONTRACT SPECIFICATION */}
        <div className="p-3 bg-[#0D0D10] border border-[#1F1F23] rounded-lg space-y-2">
          <span className="text-[9px] font-bold text-zinc-400 uppercase tracking-wider block flex items-center justify-between">
            <span>Contract Specification</span>
            <span className="text-zinc-500 font-normal">{symbol.language}</span>
          </span>

          <div className="space-y-1.5 text-[11px]">
            <div className="flex justify-between py-1 border-b border-[#1F1F23]">
              <span className="text-zinc-400">Parameters</span>
              <span className="text-zinc-200 font-semibold">{symbol.param_count} declared</span>
            </div>
            <div className="flex justify-between py-1 border-b border-[#1F1F23]">
              <span className="text-zinc-400">Return Type</span>
              <span className="text-zinc-200 font-semibold">{schema.returnType}</span>
            </div>
            <div className="flex justify-between py-1 border-b border-[#1F1F23]">
              <span className="text-zinc-400">Execution Mode</span>
              <span className={symbol.is_async ? 'text-indigo-400 font-bold' : 'text-zinc-300'}>
                {symbol.is_async ? 'Async Execution' : 'Synchronous'}
              </span>
            </div>
          </div>

          <p className="text-[10px] text-zinc-400 pt-1 font-sans italic">
            {schema.schemaNotice}
          </p>
        </div>

        {/* IMPLEMENTATION & USAGE (Epistemic distinction) */}
        <div className="grid grid-cols-2 gap-2 text-center select-none">
          <div className="p-2.5 bg-[#0D0D10] border border-[#1F1F23] rounded-lg">
            <span className="text-zinc-400 text-[8px] uppercase tracking-wider font-bold block">Internal Callers</span>
            <div className="flex items-center justify-center gap-1 mt-0.5">
              <span className="text-base font-bold text-emerald-400">{symbol.fan_in}</span>
              <span className="text-[8px] text-emerald-500 font-bold">[VERIFIED]</span>
            </div>
            <span className="text-[7px] text-zinc-500">internal call sites</span>
          </div>
          <div className="p-2.5 bg-[#0D0D10] border border-[#1F1F23] rounded-lg">
            <span className="text-zinc-400 text-[8px] uppercase tracking-wider font-bold block">External Consumers</span>
            <span className="text-sm font-bold text-zinc-400 mt-1 block uppercase">UNKNOWN</span>
            <span className="text-[7px] text-zinc-500">unestablished statically</span>
          </div>
        </div>

        {/* STRUCTURAL CHANGE SENSITIVITY */}
        <div className="p-3 bg-[#0D0D10] border border-[#1F1F23] rounded-lg space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[9px] font-bold text-zinc-400 uppercase tracking-wider">
              Change Sensitivity Verdict
            </span>
            <span className={`text-[8px] font-bold px-2 py-0.5 rounded border uppercase ${riskTone}`}>
              {sim.riskRating} Risk
            </span>
          </div>
          <ul className="text-[10px] text-zinc-300 font-sans space-y-1 pl-3 list-disc">
            {sim.riskReasons.map((reason, i) => (
              <li key={i}>{reason}</li>
            ))}
          </ul>
        </div>

        {/* SIMULATE CONTRACT CHANGE INTERACTIVE DRAWER */}
        {showSim && (
          <div className="p-3 bg-[#08080A] border border-amber-500/40 rounded-lg space-y-2.5 animate-in fade-in duration-200 shadow-xl">
            <div className="flex items-center justify-between">
              <span className="text-[9px] font-bold text-amber-400 uppercase tracking-wider flex items-center gap-1">
                <Zap className="h-3 w-3" /> WHAT IF I CHANGE THIS? (STATIC GRAPH IMPACT)
              </span>
              <button onClick={() => setShowSim(false)} className="text-zinc-500 hover:text-zinc-200">
                <X className="h-3 w-3" />
              </button>
            </div>
            <p className="text-[10px] text-zinc-300 font-sans leading-relaxed">
              {sim.narrativeImpact}
            </p>
            <div className="grid grid-cols-4 gap-1 text-center text-[10px]">
              <div className="p-1 bg-[#0D0D10] rounded border border-[#1F1F23]">
                <span className="text-zinc-500 block text-[7px]">Entry Paths</span>
                <span className="font-bold text-indigo-400">{sim.executionPathsCount}</span>
              </div>
              <div className="p-1 bg-[#0D0D10] rounded border border-[#1F1F23]">
                <span className="text-zinc-500 block text-[7px]">Callers</span>
                <span className="font-bold text-emerald-400">{sim.internalCallersCount}</span>
              </div>
              <div className="p-1 bg-[#0D0D10] rounded border border-[#1F1F23]">
                <span className="text-zinc-500 block text-[7px]">Downstream</span>
                <span className="font-bold text-amber-400">{sim.downstreamSymbolsCount}</span>
              </div>
              <div className="p-1 bg-[#0D0D10] rounded border border-[#1F1F23]">
                <span className="text-zinc-500 block text-[7px]">Tests</span>
                <span className="font-bold text-zinc-200">{sim.affectedTestsCount}</span>
              </div>
            </div>
          </div>
        )}

        {/* DYNAMIC NEXT INVESTIGATION PROMPTS */}
        <div className="space-y-1.5 pt-2 border-t border-[#1F1F23]">
          <span className="text-[9px] text-indigo-400 uppercase font-bold tracking-wider block flex items-center gap-1">
            <Sparkles className="h-3 w-3" /> Next Investigation
          </span>
          <div className="space-y-1">
            {questions.map((q, idx) => (
              <button
                key={idx}
                onClick={() => handleAskAria(q)}
                className="w-full text-left p-2 bg-[#0D0D10] hover:bg-zinc-800/80 border border-[#1F1F23] hover:border-indigo-500/40 rounded text-[10px] text-zinc-300 hover:text-zinc-100 transition-all font-sans leading-snug flex items-start gap-1.5"
              >
                <ArrowRight className="h-3 w-3 text-indigo-400 shrink-0 mt-0.5" />
                <span>{q}</span>
              </button>
            ))}
          </div>
        </div>

        {/* ACTIONS */}
        <div className="space-y-2 pt-2 border-t border-[#1F1F23]">
          {/* PRIMARY ACTION: SIMULATE CONTRACT CHANGE */}
          <button
            onClick={() => setShowSim((prev) => !prev)}
            className="w-full flex items-center justify-center gap-1.5 bg-[#5E6AD2] hover:bg-[#4E5AC0] text-white font-bold px-3 py-2 rounded text-[10px] transition-all uppercase shadow-md"
          >
            <Zap className="h-3.5 w-3.5" /> {showSim ? 'Hide Simulation' : 'Simulate Contract Change'}
          </button>

          {/* SECONDARY ACTIONS: BLAST RADIUS, CALL GRAPH, FILE GRAPH */}
          <div className="grid grid-cols-3 gap-1.5">
            <button
              onClick={handleOpenImpact}
              title="Analyze Blast Radius"
              className="flex items-center justify-center gap-1 bg-[#0D0D10] hover:bg-zinc-800 border border-[#1F1F23] text-zinc-300 hover:text-zinc-100 font-bold px-2 py-1.5 rounded text-[9px] transition-all"
            >
              <Activity className="h-3 w-3 text-emerald-400" /> Blast Radius
            </button>
            <button
              onClick={handleOpenCallGraph}
              title="View in Call Graph"
              className="flex items-center justify-center gap-1 bg-[#0D0D10] hover:bg-zinc-800 border border-[#1F1F23] text-zinc-300 hover:text-zinc-100 font-bold px-2 py-1.5 rounded text-[9px] transition-all"
            >
              <Workflow className="h-3 w-3 text-cyan-400" /> Call Graph
            </button>
            <button
              onClick={handleOpenFileGraph}
              title="View in File Graph"
              className="flex items-center justify-center gap-1 bg-[#0D0D10] hover:bg-zinc-800 border border-[#1F1F23] text-zinc-300 hover:text-zinc-100 font-bold px-2 py-1.5 rounded text-[9px] transition-all"
            >
              <ExternalLink className="h-3 w-3 text-indigo-400" /> File Graph
            </button>
          </div>

          {/* TERTIARY ACTION: ASK ARIA ABOUT CONTRACT */}
          <button
            onClick={() => handleAskAria()}
            className="w-full flex items-center justify-center gap-1.5 bg-[#0D0D10] hover:bg-zinc-800 border border-indigo-500/40 text-indigo-300 hover:text-indigo-200 font-bold px-2 py-1.5 rounded text-[10px] transition-all"
          >
            <Sparkles className="h-3.5 w-3.5 text-indigo-400" /> Ask ARIA About Contract
          </button>
        </div>
      </div>
    </aside>
  );
};

// ── Main Component ─────────────────────────────────────────────────────────

export const APISurfaceAnalyzer: React.FC<Props> = ({ repoName }) => {
  const [owner, repoSlug] = repoName.split('/');

  // Build state
  const [building, setBuilding] = useState(false);
  const [buildProgress, setBuildProgress] = useState('');
  const [buildError, setBuildError] = useState<string | null>(null);

  // Data state
  const [stats, setStats] = useState<APISurfaceStats | null>(null);
  const [publicSyms, setPublicSyms] = useState<ClassifiedSymbol[]>([]);
  const [internalSyms, setInternalSyms] = useState<ClassifiedSymbol[]>([]);
  const [deprecatedSyms, setDeprecatedSyms] = useState<ClassifiedSymbol[]>([]);
  const [orphanSyms, setOrphanSyms] = useState<ClassifiedSymbol[]>([]);
  const [routeSyms, setRouteSyms] = useState<ClassifiedSymbol[]>([]);

  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  // UI Views & Filter state
  const [activeView, setActiveView] = useState<ViewId>('overview');
  const [secondaryFilter, setSecondaryFilter] = useState<SecondaryFilter>('all');
  const [routeSort, setRouteSort] = useState<RouteSortMode>('relevance');
  const [searchQuery, setSearchQuery] = useState('');
  const [methodFilter, setMethodFilter] = useState<string>('ALL');

  // Progressive disclosure toggles for deep inventory
  const [showAllPublic, setShowAllPublic] = useState(false);
  const [showAllInternal, setShowAllInternal] = useState(false);

  // Selected symbol for inspector & keyboard nav
  const [selectedSymbol, setSelectedSymbol] = useState<ClassifiedSymbol | null>(null);
  const [selectedRoute, setSelectedRoute] = useState<HttpRouteInfo | undefined>(undefined);
  const [focusedRouteIndex, setFocusedRouteIndex] = useState<number>(-1);

  const searchInputRef = useRef<HTMLInputElement>(null);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    setStats(null);
    setPublicSyms([]);
    setInternalSyms([]);
    setDeprecatedSyms([]);
    setOrphanSyms([]);
    setRouteSyms([]);
    try {
      const [statsRes, pubRes, intRes, depRes, breakRes, routeRes] = await Promise.all([
        fetch(apiUrl(`/api/v1/api-surface/${owner}/${repoSlug}/stats`)),
        fetch(apiUrl(`/api/v1/api-surface/${owner}/${repoSlug}/public`)),
        fetch(apiUrl(`/api/v1/api-surface/${owner}/${repoSlug}/internal`)),
        fetch(apiUrl(`/api/v1/api-surface/${owner}/${repoSlug}/deprecated`)),
        fetch(apiUrl(`/api/v1/api-surface/${owner}/${repoSlug}/breaking`)),
        fetch(apiUrl(`/api/v1/api-surface/${owner}/${repoSlug}/public?kind=route&limit=200`)),
      ]);

      if (statsRes.status === 404) { setLoading(false); return; }
      if (!statsRes.ok) throw new Error(`HTTP ${statsRes.status}`);

      const [statsData, pubData, intData, depData, breakData, routeData] = await Promise.all([
        statsRes.json(), pubRes.json(), intRes.json(),
        depRes.json(), breakRes.json(), routeRes.json(),
      ]);

      setStats(statsData);
      setPublicSyms(pubData.symbols ?? []);
      setInternalSyms(intData.symbols ?? []);
      setDeprecatedSyms(depData.symbols ?? []);
      setOrphanSyms(breakData.orphans ?? []);
      setRouteSyms(routeData.symbols ?? []);
    } catch (err: any) {
      setLoadError(extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [owner, repoSlug]);

  useEffect(() => { loadAll(); }, [loadAll]);

  // Derived Intelligence Signals
  const signals: ApiExposureSignals = useMemo(() => {
    return computeApiExposureSignals(stats, publicSyms, internalSyms, deprecatedSyms, orphanSyms, routeSyms);
  }, [stats, publicSyms, internalSyms, deprecatedSyms, orphanSyms, routeSyms]);

  const allSymbols = useMemo(() => [...publicSyms, ...internalSyms], [publicSyms, internalSyms]);

  // Grouped modules for curated views
  const publicModuleGroups = useMemo(() => groupSymbolsByModule(publicSyms), [publicSyms]);
  const internalModuleGroups = useMemo(() => groupSymbolsByModule(internalSyms), [internalSyms]);

  // Filtered & Sorted Routes
  const filteredRoutes = useMemo(() => {
    let list = sortRoutes(signals.routes, routeSort);
    if (methodFilter !== 'ALL') {
      list = list.filter((r) => r.method === methodFilter);
    }
    if (secondaryFilter === 'high_impact') {
      list = list.filter((r) => r.impactLevel === 'HIGH IMPACT');
    } else if (secondaryFilter === 'no_internal_callers') {
      list = list.filter((r) => r.internalCallersCount === 0);
    } else if (secondaryFilter === 'deprecated') {
      list = list.filter((r) => r.status === 'deprecated');
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      list = list.filter(
        (r) =>
          r.path.toLowerCase().includes(q) ||
          r.handlerName.toLowerCase().includes(q) ||
          r.filePath.toLowerCase().includes(q)
      );
    }
    return list;
  }, [signals.routes, routeSort, methodFilter, secondaryFilter, searchQuery]);

  // Keyboard navigation ('/', '↑', '↓', 'Enter', 'Esc')
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const isInput = target?.tagName === 'INPUT' || target?.tagName === 'TEXTAREA' || target?.isContentEditable;

      if (event.key === '/' && !event.metaKey && !event.ctrlKey && !event.altKey && !isInput) {
        event.preventDefault();
        searchInputRef.current?.focus();
        return;
      }

      if (event.key === 'Escape') {
        if (selectedSymbol) {
          setSelectedSymbol(null);
          setSelectedRoute(undefined);
        } else if (searchQuery) {
          setSearchQuery('');
        }
        return;
      }

      if (activeView === 'routes' && filteredRoutes.length > 0 && !isInput) {
        if (event.key === 'ArrowDown') {
          event.preventDefault();
          setFocusedRouteIndex((prev) => (prev < filteredRoutes.length - 1 ? prev + 1 : 0));
        } else if (event.key === 'ArrowUp') {
          event.preventDefault();
          setFocusedRouteIndex((prev) => (prev > 0 ? prev - 1 : filteredRoutes.length - 1));
        } else if (event.key === 'Enter' && focusedRouteIndex >= 0 && focusedRouteIndex < filteredRoutes.length) {
          event.preventDefault();
          const target = filteredRoutes[focusedRouteIndex];
          setSelectedSymbol(target.rawSymbol);
          setSelectedRoute(target);
        }
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [activeView, filteredRoutes, focusedRouteIndex, selectedSymbol, searchQuery]);

  // Build handler
  const handleBuild = useCallback(async () => {
    setBuilding(true);
    setBuildError(null);
    setBuildProgress('Starting…');
    setStats(null);

    try {
      const res = await fetch(apiUrl('/api/v1/api-surface/build'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ repo: repoName }),
      });

      if (!res.body) throw new Error('No response body.');
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop() ?? '';

        for (const part of parts) {
          const line = part.replace(/^data: /, '').trim();
          if (!line) continue;
          try {
            const ev = JSON.parse(line);
            if (ev.status === 'error') { setBuildError(ev.message); setBuilding(false); return; }
            if (ev.status === 'done')  { setBuilding(false); loadAll(); return; }
            if (ev.message)             setBuildProgress(ev.message);
          } catch { /* non-JSON */ }
        }
      }
    } catch (err: any) {
      setBuildError(extractErrorMessage(err));
    } finally {
      setBuilding(false);
    }
  }, [repoName, loadAll]);

  const notBuilt = !loading && !stats && !loadError;
  const hasData = !!stats;

  // Filtered Public Symbols
  const filteredPublicSymbols = useMemo(() => {
    let list = publicSyms;
    if (secondaryFilter === 'high_impact') {
      list = list.filter((s) => s.fan_in >= 4);
    } else if (secondaryFilter === 'no_internal_callers') {
      list = list.filter((s) => s.is_orphan || s.fan_in === 0);
    } else if (secondaryFilter === 'deprecated') {
      list = list.filter((s) => s.status === 'deprecated');
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      list = list.filter(
        (s) =>
          s.name.toLowerCase().includes(q) ||
          s.qualified.toLowerCase().includes(q) ||
          s.file_path.toLowerCase().includes(q)
      );
    }
    return list;
  }, [publicSyms, secondaryFilter, searchQuery]);

  // Filtered Internal Symbols
  const filteredInternalSymbols = useMemo(() => {
    let list = internalSyms;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      list = list.filter(
        (s) =>
          s.name.toLowerCase().includes(q) ||
          s.qualified.toLowerCase().includes(q) ||
          s.file_path.toLowerCase().includes(q)
      );
    }
    return list;
  }, [internalSyms, searchQuery]);

  // View Modes Definition
  const MODES: [ViewId, string, React.ComponentType<{ className?: string }>, number][] = [
    ['overview', 'OVERVIEW', LayoutList, 0],
    ['routes',   'ROUTES',   Route, signals.routeCount],
    ['public',   'PUBLIC',   Globe, signals.publicCount],
    ['internal', 'INTERNAL', Lock, signals.internalCount],
    ['issues',   'ISSUES',   AlertTriangle, signals.noInternalCallersCount + signals.deprecatedCount],
  ];

  return (
    <div className="space-y-6 fade-up min-w-0 font-mono">
      {/* ── 1. Executive Contract Briefing ───────────────────────────────── */}
      <header className="min-w-0 space-y-4">
        <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4">
          <div className="min-w-0 max-w-2xl">
            <span className="text-[10px] font-bold text-indigo-400 uppercase tracking-wider block mb-1">
              API CONTRACT / EXPOSURE INTELLIGENCE
            </span>
            <h2 className="text-xl sm:text-2xl font-bold text-zinc-100 tracking-tight font-mono">
              WHAT DOES THIS SYSTEM EXPOSE?
            </h2>
            <p className="text-xs text-zinc-400 leading-relaxed mt-1.5 max-w-xl font-sans">
              Find the contracts that matter, understand how they are consumed, and estimate change risk before editing code.
            </p>
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-3 shrink-0">
            {hasData && (
              <button
                type="button"
                onClick={loadAll}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded border border-[#1F1F23] bg-[#08080A] hover:bg-zinc-800 text-zinc-300 text-xs font-bold transition-colors"
              >
                <RefreshCw className="h-3.5 w-3.5" /> Refresh
              </button>
            )}
            <button
              type="button"
              onClick={handleBuild}
              disabled={building}
              className="flex items-center gap-1.5 px-3.5 py-1.5 rounded bg-[#5E6AD2] hover:bg-[#4E5AC0] disabled:opacity-50 text-white text-xs font-bold transition-colors shadow-sm"
            >
              {building ? (
                <>
                  <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                  Analyzing
                </>
              ) : hasData ? (
                <>
                  <RefreshCw className="h-3.5 w-3.5" />
                  Rebuild
                </>
              ) : (
                <>
                  Analyze API Surface
                  <ArrowRight className="h-3.5 w-3.5" />
                </>
              )}
            </button>
          </div>
        </div>

        {building && (
          <div className="space-y-2 pt-2" role="status" aria-live="polite">
            <div className="h-1 w-full bg-[#08080A] border border-[#1F1F23] rounded overflow-hidden">
              <div className="h-full w-1/3 bg-[#5E6AD2] animate-pulse" />
            </div>
            <p className="text-[10px] text-zinc-400">{buildProgress}</p>
          </div>
        )}

        {buildError && (
          <div
            role="alert"
            className="flex items-start gap-3 border border-red-500/30 bg-red-950/20 p-3 rounded-lg text-xs text-red-300"
          >
            <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5 text-red-400" />
            <p>{buildError}</p>
          </div>
        )}
      </header>

      {/* Loading state */}
      {loading && !hasData && (
        <SkeletonGroup label="Loading API surface">
          <div className="space-y-3">
            <SkeletonCard />
            <SkeletonCard />
          </div>
        </SkeletonGroup>
      )}

      {/* Not built state */}
      {notBuilt && !building && (
        <EmptyState
          icon={<Globe className="h-6 w-6 text-indigo-400" />}
          title="API surface not analyzed yet"
          description="Analyze public interfaces, HTTP routes, deprecation flags, and exposure boundaries."
          action={<Button onClick={handleBuild}>Analyze API Surface</Button>}
        />
      )}

      {/* Load error */}
      {loadError && !loading && (
        <div
          role="alert"
          className="flex items-start gap-3 border border-red-500/30 bg-red-950/20 p-3 rounded-lg text-xs text-red-300"
        >
          <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5 text-red-400" />
          <p>{loadError}</p>
        </div>
      )}

      {/* ── Surface Intelligence ────────────────────────────────────────── */}
      {hasData && !loading && (
        <div className="space-y-5 min-w-0">
          {/* ── 2. Key Contract Metrics System ────────────────────────────── */}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2.5">
            <div className="p-3 bg-[#08080A] border border-[#5E6AD2]/50 rounded-lg col-span-1 lg:col-span-1 shadow-md">
              <span className="text-[9px] font-bold text-indigo-400 uppercase tracking-wider block">High-Impact Contracts</span>
              <span className="text-xl font-extrabold text-indigo-300 mt-0.5 block">{signals.highImpactCount}</span>
              <span className="text-[8px] text-zinc-500 font-sans">elevated reach / fan-in</span>
            </div>
            <div className="p-3 bg-[#08080A] border border-amber-500/40 rounded-lg col-span-1 lg:col-span-1 shadow-md">
              <span className="text-[9px] font-bold text-amber-400 uppercase tracking-wider block">No Internal Callers</span>
              <span className="text-xl font-extrabold text-amber-300 mt-0.5 block">{signals.noInternalCallersCount.toLocaleString()}</span>
              <span className="text-[8px] text-zinc-500 font-sans">external / uncalled locally</span>
            </div>
            <div className="p-3 bg-[#08080A] border border-[#1F1F23] rounded-lg col-span-1 lg:col-span-1">
              <span className="text-[9px] font-bold text-zinc-400 uppercase tracking-wider block">Deprecated</span>
              <span className={`text-xl font-bold mt-0.5 block ${signals.deprecatedCount > 0 ? 'text-rose-400' : 'text-zinc-500'}`}>
                {signals.deprecatedCount}
              </span>
              <span className="text-[8px] text-zinc-500 font-sans">marked in AST</span>
            </div>
            <div className="p-3 bg-[#08080A] border border-[#1F1F23] rounded-lg col-span-1 lg:col-span-1">
              <span className="text-[9px] font-bold text-zinc-500 uppercase tracking-wider block">HTTP Routes</span>
              <span className="text-lg font-bold text-zinc-200 mt-0.5 block">{signals.routeCount}</span>
              <span className="text-[8px] text-zinc-500 font-sans">endpoints</span>
            </div>
            <div className="p-3 bg-[#08080A] border border-[#1F1F23] rounded-lg col-span-1 lg:col-span-1">
              <span className="text-[9px] font-bold text-zinc-500 uppercase tracking-wider block">Public Symbols</span>
              <span className="text-lg font-bold text-zinc-200 mt-0.5 block">{signals.publicCount.toLocaleString()}</span>
              <span className="text-[8px] text-zinc-500 font-sans">total exported</span>
            </div>
            <div className="p-3 bg-[#08080A] border border-[#1F1F23] rounded-lg col-span-1 lg:col-span-1">
              <span className="text-[9px] font-bold text-zinc-500 uppercase tracking-wider block">Internal Symbols</span>
              <span className="text-lg font-bold text-zinc-200 mt-0.5 block">{signals.internalCount.toLocaleString()}</span>
              <span className="text-[8px] text-zinc-500 font-sans">package-private</span>
            </div>
          </div>

          {/* ── 3. KEY INVESTIGATION TARGETS (Start Here) ─────────────────── */}
          {signals.startHereCards.length > 0 && (
            <section aria-label="Start Here" className="p-4 bg-[#08080A] border border-[#1F1F23] rounded-xl space-y-3 shadow-lg">
              <div className="flex items-center justify-between pb-1 border-b border-[#1F1F23]">
                <div className="flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-indigo-400" />
                  <h3 className="text-xs font-bold text-zinc-100 uppercase tracking-wider font-mono">
                    START HERE — KEY INVESTIGATION TARGETS
                  </h3>
                </div>
                <span className="text-[9px] text-zinc-500 font-sans">Dynamically derived from repository evidence</span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                {signals.startHereCards.map((card) => (
                  <div
                    key={card.id}
                    className="p-3 bg-[#0D0D10] border border-[#1F1F23] hover:border-indigo-500/50 rounded-lg flex flex-col justify-between space-y-2.5 transition-all text-xs"
                  >
                    <div className="space-y-1.5">
                      <div className="flex items-center justify-between">
                        <span className={`text-[8px] font-bold px-1.5 py-0.5 rounded border uppercase ${
                          card.badge === 'MOST IMPORTANT ROUTE'
                            ? 'text-indigo-300 bg-indigo-950/40 border-indigo-500/40'
                            : card.badge === 'MOST CONSUMED CONTRACT'
                              ? 'text-emerald-300 bg-emerald-950/40 border-emerald-500/40'
                              : card.badge === 'EXPOSURE ANOMALY'
                                ? 'text-amber-300 bg-amber-950/40 border-amber-500/40'
                                : 'text-rose-300 bg-rose-950/40 border-rose-500/40'
                        }`}>
                          {card.badge}
                        </span>
                        <span className={`text-[8px] font-bold px-1 py-0.5 rounded border uppercase ${getEvidenceBadgeClass(card.evidence)}`}>
                          [{card.evidence}]
                        </span>
                      </div>

                      <h4 className="font-bold text-zinc-100 text-xs truncate font-mono" title={card.title}>
                        {card.title}
                      </h4>

                      <p className="text-[9px] text-zinc-500 truncate">
                        {card.subtitle}
                      </p>

                      <p className="text-[10px] text-zinc-400 font-sans leading-relaxed pt-1">
                        {card.whyItMatters}
                      </p>
                    </div>

                    <div className="pt-2 border-t border-[#1F1F23] flex items-center justify-between">
                      <button
                        onClick={() => {
                          if (card.targetSymbol) {
                            setSelectedSymbol(card.targetSymbol);
                            setSelectedRoute(card.targetRoute);
                          } else if (card.actionIntent === 'review') {
                            setActiveView('issues');
                          }
                        }}
                        className="text-[9px] font-bold text-indigo-400 hover:text-indigo-300 flex items-center gap-1 uppercase tracking-wider"
                      >
                        {card.actionLabel} <ArrowRight className="h-3 w-3" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* ── 4. View Modes, Subordinate Filters & Search Controller ─────── */}
          <div className="space-y-2">
            {/* Primary View Navigation Tabs */}
            <div className="flex items-center justify-between gap-3 flex-wrap p-2 bg-[#08080A] border border-[#1F1F23] rounded-lg text-xs shadow-md">
              <div className="flex items-center bg-[#0D0D10] border border-[#1F1F23] rounded p-0.5 text-[10px] overflow-x-auto">
                {MODES.map(([v, label, Icon, count]) => {
                  const isActive = activeView === v;
                  return (
                    <button
                      key={v}
                      onClick={() => setActiveView(v)}
                      className={`px-3.5 py-1.5 rounded transition-all font-bold whitespace-nowrap flex items-center gap-1.5 ${
                        isActive
                          ? 'bg-[#5E6AD2] text-white shadow-sm'
                          : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/40'
                      }`}
                    >
                      <Icon className="h-3.5 w-3.5" />
                      <span>{label}</span>
                      {count > 0 && <span className={`text-[9px] ${isActive ? 'text-indigo-100' : 'text-zinc-500'}`}>({count})</span>}
                    </button>
                  );
                })}
              </div>

              {/* Search Input */}
              <div className="relative flex-grow max-w-xs ml-auto">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-zinc-500 pointer-events-none" />
                <input
                  ref={searchInputRef}
                  type="search"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search routes, symbols, handlers…"
                  className="w-full bg-[#0D0D10] border border-[#1F1F23] rounded pl-8 pr-8 py-1.5 text-xs font-mono focus:outline-none focus:border-[#5E6AD2] text-zinc-100 placeholder:text-zinc-600"
                  aria-label="Search API surface"
                />
                {searchQuery ? (
                  <button
                    onClick={() => setSearchQuery('')}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-100"
                    aria-label="Clear search"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                ) : (
                  <kbd className="absolute right-2 top-1/2 -translate-y-1/2 text-[9px] font-mono text-zinc-500 bg-[#08080A] border border-[#1F1F23] px-1 py-0.5 rounded pointer-events-none">
                    /
                  </kbd>
                )}
              </div>
            </div>

            {/* Subordinate Secondary Filter & Controls Bar */}
            <div className="flex items-center justify-between gap-3 flex-wrap px-3 py-1.5 bg-[#08080A]/60 border border-[#1F1F23]/60 rounded-md text-[9px]">
              <div className="flex items-center gap-1.5 overflow-x-auto">
                <span className="text-zinc-500 font-bold uppercase tracking-wider mr-1">FILTER:</span>
                <button
                  onClick={() => setSecondaryFilter('all')}
                  className={`px-2 py-0.5 rounded border transition-all ${
                    secondaryFilter === 'all'
                      ? 'bg-zinc-800 border-zinc-700 text-zinc-100 font-bold'
                      : 'border-transparent text-zinc-500 hover:text-zinc-300'
                  }`}
                >
                  ALL
                </button>
                <button
                  onClick={() => setSecondaryFilter('high_impact')}
                  className={`px-2 py-0.5 rounded border transition-all ${
                    secondaryFilter === 'high_impact'
                      ? 'bg-indigo-950/60 border-indigo-800 text-indigo-300 font-bold'
                      : 'border-transparent text-zinc-500 hover:text-zinc-300'
                  }`}
                >
                  HIGH IMPACT
                </button>
                <button
                  onClick={() => setSecondaryFilter('no_internal_callers')}
                  className={`px-2 py-0.5 rounded border transition-all ${
                    secondaryFilter === 'no_internal_callers'
                      ? 'bg-amber-950/60 border-amber-800 text-amber-300 font-bold'
                      : 'border-transparent text-zinc-500 hover:text-zinc-300'
                  }`}
                >
                  NO INTERNAL CALLERS
                </button>
                <button
                  onClick={() => setSecondaryFilter('deprecated')}
                  className={`px-2 py-0.5 rounded border transition-all ${
                    secondaryFilter === 'deprecated'
                      ? 'bg-rose-950/60 border-rose-800 text-rose-300 font-bold'
                      : 'border-transparent text-zinc-500 hover:text-zinc-300'
                  }`}
                >
                  DEPRECATED
                </button>
              </div>

              {activeView === 'routes' && (
                <div className="flex items-center gap-3 ml-auto">
                  {/* Method filter */}
                  <div className="flex items-center gap-1">
                    {['ALL', 'GET', 'POST', 'PUT', 'PATCH', 'DELETE'].map((m) => (
                      <button
                        key={m}
                        onClick={() => setMethodFilter(m)}
                        className={`px-1.5 py-0.5 rounded border uppercase font-bold transition-all ${
                          methodFilter === m
                            ? 'bg-zinc-800 border-zinc-600 text-zinc-100'
                            : 'border-transparent text-zinc-500 hover:text-zinc-300'
                        }`}
                      >
                        {m}
                      </button>
                    ))}
                  </div>

                  {/* Sort modes */}
                  <div className="flex items-center gap-1 pl-2 border-l border-[#1F1F23]">
                    <span className="text-zinc-500 font-bold uppercase">SORT:</span>
                    {(['relevance', 'impact', 'callers', 'risk'] as RouteSortMode[]).map((mode) => (
                      <button
                        key={mode}
                        onClick={() => setRouteSort(mode)}
                        className={`px-2 py-0.5 rounded border uppercase font-bold transition-all ${
                          routeSort === mode
                            ? 'bg-indigo-950/80 border-indigo-700 text-indigo-300'
                            : 'border-transparent text-zinc-500 hover:text-zinc-300'
                        }`}
                      >
                        {mode}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* ── 5. Main Content Workspace + Inspector ──────────────────────── */}
          <div className="flex border border-[#1F1F23] rounded-lg overflow-hidden bg-[#08080A] min-h-[580px] relative shadow-2xl">
            <div className="flex-1 min-w-0 overflow-y-auto p-4 space-y-5">
              {/* ── VIEW: OVERVIEW ────────────────────────────────────────── */}
              {activeView === 'overview' && (
                <div className="space-y-5">
                  {/* Exposure Summary & What This Means */}
                  <div className="p-3.5 bg-[#0D0D10] border border-[#5E6AD2]/30 rounded-lg space-y-2 text-xs">
                    <span className="text-[9px] font-bold text-indigo-400 uppercase tracking-wider block">
                      EXPOSURE SUMMARY
                    </span>
                    <p className="text-zinc-100 font-sans leading-relaxed text-xs">
                      {signals.exposureSummary}
                    </p>

                    <div className="pt-2 border-t border-[#1F1F23] space-y-1">
                      <span className="text-[9px] font-bold text-zinc-400 uppercase tracking-wider block">
                        WHAT THIS MEANS
                      </span>
                      <p className="text-zinc-300 font-sans leading-relaxed text-[11px] italic">
                        {signals.whatThisMeans}
                      </p>
                    </div>
                  </div>

                  {/* Contract Health Verdict */}
                  <div className="p-3.5 bg-[#0D0D10] border border-[#1F1F23] rounded-lg space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-[9px] font-bold text-zinc-400 uppercase tracking-wider">
                        CONTRACT HEALTH
                      </span>
                      <span className={`text-[9px] font-bold px-2 py-0.5 rounded border uppercase ${
                        signals.healthDiagnosis.verdict === 'HEALTHY'
                          ? 'text-emerald-300 bg-emerald-950/60 border-emerald-800'
                          : signals.healthDiagnosis.verdict === 'REVIEW REQUIRED'
                            ? 'text-amber-300 bg-amber-950/60 border-amber-800'
                            : signals.healthDiagnosis.verdict === 'HIGH RISK'
                              ? 'text-rose-300 bg-rose-950/60 border-rose-800'
                              : 'text-zinc-400 bg-[#08080A] border-[#1F1F23]'
                      }`}>
                        VERDICT: {signals.healthDiagnosis.verdict}
                      </span>
                    </div>

                    <ul className="text-xs text-zinc-300 font-sans space-y-1 pl-4 list-disc">
                      {signals.healthDiagnosis.reasons.map((reason, i) => (
                        <li key={i}>{reason}</li>
                      ))}
                    </ul>
                  </div>

                  {/* Key HTTP Routes */}
                  {signals.routes.length > 0 && (
                    <div className="space-y-2">
                      <div className="flex items-center justify-between pb-1 border-b border-[#1F1F23]">
                        <span className="text-xs font-bold text-indigo-400 uppercase tracking-wider flex items-center gap-1.5">
                          <Route className="h-3.5 w-3.5" /> High-Priority HTTP Routes
                        </span>
                        <button
                          onClick={() => setActiveView('routes')}
                          className="text-[10px] text-zinc-400 hover:text-zinc-200 font-bold uppercase"
                        >
                          Explore Routes ({signals.routeCount}) →
                        </button>
                      </div>

                      <div className="space-y-1.5">
                        {signals.routes.slice(0, 5).map((route) => (
                          <div
                            key={route.id}
                            onClick={() => {
                              setSelectedSymbol(route.rawSymbol);
                              setSelectedRoute(route);
                            }}
                            className={`p-2.5 rounded-lg border flex items-center justify-between gap-3 cursor-pointer transition-all ${
                              selectedRoute?.id === route.id
                                ? 'bg-[#5E6AD2]/20 border-[#5E6AD2] ring-1 ring-[#5E6AD2]/50'
                                : 'bg-[#0D0D10] border-[#1F1F23] hover:border-zinc-700'
                            }`}
                          >
                            <div className="flex items-center gap-2.5 min-w-0">
                              <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded border uppercase shrink-0 ${methodTagStyle(route.method).bg} ${methodTagStyle(route.method).border}`}>
                                {route.method}
                              </span>
                              <div className="min-w-0">
                                <span className="text-xs font-bold text-zinc-100 truncate block">{route.path}</span>
                                <span className="text-[9px] text-zinc-500 truncate block">{route.handlerName}() · {route.filePath}:{route.lineNumber}</span>
                              </div>
                            </div>

                            <div className="flex items-center gap-2 shrink-0">
                              <span className="text-[9px] text-emerald-400 font-bold">{route.internalCallersCount} caller{route.internalCallersCount === 1 ? '' : 's'}</span>
                              <span className={`text-[8px] border px-1.5 py-0.5 rounded uppercase font-bold ${getEvidenceBadgeClass(route.evidence)}`}>
                                [{route.evidence}]
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* High-Impact Contracts Summary */}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between pb-1 border-b border-[#1F1F23]">
                      <span className="text-xs font-bold text-emerald-400 uppercase tracking-wider flex items-center gap-1.5">
                        <Globe className="h-3.5 w-3.5" /> High-Impact Public Interfaces
                      </span>
                      <button
                        onClick={() => setActiveView('public')}
                        className="text-[10px] text-zinc-400 hover:text-zinc-200 font-bold uppercase"
                      >
                        Public Surface ({signals.publicCount}) →
                      </button>
                    </div>

                    <div className="space-y-1.5">
                      {publicSyms.slice(0, 5).map((sym) => (
                        <div
                          key={`${sym.file_path}::${sym.qualified}`}
                          onClick={() => {
                            setSelectedSymbol(sym);
                            setSelectedRoute(undefined);
                          }}
                          className={`p-2.5 rounded-lg border flex items-center justify-between gap-3 cursor-pointer transition-all ${
                            selectedSymbol?.qualified === sym.qualified
                              ? 'bg-[#5E6AD2]/20 border-[#5E6AD2] ring-1 ring-[#5E6AD2]/50'
                              : 'bg-[#0D0D10] border-[#1F1F23] hover:border-zinc-700'
                          }`}
                        >
                          <div className="min-w-0">
                            <span className="text-xs font-semibold text-zinc-100 truncate block">{shortSymbolName(sym.qualified)}()</span>
                            <span className="text-[9px] text-zinc-500 truncate block">{sym.file_path}:{sym.line_number}</span>
                          </div>

                          <div className="flex items-center gap-2 shrink-0">
                            <span className="text-[9px] text-emerald-400 font-bold">{sym.fan_in} caller{sym.fan_in === 1 ? '' : 's'}</span>
                            <span className="text-[8px] bg-[#08080A] text-zinc-400 border border-[#1F1F23] px-1.5 py-0.5 rounded uppercase font-bold">
                              {sym.api_kind}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* ── VIEW: ROUTES ──────────────────────────────────────────── */}
              {activeView === 'routes' && (
                <div className="space-y-4">
                  {filteredRoutes.length === 0 ? (
                    <EmptyState
                      compact
                      icon={<Route className="h-5 w-5 text-indigo-400" />}
                      title="No matching HTTP routes"
                      description="No HTTP routes match the current filter criteria."
                    />
                  ) : (
                    <div className="space-y-1.5">
                      {filteredRoutes.map((route, idx) => {
                        const isSelected = selectedRoute?.id === route.id;
                        const isFocused = focusedRouteIndex === idx;

                        return (
                          <div
                            key={route.id}
                            onClick={() => {
                              setSelectedSymbol(route.rawSymbol);
                              setSelectedRoute(route);
                              setFocusedRouteIndex(idx);
                            }}
                            className={`p-3 rounded-lg border flex flex-col gap-2 cursor-pointer transition-all ${
                              isSelected
                                ? 'bg-[#5E6AD2]/20 border-[#5E6AD2] ring-1 ring-[#5E6AD2]/50'
                                : isFocused
                                  ? 'bg-[#0D0D10] border-zinc-700'
                                  : 'bg-[#0D0D10] border-[#1F1F23] hover:border-zinc-700'
                            }`}
                          >
                            <div className="flex items-center justify-between gap-4">
                              <div className="flex items-center gap-3 min-w-0">
                                <span className={`text-[10px] font-bold px-2 py-0.5 rounded border uppercase shrink-0 ${methodTagStyle(route.method).bg} ${methodTagStyle(route.method).border}`}>
                                  {route.method}
                                </span>
                                <div className="min-w-0">
                                  <div className="flex items-center gap-2">
                                    <span className="text-xs font-bold text-zinc-100 truncate">{route.path}</span>
                                    <span className={`text-[8px] border px-1 py-0.5 rounded font-bold uppercase ${getEvidenceBadgeClass(route.evidence)}`}>
                                      [{route.evidence}]
                                    </span>
                                  </div>
                                  <div className="text-[9px] text-zinc-400 flex items-center gap-2 mt-0.5">
                                    <span>Handler: <strong>{route.handlerName}()</strong></span>
                                    <span>·</span>
                                    <span className="truncate">{route.filePath}:{route.lineNumber}</span>
                                  </div>
                                </div>
                              </div>

                              <div className="flex items-center gap-3 shrink-0 text-[10px]">
                                <span className="text-emerald-400 font-bold">{route.internalCallersCount} caller{route.internalCallersCount === 1 ? '' : 's'}</span>
                                <span className={`text-[8px] px-1.5 py-0.5 rounded uppercase font-bold border ${
                                  route.impactLevel === 'HIGH IMPACT'
                                    ? 'text-indigo-300 bg-indigo-950/60 border-indigo-800'
                                    : 'text-zinc-400 bg-[#08080A] border-[#1F1F23]'
                                }`}>
                                  {route.impactLevel}
                                </span>
                              </div>
                            </div>

                            {/* Inline "Why This Route Matters" */}
                            <div className="text-[10px] text-zinc-400 font-sans flex items-center justify-between pt-1 border-t border-[#1F1F23]">
                              <span className="truncate">{route.whyItMatters}</span>
                              <span className="text-indigo-400 text-[9px] font-bold uppercase shrink-0 ml-2">Inspect →</span>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}

              {/* ── VIEW: PUBLIC ──────────────────────────────────────────── */}
              {activeView === 'public' && (
                <div className="space-y-4">
                  <div className="flex items-center justify-between pb-1 border-b border-[#1F1F23] text-xs">
                    <span className="font-bold text-zinc-200 uppercase">Public Contract Landscape</span>
                    <span className="text-zinc-500 text-[10px]">{publicSyms.length.toLocaleString()} exported symbols</span>
                  </div>

                  {/* Curated Module Breakdown First */}
                  <div className="space-y-2">
                    <span className="text-[9px] font-bold text-zinc-400 uppercase tracking-wider block">
                      Curated Module Packages
                    </span>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                      {publicModuleGroups.slice(0, 4).map((mod) => (
                        <div key={mod.moduleName} className="p-3 bg-[#0D0D10] border border-[#1F1F23] rounded-lg space-y-2">
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-bold text-zinc-200">{mod.moduleName}</span>
                            <span className="text-[9px] text-emerald-400 font-bold">{mod.publicCount} public symbols</span>
                          </div>
                          <div className="space-y-1">
                            {mod.topSymbols.slice(0, 3).map((s) => (
                              <button
                                key={s.qualified}
                                onClick={() => {
                                  setSelectedSymbol(s);
                                  setSelectedRoute(undefined);
                                }}
                                className="w-full text-left flex items-center justify-between text-[10px] text-zinc-400 hover:text-zinc-100 p-1 hover:bg-zinc-800/80 rounded transition-all"
                              >
                                <span className="truncate">{shortSymbolName(s.qualified)}()</span>
                                <span className="text-emerald-400 font-bold shrink-0">{s.fan_in} caller{s.fan_in === 1 ? '' : 's'}</span>
                              </button>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Progressive Disclosure for Deep Inventory */}
                  <div className="pt-3 border-t border-[#1F1F23] space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-[9px] font-bold text-zinc-400 uppercase tracking-wider">
                        Public Inventory
                      </span>
                      <button
                        onClick={() => setShowAllPublic((p) => !p)}
                        className="text-[10px] font-bold text-indigo-400 hover:text-indigo-300 uppercase flex items-center gap-1"
                      >
                        {showAllPublic ? 'Hide Full Inventory' : `View Complete Public Inventory (${filteredPublicSymbols.length.toLocaleString()} Symbols)`}
                        {showAllPublic ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                      </button>
                    </div>

                    {showAllPublic && (
                      <div className="space-y-1.5 max-h-96 overflow-y-auto">
                        {filteredPublicSymbols.slice(0, 100).map((sym) => (
                          <div
                            key={`${sym.file_path}::${sym.qualified}`}
                            onClick={() => {
                              setSelectedSymbol(sym);
                              setSelectedRoute(undefined);
                            }}
                            className={`p-2.5 rounded-lg border flex items-center justify-between gap-3 cursor-pointer transition-all ${
                              selectedSymbol?.qualified === sym.qualified
                                ? 'bg-[#5E6AD2]/20 border-[#5E6AD2] ring-1 ring-[#5E6AD2]/50'
                                : 'bg-[#0D0D10] border-[#1F1F23] hover:border-zinc-700'
                            }`}
                          >
                            <div className="min-w-0">
                              <span className="text-xs font-semibold text-zinc-100 truncate block">{shortSymbolName(sym.qualified)}()</span>
                              <span className="text-[9px] text-zinc-500 truncate block">{sym.file_path}:{sym.line_number}</span>
                            </div>

                            <div className="flex items-center gap-2 shrink-0 text-[10px]">
                              <span className="text-emerald-400 font-bold">{sym.fan_in} caller{sym.fan_in === 1 ? '' : 's'}</span>
                              <span className="text-[8px] bg-[#08080A] text-zinc-400 border border-[#1F1F23] px-1.5 py-0.5 rounded uppercase font-bold">
                                {sym.api_kind}
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* ── VIEW: INTERNAL ────────────────────────────────────────── */}
              {activeView === 'internal' && (
                <div className="space-y-4">
                  <div className="flex items-center justify-between pb-1 border-b border-[#1F1F23] text-xs">
                    <span className="font-bold text-zinc-300 uppercase">Internal Implementation Surface</span>
                    <span className="text-zinc-500 text-[10px]">{internalSyms.length.toLocaleString()} package-private symbols</span>
                  </div>

                  <p className="text-[10px] text-zinc-400 font-sans italic">
                    Not part of the published contract — these symbols are reachable within the package but are not intended for external consumers.
                  </p>

                  {/* Heavily Consumed Internals */}
                  <div className="space-y-2">
                    <span className="text-[9px] font-bold text-zinc-400 uppercase tracking-wider block">
                      Implementation Hubs & Shared Internals
                    </span>
                    <div className="space-y-1.5">
                      {internalSyms.slice(0, 5).map((sym) => (
                        <div
                          key={`${sym.file_path}::${sym.qualified}`}
                          onClick={() => {
                            setSelectedSymbol(sym);
                            setSelectedRoute(undefined);
                          }}
                          className={`p-2.5 rounded-lg border flex items-center justify-between gap-3 cursor-pointer transition-all ${
                            selectedSymbol?.qualified === sym.qualified
                              ? 'bg-[#5E6AD2]/20 border-[#5E6AD2] ring-1 ring-[#5E6AD2]/50'
                              : 'bg-[#0D0D10] border-[#1F1F23] hover:border-zinc-700'
                          }`}
                        >
                          <div className="min-w-0">
                            <span className="text-xs font-semibold text-zinc-200 truncate block">{shortSymbolName(sym.qualified)}()</span>
                            <span className="text-[9px] text-zinc-500 truncate block">{sym.file_path}:{sym.line_number}</span>
                          </div>

                          <div className="flex items-center gap-2 shrink-0 text-[10px]">
                            <span className="text-zinc-300 font-bold">{sym.fan_in} caller{sym.fan_in === 1 ? '' : 's'}</span>
                            <span className="text-[8px] bg-[#08080A] text-zinc-400 border border-[#1F1F23] px-1.5 py-0.5 rounded uppercase font-bold">
                              {sym.api_kind}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Progressive Disclosure for Deep Internal Inventory */}
                  <div className="pt-3 border-t border-[#1F1F23] space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-[9px] font-bold text-zinc-400 uppercase tracking-wider">
                        Internal Inventory
                      </span>
                      <button
                        onClick={() => setShowAllInternal((p) => !p)}
                        className="text-[10px] font-bold text-indigo-400 hover:text-indigo-300 uppercase flex items-center gap-1"
                      >
                        {showAllInternal ? 'Hide Full Inventory' : `View Complete Internal Inventory (${filteredInternalSymbols.length.toLocaleString()} Symbols)`}
                        {showAllInternal ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                      </button>
                    </div>

                    {showAllInternal && (
                      <div className="space-y-1.5 max-h-96 overflow-y-auto">
                        {filteredInternalSymbols.slice(0, 100).map((sym) => (
                          <div
                            key={`${sym.file_path}::${sym.qualified}`}
                            onClick={() => {
                              setSelectedSymbol(sym);
                              setSelectedRoute(undefined);
                            }}
                            className={`p-2.5 rounded-lg border flex items-center justify-between gap-3 cursor-pointer transition-all ${
                              selectedSymbol?.qualified === sym.qualified
                                ? 'bg-[#5E6AD2]/20 border-[#5E6AD2] ring-1 ring-[#5E6AD2]/50'
                                : 'bg-[#0D0D10] border-[#1F1F23] hover:border-zinc-700'
                            }`}
                          >
                            <div className="min-w-0">
                              <span className="text-xs font-semibold text-zinc-200 truncate block">{shortSymbolName(sym.qualified)}()</span>
                              <span className="text-[9px] text-zinc-500 truncate block">{sym.file_path}:{sym.line_number}</span>
                            </div>

                            <div className="flex items-center gap-2 shrink-0 text-[10px]">
                              <span className="text-zinc-300 font-bold">{sym.fan_in} caller{sym.fan_in === 1 ? '' : 's'}</span>
                              <span className="text-[8px] bg-[#08080A] text-zinc-400 border border-[#1F1F23] px-1.5 py-0.5 rounded uppercase font-bold">
                                {sym.api_kind}
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* ── VIEW: ISSUES ──────────────────────────────────────────── */}
              {activeView === 'issues' && (
                <div className="space-y-6">
                  {/* Deprecated */}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between pb-1 border-b border-[#1F1F23]">
                      <span className="text-xs font-bold text-rose-400 uppercase flex items-center gap-1.5">
                        <AlertTriangle className="h-3.5 w-3.5" /> Deprecated Interfaces ({deprecatedSyms.length})
                      </span>
                    </div>

                    {deprecatedSyms.length === 0 ? (
                      <p className="text-xs text-zinc-400 italic p-2.5 bg-[#0D0D10] border border-[#1F1F23] rounded">
                        No explicitly deprecated APIs were detected in the indexed repository.
                      </p>
                    ) : (
                      <div className="space-y-2">
                        {deprecatedSyms.map((sym) => (
                          <div
                            key={`${sym.file_path}::${sym.qualified}`}
                            className="p-3 bg-[#0D0D10] border border-rose-500/40 rounded-lg space-y-1.5 text-xs"
                          >
                            <div className="flex items-center justify-between">
                              <span className="font-bold text-zinc-100">{shortSymbolName(sym.qualified)}()</span>
                              <span className="text-[8px] bg-rose-950/40 text-rose-300 border border-rose-500/40 px-1.5 py-0.5 rounded font-bold uppercase">
                                [VERIFIED DEPRECATED]
                              </span>
                            </div>
                            <p className="text-[10px] text-zinc-400 font-sans">
                              Explicitly marked deprecated in source code annotations or docstrings.
                            </p>
                            <div className="pt-1 flex items-center justify-between border-t border-[#1F1F23]">
                              <span className="text-[9px] text-zinc-500">{sym.file_path}:{sym.line_number}</span>
                              <button
                                onClick={() => {
                                  setSelectedSymbol(sym);
                                  setSelectedRoute(undefined);
                                }}
                                className="text-[9px] font-bold text-rose-400 hover:text-rose-300 uppercase"
                              >
                                Inspect Deprecation →
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* No Internal Callers with Mandatory Caveat */}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between pb-1 border-b border-[#1F1F23]">
                      <span className="text-xs font-bold text-amber-400 uppercase flex items-center gap-1.5">
                        <Info className="h-3.5 w-3.5" /> Public Symbols With No Internal Callers ({orphanSyms.length})
                      </span>
                    </div>

                    <div className="p-2.5 bg-amber-950/20 border border-amber-500/30 rounded text-xs text-amber-200/90 font-sans leading-relaxed">
                      No repository-internal callers were detected. This does NOT prove that the symbol is unused because external consumers cannot be inferred from static repository analysis.
                    </div>

                    {orphanSyms.length === 0 ? (
                      <p className="text-xs text-zinc-400 italic p-2.5 bg-[#0D0D10] border border-[#1F1F23] rounded">
                        All public APIs have at least one internal caller detected in the indexed call graph.
                      </p>
                    ) : (
                      <div className="space-y-1.5 max-h-72 overflow-y-auto">
                        {orphanSyms.slice(0, 40).map((sym) => (
                          <div
                            key={`${sym.file_path}::${sym.qualified}`}
                            onClick={() => {
                              setSelectedSymbol(sym);
                              setSelectedRoute(undefined);
                            }}
                            className={`p-2.5 bg-[#0D0D10] border border-amber-500/30 hover:border-amber-500 rounded-lg flex items-center justify-between cursor-pointer transition-colors ${
                              selectedSymbol?.qualified === sym.qualified ? 'ring-1 ring-amber-500/50' : ''
                            }`}
                          >
                            <div className="min-w-0">
                              <span className="text-xs font-bold text-zinc-100 truncate block">{shortSymbolName(sym.qualified)}()</span>
                              <span className="text-[9px] text-zinc-500 truncate block">{sym.file_path}:{sym.line_number}</span>
                            </div>
                            <span className="text-[8px] bg-amber-950/40 text-amber-300 border border-amber-500/40 px-1.5 py-0.5 rounded font-bold uppercase">
                              No Callers
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* ── 6. API Contract & Impact Inspector Drawer ────────────────── */}
            {selectedSymbol && (
              <ApiContractInspector
                symbol={selectedSymbol}
                routeInfo={selectedRoute}
                allSymbols={allSymbols}
                repoName={repoName}
                onClose={() => {
                  setSelectedSymbol(null);
                  setSelectedRoute(undefined);
                }}
                onSelectSymbol={(s) => setSelectedSymbol(s)}
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default APISurfaceAnalyzer;
