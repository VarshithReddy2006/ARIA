/**
 * DeadCodeAnalyzer — ARIA Dead Code & Reachability Intelligence Workspace
 *
 * 10/10 PRODUCTION UI/UX DESIGN SYSTEM:
 * - Canvas & Glass Cards: Deep Obsidian bg-gradient-to-b from-[#0D1220]/90 to-[#070A12]/95 border-white/[0.08]
 * - Electric Indigo / Violet: #6366F1 / #818CF8 (Primary Brand & Accent Glows)
 * - Emerald Vitality: #10B981 / #34D399 (Safe, High Confidence, Health)
 * - Luminous Amber: #FFB800 / #FCD34D (Unused Files, Review, Warnings)
 * - Orchid / Purple: #A855F7 / #C084FC (Orphan Modules & Dependency Chains)
 * - Vivid Rose: #FF4D6D / #FF758F (High Risk, Breaking, Removal Alerts)
 */

import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { apiUrl, extractErrorMessage } from '../../lib/api';
import {
  AlertTriangle, ArrowRight, Loader2, RefreshCw, Search, X,
  Layers, Sparkles, Copy, Check, Info, FileCode, SlidersHorizontal,
  Trash2, ArrowUpRight, HelpCircle, Plus, ShieldCheck, AlertCircle,
  GitBranch, Terminal, ShieldAlert
} from 'lucide-react';
import { PrerequisitesBanner } from './pr/PrerequisitesBanner';
import { usePrerequisites } from './pr/usePrerequisites';
import { SkeletonCard, SkeletonGroup } from '../ui/Skeleton';
import { FilePath } from '../ui/FilePath';

// ── Types ───────────────────────────────────────────────────────────────────

export interface DeadFile {
  file_path: string;
  confidence: number;
  risk_level: string;
  recommendation: string;
}

export interface OrphanModule {
  file_path: string;
  confidence: number;
  risk_level: string;
  recommendation: string;
  last_reachable_parent?: string | null;
}

export interface DeadDependencyChain {
  chain: string[];
  confidence: number;
  risk_level: string;
  recommendation: string;
  length: number;
  total_nodes: number;
  max_centrality: number;
}

export interface DeadCodeResult {
  repo: string;
  cleanup_score: number;
  previous_cleanup_score?: number;
  estimated_cleanup_effort: string;
  unused_files: DeadFile[];
  orphan_modules: OrphanModule[];
  dead_dependency_chains: DeadDependencyChain[];
  cleanup_recommendations: string[];
  analyzed_at: string;
}

export interface NormalizedFinding {
  id: string;
  type: 'unused_file' | 'orphan_module' | 'dead_chain';
  typeLabel: string;
  filePath: string;
  fileName: string;
  confidence: number;
  riskLevel: 'SAFE' | 'REVIEW' | 'HIGH RISK';
  recommendation: string;
  lastReachableParent?: string | null;
  chain?: string[];
  totalNodes?: number;
  maxCentrality?: number;
}

interface Props {
  repoName?: string;
}

type FilterCategory = 'ALL' | 'UNUSED' | 'ORPHANS' | 'CHAINS' | 'HIGH_CONFIDENCE' | 'REVIEW_REQUIRED';
type SortOption = 'CONFIDENCE_DESC' | 'RISK_DESC' | 'PATH_ASC';

const INITIAL_BATCH_SIZE = 8;
const BATCH_INCREMENT = 8;

// ── Utility Helpers ─────────────────────────────────────────────────────────

function resolveRepo(repoName?: string): string {
  if (repoName) return repoName;
  if (typeof window !== 'undefined') {
    const urlParams = new URLSearchParams(window.location.search);
    const owner = urlParams.get('owner');
    const repo = urlParams.get('repo');
    if (owner && repo) return `${owner}/${repo}`;
    const stored = localStorage.getItem('activeRepo');
    if (stored) return stored;
  }
  return '';
}

function normalizeRisk(risk: string): 'SAFE' | 'REVIEW' | 'HIGH RISK' {
  const r = (risk || '').toUpperCase();
  if (r.includes('HIGH') || r.includes('CRITICAL') || r.includes('DANGER')) return 'HIGH RISK';
  if (r.includes('REVIEW') || r.includes('MED') || r.includes('MODERATE')) return 'REVIEW';
  return 'SAFE';
}

/** Classification-specific styling tokens with modern saturated dark glass colors */
function classificationTokens(type: 'unused_file' | 'orphan_module' | 'dead_chain') {
  switch (type) {
    case 'unused_file':
      return {
        color: '#FCD34D',
        bg: 'bg-[#FFB800]/12',
        border: 'border-[#FFB800]/30',
        dot: 'bg-[#FFB800] shadow-[0_0_8px_rgba(255,184,0,0.6)]',
        text: 'text-[#FCD34D]',
        label: 'UNUSED FILE',
      };
    case 'orphan_module':
      return {
        color: '#C084FC',
        bg: 'bg-[#A855F7]/12',
        border: 'border-[#A855F7]/30',
        dot: 'bg-[#C084FC] shadow-[0_0_8px_rgba(192,132,252,0.6)]',
        text: 'text-[#C084FC]',
        label: 'ORPHANED MODULE',
      };
    case 'dead_chain':
      return {
        color: '#E879F9',
        bg: 'bg-[#D946EF]/12',
        border: 'border-[#D946EF]/30',
        dot: 'bg-[#E879F9] shadow-[0_0_8px_rgba(232,121,249,0.6)]',
        text: 'text-[#E879F9]',
        label: 'ORPHAN CHAIN',
      };
  }
}

/** Confidence specific coloring */
function confidenceColor(val: number): string {
  if (val >= 0.85) return 'text-[#34D399]';
  if (val >= 0.60) return 'text-[#FCD34D]';
  return 'text-[#FF758F]';
}

/** Risk indicator tokens */
function riskIndicator(risk: 'SAFE' | 'REVIEW' | 'HIGH RISK') {
  switch (risk) {
    case 'SAFE':
      return {
        dot: 'bg-[#34D399] shadow-[0_0_6px_rgba(52,211,153,0.6)]',
        text: 'text-[#34D399]',
        border: 'border-[#10B981]/30',
        bg: 'bg-[#10B981]/12',
        label: 'SAFE',
      };
    case 'REVIEW':
      return {
        dot: 'bg-[#FCD34D] shadow-[0_0_6px_rgba(252,211,77,0.6)]',
        text: 'text-[#FCD34D]',
        border: 'border-[#FFB800]/30',
        bg: 'bg-[#FFB800]/12',
        label: 'REVIEW',
      };
    case 'HIGH RISK':
      return {
        dot: 'bg-[#FF758F] shadow-[0_0_6px_rgba(255,117,143,0.6)]',
        text: 'text-[#FF758F]',
        border: 'border-[#FF4D6D]/30',
        bg: 'bg-[#FF4D6D]/12',
        label: 'HIGH RISK',
      };
  }
}

function openInGraph(repoSlug: string, path: string) {
  const [owner, repo] = repoSlug.split('/');
  window.dispatchEvent(
    new CustomEvent('aria-open-graph', {
      detail: { owner, repo, path, file: path, source: 'dead-code' },
    })
  );
}

function openInChat(repoSlug: string, path: string, prompt: string) {
  const [owner, repo] = repoSlug.split('/');
  window.dispatchEvent(
    new CustomEvent('aria-open-chat', {
      detail: { owner, repo, path, file: path, prompt, source: 'dead-code' },
    })
  );
}

