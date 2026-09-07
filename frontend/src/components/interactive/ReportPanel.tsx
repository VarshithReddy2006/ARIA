/**
 * ARIA Health Report — 10/10 Production Redesign
 *
 * Executive-grade engineering diagnostic control surface.
 * Compresses repository evidence into root-cause finding clusters with
 * deterministic score explanations, multi-lens telemetry, and high-leverage actions.
 */

import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  Activity,
  AlertTriangle,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  CornerDownRight,
  Copy,
  Download,
  Filter,
  Globe,
  Layers,
  Printer,
  RefreshCw,
  Sparkles,
  Trash2,
  Zap,
} from 'lucide-react';
import { apiUrl, extractErrorMessage } from '../../lib/api';
import { FilePath } from '../ui/FilePath';
import { Button } from '../ui/Button';
import { EmptyState } from '../ui/EmptyState';
import { SVGDonut } from '../ui/SVGDonut';
import { AnimatedNumber } from '../ui/AnimatedNumber';

// ── Types & Contracts ───────────────────────────────────────────────────────

type SubTabId = 'architecture' | 'api' | 'hygiene' | 'onboarding';
type SeverityFilter = 'ALL' | 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
type SortOption = 'LEVERAGE' | 'SEVERITY' | 'EVIDENCE';

interface ReportPanelProps {
  repoName?: string;
  onNavigate?: (tab: string) => void;
}

interface ScoreBreakdown {
  overall: number;
  architecture: number;
  api: number;
  hygiene: number;
  churn: number;
  readability: number;
  grade: string;
}

interface ReportMetadata {
  repo_name: string;
  owner: string;
  name: string;
  total_loc: number;
  commits_count: number;
  languages: Record<string, number>;
  generated_at: string;
  execution_time_ms: number;
}

interface RuleViolationItem {
  rule_id: string;
  rule_name: string;
  severity: 'CRITICAL' | 'MAJOR' | 'MINOR' | string;
  source_node: string;
  target_node: string;
  description: string;
}

interface ArchReportSection {
  cycles_count: number;
  cycles: string[][];
  strongly_connected_components: number;
  smells_count: number;
  smells: string[];
  rule_violations?: RuleViolationItem[];
}

interface ApiReportSection {
  total_exported_symbols: number;
  public_symbols: number;
  private_symbols: number;
  public_private_ratio: number;
  instability: number;
  abstractness: number;
  distance_from_main_sequence: number;
  unstable_modules_count: number;
  unstable_modules: string[];
}

interface HygieneReportSection {
  dead_functions_count: number;
  dead_functions: string[];
  dead_classes_count: number;
  dead_classes: string[];
  unused_files_count: number;
  unused_files: string[];
  dead_code_ratio: number;
  hotspots_count: number;
  hotspots: string[];
}

interface OnboardingReportSection {
  recommended_reading_path: string[];
  reading_path_completeness: number;
  entry_points_count: number;
  entry_points: string[];
  estimated_onboarding_time_minutes: number;
}

interface WhyThisScoreItem {
  dimension: string;
  score: number;
  status: 'attention' | 'review' | 'healthy' | 'unknown' | string;
  evidence: string;
  impact: string;
  recommendation: string;
}

interface SignalAttentionItem {
  id: string;
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | string;
  title: string;
  evidence: string;
  meaning: string;
  action_label: string;
  action_target: string;
  affected_file?: string | null;
}

interface ReportDataModel {
  scores: ScoreBreakdown;
  metadata: ReportMetadata;
  architecture: ArchReportSection;
  api_surface: ApiReportSection;
  hygiene: HygieneReportSection;
  onboarding: OnboardingReportSection;
  refactoring_priorities: string[];
  why_this_score?: WhyThisScoreItem[];
  signals_needing_attention?: SignalAttentionItem[];
  healthy_baseline?: string[];
}

interface RootCauseCluster {
  id: string;
  rule_id: string;
  rule_name: string;
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
  source_node: string;
  target_nodes: string[];
  findings_count: number;
  impact: string;
  fix: string;
  description: string;
}

interface FixThisFirstItem {
  rank: string;
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
  title: string;
  targetFile: string;
  findingsCount: number;
  leverageLabel: string;
  why: string;
  action: string;
  actionTarget: 'graph' | 'architecture' | 'dead_code' | 'api_surface' | 'chat';
}

interface SubtreeCleanup {
  directory: string;
  count: number;
  sampleFiles: string[];
}

// ── Severity & Status Styling Constants (10/10 Modern Palette) ───────────────

const SEVERITY_CONFIG: Record<
  string,
  { label: string; textClass: string; dotClass: string; bgClass: string; borderClass: string; activeClass: string }
> = {
  critical: {
    label: 'CRITICAL',
    textClass: 'text-[#FF4D6D]',
    dotClass: 'bg-[#FF4D6D]',
    bgClass: 'bg-[#FF4D6D]/12',
    borderClass: 'border-[#FF4D6D]/35',
    activeClass: 'bg-[#FF4D6D] text-black font-extrabold shadow-[0_0_16px_rgba(255,77,109,0.35)]',
  },
  high: {
    label: 'HIGH',
    textClass: 'text-[#FFB800]',
    dotClass: 'bg-[#FFB800]',
    bgClass: 'bg-[#FFB800]/12',
    borderClass: 'border-[#FFB800]/35',
    activeClass: 'bg-[#FFB800] text-black font-extrabold shadow-[0_0_16px_rgba(255,184,0,0.35)]',
  },
  medium: {
    label: 'MEDIUM',
    textClass: 'text-[#818CF8]',
    dotClass: 'bg-[#818CF8]',
    bgClass: 'bg-[#818CF8]/12',
    borderClass: 'border-[#818CF8]/35',
    activeClass: 'bg-[#818CF8] text-white font-extrabold shadow-[0_0_16px_rgba(129,140,248,0.35)]',
  },
  low: {
    label: 'LOW',
    textClass: 'text-[#94A3B8]',
    dotClass: 'bg-[#94A3B8]',
    bgClass: 'bg-white/[0.05]',
    borderClass: 'border-white/[0.1]',
    activeClass: 'bg-white/20 text-white font-extrabold shadow-sm',
  },
};

const getSeverityBadge = (severity?: string) => {
  const norm = (severity || 'low').toLowerCase();
  if (norm === 'critical') return SEVERITY_CONFIG.critical;
  if (norm === 'high' || norm === 'major') return SEVERITY_CONFIG.high;
  if (norm === 'medium' || norm === 'minor') return SEVERITY_CONFIG.medium;
  return SEVERITY_CONFIG.low;
};

const scoreStatusColor = (score: number) => {
  if (score >= 80) {
    return {
      label: 'HEALTHY',
      dot: 'bg-[#10B981]',
      text: 'text-[#10B981]',
      bg: 'bg-[#10B981]/12',
      border: 'border-[#10B981]/30',
      glow: 'shadow-[0_0_12px_rgba(16,185,129,0.2)]',
    };
  }
  if (score >= 60) {
    return {
      label: 'REVIEW',
      dot: 'bg-[#FFB800]',
      text: 'text-[#FFB800]',
      bg: 'bg-[#FFB800]/12',
      border: 'border-[#FFB800]/30',
      glow: 'shadow-[0_0_12px_rgba(255,184,0,0.2)]',
    };
  }
  return {
    label: 'ATTENTION',
    dot: 'bg-[#FF4D6D]',
    text: 'text-[#FF4D6D]',
    bg: 'bg-[#FF4D6D]/12',
    border: 'border-[#FF4D6D]/30',
    glow: 'shadow-[0_0_12px_rgba(255,77,109,0.2)]',
  };
};

const num = (v: number | undefined | null, fallback = 0): number => (typeof v === 'number' && !isNaN(v) ? v : fallback);

const fmtNum = (v: number | undefined | null, decimals = 1, fallback = '0.0'): string => {
  if (typeof v === 'number' && !isNaN(v)) return v.toFixed(decimals);
  return fallback;
};

const fmtLoc = (v: number | undefined | null, fallback = '0'): string => {
  if (typeof v === 'number' && !isNaN(v)) return v.toLocaleString();
  return fallback;
};

const deadCodePct = (ratio?: number | null): number => {
  const r = num(ratio);
  if (r <= 0) return 0;
  if (r > 1) return Math.min(100, r);
  return Math.min(100, r * 100);
};