const PATH_RE = /([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)/;

function splitRecommendation(text: string): { action: string; path: string | null; rest: string } {
  const colon = text.indexOf(':');
  const action = colon > 0 ? text.slice(0, colon).trim() : text.trim();
  const remainder = colon > 0 ? text.slice(colon + 1).trim() : '';
  const match = PATH_RE.exec(remainder) || (colon > 0 ? null : PATH_RE.exec(text));
  const path = match ? match[1] : null;
  const rest = path ? remainder.replace(path, '').replace(/^[\s·—-]+/, '').trim() : remainder;
  return { action, path, rest };
}

// ── Main Component ─────────────────────────────────────────────────────────

export const DeadCodeAnalyzer: React.FC<Props> = ({ repoName }) => {
  const [activeRepo, setActiveRepo] = useState(() => resolveRepo(repoName));
  const { healthStatus, hasPrerequisites, isRepairing, repair } = usePrerequisites(activeRepo);

  const [isLoading, setIsLoading] = useState(false);
  const [analyzerResult, setAnalyzerResult] = useState<DeadCodeResult | null>(null);
  const [errorMsg, setErrorMsg] = useState('');

  // Interactive UI State
  const [searchQuery, setSearchQuery] = useState('');
  const [activeFilter, setActiveFilter] = useState<FilterCategory>('ALL');
  const [sortOption, setSortOption] = useState<SortOption>('CONFIDENCE_DESC');
  const [selectedFindingId, setSelectedFindingId] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Progressive Disclosure Window State
  const [visibleCount, setVisibleCount] = useState<number>(INITIAL_BATCH_SIZE);

  const inspectorRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  // Keyboard Shortcuts: '/' to focus search, 'Escape' to clear
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (
        e.key === '/' &&
        document.activeElement !== searchInputRef.current &&
        !(document.activeElement instanceof HTMLInputElement || document.activeElement instanceof HTMLTextAreaElement)
      ) {
        e.preventDefault();
        searchInputRef.current?.focus();
      } else if (e.key === 'Escape') {
        if (searchQuery) {
          setSearchQuery('');
          setVisibleCount(INITIAL_BATCH_SIZE);
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [searchQuery]);

  // Sync activeRepo with repoName prop changes
  useEffect(() => {
    const nextRepo = resolveRepo(repoName);
    if (nextRepo !== activeRepo) {
      setActiveRepo(nextRepo);
      setAnalyzerResult(null);
      setErrorMsg('');
      setSelectedFindingId(null);
      setVisibleCount(INITIAL_BATCH_SIZE);
    }
  }, [repoName, activeRepo]);

  // Execute Dead Code Analysis
  const handleRunAnalysis = useCallback(async () => {
    if (!activeRepo) {
      setErrorMsg('No active repository loaded.');
      return;
    }
    const [owner, repo] = activeRepo.split('/');
    if (!owner || !repo) {
      setErrorMsg('Invalid repository identifier.');
      return;
    }

    setIsLoading(true);
    setErrorMsg('');

    try {
      const res = await fetch(apiUrl('/api/v1/dead-code/analyze'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ owner, repo }),
      });
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(extractErrorMessage(errorData) || `Analysis failed with status ${res.status}`);
      }
      const data: DeadCodeResult = await res.json();
      setAnalyzerResult(data);
      setVisibleCount(INITIAL_BATCH_SIZE);
    } catch (err: any) {
      setErrorMsg(extractErrorMessage(err));
    } finally {
      setIsLoading(false);
    }
  }, [activeRepo]);

  // Auto-run analysis on mount if repo is present and not yet analyzed
  useEffect(() => {
    if (activeRepo && !analyzerResult && !isLoading && !errorMsg) {
      handleRunAnalysis();
    }
  }, [activeRepo]);

  // Normalize all findings into unified list
  const allFindings = useMemo<NormalizedFinding[]>(() => {
    if (!analyzerResult) return [];

    const list: NormalizedFinding[] = [];

    // 1. Unused Files
    (analyzerResult.unused_files || []).forEach((file, idx) => {
      const parts = file.file_path.split('/');
      list.push({
        id: `unused-${idx}`,
        type: 'unused_file',
        typeLabel: 'UNUSED FILE',
        filePath: file.file_path,
        fileName: parts[parts.length - 1] || file.file_path,
        confidence: file.confidence,
        riskLevel: normalizeRisk(file.risk_level),
        recommendation: file.recommendation,
      });
    });

    // 2. Orphan Modules
    (analyzerResult.orphan_modules || []).forEach((mod, idx) => {
      const parts = mod.file_path.split('/');
      list.push({
        id: `orphan-${idx}`,
        type: 'orphan_module',
        typeLabel: 'ORPHANED MODULE',
        filePath: mod.file_path,
        fileName: parts[parts.length - 1] || mod.file_path,
        confidence: mod.confidence,
        riskLevel: normalizeRisk(mod.risk_level),
        recommendation: mod.recommendation,
        lastReachableParent: mod.last_reachable_parent,
      });
    });

    // 3. Dead Dependency Chains
    (analyzerResult.dead_dependency_chains || []).forEach((chainItem, idx) => {
      const rootPath = chainItem.chain[0] || 'unknown-chain';
      const parts = rootPath.split('/');
      list.push({
        id: `chain-${idx}`,
        type: 'dead_chain',
        typeLabel: 'ORPHAN CHAIN',
        filePath: rootPath,
        fileName: parts[parts.length - 1] || rootPath,
        confidence: chainItem.confidence,
        riskLevel: normalizeRisk(chainItem.risk_level),
        recommendation: chainItem.recommendation,
        chain: chainItem.chain,
        totalNodes: chainItem.total_nodes,
        maxCentrality: chainItem.max_centrality,
      });
    });

    return list;
  }, [analyzerResult]);

  // Filter and sort entire finding dataset
  const filteredFindings = useMemo(() => {
    let result = [...allFindings];

    // 1. Filter Category
    if (activeFilter === 'UNUSED') {
      result = result.filter((f) => f.type === 'unused_file');
    } else if (activeFilter === 'ORPHANS') {
      result = result.filter((f) => f.type === 'orphan_module');
    } else if (activeFilter === 'CHAINS') {
      result = result.filter((f) => f.type === 'dead_chain');
    } else if (activeFilter === 'HIGH_CONFIDENCE') {
      result = result.filter((f) => f.confidence >= 0.85);
    } else if (activeFilter === 'REVIEW_REQUIRED') {
      result = result.filter((f) => f.riskLevel !== 'SAFE');
    }

    // 2. Search Query
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      result = result.filter((f) => {
        return (
          f.filePath.toLowerCase().includes(q) ||
          f.fileName.toLowerCase().includes(q) ||
          f.recommendation.toLowerCase().includes(q) ||
          (f.chain && f.chain.some((c) => c.toLowerCase().includes(q)))
        );
      });
    }

    // 3. Sorting
    if (sortOption === 'CONFIDENCE_DESC') {
      result.sort((a, b) => b.confidence - a.confidence);
    } else if (sortOption === 'RISK_DESC') {
      const weight = { 'HIGH RISK': 3, REVIEW: 2, SAFE: 1 };
      result.sort((a, b) => weight[b.riskLevel] - weight[a.riskLevel]);
    } else if (sortOption === 'PATH_ASC') {
      result.sort((a, b) => a.filePath.localeCompare(b.filePath));
    }

    return result;
  }, [allFindings, activeFilter, searchQuery, sortOption]);

  // Progressive Disclosure:
  const isSearching = searchQuery.trim().length > 0;
  const visibleFindings = useMemo(() => {
    if (isSearching) return filteredFindings;
    return filteredFindings.slice(0, visibleCount);
  }, [filteredFindings, visibleCount, isSearching]);

  // Synchronize selection safely to a visible finding
  useEffect(() => {
    if (visibleFindings.length > 0) {
      if (!selectedFindingId || !visibleFindings.some((f) => f.id === selectedFindingId)) {
        setSelectedFindingId(visibleFindings[0].id);
      }
    } else {
      setSelectedFindingId(null);
    }
  }, [visibleFindings, selectedFindingId]);

  const selectedFinding = useMemo(() => {
    if (!selectedFindingId) return null;
    return visibleFindings.find((f) => f.id === selectedFindingId) || null;
  }, [visibleFindings, selectedFindingId]);

  // Filter handler (resets visible window to 8)
  const handleFilterChange = (filter: FilterCategory) => {
    setActiveFilter(filter);
    setVisibleCount(INITIAL_BATCH_SIZE);
  };

  // Sort handler (resets visible window to 8)
  const handleSortChange = (sort: SortOption) => {
    setSortOption(sort);
    setVisibleCount(INITIAL_BATCH_SIZE);
  };

  // Clear search handler (resets visible window to 8)
  const handleClearSearch = () => {
    setSearchQuery('');
    setVisibleCount(INITIAL_BATCH_SIZE);
  };

  // Copy helper
  const handleCopyPath = (e: React.MouseEvent, path: string, id: string) => {
    e.stopPropagation();
    if (typeof navigator !== 'undefined' && navigator.clipboard) {
      navigator.clipboard.writeText(path);
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 1500);
    }
  };

  // Select finding handler
  const handleSelectFinding = (finding: NormalizedFinding) => {
    setSelectedFindingId(finding.id);
    if (window.innerWidth < 1024 && inspectorRef.current) {
      inspectorRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  // Human-readable sort descriptor
  const sortDescriptor = useMemo(() => {
    switch (sortOption) {
      case 'CONFIDENCE_DESC': return 'CONFIDENCE · HIGH → LOW';
      case 'RISK_DESC': return 'RISK · HIGH → LOW';
      case 'PATH_ASC': return 'PATH · A → Z';
    }
  }, [sortOption]);

  // Metric counts
  const highConfidenceCount = useMemo(() => allFindings.filter((f) => f.confidence >= 0.85).length, [allFindings]);
  const reviewRequiredCount = useMemo(() => allFindings.filter((f) => f.riskLevel !== 'SAFE').length, [allFindings]);

  return (
    <div className="flex flex-col text-[#F5F7FA] min-w-0 space-y-6 font-sans">
      {/* ── 1. DEAD CODE WORKSPACE HEADER & EXECUTIVE METRIC RAIL ─────────── */}
      <header className="min-w-0 pb-5 border-b border-white/[0.08] space-y-5">
        <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4">
          <div className="min-w-0 max-w-2xl space-y-1.5">
            <div className="flex items-center gap-2">
              <span className="text-[10.5px] font-bold text-[#818CF8] uppercase tracking-widest font-mono flex items-center gap-1.5">
                <Trash2 className="h-3.5 w-3.5 text-[#818CF8]" />
                DEAD CODE / REACHABILITY INTELLIGENCE
              </span>
              <span className="h-1 w-1 rounded-full bg-white/30" />
              <span className="text-[9.5px] font-mono text-[#34D399] bg-[#10B981]/10 border border-[#10B981]/25 px-2 py-0.5 rounded-full uppercase tracking-wider flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-[#34D399] shadow-[0_0_6px_rgba(52,211,153,0.8)]" />
                STATIC ANALYSIS SNAPSHOT
              </span>
            </div>
            <h2 className="text-xl sm:text-2xl lg:text-3xl font-extrabold text-[#F8FAFC] tracking-tight font-mono">
              WHAT CODE APPEARS UNREACHABLE OR UNUSED?
            </h2>
            <p className="text-xs sm:text-[13px] text-[#94A3B8] leading-relaxed max-w-xl font-sans">
              Investigate unconsumed files, isolated subgraphs, and safe dependency chain prune targets using static reachability evidence.
            </p>
          </div>

          <button
            type="button"
            onClick={handleRunAnalysis}
            disabled={isLoading || !activeRepo}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-gradient-to-r from-[#6366F1] to-[#4F46E5] hover:from-[#818CF8] hover:to-[#6366F1] active:scale-[0.98] border border-indigo-400/30 text-white text-xs font-bold font-mono transition-all shadow-[0_0_20px_rgba(99,102,241,0.25)] self-start lg:self-auto disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#818CF8]/50"
          >
            {isLoading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                <span>AUDITING GRAPH…</span>
              </>
            ) : (
              <>
                <RefreshCw className="h-4 w-4" aria-hidden="true" />
                <span>{analyzerResult ? 'RE-RUN AUDIT' : 'RUN AUDIT'}</span>
              </>
            )}
          </button>
        </div>

        {/* Executive Continuous Metric Rail (Vibrant Elevated Glass Cards) */}
        {analyzerResult && (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 pt-1">
            {/* UNUSED FILES */}
            <div className="p-4 rounded-xl bg-gradient-to-b from-[#0D1220]/90 to-[#070A12]/95 border border-white/[0.08] hover:border-[#FFB800]/40 transition-all shadow-md relative overflow-hidden group">
              <div className="absolute top-0 inset-x-0 h-0.5 bg-gradient-to-r from-transparent via-[#FFB800]/40 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
              <div className="space-y-1">
                <span className="text-2xl sm:text-3xl font-extrabold font-mono text-[#FCD34D] block leading-none">
                  {analyzerResult.unused_files?.length || 0}
                </span>
                <span className="text-[10px] font-bold text-[#94A3B8] uppercase tracking-wider font-mono block">
                  UNUSED FILES
                </span>
              </div>
              <span className="text-[11px] text-[#64748B] block font-sans mt-2">
                In-degree = 0 · no callers
              </span>
            </div>

            {/* ORPHAN CANDIDATES */}
            <div className="p-4 rounded-xl bg-gradient-to-b from-[#0D1220]/90 to-[#070A12]/95 border border-white/[0.08] hover:border-[#C084FC]/40 transition-all shadow-md relative overflow-hidden group">
              <div className="absolute top-0 inset-x-0 h-0.5 bg-gradient-to-r from-transparent via-[#C084FC]/40 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
              <div className="space-y-1">
                <span className="text-2xl sm:text-3xl font-extrabold font-mono text-[#C084FC] block leading-none">
                  {analyzerResult.orphan_modules?.length || 0}
                </span>
                <span className="text-[10px] font-bold text-[#94A3B8] uppercase tracking-wider font-mono block">
                  ORPHAN CANDIDATES
                </span>
              </div>
              <span className="text-[11px] text-[#64748B] block font-sans mt-2">
                Isolated from entry points
              </span>
            </div>

            {/* ORPHAN CHAINS */}
            <div className="p-4 rounded-xl bg-gradient-to-b from-[#0D1220]/90 to-[#070A12]/95 border border-white/[0.08] hover:border-[#E879F9]/40 transition-all shadow-md relative overflow-hidden group">
              <div className="absolute top-0 inset-x-0 h-0.5 bg-gradient-to-r from-transparent via-[#E879F9]/40 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
              <div className="space-y-1">
                <span className="text-2xl sm:text-3xl font-extrabold font-mono text-[#E879F9] block leading-none">
                  {analyzerResult.dead_dependency_chains?.length || 0}
                </span>
                <span className="text-[10px] font-bold text-[#94A3B8] uppercase tracking-wider font-mono block">
                  ORPHAN CHAINS
                </span>
              </div>
              <span className="text-[11px] text-[#64748B] block font-sans mt-2">
                Prunable chain units (&ge;2)
              </span>
            </div>

            {/* HIGH CONFIDENCE */}
            <div className="p-4 rounded-xl bg-gradient-to-b from-[#0D1220]/90 to-[#070A12]/95 border border-white/[0.08] hover:border-[#34D399]/40 transition-all shadow-md relative overflow-hidden group">
              <div className="absolute top-0 inset-x-0 h-0.5 bg-gradient-to-r from-transparent via-[#34D399]/40 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
              <div className="space-y-1">
                <span className="text-2xl sm:text-3xl font-extrabold font-mono text-[#34D399] block leading-none">
                  {highConfidenceCount}
                </span>
                <span className="text-[10px] font-bold text-[#94A3B8] uppercase tracking-wider font-mono block">
                  HIGH CONFIDENCE
                </span>
              </div>
              <span className="text-[11px] text-[#64748B] block font-sans mt-2">
                &ge;85% static proof
              </span>
            </div>

            {/* CLEANUP PRIORITY */}
            <div className="p-4 rounded-xl bg-gradient-to-b from-[#0D1220]/90 to-[#070A12]/95 border border-white/[0.08] hover:border-[#818CF8]/40 transition-all shadow-md relative overflow-hidden group">
              <div className="absolute top-0 inset-x-0 h-0.5 bg-gradient-to-r from-transparent via-[#818CF8]/40 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
              <div className="space-y-1">
                <div className="flex items-baseline gap-1">
                  <span className={`text-2xl sm:text-3xl font-extrabold font-mono block leading-none ${analyzerResult.cleanup_score === 0 ? 'text-[#FCD34D]' : 'text-[#34D399]'}`}>
                    {analyzerResult.cleanup_score}
                  </span>
                  <span className="text-[11px] font-mono text-[#64748B]">/100</span>
                </div>
                <span className="text-[10px] font-bold text-[#94A3B8] uppercase tracking-wider font-mono block">
                  CLEANUP PRIORITY
                </span>
              </div>
              <span className="text-[11px] text-[#64748B] block font-sans mt-2">
                {analyzerResult.cleanup_score === 0
                  ? `Reachability debt (${allFindings.length})`
                  : 'Measured health score'}
              </span>
            </div>

            {/* ESTIMATED EFFORT */}
            <div className="p-4 rounded-xl bg-gradient-to-b from-[#0D1220]/90 to-[#070A12]/95 border border-white/[0.08] hover:border-[#FFB800]/40 transition-all shadow-md relative overflow-hidden group">
              <div className="absolute top-0 inset-x-0 h-0.5 bg-gradient-to-r from-transparent via-[#FFB800]/40 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-[#FFB800] shadow-[0_0_8px_rgba(255,184,0,0.8)]" />
                  <span className="text-2xl sm:text-3xl font-extrabold font-mono uppercase text-[#FCD34D] block leading-none">
                    {analyzerResult.estimated_cleanup_effort || 'HIGH'}
                  </span>
                </div>
                <span className="text-[10px] font-bold text-[#94A3B8] uppercase tracking-wider font-mono block">
                  ESTIMATED EFFORT
                </span>
              </div>
              <span className="text-[11px] text-[#64748B] block font-sans mt-2">
                Candidate volume + impact
              </span>
            </div>
          </div>
        )}

        {!hasPrerequisites && healthStatus && (
          <div className="mt-2">
            <PrerequisitesBanner
              activeRepo={activeRepo}
              healthStatus={healthStatus}
              onRepair={repair}
              isRepairing={isRepairing}
            />
          </div>
        )}
      </header>

      {/* ── 2. EPISTEMIC / EVIDENCE NOTICE ────────────────────────────────── */}
      <div className="p-4 sm:p-5 rounded-xl bg-gradient-to-r from-[#FFB800]/12 via-[#FFB800]/6 to-transparent border border-[#FFB800]/30 shadow-lg flex items-start gap-3.5 relative overflow-hidden">
        <div className="absolute top-0 left-0 w-1 h-full bg-[#FFB800]" />
        <Info className="h-5 w-5 text-[#FFB800] shrink-0 mt-0.5" aria-hidden="true" />
        <div className="text-xs space-y-1.5 font-sans min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-mono font-bold text-[11px] text-[#FCD34D] uppercase tracking-wider">
              STATIC REACHABILITY &ne; PROOF OF UNUSED CODE
            </span>
            <span className="text-[10px] font-mono text-[#94A3B8] hidden sm:inline">
              · EVIDENCE GUIDANCE
            </span>
          </div>
          <p className="text-[#CBD5E1] leading-relaxed text-[12px]">
            Static analysis can establish repository reachability, but cannot prove: <span className="text-white font-mono text-[11px] bg-white/5 px-1 py-0.5 rounded border border-white/10">runtime discovery</span>, <span className="text-white font-mono text-[11px] bg-white/5 px-1 py-0.5 rounded border border-white/10">reflection</span>, <span className="text-white font-mono text-[11px] bg-white/5 px-1 py-0.5 rounded border border-white/10">dynamic imports</span>, <span className="text-white font-mono text-[11px] bg-white/5 px-1 py-0.5 rounded border border-white/10">framework routing</span>, <span className="text-white font-mono text-[11px] bg-white/5 px-1 py-0.5 rounded border border-white/10">runtime configuration</span>, or <span className="text-white font-mono text-[11px] bg-white/5 px-1 py-0.5 rounded border border-white/10">external package consumption</span>.
          </p>
          <div className="text-[10.5px] font-mono font-bold text-[#FCD34D] uppercase tracking-wider pt-0.5 flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-[#FFB800] animate-ping" />
            VERIFY BEFORE REMOVAL.
          </div>
        </div>
      </div>

      {/* ── ERROR STATE ────────────────────────────────────────────────────── */}
      {errorMsg && (
        <div
          role="alert"
          className="p-4 rounded-xl border border-[#FF4D6D]/40 bg-gradient-to-r from-[#FF4D6D]/15 to-[#FF4D6D]/5 flex items-start gap-3.5 text-xs shadow-lg"
        >
          <AlertTriangle className="h-5 w-5 text-[#FF4D6D] shrink-0 mt-0.5" aria-hidden="true" />
          <div className="space-y-1.5 font-mono">
            <span className="font-bold text-[#FF758F] block text-sm">REACHABILITY AUDIT FAILED</span>
            <p className="text-[#E2E8F0] font-sans leading-relaxed text-xs">{errorMsg}</p>
            <button
              type="button"
              onClick={handleRunAnalysis}
              className="mt-2 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#FF4D6D]/20 hover:bg-[#FF4D6D]/30 text-[#FF758F] border border-[#FF4D6D]/40 text-xs font-bold uppercase transition-colors"
            >
              Retry Audit
            </button>
          </div>
        </div>
      )}

      {/* ── LOADING STATE ──────────────────────────────────────────────────── */}
      {isLoading && (
        <div className="space-y-4 font-mono select-none py-6">
          <div className="flex items-center gap-3">
            <RefreshCw className="h-5 w-5 text-[#818CF8] animate-spin" aria-hidden="true" />
            <span className="text-xs sm:text-sm font-bold text-[#F8FAFC] uppercase tracking-widest">
              AUDITING REPOSITORY CALL GRAPH &amp; AST REACHABILITY…
            </span>
          </div>
          <SkeletonGroup label="Running reachability sweep">
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
              <div className="lg:col-span-8 space-y-3">
                <SkeletonCard /><SkeletonCard /><SkeletonCard />
              </div>
              <div className="lg:col-span-4 space-y-3">
                <SkeletonCard /><SkeletonCard />
              </div>
            </div>
          </SkeletonGroup>
        </div>
      )}

      {/* ── CASE 1: ANALYSIS NOT RUN ───────────────────────────────────────── */}
      {!analyzerResult && !isLoading && !errorMsg && (
        <div className="p-10 text-center rounded-2xl border border-white/[0.08] bg-gradient-to-b from-[#0D1220]/90 to-[#070A12]/95 space-y-5 max-w-xl mx-auto shadow-2xl backdrop-blur-xl">
          <div className="h-12 w-12 rounded-xl bg-[#6366F1]/10 border border-[#6366F1]/30 flex items-center justify-center text-[#818CF8] mx-auto shadow-[0_0_20px_rgba(99,102,241,0.2)]">
            <Trash2 className="h-6 w-6" />
          </div>
          <div className="space-y-2">
            <h3 className="text-sm sm:text-base font-bold font-mono text-[#F8FAFC] uppercase tracking-wider">
              DEAD CODE ANALYSIS NOT RUN
            </h3>
            <p className="text-xs sm:text-[13px] text-[#94A3B8] max-w-md mx-auto font-sans leading-relaxed">
              The repository graph has not yet been audited for unreachable modules, isolated files, or dead dependency chains.
            </p>
          </div>
          <button
            type="button"
            onClick={handleRunAnalysis}
            disabled={isLoading || !activeRepo}
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-gradient-to-r from-[#6366F1] to-[#4F46E5] hover:from-[#818CF8] hover:to-[#6366F1] text-white text-xs font-bold font-mono transition-all shadow-[0_0_20px_rgba(99,102,241,0.3)]"
          >
            <span>RUN REACHABILITY AUDIT</span>
            <ArrowRight className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* ── RESULTS ACTIVE WORKSPACE ────────────────────────────────────────── */}
      {analyzerResult && !isLoading && (
        <div className="space-y-6">
          {/* ── 3. INVESTIGATION TOOLBAR ───────────────────────────────────── */}
          <div className="p-3.5 sm:p-4 bg-gradient-to-b from-[#0D1220]/90 to-[#070A12]/95 border border-white/[0.08] rounded-xl space-y-3 backdrop-blur-xl shadow-lg">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
              {/* Filter Pills with Solid Saturated Borders and Glowing Badges */}
              <div className="flex items-center gap-2 flex-wrap">
                {[
                  { id: 'ALL' as FilterCategory, label: 'ALL', count: allFindings.length },
                  { id: 'UNUSED' as FilterCategory, label: 'UNUSED FILES', count: analyzerResult.unused_files?.length || 0 },
                  { id: 'ORPHANS' as FilterCategory, label: 'ORPHANED MODULES', count: analyzerResult.orphan_modules?.length || 0 },
                  { id: 'CHAINS' as FilterCategory, label: 'ORPHAN CHAINS', count: analyzerResult.dead_dependency_chains?.length || 0 },
                  { id: 'HIGH_CONFIDENCE' as FilterCategory, label: 'HIGH CONFIDENCE', count: highConfidenceCount },
                  { id: 'REVIEW_REQUIRED' as FilterCategory, label: 'REVIEW REQUIRED', count: reviewRequiredCount },
                ].map((pill) => {
                  const isActive = activeFilter === pill.id;
                  return (
                    <button
                      key={pill.id}
                      type="button"
                      onClick={() => handleFilterChange(pill.id)}
                      className={`px-3 py-1.5 rounded-lg text-[11px] font-mono font-semibold tracking-wider transition-all flex items-center gap-2 focus-visible:outline-none ${
                        isActive
                          ? 'border border-[#818CF8] bg-[#6366F1]/20 text-white shadow-[0_0_16px_rgba(99,102,241,0.25)]'
                          : 'border border-white/[0.06] bg-white/[0.02] text-[#94A3B8] hover:text-[#F8FAFC] hover:bg-white/[0.06]'
                      }`}
                    >
                      <span>{pill.label}</span>
                      <span className={`text-[9.5px] px-1.5 py-0.5 rounded-full font-mono ${
                        isActive ? 'bg-[#818CF8] text-[#0A0D14] font-bold' : 'bg-white/10 text-[#94A3B8]'
                      }`}>
                        {pill.count}
                      </span>
                    </button>
                  );
                })}
              </div>

              {/* Sort Selector */}
              <div className="flex items-center gap-2 shrink-0 text-xs font-mono text-[#94A3B8]">
                <SlidersHorizontal className="h-3.5 w-3.5 text-[#818CF8]" />
                <span className="text-[10px] uppercase font-bold text-[#818CF8]">SORT:</span>
                <select
                  value={sortOption}
                  onChange={(e) => handleSortChange(e.target.value as SortOption)}
                  className="bg-[#0A0D14] border border-white/10 text-[#F8FAFC] text-[11px] rounded-lg px-2.5 py-1 focus-visible:outline-none focus-visible:border-[#818CF8]"
                >
                  <option value="CONFIDENCE_DESC">CONFIDENCE (HIGH &rarr; LOW)</option>
                  <option value="RISK_DESC">RISK (HIGH &rarr; LOW)</option>
                  <option value="PATH_ASC">PATH (A &rarr; Z)</option>
                </select>
              </div>
            </div>

            {/* Dark Inset Search Input Row */}
            <div className="relative">
              <Search className="h-4 w-4 text-[#64748B] absolute left-3.5 top-1/2 -translate-y-1/2" />
              <input
                ref={searchInputRef}
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search path, filename, recommendation, chain member... (Press '/' to focus)"
                className="w-full bg-[#07090E] border border-white/10 rounded-lg pl-10 pr-14 py-2 text-xs text-[#F8FAFC] placeholder-[#475569] font-mono focus:border-[#818CF8] focus:ring-1 focus:ring-[#818CF8] focus-visible:outline-none transition-all shadow-inner"
              />
              <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-1.5">
                {searchQuery ? (
                  <button
                    type="button"
                    onClick={handleClearSearch}
                    className="text-[#94A3B8] hover:text-white p-1 rounded-md transition-colors"
                    title="Clear search (Esc)"
                  >
                    <X className="h-4 w-4" />
                  </button>
                ) : (
                  <kbd className="hidden sm:inline-block px-2 py-0.5 text-[10px] font-mono text-[#94A3B8] bg-white/5 border border-white/10 rounded-md">
                    /
                  </kbd>
                )}
              </div>
            </div>
          </div>

          {/* ── 4. PRIORITIZED FINDINGS + INSPECTOR (68% / 32% SPLIT) ──────── */}
          {filteredFindings.length === 0 ? (
            /* EMPTY / ZERO MATCHES */
            <div className="p-10 text-center rounded-xl border border-white/[0.08] bg-gradient-to-b from-[#0D1220]/90 to-[#070A12]/95 space-y-4 shadow-xl">
              <div className="h-10 w-10 rounded-lg bg-white/5 border border-white/10 flex items-center justify-center text-[#94A3B8] mx-auto">
                <Search className="h-5 w-5" />
              </div>
              <div className="space-y-1">
                <h4 className="text-xs sm:text-sm font-mono font-bold text-[#F8FAFC] uppercase">
                  {isSearching ? 'NO MATCHING FINDINGS' : 'NO FINDINGS IN THIS CATEGORY'}
                </h4>
                <p className="text-xs text-[#94A3B8] font-sans max-w-sm mx-auto">
                  {isSearching
                    ? 'Try another filename, path, recommendation, or dependency term.'
                    : 'No dead code findings match your active filter category.'}
                </p>
              </div>
              {(isSearching || activeFilter !== 'ALL') && (
                <button
                  type="button"
                  onClick={() => { setActiveFilter('ALL'); setSearchQuery(''); setVisibleCount(INITIAL_BATCH_SIZE); }}
                  className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 text-xs font-mono text-[#F8FAFC] transition-colors"
                >
                  <span>CLEAR FILTERS</span>
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
              {/* ── LEFT: PRIORITIZED FINDINGS LIST (68%) ─────────────────── */}
              <div className="lg:col-span-8 space-y-3 min-w-0">
                {/* Section Header with Prioritization Language */}
                <div className="flex items-center justify-between pb-1 text-[11px] font-mono text-[#94A3B8] uppercase tracking-wider">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-[#818CF8]">
                      {isSearching ? 'SEARCH MATCHES' : 'PRIORITIZED FINDINGS'}
                    </span>
                    {!isSearching && (
                      <span className="text-[10px] text-[#64748B] hidden sm:inline">
                        · SORTED BY {sortDescriptor}
                      </span>
                    )}
                  </div>
                  <span className="text-[10.5px] text-[#94A3B8]">
                    {isSearching
                      ? `ALL ${filteredFindings.length} MATCHES SHOWN`
                      : `DISPLAYING ${Math.min(visibleCount, filteredFindings.length)} OF ${filteredFindings.length} FINDINGS`}
                  </span>
                </div>

                {/* Finding Registry Rows */}
                <div className="space-y-2.5">
                  {visibleFindings.map((finding, idx) => {
                    const isSelected = selectedFinding?.id === finding.id;
                    const classTokens = classificationTokens(finding.type);
                    const risk = riskIndicator(finding.riskLevel);
                    const confColor = confidenceColor(finding.confidence);
                    const isCopied = copiedId === finding.id;

                    return (
                      <div
                        key={finding.id}
                        onClick={() => handleSelectFinding(finding)}
                        className={`p-4 rounded-xl border transition-all duration-200 cursor-pointer space-y-2.5 relative overflow-hidden group ${
                          isSelected
                            ? 'bg-gradient-to-r from-[#6366F1]/15 via-[#0D1220] to-[#070A12] border-[#818CF8] shadow-[0_0_24px_rgba(99,102,241,0.2)] border-l-4 border-l-[#818CF8]'
                            : 'bg-gradient-to-b from-[#0D1220]/90 to-[#070A12]/95 border-white/[0.08] hover:border-[#818CF8]/40 hover:bg-[#0D1424] hover:-translate-y-0.5 hover:shadow-lg'
                        }`}
                      >
                        {/* 1. Rank + Classification + Risk Micro-pill + Confidence */}
                        <div className="flex items-center justify-between gap-2 flex-wrap text-xs">
                          <div className="flex items-center gap-2.5 min-w-0">
                            {/* Rank */}
                            <span className="text-[11px] font-mono font-bold text-[#64748B]">
                              {String(idx + 1).padStart(2, '0')}
                            </span>

                            {/* Classification Badge with dot */}
                            <span className={`text-[10px] font-mono font-semibold px-2.5 py-0.5 rounded-md flex items-center gap-1.5 border ${classTokens.bg} ${classTokens.border}`}>
                              <span className={`h-1.5 w-1.5 rounded-full ${classTokens.dot}`} />
                              <span className={classTokens.text}>{classTokens.label}</span>
                            </span>

                            {/* Safety / Risk Micro-pill */}
                            <span className={`text-[10px] font-mono font-semibold flex items-center gap-1.5 px-2 py-0.5 rounded-md border ${risk.bg} ${risk.border}`}>
                              <span className={`h-1.5 w-1.5 rounded-full ${risk.dot}`} />
                              <span className={risk.text}>{risk.label}</span>
                            </span>
                          </div>

                          {/* Confidence */}
                          <div className="flex items-center gap-1.5 text-[11px] font-mono tabular-nums">
                            <span className={`font-extrabold ${confColor}`}>{(finding.confidence * 100).toFixed(0)}%</span>
                            <span className="text-[#64748B] text-[10px]">CONFIDENCE</span>
                          </div>
                        </div>

                        {/* 2. File Path (Strongest Text) */}
                        <div className="flex items-center justify-between gap-2 pt-0.5">
                          <FilePath
                            path={finding.filePath}
                            tone="primary"
                            size="md"
                            className="min-w-0 font-medium"
                          />

                          <button
                            type="button"
                            onClick={(e) => handleCopyPath(e, finding.filePath, finding.id)}
                            className="p-1.5 rounded-md text-[#94A3B8] hover:text-white hover:bg-white/10 transition-colors shrink-0"
                            title="Copy file path"
                          >
                            {isCopied ? <Check className="h-3.5 w-3.5 text-[#34D399]" /> : <Copy className="h-3.5 w-3.5" />}
                          </button>
                        </div>

                        {/* 3. Recommendation Statement */}
                        <p className="text-xs text-[#94A3B8] font-sans leading-relaxed line-clamp-2">
                          {finding.recommendation}
                        </p>

                        {/* 4. Reachability / Evidence + Quiet Action Links */}
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pt-2.5 border-t border-white/[0.06] text-[11px] font-mono">
                          {/* Reachability Indicator */}
                          <div className="text-[#64748B] flex items-center gap-1.5 truncate">
                            <span className="text-[#818CF8] font-semibold">REACHABILITY:</span>
                            {finding.type === 'orphan_module' ? (
                              <span className="text-[#94A3B8]">
                                {finding.lastReachableParent ? `Connected via ${finding.lastReachableParent}` : 'In-degree = 0 · no callers'}
                              </span>
                            ) : finding.type === 'dead_chain' ? (
                              <span className="text-[#94A3B8]">
                                Disconnected chain of {finding.totalNodes || finding.chain?.length || 2} modules
                              </span>
                            ) : (
                              <span className="text-[#94A3B8]">
                                In-degree = 0 · no repository callers
                              </span>
                            )}
                          </div>

                          {/* Quick Action Links */}
                          <div className="flex items-center gap-3 self-end sm:self-auto shrink-0">
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                openInGraph(activeRepo, finding.filePath);
                              }}
                              className="text-[#818CF8] hover:text-[#A5B4FC] flex items-center gap-1 uppercase transition-colors"
                              title="Inspect structural relations in File Graph"
                            >
                              <span>GRAPH</span>
                              <ArrowUpRight className="h-3.5 w-3.5" />
                            </button>

                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                openInChat(
                                  activeRepo,
                                  finding.filePath,
                                  `Is \`${finding.filePath}\` safe to delete? It was flagged as ${finding.typeLabel} with ${(finding.confidence * 100).toFixed(0)}% confidence.`
                                );
                              }}
                              className="text-[#818CF8] hover:text-[#A5B4FC] flex items-center gap-1 uppercase transition-colors"
                              title="Ask ARIA copilot about this finding"
                            >
                              <span>CHAT</span>
                              <ArrowUpRight className="h-3.5 w-3.5" />
                            </button>

                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                handleSelectFinding(finding);
                              }}
                              className={`flex items-center gap-1 uppercase font-bold transition-colors ${
                                isSelected ? 'text-[#818CF8]' : 'text-[#94A3B8] hover:text-[#818CF8]'
                              }`}
                            >
                              <span>INSPECT</span>
                              <ArrowRight className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>

                {/* ── PROGRESSIVE DISCLOSURE ("SHOW MORE" / "COLLAPSE") ──────── */}
                {!isSearching && filteredFindings.length > INITIAL_BATCH_SIZE && (
                  <div className="pt-3 flex flex-col items-center justify-center space-y-2 select-none">
                    {visibleCount < filteredFindings.length ? (
                      <button
                        type="button"
                        onClick={() => setVisibleCount((prev) => Math.min(prev + BATCH_INCREMENT, filteredFindings.length))}
                        className="w-full sm:w-auto px-7 py-2.5 rounded-xl bg-gradient-to-b from-[#0D1220] to-[#070A12] hover:bg-[#131A2E] border border-white/10 hover:border-[#818CF8]/60 text-xs font-mono font-bold text-white flex items-center justify-center gap-2.5 transition-all shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#818CF8]/40 group"
                      >
                        <Plus className="h-4 w-4 text-[#818CF8] group-hover:scale-110 transition-transform" />
                        <span>SHOW MORE FINDINGS</span>
                        <span className="text-[11px] text-[#94A3B8] group-hover:text-white">
                          ({visibleCount} &rarr; {Math.min(visibleCount + BATCH_INCREMENT, filteredFindings.length)})
                        </span>
                      </button>
                    ) : (
                      <div className="flex items-center gap-3">
                        <span className="text-[11px] font-mono text-[#94A3B8] uppercase tracking-wider">
                          ALL {filteredFindings.length} FINDINGS DISPLAYED
                        </span>
                        <button
                          type="button"
                          onClick={() => setVisibleCount(INITIAL_BATCH_SIZE)}
                          className="px-3.5 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 text-xs font-mono font-bold text-[#818CF8] hover:text-white uppercase transition-colors"
                        >
                          COLLAPSE TO 8
                        </button>
                      </div>
                    )}
                    <span className="text-[10.5px] font-mono text-[#64748B]">
                      DISPLAYING {Math.min(visibleCount, filteredFindings.length)} OF {filteredFindings.length} FINDINGS
                    </span>
                  </div>
                )}
              </div>

              {/* ── RIGHT: ATTACHED FORENSIC INSPECTOR PANEL (32%) ─────────── */}
              <div ref={inspectorRef} className="lg:col-span-4 sticky top-16 space-y-3">
                <div className="flex items-center justify-between pb-1 text-[11px] font-mono text-[#94A3B8] uppercase tracking-wider">
                  <span className="text-[#818CF8] font-bold flex items-center gap-1.5">
                    <Terminal className="h-3.5 w-3.5 text-[#818CF8]" />
                    INSPECTOR PANEL
                  </span>
                  <span className="text-[#34D399] flex items-center gap-1.5 font-bold">
                    <span className="h-2 w-2 rounded-full bg-[#34D399] shadow-[0_0_8px_rgba(52,211,153,0.8)]" />
                    ACTIVE TARGET
                  </span>
                </div>

                {selectedFinding ? (
                  <div className="p-5 rounded-xl border border-white/[0.08] bg-gradient-to-b from-[#0D1220]/95 to-[#070A12]/98 space-y-4 shadow-2xl border-l-4 border-l-[#818CF8] backdrop-blur-xl relative overflow-hidden">
                    {/* Top ambient highlight */}
                    <div className="absolute top-0 inset-x-0 h-px bg-gradient-to-r from-transparent via-[#818CF8]/40 to-transparent" />

                    {/* Header */}
                    <div className="space-y-2 pb-3.5 border-b border-white/[0.08]">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-[9.5px] font-mono font-bold text-[#818CF8] uppercase tracking-widest">
                          DEAD CODE FINDING
                        </span>
                        <span className={`text-[10px] font-mono font-semibold flex items-center gap-1.5 px-2 py-0.5 rounded-md border ${riskIndicator(selectedFinding.riskLevel).bg} ${riskIndicator(selectedFinding.riskLevel).border}`}>
                          <span className={`h-1.5 w-1.5 rounded-full ${riskIndicator(selectedFinding.riskLevel).dot}`} />
                          <span className={riskIndicator(selectedFinding.riskLevel).text}>{selectedFinding.riskLevel}</span>
                        </span>
                      </div>

                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2 min-w-0">
                          <FileCode className="h-4 w-4 text-[#818CF8] shrink-0" />
                          <h3 className="font-mono text-sm font-bold text-[#F8FAFC] truncate" title={selectedFinding.fileName}>
                            {selectedFinding.fileName}
                          </h3>
                        </div>
                        <button
                          type="button"
                          onClick={(e) => handleCopyPath(e, selectedFinding.filePath, 'inspector')}
                          className="p-1.5 rounded-md text-[#94A3B8] hover:text-white hover:bg-white/10 transition-colors shrink-0"
                          title="Copy path"
                        >
                          {copiedId === 'inspector' ? <Check className="h-4 w-4 text-[#34D399]" /> : <Copy className="h-4 w-4" />}
                        </button>
                      </div>

                      <FilePath
                        path={selectedFinding.filePath}
                        tone="secondary"
                        size="sm"
                      />
                    </div>

                    {/* Technical Matrix */}
                    <div className="grid grid-cols-2 gap-2 text-xs font-mono">
                      <div className="p-2.5 bg-[#07090E] border border-white/[0.06] rounded-lg space-y-1">
                        <span className="text-[9px] font-bold text-[#818CF8] uppercase tracking-wider block">
                          CLASSIFICATION
                        </span>
                        <span
                          className="text-[11px] font-semibold block"
                          style={{ color: classificationTokens(selectedFinding.type).color }}
                        >
                          {selectedFinding.typeLabel}
                        </span>
                      </div>

                      <div className="p-2.5 bg-[#07090E] border border-white/[0.06] rounded-lg space-y-1">
                        <div className="flex items-center justify-between">
                          <span className="text-[9px] font-bold text-[#818CF8] uppercase tracking-wider">
                            CONFIDENCE
                          </span>
                          <span title="Confidence reflects static repository evidence; it does not account for runtime-only consumers.">
                            <HelpCircle className="h-3 w-3 text-[#64748B]" />
                          </span>
                        </div>
                        <span className={`font-extrabold text-[12px] block ${confidenceColor(selectedFinding.confidence)}`}>
                          {(selectedFinding.confidence * 100).toFixed(0)}%
                        </span>
                      </div>

                      <div className="p-2.5 bg-[#07090E] border border-white/[0.06] rounded-lg space-y-1 col-span-2">
                        <span className="text-[9px] font-bold text-[#818CF8] uppercase tracking-wider block">
                          GRAPH REACHABILITY
                        </span>
                        <span className="text-[#CBD5E1] text-[11px] block leading-relaxed">
                          {selectedFinding.type === 'orphan_module'
                            ? selectedFinding.lastReachableParent
                              ? `Last reachable parent: ${selectedFinding.lastReachableParent}`
                              : 'In-degree = 0 · Disconnected from entry points'
                            : selectedFinding.type === 'dead_chain'
                            ? `Disconnected chain of ${selectedFinding.totalNodes || selectedFinding.chain?.length || 2} modules`
                            : 'In-degree = 0 · No repository caller references detected'}
                        </span>
                      </div>
                    </div>

                    {/* WHY THIS WAS FLAGGED */}
                    <div className="space-y-1.5 text-xs">
                      <span className="text-[9.5px] font-mono font-bold text-[#818CF8] uppercase tracking-wider block">
                        WHY THIS WAS FLAGGED
                      </span>
                      <p className="text-[#94A3B8] font-sans leading-relaxed text-[12px]">
                        {selectedFinding.type === 'unused_file'
                          ? 'Static AST parsing detected 0 incoming import statements across the entire repository.'
                          : selectedFinding.type === 'orphan_module'
                          ? 'This module is structurally disconnected from any reachable entry points in the dependency graph.'
                          : 'This cluster of modules forms an unreachable dependency chain that may be pruned together.'}
                      </p>
                    </div>

                    {/* EVIDENCE DETAIL */}
                    <div className="p-3 bg-[#07090E] border border-white/[0.06] rounded-lg space-y-1 text-xs font-mono">
                      <span className="text-[9px] font-bold text-[#818CF8] uppercase tracking-wider block">
                        EVIDENCE DETAIL
                      </span>
                      <p className="text-[#CBD5E1] text-[11px] leading-relaxed">
                        {selectedFinding.recommendation}
                      </p>
                    </div>

                    {/* WHAT STATIC ANALYSIS CANNOT PROVE */}
                    <div className="space-y-1 text-xs">
                      <span className="text-[9.5px] font-mono font-bold text-[#FCD34D] uppercase tracking-wider block">
                        WHAT STATIC ANALYSIS CANNOT PROVE
                      </span>
                      <p className="text-[#94A3B8] font-sans leading-relaxed text-[11.5px]">
                        Dynamic runtime imports, reflection, framework routing, or external package exports may still consume this module.
                      </p>
                    </div>

                    {/* RELATED MODULES (Chain or Orphan Parent) */}
                    {selectedFinding.chain && selectedFinding.chain.length > 1 && (
                      <div className="space-y-1.5 text-xs font-mono">
                        <span className="text-[9.5px] font-bold text-[#C084FC] uppercase tracking-wider block">
                          CHAIN MODULES ({selectedFinding.chain.length})
                        </span>
                        <div className="max-h-28 overflow-y-auto space-y-1 pr-1">
                          {selectedFinding.chain.map((c, i) => (
                            <div key={i} className="flex items-center justify-between gap-2 p-2 rounded-lg bg-[#07090E] border border-white/[0.06] text-[11px]">
                              <span className="text-[#CBD5E1] truncate">{c}</span>
                              <button
                                type="button"
                                onClick={() => openInGraph(activeRepo, c)}
                                className="text-[#818CF8] hover:text-[#A5B4FC] text-[10px] uppercase font-bold shrink-0"
                              >
                                Graph &rarr;
                              </button>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* RECOMMENDED NEXT STEP */}
                    <div className="space-y-1 text-xs">
                      <span className="text-[9.5px] font-mono font-bold text-[#34D399] uppercase tracking-wider block">
                        RECOMMENDED NEXT STEP
                      </span>
                      <p className="text-[#94A3B8] font-sans leading-relaxed text-[12px]">
                        Verify whether dynamic runtime invocations exist, run test suites, and review before removal.
                      </p>
                    </div>

                    {/* Actions Toolbar */}
                    <div className="pt-3.5 border-t border-white/[0.08] flex flex-col gap-2.5">
                      <button
                        type="button"
                        onClick={() => openInGraph(activeRepo, selectedFinding.filePath)}
                        className="w-full py-2.5 px-4 rounded-lg bg-gradient-to-r from-[#6366F1] to-[#4F46E5] hover:from-[#818CF8] hover:to-[#6366F1] border border-indigo-400/30 text-white text-xs font-bold font-mono uppercase flex items-center justify-center gap-2 transition-all shadow-[0_0_16px_rgba(99,102,241,0.25)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#818CF8]/50"
                      >
                        <Layers className="h-4 w-4" />
                        <span>VIEW IN FILE GRAPH</span>
                      </button>

                      <button
                        type="button"
                        onClick={() =>
                          openInChat(
                            activeRepo,
                            selectedFinding.filePath,
                            `Regarding \`${selectedFinding.filePath}\`: it was flagged as ${selectedFinding.typeLabel} with ${(selectedFinding.confidence * 100).toFixed(0)}% confidence. How should I safely verify and prune it?`
                          )
                        }
                        className="w-full py-2.5 px-4 rounded-lg bg-[#07090E] hover:bg-[#0E1322] border border-white/10 text-[#818CF8] hover:text-white text-xs font-bold font-mono uppercase flex items-center justify-center gap-2 transition-all"
                      >
                        <Sparkles className="h-4 w-4 text-[#818CF8]" />
                        <span>OPEN IN ARIA COPILOT</span>
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="p-8 text-center rounded-xl border border-white/[0.08] bg-gradient-to-b from-[#0D1220]/90 to-[#070A12]/95 text-xs text-[#94A3B8] font-sans">
                    Select any finding on the left to inspect detailed reachability signals.
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ── 5. CLEANUP PRIORITIES ──────────────────────────────────────── */}
          {analyzerResult.cleanup_recommendations && analyzerResult.cleanup_recommendations.length > 0 && (
            <section aria-labelledby="cleanup-priorities-heading" className="pt-6 border-t border-white/[0.08] space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-baseline sm:justify-between gap-2 pb-2 border-b border-white/[0.08]">
                <div>
                  <h3 id="cleanup-priorities-heading" className="text-sm sm:text-base font-bold font-mono text-[#F8FAFC] uppercase tracking-wider flex items-center gap-2">
                    <Trash2 className="h-4 w-4 text-[#818CF8]" /> CLEANUP PRIORITIES
                  </h3>
                  <p className="text-xs text-[#94A3B8] font-sans mt-0.5">
                    Highest-confidence interventions requiring developer verification.
                  </p>
                </div>
                <span className="text-[11px] font-mono text-[#818CF8] font-bold">
                  {analyzerResult.cleanup_recommendations.length} PRIORITIZED ACTIONS
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {analyzerResult.cleanup_recommendations.map((rec, idx) => {
                  const { action, path, rest } = splitRecommendation(rec);
                  const isCopied = copiedId === `rec-${idx}`;

                  return (
                    <div
                      key={idx}
                      className="p-4 sm:p-5 rounded-xl border border-white/[0.08] bg-gradient-to-b from-[#0D1220]/90 to-[#070A12]/95 hover:bg-[#0D1424] hover:border-[#818CF8]/40 transition-all space-y-3 shadow-md relative overflow-hidden group"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <span className="text-[11px] font-mono font-bold text-[#64748B]">
                            {String(idx + 1).padStart(2, '0')}
                          </span>
                          <span className="text-[10px] font-mono font-bold text-[#FCD34D] uppercase px-2 py-0.5 rounded-md bg-[#FFB800]/12 border border-[#FFB800]/30 flex items-center gap-1.5">
                            <span className="h-1.5 w-1.5 rounded-full bg-[#FFB800]" />
                            HIGH PRIORITY
                          </span>
                        </div>
                        <span className="text-[10px] font-mono text-[#34D399] font-bold flex items-center gap-1">
                          VERIFY &rarr; PRUNE
                        </span>
                      </div>

                      <div className="space-y-1.5">
                        <h4 className="text-xs sm:text-[13px] font-mono font-bold text-[#F8FAFC] leading-snug">
                          {action}
                        </h4>
                        {path && (
                          <div className="flex items-center justify-between gap-2 py-1.5 px-2.5 rounded-lg bg-[#07090E] border border-white/[0.06] text-[11px] font-mono">
                            <span className="text-[#F8FAFC] truncate font-medium">{path}</span>
                            <button
                              type="button"
                              onClick={(e) => handleCopyPath(e, path, `rec-${idx}`)}
                              className="text-[#94A3B8] hover:text-white p-1 rounded transition-colors"
                              title="Copy path"
                            >
                              {isCopied ? <Check className="h-3.5 w-3.5 text-[#34D399]" /> : <Copy className="h-3.5 w-3.5" />}
                            </button>
                          </div>
                        )}
                        {rest && (
                          <p className="text-xs text-[#94A3B8] font-sans leading-relaxed">
                            {rest}
                          </p>
                        )}
                      </div>

                      {/* Action Links */}
                      {path && (
                        <div className="flex items-center gap-4 pt-2.5 border-t border-white/[0.06] text-[11px] font-mono">
                          <button
                            type="button"
                            onClick={() => openInGraph(activeRepo, path)}
                            className="text-[#818CF8] hover:text-[#A5B4FC] flex items-center gap-1 uppercase font-semibold transition-colors"
                          >
                            <span>Graph</span>
                            <ArrowUpRight className="h-3.5 w-3.5" />
                          </button>
                          <button
                            type="button"
                            onClick={() =>
                              openInChat(
                                activeRepo,
                                path,
                                `Regarding cleanup priority "${action}": what are the safest steps to refactor or remove \`${path}\`?`
                              )
                            }
                            className="text-[#818CF8] hover:text-[#A5B4FC] flex items-center gap-1 uppercase font-semibold transition-colors"
                          >
                            <span>Chat</span>
                            <ArrowUpRight className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  );
};

export default DeadCodeAnalyzer;