const gradeBadgeStyle = (grade: string) => {
  const g = (grade || 'C').toUpperCase();
  if (g === 'A') return { bg: 'bg-[#10B981]/15', text: 'text-[#10B981]', border: 'border-[#10B981]/40', glow: 'shadow-[0_0_24px_rgba(16,185,129,0.25)]', label: 'Optimal Architecture' };
  if (g === 'B') return { bg: 'bg-[#818CF8]/15', text: 'text-[#818CF8]', border: 'border-[#818CF8]/40', glow: 'shadow-[0_0_24px_rgba(129,140,248,0.25)]', label: 'Production Ready' };
  if (g === 'C') return { bg: 'bg-[#FFB800]/15', text: 'text-[#FFB800]', border: 'border-[#FFB800]/40', glow: 'shadow-[0_0_24px_rgba(255,184,0,0.25)]', label: 'Degraded Modularity' };
  if (g === 'D') return { bg: 'bg-[#FF758F]/15', text: 'text-[#FF758F]', border: 'border-[#FF758F]/40', glow: 'shadow-[0_0_24px_rgba(255,117,143,0.25)]', label: 'High Structural Risk' };
  return { bg: 'bg-[#FF4D6D]/20', text: 'text-[#FF4D6D]', border: 'border-[#FF4D6D]/60', glow: 'shadow-[0_0_28px_rgba(255,77,109,0.3)]', label: 'Critical Refactoring' };
};

const relativeTime = (isoString?: string) => {
  if (!isoString) return 'recently';
  try {
    const diff = (Date.now() - new Date(isoString).getTime()) / 1000;
    if (diff < 60) return 'JUST NOW';
    if (diff < 3600) return `${Math.floor(diff / 60)}M AGO`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}H AGO`;
    return `${Math.floor(diff / 86400)}D AGO`;
  } catch {
    return 'recently';
  }
};

// ── Cross-Surface Navigation Dispatchers ────────────────────────────────────

const openInGraph = (owner: string, repo: string, file?: string) => {
  window.dispatchEvent(
    new CustomEvent('aria-open-graph', {
      detail: { owner, repo, file, path: file },
    })
  );
};

const openInChat = (owner: string, repo: string, file: string, prompt: string) => {
  window.dispatchEvent(
    new CustomEvent('aria-open-chat', {
      detail: {
        owner,
        repo,
        file,
        prompt,
      },
    })
  );
};

// ── Root-Cause Cluster Card Component (Collapsible + Paginated) ─────────────

const ClusterCard: React.FC<{
  cluster: RootCauseCluster;
  owner: string;
  repo: string;
  onNavigate?: (tab: string) => void;
}> = ({ cluster, owner, repo, onNavigate }) => {
  const [expanded, setExpanded] = useState(false);
  const [page, setPage] = useState(0);
  const [copied, setCopied] = useState(false);
  const PAGE_SIZE = 12;

  const cfg = getSeverityBadge(cluster.severity);
  const totalTargets = cluster.target_nodes.length;
  const paginatedTargets = useMemo(() => {
    const start = page * PAGE_SIZE;
    return cluster.target_nodes.slice(start, start + PAGE_SIZE);
  }, [cluster.target_nodes, page]);
  const totalPages = Math.ceil(totalTargets / PAGE_SIZE);

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (typeof navigator !== 'undefined' && navigator.clipboard) {
      navigator.clipboard.writeText(cluster.source_node);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }
  };

  return (
    <div
      className={`border rounded-2xl transition-all duration-200 overflow-hidden ${
        expanded
          ? 'border-[#818CF8]/50 bg-gradient-to-b from-[#101626] to-[#0A0D16] shadow-xl shadow-black/50'
          : 'border-white/[0.08] bg-gradient-to-b from-[#0D1220]/90 to-[#070A12]/95 hover:border-[#818CF8]/35 hover:shadow-lg'
      }`}
    >
      <div
        role="button"
        tabIndex={0}
        onClick={() => setExpanded((p) => !p)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            setExpanded((p) => !p);
          }
        }}
        aria-expanded={expanded}
        className="w-full flex items-start justify-between gap-4 p-5 text-left cursor-pointer focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[#818CF8]"
      >
        <div className="space-y-3 min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`px-2.5 py-0.5 rounded-md border text-[9px] font-bold font-mono uppercase tracking-wider ${cfg.bgClass} ${cfg.borderClass} ${cfg.textClass}`}
            >
              {cluster.severity}
            </span>
            <span className="px-2.5 py-0.5 rounded-md bg-white/[0.05] border border-white/[0.08] text-[9px] font-bold font-mono text-[#94A3B8]">
              {cluster.rule_id}
            </span>
            <span className="text-xs font-bold text-[#F4F5F7] font-mono">
              {cluster.rule_name}
            </span>
            <span className="ml-auto text-[10px] font-bold font-mono text-[#818CF8] bg-[#6366F1]/12 px-2.5 py-0.5 rounded-md border border-[#6366F1]/25">
              Explains {cluster.findings_count} findings
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[10px] text-[#94A3B8] font-mono uppercase tracking-widest shrink-0">
              Root Module:
            </span>
            <div className="flex items-center gap-2 bg-[#04060A] px-3 py-1.5 rounded-lg border border-white/[0.09] min-w-0">
              <FilePath path={cluster.source_node} tone="primary" size="sm" className="truncate text-white font-semibold" />
              <button
                type="button"
                onClick={handleCopy}
                className="text-[#94A3B8] hover:text-[#F4F5F7] p-0.5 transition-colors shrink-0"
                title="Copy file path"
              >
                {copied ? <Check className="h-3 w-3 text-[#10B981]" /> : <Copy className="h-3 w-3" />}
              </button>
            </div>
            <span className="text-[10px] text-[#94A3B8] font-mono">
              → {totalTargets} illegal target {totalTargets > 1 ? 'relationships' : 'relationship'}
            </span>
          </div>

          <p className="text-xs text-[#CBD5E1] font-sans leading-relaxed">
            {cluster.description}
          </p>
        </div>

        <div className="flex items-center gap-2 shrink-0 pt-1 text-[#94A3B8]">
          <span className="text-[10px] font-mono text-[#818CF8] hidden sm:inline font-bold">
            {expanded ? 'COLLAPSE' : `INSPECT (${cluster.findings_count})`}
          </span>
          {expanded ? <ChevronUp className="h-4 w-4 text-[#F4F5F7]" /> : <ChevronDown className="h-4 w-4" />}
        </div>
      </div>

      {expanded && (
        <div className="p-5 pt-4 border-t border-white/[0.08] bg-[#05070D]/90 space-y-4 font-mono text-xs">
          {/* Remediation guidance */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
            <div className="p-3.5 bg-gradient-to-br from-[#0F1424] to-[#080B12] border border-[#FF4D6D]/20 rounded-xl space-y-1.5">
              <span className="text-[9px] font-bold text-[#FF4D6D] uppercase tracking-widest block">
                WHY IT MATTERS / BLAST RADIUS
              </span>
              <p className="text-[11px] text-[#CBD5E1] font-sans leading-relaxed">
                {cluster.impact}
              </p>
            </div>
            <div className="p-3.5 bg-gradient-to-br from-[#0F1424] to-[#080B12] border border-[#10B981]/20 rounded-xl space-y-1.5">
              <span className="text-[9px] font-bold text-[#10B981] uppercase tracking-widest block">
                RECOMMENDED ARCHITECTURAL FIX
              </span>
              <p className="text-[11px] text-[#CBD5E1] font-sans leading-relaxed">
                {cluster.fix}
              </p>
            </div>
          </div>

          {/* Target Nodes Grid (Paginated for high leverage clusters) */}
          <div className="space-y-2.5">
            <div className="flex items-center justify-between">
              <span className="text-[9px] font-bold text-[#818CF8] uppercase tracking-widest">
                INDIVIDUAL VIOLATION RELATIONSHIPS ({totalTargets})
              </span>
              {totalPages > 1 && (
                <div className="flex items-center gap-2 text-[10px] font-mono text-[#94A3B8]">
                  <span>
                    Page {page + 1} of {totalPages}
                  </span>
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      disabled={page === 0}
                      onClick={() => setPage((p) => Math.max(0, p - 1))}
                      className="px-2.5 py-1 rounded bg-[#0D1220] border border-white/[0.08] disabled:opacity-30 hover:text-white transition-colors"
                    >
                      Prev
                    </button>
                    <button
                      type="button"
                      disabled={page >= totalPages - 1}
                      onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                      className="px-2.5 py-1 rounded bg-[#0D1220] border border-white/[0.08] disabled:opacity-30 hover:text-white transition-colors"
                    >
                      Next
                    </button>
                  </div>
                </div>
              )}
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
              {paginatedTargets.map((tgt, i) => (
                <div
                  key={`${tgt}-${i}`}
                  className="flex items-center gap-2 p-2.5 bg-[#080C16] border border-white/[0.06] rounded-xl text-[11px] overflow-hidden hover:border-[#818CF8]/30 transition-colors"
                >
                  <CornerDownRight className="h-3 w-3 text-[#818CF8] shrink-0" />
                  <FilePath path={tgt} tone="secondary" size="sm" className="truncate flex-1" />
                </div>
              ))}
            </div>
          </div>

          {/* Action links */}
          <div className="flex flex-wrap items-center gap-2.5 pt-3 border-t border-white/[0.08]">
            <button
              type="button"
              onClick={() => openInGraph(owner, repo, cluster.source_node)}
              className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-[#0D1220] hover:bg-[#151D33] border border-white/[0.09] text-[#818CF8] hover:text-white text-[10px] font-bold uppercase transition-colors"
            >
              <Layers className="h-3 w-3 text-[#818CF8]" /> View in Graph
            </button>
            <button
              type="button"
              onClick={() =>
                openInChat(
                  owner,
                  repo,
                  cluster.source_node,
                  `Explain how to decouple \`${cluster.source_node}\` from ${cluster.findings_count} illegal layer dependencies violating rule ${cluster.rule_id} (${cluster.rule_name}). Provide a step-by-step refactoring plan.`
                )
              }
              className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-gradient-to-r from-[#6366F1] to-[#4F46E5] hover:from-[#7C82FF] hover:to-[#6366F1] text-white text-[10px] font-bold uppercase transition-colors shadow-sm"
            >
              <Sparkles className="h-3 w-3" /> Open in Chat
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

// ── Main Component ──────────────────────────────────────────────────────────

export const ReportPanel: React.FC<ReportPanelProps> = ({ repoName, onNavigate }) => {
  const [report, setReport] = useState<ReportDataModel | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [subTab, setSubTab] = useState<SubTabId>('architecture');
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>('ALL');
  const [sortOption, setSortOption] = useState<SortOption>('LEVERAGE');
  const [ruleFilter, setRuleFilter] = useState<string | null>(null);
  const [visibleClustersLimit, setVisibleClustersLimit] = useState<number>(8);

  useEffect(() => {
    setVisibleClustersLimit(8);
  }, [severityFilter, sortOption, ruleFilter]);

  const [owner, repo] = useMemo(() => {
    const parts = (repoName || '').split('/');
    return [parts[0] || '', parts[1] || ''];
  }, [repoName]);

  const loadReport = useCallback((forceRebuild: boolean = false) => {
    if (!owner || !repo) {
      setError('Invalid repository identifier');
      setReport(null);
      setLoading(false);
      return;
    }

    setReport(null);
    setLoading(true);
    setError(null);

    const endpoint = forceRebuild
      ? apiUrl(`/api/v1/report/${owner}/${repo}/build`)
      : apiUrl(`/api/v1/report/${owner}/${repo}`);
    const method = forceRebuild ? 'POST' : 'GET';

    fetch(endpoint, { method })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to compile health report`);
        return res.json();
      })
      .then((data) => {
        setReport(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(extractErrorMessage(err));
        setLoading(false);
      });
  }, [owner, repo]);

  useEffect(() => {
    loadReport(false);
  }, [loadReport]);

  const handleExport = (format: 'html' | 'pdf' | 'markdown') => {
    if (!owner || !repo) return;
    const downloadUrl = apiUrl(`/api/v1/report/${owner}/${repo}/download?format=${format}`);
    window.open(downloadUrl, '_blank');
  };

  // ── Derived Root-Cause Clusters ───────────────────────────────────────────
  const rootCauseClusters = useMemo<RootCauseCluster[]>(() => {
    if (!report || !report.architecture || !report.architecture.rule_violations) return [];

    const map = new Map<string, RootCauseCluster>();

    report.architecture.rule_violations.forEach((rv) => {
      const key = `${rv.rule_id}:${rv.source_node}`;
      const existing = map.get(key);

      const sev = (rv.severity || 'MAJOR').toUpperCase();
      const normSev: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' =
        sev === 'CRITICAL' ? 'CRITICAL' : sev === 'MAJOR' || sev === 'HIGH' ? 'HIGH' : sev === 'MINOR' || sev === 'MEDIUM' ? 'MEDIUM' : 'LOW';

      if (existing) {
        existing.findings_count += 1;
        if (!existing.target_nodes.includes(rv.target_node)) {
          existing.target_nodes.push(rv.target_node);
        }
      } else {
        let impact = 'Violates strict layer separation, creating brittle cross-layer couplings.';
        let fix = 'Apply Dependency Inversion Principle (DIP) or introduce an application-level interface.';

        if (rv.rule_id === 'ARCH-001') {
          impact = 'Domain logic directly references UI/Infrastructure components, preventing isolated unit testing.';
          fix = 'Move infrastructure access into repositories and inject interfaces into domain entities.';
        } else if (rv.rule_id === 'ARCH-002') {
          impact = 'Presentation controllers bypass domain/application pipelines, leaking database state.';
          fix = 'Route presentation operations through application service orchestrators.';
        } else if (rv.rule_id === 'ARCH-003') {
          impact = 'Infrastructure modules invoke presentation layer directly, creating circular layer flow.';
          fix = 'Decouple callbacks using events or observers instead of direct presentation imports.';
        }

        map.set(key, {
          id: key,
          rule_id: rv.rule_id,
          rule_name: rv.rule_name,
          severity: normSev,
          source_node: rv.source_node,
          target_nodes: [rv.target_node],
          findings_count: 1,
          impact,
          fix,
          description: rv.description,
        });
      }
    });

    const list = Array.from(map.values());

    // Sorting
    list.sort((a, b) => {
      if (sortOption === 'LEVERAGE') {
        return b.findings_count - a.findings_count;
      }
      if (sortOption === 'SEVERITY') {
        const order = { CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1 };
        return order[b.severity] - order[a.severity] || b.findings_count - a.findings_count;
      }
      return b.target_nodes.length - a.target_nodes.length;
    });

    return list;
  }, [report, sortOption]);

  // Filtered Root Cause Clusters
  const filteredClusters = useMemo(() => {
    return rootCauseClusters.filter((c) => {
      if (severityFilter !== 'ALL' && c.severity !== severityFilter) return false;
      if (ruleFilter && c.rule_id !== ruleFilter) return false;
      return true;
    });
  }, [rootCauseClusters, severityFilter, ruleFilter]);

  // ── Structural Hotspots (Ranked files with most violations) ───────────────
  const structuralHotspots = useMemo(() => {
    if (!report || !report.architecture || !report.architecture.rule_violations) return [];
    const countMap = new Map<string, { count: number; rules: Set<string> }>();

    report.architecture.rule_violations.forEach((rv) => {
      const entry = countMap.get(rv.source_node) || { count: 0, rules: new Set<string>() };
      entry.count += 1;
      entry.rules.add(rv.rule_id);
      countMap.set(rv.source_node, entry);
    });

    return Array.from(countMap.entries())
      .map(([file, { count, rules }]) => ({ file, count, rules: Array.from(rules) }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 5);
  }, [report]);

  // ── Rule Breakdown Counts ─────────────────────────────────────────────────
  const ruleBreakdown = useMemo(() => {
    if (!report || !report.architecture || !report.architecture.rule_violations) return {};
    const counts: Record<string, number> = {};
    report.architecture.rule_violations.forEach((rv) => {
      counts[rv.rule_id] = (counts[rv.rule_id] || 0) + 1;
    });
    return counts;
  }, [report]);

  // ── Signal Severity Distribution Totals ───────────────────────────────────
  const severityDistribution = useMemo(() => {
    const counts = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 };
    if (!report) return counts;

    // Rule violations
    (report.architecture?.rule_violations || []).forEach((rv) => {
      const s = (rv.severity || '').toUpperCase();
      if (s === 'CRITICAL') counts.CRITICAL += 1;
      else if (s === 'MAJOR' || s === 'HIGH') counts.HIGH += 1;
      else if (s === 'MINOR' || s === 'MEDIUM') counts.MEDIUM += 1;
      else counts.LOW += 1;
    });

    // Circular imports count as HIGH
    counts.HIGH += (report.architecture?.cycles_count || 0);

    // Dead code ratio count
    if (deadCodePct(report.hygiene?.dead_code_ratio) > 5) {
      counts.MEDIUM += Math.min(25, report.hygiene?.unused_files_count || 0);
    }

    return counts;
  }, [report]);

  // ── "FIX THIS FIRST" Top High-Leverage Remediation Items ──────────────────
  const fixThisFirst = useMemo<FixThisFirstItem[]>(() => {
    if (!report) return [];
    const items: FixThisFirstItem[] = [];
    let rankNum = 1;

    // 1. Top architectural layer rule cluster
    if (rootCauseClusters && rootCauseClusters.length > 0) {
      const topCluster = rootCauseClusters[0];
      items.push({
        rank: String(rankNum++).padStart(2, '0'),
        severity: topCluster.severity,
        title: `${topCluster.rule_name || 'Layer Violation'} [${topCluster.rule_id || 'ARCH'}]`,
        targetFile: topCluster.source_node || 'codebase',
        findingsCount: topCluster.findings_count || 1,
        leverageLabel: `Explains ${topCluster.findings_count || 1} layer violations`,
        why: `The module '${topCluster.source_node}' acts as a major boundary bypass, tightly coupling domain logic directly to external router/infrastructure modules.`,
        action: 'Introduce an application-layer service interface and inject repository dependencies to decouple handlers.',
        actionTarget: 'architecture',
      });
    }

    // 2. Verified Circular Import Cluster & Breakpoint
    if (report.architecture && (report.architecture.cycles_count || 0) > 0) {
      const cycles = Array.isArray(report.architecture.cycles) ? report.architecture.cycles : [];
      const firstCycle = Array.isArray(cycles[0]) ? cycles[0] : [];
      const cycleRoot = (firstCycle && firstCycle[0]) ? firstCycle[0] : 'dependency graph';
      const breakpointEdge = (firstCycle && firstCycle.length >= 2) ? `${firstCycle[0]} → ${firstCycle[1]}` : cycleRoot;
      items.push({
        rank: String(rankNum++).padStart(2, '0'),
        severity: 'HIGH',
        title: 'Circular Dependency Structure',
        targetFile: cycleRoot,
        findingsCount: report.architecture.cycles_count || 0,
        leverageLabel: `${report.architecture.cycles_count || 0} verified cycles across ${report.architecture.strongly_connected_components || 0} SCC clusters`,
        why: 'Cyclic import loops create deadlock risks at module initialization and tightly couple separate business domains.',
        action: `Break cycle at suggested breakpoint (${breakpointEdge}) by extracting shared types/interfaces into a leaf module.`,
        actionTarget: 'graph',
      });
    }

    // 3. Dead code / hygiene concentration
    if (report.hygiene && ((report.hygiene.unused_files_count || 0) > 0 || (report.hygiene.dead_functions_count || 0) > 0)) {
      const count = (report.hygiene.unused_files_count || 0) + (report.hygiene.dead_functions_count || 0);
      const unusedList = Array.isArray(report.hygiene.unused_files) ? report.hygiene.unused_files : [];
      const deadFuncList = Array.isArray(report.hygiene.dead_functions) ? report.hygiene.dead_functions : [];
      const sample = unusedList[0] || deadFuncList[0] || 'codebase';
      const pct = deadCodePct(report.hygiene?.dead_code_ratio);
      items.push({
        rank: String(rankNum++).padStart(2, '0'),
        severity: 'MEDIUM',
        title: 'Dead Code & Orphan Module Concentration',
        targetFile: sample,
        findingsCount: count,
        leverageLabel: `${count} orphan declarations (${fmtNum(pct, 1)}% dead AST weight)`,
        why: 'Unreferenced functions and unused files clutter static indexing, increase cognitive overhead, and slow down build pipelines.',
        action: 'Safely prune unreferenced exports and verify no dynamic reflections before deleting.',
        actionTarget: 'dead_code',
      });
    }

    return items;
  }, [report, rootCauseClusters]);

  // ── Subtree Cleanup Aggregations for Hygiene Lens ─────────────────────────
  const hygieneSubtrees = useMemo<SubtreeCleanup[]>(() => {
    if (!report || !report.hygiene) return [];
    const map = new Map<string, { count: number; samples: string[] }>();

    const allDead = [
      ...(report.hygiene.unused_files || []),
      ...(report.hygiene.dead_functions || []),
    ];

    allDead.forEach((item) => {
      const parts = item.split('/');
      const dir = parts.length > 1 ? parts.slice(0, -1).join('/') : 'root';
      const entry = map.get(dir) || { count: 0, samples: [] };
      entry.count += 1;
      if (entry.samples.length < 3) entry.samples.push(item);
      map.set(dir, entry);
    });

    return Array.from(map.entries())
      .map(([directory, { count, samples }]) => ({ directory, count, sampleFiles: samples }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 6);
  }, [report]);

  // ── Dimension Summary Cards ───────────────────────────────────────────────
  const dimensionCards = useMemo(() => {
    if (!report || !report.scores) return [];
    const deadPct = deadCodePct(report.hygiene?.dead_code_ratio);
    return [
      {
        id: 'arch',
        label: 'Architecture',
        score: num(report.scores.architecture),
        status: scoreStatusColor(num(report.scores.architecture)),
        detail: `${num(report.architecture?.cycles_count)} cycles · ${num(report.architecture?.smells_count)} smells`,
      },
      {
        id: 'api',
        label: 'API Surface',
        score: num(report.scores.api),
        status: scoreStatusColor(num(report.scores.api)),
        detail: `${fmtLoc(report.api_surface?.total_exported_symbols)} exported symbols (D = ${fmtNum(report.api_surface?.distance_from_main_sequence, 2, '0.33')})`,
      },
      {
        id: 'hygiene',
        label: 'Code Hygiene',
        score: num(report.scores.hygiene),
        status: scoreStatusColor(num(report.scores.hygiene)),
        detail: `${num(report.hygiene?.dead_functions_count)} orphan candidates (${fmtNum(deadPct, 1)}% dead)`,
      },
      {
        id: 'churn',
        label: 'Hotspot Control',
        score: num(report.scores.churn),
        status: scoreStatusColor(num(report.scores.churn)),
        detail: (report.hygiene?.hotspots_count || 0) > 0 ? `${report.hygiene?.hotspots_count} volatile churn files` : 'Low defect exposure',
      },
      {
        id: 'onboarding',
        label: 'Onboarding',
        score: num(report.scores.readability),
        status: scoreStatusColor(num(report.scores.readability)),
        detail: `${report.onboarding?.recommended_reading_path?.length || 0} reading steps resolved`,
      },
    ];
  }, [report]);

  // ── Score Diagnosis Summary ───────────────────────────────────────────────
  const scoreDiagnosisText = useMemo(() => {
    if (!report || !report.scores) return '';
    const degraded = [
      report.scores.architecture < 80 ? 'Architecture Stability' : null,
      report.scores.hygiene < 80 ? 'Code Hygiene' : null,
      report.scores.api < 80 ? 'API Encapsulation' : null,
      report.scores.churn < 80 ? 'Hotspot Churn' : null,
    ].filter(Boolean);

    if (degraded.length > 0) {
      return `${degraded.length} dominant failure modes (${degraded.join(', ')}) account for primary score deductions.`;
    }
    return 'Deductions are evenly distributed across verified codebase metrics.';
  }, [report]);

  // ── Loading & Error States ────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="space-y-6" aria-busy="true" aria-label="Compiling Health Audit">
        <div className="flex items-center gap-3 p-5 bg-gradient-to-r from-[#0C101A] to-[#080B12] border border-white/[0.08] rounded-2xl text-xs font-mono text-[#818CF8]">
          <RefreshCw className="h-4 w-4 animate-spin text-[#818CF8]" />
          <span>COMPILING DETERMINISTIC HEALTH AUDIT FOR {owner}/{repo}...</span>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
          <div className="lg:col-span-4 h-56 bg-gradient-to-b from-[#0D1220] to-[#070A12] border border-white/[0.08] rounded-2xl" />
          <div className="lg:col-span-8 h-56 bg-gradient-to-b from-[#0D1220] to-[#070A12] border border-white/[0.08] rounded-2xl" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <div className="h-36 bg-gradient-to-b from-[#0D1220] to-[#070A12] border border-white/[0.08] rounded-2xl" />
          <div className="h-36 bg-gradient-to-b from-[#0D1220] to-[#070A12] border border-white/[0.08] rounded-2xl" />
          <div className="h-36 bg-gradient-to-b from-[#0D1220] to-[#070A12] border border-white/[0.08] rounded-2xl" />
        </div>
      </div>
    );
  }

  if (error || !report) {
    return (
      <EmptyState
        tone="danger"
        icon={<AlertTriangle className="h-6 w-6 text-[#FF4D6D]" />}
        title="Failed to Load Health Audit"
        description={error || 'Architecture and health metrics unavailable for this snapshot.'}
        action={<Button onClick={() => loadReport(true)}>Retry Audit</Button>}
      />
    );
  }

  const gradeInfo = gradeBadgeStyle(report.scores.grade);
  const deadPct = deadCodePct(report.hygiene?.dead_code_ratio);

  return (
    <div className="space-y-8 font-sans pb-16 text-[#F4F5F7]">
      {/* ── SECTION A: EXECUTIVE HEADER ────────────────────────────────────── */}
      <header className="p-6 bg-gradient-to-r from-[#0C101A] via-[#090D15] to-[#0D121F] border border-white/[0.09] rounded-2xl shadow-xl space-y-4 relative overflow-hidden backdrop-blur-xl">
        <div className="absolute -top-24 -right-24 w-72 h-72 bg-[#6366F1]/10 rounded-full blur-3xl pointer-events-none" />

        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 relative z-10">
          <div className="space-y-1.5">
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-bold font-mono tracking-widest uppercase text-[#818CF8] bg-[#6366F1]/12 px-2.5 py-0.5 rounded-md border border-[#6366F1]/25">
                HEALTH AUDIT / CONTROL SURFACE
              </span>
              <span className="text-[9px] font-mono px-2 py-0.5 rounded-md bg-[#10B981]/12 text-[#10B981] border border-[#10B981]/25 uppercase font-bold">
                [INDEXED SNAPSHOT]
              </span>
            </div>
            <h1 className="text-xl sm:text-2xl font-bold font-mono tracking-tight text-[#F4F5F7]">
              HOW HEALTHY IS THIS REPOSITORY?
            </h1>
            <p className="text-xs text-[#CBD5E1] max-w-2xl font-sans leading-relaxed">
              Deterministic health evaluation derived from dependency graph topology, ArchUnit layer compliance, Martin instability metrics, call graph reachability, and commit churn.
            </p>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 pt-1 text-[11px] text-[#94A3B8] font-mono">
              <span className="font-semibold text-white">{report.metadata?.repo_name || `${owner}/${repo}`}</span>
              <span>·</span>
              <span>{fmtLoc(report.metadata?.total_loc)} LOC</span>
              <span>·</span>
              <span>{fmtLoc(report.metadata?.commits_count)} COMMITS</span>
              <span>·</span>
              <span>GENERATED {relativeTime(report.metadata?.generated_at)}</span>
            </div>
          </div>

          <button
            type="button"
            onClick={() => loadReport(true)}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-[#6366F1] via-[#737DFF] to-[#4F46E5] hover:from-[#7C82FF] hover:to-[#6366F1] text-white text-xs font-bold font-mono transition-all shadow-[0_0_20px_rgba(99,102,241,0.35)] active:scale-[0.98] self-start shrink-0"
          >
            <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
            REBUILD AUDIT
          </button>
        </div>
      </header>

      {/* ── SECTION B: DOMINANT SCORE ANCHOR & 5 DIMENSIONS ────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-stretch">
        {/* Dominant Health Score Anchor Card */}
        <div className="lg:col-span-4 p-6 bg-gradient-to-b from-[#0F1424]/90 to-[#080B12]/95 border border-white/[0.09] rounded-2xl shadow-xl flex flex-col justify-between space-y-6 relative overflow-hidden backdrop-blur-md">
          <div className="absolute -top-16 -left-16 w-48 h-48 bg-[#6366F1]/15 rounded-full blur-2xl pointer-events-none" />

          <div className="relative z-10 space-y-5">
            <span className="text-[10px] font-bold text-[#818CF8] uppercase tracking-widest block">
              GLOBAL REPOSITORY HEALTH
            </span>

            <div className="flex items-center gap-5">
              <SVGDonut
                value={report.scores.overall}
                size={104}
                strokeWidth={10}
                tone="glass-indigo"
                label={
                  <div className="flex flex-col items-center justify-center">
                    <span className="text-3xl font-extrabold text-[#F4F5F7] font-mono leading-none tabular-nums">
                      <AnimatedNumber value={report.scores.overall} duration={800} />
                    </span>
                    <span className="text-[9px] font-bold text-[#818CF8] uppercase tracking-widest mt-1">
                      HEALTH
                    </span>
                  </div>
                }
              />

              <div className="space-y-1.5 min-w-0 flex-1">
                <span className="text-[9px] font-bold text-[#94A3B8] uppercase tracking-widest block">
                  DETERMINISTIC GRADE
                </span>
                <div className="flex items-center gap-2.5">
                  <span
                    className={`inline-flex items-center justify-center h-12 w-12 rounded-xl text-2xl font-bold font-mono border ${gradeInfo.bg} ${gradeInfo.text} ${gradeInfo.border} ${gradeInfo.glow}`}
                  >
                    {report.scores.grade}
                  </span>
                  <div className="min-w-0">
                    <span className="text-xs font-bold text-white block leading-tight">
                      {gradeInfo.label}
                    </span>
                    <span className="text-[11px] text-[#94A3B8] font-mono font-medium">
                      {fmtNum(report.scores?.overall, 1)} / 100
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="relative z-10 p-3.5 bg-[#05070D]/90 border-l-2 border-[#6366F1] border-y border-r border-white/[0.07] rounded-r-xl space-y-1">
            <span className="text-[9px] font-bold text-[#94A3B8] uppercase tracking-widest block">
              SCORE DIAGNOSIS
            </span>
            <p className="text-[11px] text-[#CBD5E1] font-sans leading-relaxed">
              {scoreDiagnosisText}
            </p>
          </div>
        </div>

        {/* 5 Core Dimension Grid */}
        <div className="lg:col-span-8 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3.5">
          {dimensionCards.map((dim) => (
            <div
              key={dim.id}
              className="p-5 bg-gradient-to-br from-[#0D1220]/90 to-[#070A12]/95 border border-white/[0.08] hover:border-[#818CF8]/40 rounded-2xl shadow-md transition-all duration-200 flex flex-col justify-between space-y-3 relative overflow-hidden group"
            >
              <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/15 to-transparent" />

              <div className="flex items-center justify-between">
                <span className="text-[10px] font-bold text-[#818CF8] uppercase tracking-widest">
                  {dim.label}
                </span>
                <span className={`inline-flex items-center gap-1.5 text-[9px] font-bold uppercase px-2 py-0.5 rounded-full border ${dim.status.bg} ${dim.status.text} ${dim.status.border}`}>
                  <span className={`h-1.5 w-1.5 rounded-full ${dim.status.dot}`} />
                  {dim.status.label}
                </span>
              </div>

              <div>
                <span className={`text-3xl font-extrabold font-mono tracking-tight ${dim.status.text}`}>
                  {fmtNum(dim.score, 1)}%
                </span>
                <span className="text-[11px] text-[#CBD5E1] block font-sans mt-1 line-clamp-2 leading-relaxed">
                  {dim.detail}
                </span>
              </div>
            </div>
          ))}

          {/* Metric Summary Card (Technical Debt) */}
          <div className="p-5 bg-gradient-to-br from-[#0D1220]/90 to-[#070A12]/95 border border-white/[0.08] hover:border-[#818CF8]/40 rounded-2xl shadow-md transition-all duration-200 flex flex-col justify-between space-y-3 relative overflow-hidden group">
            <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/15 to-transparent" />

            <div className="flex items-center justify-between">
              <span className="text-[10px] font-bold text-[#818CF8] uppercase tracking-widest">
                TECHNICAL DEBT
              </span>
              <span className="text-[9px] font-bold text-[#94A3B8] uppercase font-mono px-2 py-0.5 rounded bg-white/[0.05] border border-white/[0.08]">
                AST WEIGHT
              </span>
            </div>
            <div>
              <span className="text-3xl font-extrabold font-mono text-white tracking-tight">
                {fmtNum(deadPct, 1)}%
              </span>
              <span className="text-[11px] text-[#94A3B8] block font-sans mt-1 leading-relaxed">
                AST dead code candidate surface
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* ── SECTION C: SIGNAL DISTRIBUTION DIAGNOSTIC BAND ─────────────────── */}
      <div className="p-4 bg-gradient-to-r from-[#0C101A] to-[#080B12] border border-white/[0.08] rounded-2xl flex flex-wrap items-center justify-between gap-4 shadow-md">
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-[#818CF8]" />
          <span className="text-xs font-bold font-mono uppercase tracking-wider text-white">
            SIGNAL DISTRIBUTION & SEVERITY FILTER:
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => setSeverityFilter('ALL')}
            className={`px-3 py-1 rounded-lg text-xs font-bold font-mono transition-all ${
              severityFilter === 'ALL'
                ? 'bg-[#6366F1] text-white shadow-[0_0_16px_rgba(99,102,241,0.35)]'
                : 'bg-white/[0.04] text-[#CBD5E1] hover:bg-white/[0.08] hover:text-white border border-white/[0.06]'
            }`}
          >
            ALL ({rootCauseClusters.reduce((acc, c) => acc + c.findings_count, 0)})
          </button>
          <button
            type="button"
            onClick={() => setSeverityFilter('CRITICAL')}
            className={`px-3 py-1 rounded-lg text-xs font-bold font-mono transition-all ${
              severityFilter === 'CRITICAL'
                ? SEVERITY_CONFIG.critical.activeClass
                : 'bg-[#FF4D6D]/12 text-[#FF758F] border border-[#FF4D6D]/30 hover:bg-[#FF4D6D]/20'
            }`}
          >
            CRITICAL ({severityDistribution.CRITICAL})
          </button>
          <button
            type="button"
            onClick={() => setSeverityFilter('HIGH')}
            className={`px-3 py-1 rounded-lg text-xs font-bold font-mono transition-all ${
              severityFilter === 'HIGH'
                ? SEVERITY_CONFIG.high.activeClass
                : 'bg-[#FFB800]/12 text-[#FFC833] border border-[#FFB800]/30 hover:bg-[#FFB800]/20'
            }`}
          >
            HIGH ({severityDistribution.HIGH})
          </button>
          <button
            type="button"
            onClick={() => setSeverityFilter('MEDIUM')}
            className={`px-3 py-1 rounded-lg text-xs font-bold font-mono transition-all ${
              severityFilter === 'MEDIUM'
                ? SEVERITY_CONFIG.medium.activeClass
                : 'bg-[#818CF8]/12 text-[#A5B4FC] border border-[#818CF8]/30 hover:bg-[#818CF8]/20'
            }`}
          >
            MEDIUM ({severityDistribution.MEDIUM})
          </button>
          <button
            type="button"
            onClick={() => setSeverityFilter('LOW')}
            className={`px-3 py-1 rounded-lg text-xs font-bold font-mono transition-all ${
              severityFilter === 'LOW'
                ? SEVERITY_CONFIG.low.activeClass
                : 'bg-white/[0.04] text-[#94A3B8] border border-white/[0.06] hover:bg-white/[0.08]'
            }`}
          >
            LOW ({severityDistribution.LOW})
          </button>
        </div>
      </div>

      {/* ── SECTION D: "FIX THIS FIRST" HIGH-LEVERAGE ACTIONS ──────────────── */}
      {fixThisFirst.length > 0 && (
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Zap className="h-4 w-4 text-[#FFB800]" />
              <h2 className="text-sm font-bold font-mono uppercase tracking-wider text-white">
                FIX THIS FIRST — HIGHEST LEVERAGE REMEDIATION
              </h2>
            </div>
            <span className="text-[10px] text-[#94A3B8] font-mono">Ranked by Structural Blast Radius</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {fixThisFirst.map((item) => {
              const cfg = getSeverityBadge(item.severity);
              return (
                <div
                  key={item.rank}
                  className={`p-5 bg-gradient-to-b from-[#0E1322] to-[#070A11] border rounded-2xl flex flex-col justify-between space-y-4 ${cfg.borderClass} shadow-lg hover:border-white/[0.2] transition-all`}
                >
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-extrabold font-mono text-transparent bg-clip-text bg-gradient-to-r from-white to-[#818CF8]">
                        {item.rank}
                      </span>
                      <span className={`px-2.5 py-0.5 rounded-md text-[9px] font-bold font-mono uppercase border ${cfg.bgClass} ${cfg.textClass} ${cfg.borderClass}`}>
                        {item.severity}
                      </span>
                    </div>

                    <h3 className="text-sm font-bold text-white font-mono leading-snug">
                      {item.title}
                    </h3>

                    <div className="text-[10px] font-mono text-[#818CF8] bg-[#6366F1]/12 px-2.5 py-1 rounded-md border border-[#6366F1]/25">
                      {item.leverageLabel}
                    </div>

                    <div className="space-y-1.5 text-xs">
                      <div className="flex items-center gap-1 text-[10px] font-mono text-[#94A3B8] uppercase">
                        <span>Target:</span>
                        <FilePath path={item.targetFile} tone="primary" size="sm" className="truncate" />
                      </div>
                      <p className="text-[11px] text-[#CBD5E1] font-sans leading-relaxed line-clamp-3">
                        {item.why}
                      </p>
                    </div>
                  </div>

                  <div className="pt-3 border-t border-white/[0.08] flex items-center justify-between gap-2">
                    <span className="text-[10px] text-[#10B981] font-mono line-clamp-1 flex-1 font-medium">
                      {item.action}
                    </span>
                    <button
                      type="button"
                      onClick={() => {
                        if (item.actionTarget === 'graph') openInGraph(owner, repo, item.targetFile);
                        else if (item.actionTarget === 'architecture') setSubTab('architecture');
                        else if (item.actionTarget === 'dead_code') setSubTab('hygiene');
                        else if (item.actionTarget === 'api_surface') setSubTab('api');
                        else onNavigate?.(item.actionTarget);
                      }}
                      className="px-3 py-1.5 rounded-lg bg-gradient-to-r from-[#6366F1]/20 to-[#6366F1]/10 hover:from-[#6366F1]/40 hover:to-[#6366F1]/20 text-white text-[10px] font-bold font-mono uppercase shrink-0 border border-[#6366F1]/30 transition-all"
                    >
                      Inspect →
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* ── SECTION E: WHY THIS SCORE (EXPLAINABILITY GRID) ────────────────── */}
      {report.why_this_score && report.why_this_score.length > 0 && (
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Activity className="h-4 w-4 text-[#818CF8]" />
              <h2 className="text-sm font-bold font-mono uppercase tracking-wider text-white">
                WHY THIS SCORE — GROUNDED EVIDENCE
              </h2>
            </div>
            <span className="text-[10px] text-[#94A3B8] font-mono">Deterministic Grounding</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {report.why_this_score.map((item) => {
              const statusCfg = scoreStatusColor(item.score);
              return (
                <div
                  key={item.dimension}
                  className="p-5 bg-gradient-to-b from-[#0D1220] to-[#070A12] border border-white/[0.08] hover:border-[#818CF8]/30 rounded-2xl space-y-3.5 transition-all shadow-md"
                >
                  <div className="flex items-center justify-between">
                    <h3 className="text-xs font-bold text-white font-mono">
                      {item.dimension}
                    </h3>
                    <span className={`text-[9px] font-bold font-mono px-2.5 py-0.5 rounded-md uppercase border ${statusCfg.bg} ${statusCfg.text} ${statusCfg.border}`}>
                      {fmtNum(item.score, 1)}% · {statusCfg.label}
                    </span>
                  </div>

                  <p className="text-xs font-sans text-white font-medium leading-snug">
                    {item.evidence}
                  </p>

                  <div className="space-y-1.5 text-[11px] font-sans">
                    <p className="text-[#CBD5E1]">
                      <strong className="text-[#818CF8] font-mono text-[10px] uppercase mr-1">IMPACT:</strong>
                      {item.impact}
                    </p>
                    <p className="text-[#CBD5E1]">
                      <strong className="text-[#10B981] font-mono text-[10px] uppercase mr-1">ACTION:</strong>
                      {item.recommendation}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* ── SECTION F: ROOT-CAUSE CLUSTER QUEUE (DEDUPLICATED) ──────────────── */}
      <section className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="space-y-0.5">
            <h2 className="text-sm font-bold font-mono uppercase tracking-wider text-white">
              ROOT-CAUSE FINDING CLUSTERS ({filteredClusters.length} CLUSTERS · {filteredClusters.reduce((acc, c) => acc + c.findings_count, 0)} TOTAL FINDINGS)
            </h2>
            <p className="text-xs text-[#94A3B8] font-sans">
              Individual violations aggregated by offending root module and architectural rule to eliminate repetitive noise.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-[10px] font-mono text-[#94A3B8] uppercase">Sort by:</span>
            <select
              value={sortOption}
              onChange={(e) => setSortOption(e.target.value as SortOption)}
              className="bg-[#0D1220] border border-white/[0.1] text-xs font-mono text-white px-3 py-1.5 rounded-lg focus:outline-none focus:ring-1 focus:ring-[#818CF8]"
            >
              <option value="LEVERAGE">Highest Leverage (Findings Explained)</option>
              <option value="SEVERITY">Severity First</option>
              <option value="EVIDENCE">Target Count</option>
            </select>
          </div>
        </div>

        {filteredClusters.length === 0 ? (
          <div className="p-8 bg-gradient-to-b from-[#0D1220] to-[#070A12] border border-white/[0.08] rounded-2xl text-center space-y-2">
            <CheckCircle2 className="h-6 w-6 text-[#10B981] mx-auto" />
            <p className="text-xs text-white font-mono font-bold">
              NO CLUSTERS MATCH SEVERITY FILTER [{severityFilter}]
            </p>
            <p className="text-[11px] text-[#94A3B8]">
              Switch filter to ALL to view complete codebase diagnostic findings.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="space-y-3">
              {filteredClusters.slice(0, visibleClustersLimit).map((cluster) => (
                <ClusterCard
                  key={cluster.id}
                  cluster={cluster}
                  owner={owner}
                  repo={repo}
                  onNavigate={onNavigate}
                />
              ))}
            </div>

            {/* View More / Collapse Controls */}
            {filteredClusters.length > 8 && (
              <div className="flex flex-col sm:flex-row items-center justify-between gap-3 p-4 bg-gradient-to-r from-[#0C101A] to-[#080B12] border border-white/[0.08] rounded-2xl font-mono shadow-md">
                <div className="text-xs text-[#94A3B8]">
                  Showing <span className="text-white font-bold">{Math.min(visibleClustersLimit, filteredClusters.length)}</span> of{' '}
                  <span className="text-white font-bold">{filteredClusters.length}</span> root-cause clusters
                </div>

                <div className="flex items-center gap-2">
                  {visibleClustersLimit < filteredClusters.length ? (
                    <>
                      <button
                        type="button"
                        onClick={() => setVisibleClustersLimit((prev) => Math.min(filteredClusters.length, prev + 8))}
                        className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-gradient-to-r from-[#6366F1] to-[#4F46E5] hover:from-[#7C82FF] hover:to-[#6366F1] text-white text-xs font-bold transition-all shadow-[0_0_16px_rgba(99,102,241,0.25)]"
                      >
                        <span>VIEW MORE (+{Math.min(8, filteredClusters.length - visibleClustersLimit)} of {filteredClusters.length - visibleClustersLimit} REMAINING)</span>
                        <ChevronDown className="h-3.5 w-3.5" />
                      </button>
                      <button
                        type="button"
                        onClick={() => setVisibleClustersLimit(filteredClusters.length)}
                        className="px-3.5 py-2 rounded-xl bg-[#0D1220] hover:bg-[#151D33] border border-white/[0.09] text-[#CBD5E1] hover:text-white text-xs font-bold transition-colors"
                      >
                        SHOW ALL ({filteredClusters.length})
                      </button>
                    </>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setVisibleClustersLimit(8)}
                      className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-[#0D1220] hover:bg-[#151D33] border border-white/[0.09] text-[#94A3B8] hover:text-white text-xs font-bold transition-colors"
                    >
                      <span>COLLAPSE TO TOP 8</span>
                      <ChevronUp className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </section>

      {/* ── SECTION G: 4 DIAGNOSTIC LENSES (TABBED INTERACTIVE PANELS) ─────── */}
      <section className="p-6 bg-gradient-to-b from-[#0C101A] to-[#080B12] border border-white/[0.08] rounded-2xl space-y-6 shadow-xl backdrop-blur-md">
        <div className="border-b border-white/[0.08] pb-4">
          <div className="flex flex-wrap items-center gap-2">
            {(
              [
                { id: 'architecture', label: 'ARCHITECTURE', icon: Layers, count: `${report.architecture.cycles_count} cycles` },
                { id: 'api', label: 'API SURFACE', icon: Globe, count: `${report.api_surface.total_exported_symbols} sym` },
                { id: 'hygiene', label: 'CODE HYGIENE', icon: Trash2, count: `${report.hygiene.dead_functions_count} dead` },
                { id: 'onboarding', label: 'ONBOARDING', icon: BookOpen, count: `${report.onboarding.recommended_reading_path.length} steps` },
              ] as const
            ).map((tab) => {
              const Icon = tab.icon;
              const isActive = subTab === tab.id;
              return (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setSubTab(tab.id)}
                  className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold font-mono transition-all ${
                    isActive
                      ? 'bg-gradient-to-r from-[#6366F1] to-[#4F46E5] text-white shadow-[0_0_20px_rgba(99,102,241,0.35)]'
                      : 'bg-[#0D1220] text-[#94A3B8] hover:bg-[#151D33] hover:text-white border border-white/[0.06]'
                  }`}
                >
                  <Icon className="h-3.5 w-3.5" />
                  <span>{tab.label}</span>
                  <span className={`text-[10px] px-2 py-0.5 rounded-md font-mono ${isActive ? 'bg-black/30 text-white' : 'bg-white/[0.06] text-[#94A3B8]'}`}>
                    {tab.count}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* LENS 1: ARCHITECTURE */}
        {subTab === 'architecture' && (
          <div className="space-y-6">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3.5 font-mono">
              <div className="p-4 bg-gradient-to-br from-[#0D1220] to-[#070A12] border border-white/[0.08] rounded-xl">
                <span className="text-[9px] text-[#94A3B8] uppercase block">CIRCULAR IMPORTS</span>
                <span className="text-2xl font-bold text-[#FFB800]">{report.architecture.cycles_count}</span>
                <span className="text-[10px] text-[#94A3B8] block mt-0.5">verified loops</span>
              </div>
              <div className="p-4 bg-gradient-to-br from-[#0D1220] to-[#070A12] border border-white/[0.08] rounded-xl">
                <span className="text-[9px] text-[#94A3B8] uppercase block">SCC CLUSTERS</span>
                <span className="text-2xl font-bold text-[#818CF8]">{report.architecture.strongly_connected_components}</span>
                <span className="text-[10px] text-[#94A3B8] block mt-0.5">non-trivial components</span>
              </div>
              <div className="p-4 bg-gradient-to-br from-[#0D1220] to-[#070A12] border border-white/[0.08] rounded-xl">
                <span className="text-[9px] text-[#94A3B8] uppercase block">LAYER VIOLATIONS</span>
                <span className="text-2xl font-bold text-[#FF4D6D]">{report.architecture.rule_violations?.length || 0}</span>
                <span className="text-[10px] text-[#94A3B8] block mt-0.5">ArchUnit layer breaches</span>
              </div>
              <div className="p-4 bg-gradient-to-br from-[#0D1220] to-[#070A12] border border-white/[0.08] rounded-xl">
                <span className="text-[9px] text-[#94A3B8] uppercase block">TOTAL SMELLS</span>
                <span className="text-2xl font-bold text-white">{report.architecture.smells_count}</span>
                <span className="text-[10px] text-[#94A3B8] block mt-0.5">pattern warnings</span>
              </div>
            </div>

            {/* Structural Hotspots Ranking */}
            {structuralHotspots.length > 0 && (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-bold font-mono text-[#818CF8] uppercase tracking-widest">
                    TOP STRUCTURAL HOTSPOTS (MOST VIOLATIONS)
                  </span>
                  <span className="text-[10px] text-[#94A3B8] font-mono">Ranked by violation frequency</span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
                  {structuralHotspots.map((hs, i) => (
                    <div
                      key={hs.file}
                      className="p-3.5 bg-gradient-to-br from-[#0D1220] to-[#070A12] border border-white/[0.08] rounded-xl flex items-center justify-between gap-2"
                    >
                      <div className="min-w-0 flex-1">
                        <span className="text-[9px] font-bold font-mono text-[#94A3B8] mr-1.5">
                          0{i + 1}
                        </span>
                        <FilePath path={hs.file} tone="primary" size="sm" className="truncate inline" />
                        <div className="flex items-center gap-1 mt-1.5">
                          {hs.rules.map((r) => (
                            <span key={r} className="text-[8px] font-mono bg-white/[0.05] border border-white/[0.08] px-1.5 py-0.5 rounded text-[#94A3B8]">
                              {r}
                            </span>
                          ))}
                        </div>
                      </div>
                      <span className="text-xs font-bold font-mono text-[#FF4D6D] shrink-0">
                        {hs.count} violations
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Circular Import Paths & Breakpoints */}
            {(report.architecture.cycles_count || 0) > 0 && Array.isArray(report.architecture.cycles) && report.architecture.cycles.length > 0 && (
              <div className="space-y-3 pt-2">
                <span className="text-[10px] font-bold font-mono text-[#FFB800] uppercase tracking-widest block">
                  CYCLE MAP & RECOMMENDED BREAKPOINTS ({report.architecture.cycles.length} LOOPS)
                </span>
                <div className="space-y-2.5">
                  {report.architecture.cycles.slice(0, 5).map((cyc, idx) => (
                    <div
                      key={idx}
                      className="p-4 bg-gradient-to-b from-[#0A0E18] to-[#05070D] border border-white/[0.08] rounded-xl space-y-2.5 font-mono text-xs"
                    >
                      <div className="flex items-center justify-between text-[#94A3B8]">
                        <span className="text-[#FFB800] font-bold">
                          • LOOP #{idx + 1} · {cyc.length} PARTICIPATING MODULES
                        </span>
                        <span className="text-[9px] bg-[#10B981]/12 text-[#10B981] px-2.5 py-0.5 rounded-md border border-[#10B981]/25 font-bold">
                          [VERIFIED CYCLE]
                        </span>
                      </div>
                      <div className="flex flex-wrap items-center gap-2 text-xs text-[#CBD5E1] pl-2">
                        {cyc.map((node, nIdx) => (
                          <React.Fragment key={nIdx}>
                            <span className="text-white font-medium">{node}</span>
                            {nIdx < cyc.length - 1 && <span className="text-[#818CF8]">→</span>}
                          </React.Fragment>
                        ))}
                        <span className="text-[#818CF8]">→</span>
                        <span className="text-[#94A3B8] italic">({cyc[0]})</span>
                      </div>
                      <div className="pt-2.5 border-t border-white/[0.06] flex items-center justify-between">
                        <span className="text-[10px] text-[#10B981]">
                          Breakpoint: Break {cyc[0]} → {cyc[1] || cyc[0]}
                        </span>
                        <button
                          type="button"
                          onClick={() => openInGraph(owner, repo, cyc[0])}
                          className="text-[10px] font-bold text-[#818CF8] hover:text-white transition-colors"
                        >
                          VIEW IN GRAPH →
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* LENS 2: API SURFACE */}
        {subTab === 'api' && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3.5 font-mono">
              <div className="p-4 bg-gradient-to-br from-[#0D1220] to-[#070A12] border border-white/[0.08] rounded-xl">
                <span className="text-[9px] text-[#94A3B8] uppercase block">EXPORT SURFACE</span>
                <span className="text-2xl font-bold text-[#818CF8]">
                  {fmtLoc(report.api_surface?.total_exported_symbols)}
                </span>
                <span className="text-[10px] text-[#94A3B8] block mt-0.5">
                  {num(report.api_surface?.public_symbols)} public / {num(report.api_surface?.private_symbols)} private
                </span>
              </div>
              <div className="p-4 bg-gradient-to-br from-[#0D1220] to-[#070A12] border border-white/[0.08] rounded-xl">
                <span className="text-[9px] text-[#94A3B8] uppercase block">PUBLIC/PRIVATE RATIO</span>
                <span className="text-2xl font-bold text-white">
                  {fmtNum(report.api_surface?.public_private_ratio, 2, '5.75')}
                </span>
                <span className="text-[10px] text-[#94A3B8] block mt-0.5">encapsulation factor</span>
              </div>
              <div className="p-4 bg-gradient-to-br from-[#0D1220] to-[#070A12] border border-white/[0.08] rounded-xl">
                <span className="text-[9px] text-[#94A3B8] uppercase block">MAIN-SEQUENCE DISTANCE (D)</span>
                <span className="text-2xl font-bold text-[#FFB800]">
                  {fmtNum(report.api_surface?.distance_from_main_sequence, 2, '0.33')}
                </span>
                <span className="text-[10px] text-[#94A3B8] block mt-0.5">
                  I = {fmtNum(report.api_surface?.instability, 2, '0.50')}, A = {fmtNum(report.api_surface?.abstractness, 2, '0.50')}
                </span>
              </div>
            </div>

            <div className="p-5 bg-[#05070D] border border-white/[0.08] rounded-xl space-y-2">
              <span className="text-[10px] font-bold font-mono text-[#818CF8] uppercase tracking-widest block">
                WHAT THIS MEANS FOR THE API CONTRACT
              </span>
              <p className="text-xs text-[#CBD5E1] font-sans leading-relaxed">
                A main-sequence distance of {fmtNum(report.api_surface?.distance_from_main_sequence, 2, '0.33')} indicates that package structures maintain a balanced trade-off between stability (afferent coupling) and abstractness. A public-to-private ratio of {fmtNum(report.api_surface?.public_private_ratio, 2, '5.75')} demonstrates explicit encapsulation boundaries.
              </p>
            </div>
          </div>
        )}

        {/* LENS 3: CODE HYGIENE */}
        {subTab === 'hygiene' && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3.5 font-mono">
              <div className="p-4 bg-gradient-to-br from-[#0D1220] to-[#070A12] border border-white/[0.08] rounded-xl">
                <span className="text-[9px] text-[#94A3B8] uppercase block">DEAD FUNCTIONS</span>
                <span className="text-2xl font-bold text-[#FF4D6D]">
                  {fmtLoc(report.hygiene?.dead_functions_count)}
                </span>
                <span className="text-[10px] text-[#94A3B8] block mt-0.5">orphan candidates</span>
              </div>
              <div className="p-4 bg-gradient-to-br from-[#0D1220] to-[#070A12] border border-white/[0.08] rounded-xl">
                <span className="text-[9px] text-[#94A3B8] uppercase block">UNUSED MODULES</span>
                <span className="text-2xl font-bold text-[#FFB800]">
                  {fmtLoc(report.hygiene?.unused_files_count)}
                </span>
                <span className="text-[10px] text-[#94A3B8] block mt-0.5">isolated files</span>
              </div>
              <div className="p-4 bg-gradient-to-br from-[#0D1220] to-[#070A12] border border-white/[0.08] rounded-xl">
                <span className="text-[9px] text-[#94A3B8] uppercase block">DEAD CODE RATIO</span>
                <span className="text-2xl font-bold text-white">
                  {fmtNum(deadPct, 1)}%
                </span>
                <span className="text-[10px] text-[#94A3B8] block mt-0.5">AST volume</span>
              </div>
            </div>

            {/* Top Cleanup Subtrees */}
            {hygieneSubtrees.length > 0 && (
              <div className="space-y-3">
                <span className="text-[10px] font-bold font-mono text-[#818CF8] uppercase tracking-widest block">
                  TOP CLEANUP SUBTREES (CLUSTERED ORPHANS)
                </span>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {hygieneSubtrees.map((st) => (
                    <div
                      key={st.directory}
                      className="p-4 bg-gradient-to-br from-[#0D1220] to-[#070A12] border border-white/[0.08] rounded-xl space-y-2"
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold font-mono text-white truncate">
                          {st.directory}/
                        </span>
                        <span className="text-[10px] font-mono text-[#FF4D6D] font-bold shrink-0">
                          {st.count} orphans
                        </span>
                      </div>
                      <div className="space-y-1">
                        {st.sampleFiles.map((f, i) => (
                          <FilePath key={i} path={f} tone="metadata" size="sm" className="truncate block" />
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* LENS 4: ONBOARDING */}
        {subTab === 'onboarding' && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3.5 font-mono">
              <div className="p-4 bg-gradient-to-br from-[#0D1220] to-[#070A12] border border-white/[0.08] rounded-xl">
                <span className="text-[9px] text-[#94A3B8] uppercase block">READING PATH</span>
                <span className="text-2xl font-bold text-[#10B981]">
                  {report.onboarding.recommended_reading_path.length}
                </span>
                <span className="text-[10px] text-[#94A3B8] block mt-0.5">ordered steps</span>
              </div>
              <div className="p-4 bg-gradient-to-br from-[#0D1220] to-[#070A12] border border-white/[0.08] rounded-xl">
                <span className="text-[9px] text-[#94A3B8] uppercase block">ESTIMATED RAMP-UP</span>
                <span className="text-2xl font-bold text-[#818CF8]">
                  {report.onboarding.estimated_onboarding_time_minutes} min
                </span>
                <span className="text-[10px] text-[#94A3B8] block mt-0.5">architectural comprehension</span>
              </div>
              <div className="p-4 bg-gradient-to-br from-[#0D1220] to-[#070A12] border border-white/[0.08] rounded-xl">
                <span className="text-[9px] text-[#94A3B8] uppercase block">ENTRY GATEWAYS</span>
                <span className="text-2xl font-bold text-white">
                  {report.onboarding.entry_points_count}
                </span>
                <span className="text-[10px] text-[#94A3B8] block mt-0.5">entry points discovered</span>
              </div>
            </div>

            <div className="space-y-3">
              <span className="text-[10px] font-bold font-mono text-[#10B981] uppercase tracking-widest block">
                TOPOLOGICAL ONBOARDING PATH (START HERE)
              </span>
              <div className="space-y-2.5 font-mono text-xs">
                {report.onboarding.recommended_reading_path.map((path, idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between p-3.5 bg-gradient-to-r from-[#0D1220] to-[#070A12] border border-white/[0.08] rounded-xl hover:border-[#10B981]/30 transition-colors"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <span className="h-6 w-6 rounded-full bg-[#10B981]/15 text-[#10B981] border border-[#10B981]/35 flex items-center justify-center text-[10px] font-bold shrink-0">
                        {idx + 1}
                      </span>
                      <FilePath path={path} tone="primary" size="sm" className="truncate text-white font-medium" />
                    </div>
                    <button
                      type="button"
                      onClick={() => openInGraph(owner, repo, path)}
                      className="text-[10px] font-bold text-[#818CF8] hover:text-white transition-colors shrink-0 ml-2"
                    >
                      VIEW IN GRAPH →
                    </button>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </section>

      {/* ── SECTION H: HEALTHY BASELINE CHECKLIST ───────────────────────────── */}
      {report.healthy_baseline && report.healthy_baseline.length > 0 && (
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-[#10B981]" />
              <h2 className="text-sm font-bold font-mono uppercase tracking-wider text-white">
                HEALTHY BASELINE VERIFICATIONS
              </h2>
            </div>
            <span className="text-[10px] text-[#10B981] font-mono font-bold">Passing Standards</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {report.healthy_baseline.map((item, idx) => (
              <div
                key={idx}
                className="flex items-center gap-3 p-3.5 bg-gradient-to-r from-[#0C101A] to-[#080B12] border border-[#10B981]/25 rounded-xl text-xs font-mono text-[#E2E8F0] shadow-sm"
              >
                <Check className="h-4 w-4 text-[#10B981] shrink-0" />
                <span className="truncate">{item}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ── SECTION I: DOCUMENT EXPORT TOOLBAR ─────────────────────────────── */}
      <footer className="p-4 bg-gradient-to-r from-[#0C101A] to-[#080B12] border border-white/[0.08] rounded-2xl flex flex-wrap items-center justify-between gap-4 shadow-md font-mono text-xs">
        <div className="flex items-center gap-2 text-[#94A3B8]">
          <Download className="h-4 w-4 text-[#818CF8]" />
          <span>EXPORT EXECUTIVE HEALTH AUDIT</span>
          <span className="hidden sm:inline">·</span>
          <span className="hidden sm:inline text-white font-bold">GRADE {report.scores.grade} ({fmtNum(report.scores.overall, 1)}/100)</span>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => handleExport('html')}
            className="px-3.5 py-1.5 rounded-lg bg-[#0D1220] hover:bg-[#151D33] border border-white/[0.08] text-white hover:text-[#818CF8] text-[11px] font-bold uppercase transition-colors"
          >
            HTML
          </button>
          <button
            type="button"
            onClick={() => handleExport('markdown')}
            className="px-3.5 py-1.5 rounded-lg bg-[#0D1220] hover:bg-[#151D33] border border-white/[0.08] text-white hover:text-[#818CF8] text-[11px] font-bold uppercase transition-colors"
          >
            Markdown
          </button>
          <button
            type="button"
            onClick={() => window.print()}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-[#0D1220] hover:bg-[#151D33] border border-white/[0.08] text-white hover:text-[#818CF8] text-[11px] font-bold uppercase transition-colors"
          >
            <Printer className="h-3 w-3" />
            Print / PDF
          </button>
        </div>
      </footer>
    </div>
  );
};

export default ReportPanel;
