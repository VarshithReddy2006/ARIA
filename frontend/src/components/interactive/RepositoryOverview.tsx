import React, { useMemo, useState } from 'react';
import {
  ShieldCheck, Package, DoorOpen, Layers3, Clock, Boxes, Code2,
  RefreshCcwDot, FileText, FlaskConical, Globe, AlertTriangle,
  CheckCircle2, Info, XCircle, ArrowRight, Search, X, Workflow,
  Sparkles, FolderTree, Activity, Compass, Terminal, Zap, BookOpen,
  GitMerge, ChevronRight, Check, CheckCircle,
} from 'lucide-react';
import { AnimatedNumber } from '../ui/AnimatedNumber';
import { Meter } from '../ui/Meter';
import { FilePath } from '../ui/FilePath';
import { EmptyState } from '../ui/EmptyState';
import { groupTech, TONE_DOT, TONE_CHIP } from '../../lib/techCategories';
import type { Insight, InsightIcon, InsightSeverity } from '../../lib/repoInsights';
import { formatDuration, type ComplexityResult } from '../../lib/repoMetrics';
import { healthTone, type RepoHealth } from './RepoHero';
import { deriveRepoBrief, type RepoBrief } from '../../lib/repoBrief';

// ── Types ───────────────────────────────────────────────────────────────────

export type OverviewTabTarget =
  | 'analysis'
  | 'reading_path'
  | 'chat'
  | 'graph'
  | 'call_graph'
  | 'api_surface'
  | 'report'
  | 'dead_code'
  | 'issues'
  | 'git_history'
  | 'pr_intelligence'
  | 'architecture_drift'
  | 'impact_analysis';

export interface ComponentRelationship {
  source: string;
  target: string;
  relationship_type: string;
  description: string;
}

export interface RepositoryOverviewProps {
  owner: string;
  repoSlug: string;
  repoName: string;
  summary: string;
  analysis: {
    structure: Record<string, string[]>;
    dependencies: string[];
    tech_stack: string[];
    metadata: Record<string, string>;
  };
  architecture: {
    summary: string;
    reading_order: string[];
    relationships: ComponentRelationship[];
  };
  health: RepoHealth | null;
  healthState: 'loading' | 'ready' | 'unavailable';
  complexity: ComplexityResult;
  primaryLanguage: string | null;
  readingMinutes: number;
  readingSteps: number;
  fileCount: number;
  directoryCount: number;
  dependencyCount: number;
  componentCount: number;
  entryPoints: string[];
  groupedEntryPoints: { name: string; paths: string[]; count: number }[];
  circularDependencies: string[][];
  insights: Insight[];
  indexedAt: number | null;
  onNavigateTab: (tab: OverviewTabTarget, file?: string | null) => void;
  onSelectFile?: (file: string) => void;
  onAskAboutFile?: (file: string) => void;
  onViewInGraph?: (file: string) => void;
}

// ── Icons & Severity Mapping ────────────────────────────────────────────────

const INSIGHT_ICONS: Record<InsightIcon, React.ComponentType<{ className?: string }>> = {
  architecture: ShieldCheck,
  dependency:   Package,
  entrypoint:   DoorOpen,
  scale:        Layers3,
  onboarding:   Clock,
  monorepo:     Boxes,
  language:     Code2,
  cycle:        RefreshCcwDot,
  docs:         FileText,
  tests:        FlaskConical,
  api:          Globe,
};

const SEVERITY_CONFIG: Record<InsightSeverity, {
  accent: string;
  border: string;
  bg: string;
  glyph: React.ComponentType<{ className?: string }>;
  srLabel: string;
  badge: string;
}> = {
  risk: {
    accent: 'text-danger',
    border: 'border-danger/40',
    bg: 'bg-danger/5',
    glyph: XCircle,
    srLabel: 'Critical Risk',
    badge: 'RISK',
  },
  warn: {
    accent: 'text-warn',
    border: 'border-warn/35',
    bg: 'bg-warn/5',
    glyph: AlertTriangle,
    srLabel: 'Needs Attention',
    badge: 'ATTENTION',
  },
  good: {
    accent: 'text-success',
    border: 'border-white/[0.07]',
    bg: 'bg-surface-1/30',
    glyph: CheckCircle2,
    srLabel: 'Healthy Signal',
    badge: 'HEALTHY',
  },
  neutral: {
    accent: 'text-text-muted',
    border: 'border-white/[0.06]',
    bg: 'bg-surface-1/20',
    glyph: Info,
    srLabel: 'Informational',
    badge: 'INFO',
  },
};

/**
 * Maps an insight finding to the most relevant navigation tab.
 */
function resolveInsightTab(insight: Insight): { tab: OverviewTabTarget; label: string } | null {
  if (insight.id === 'cycles') return { tab: 'graph', label: 'Inspect graph cycles' };
  if (insight.id === 'high-deps' || insight.id === 'lean-deps') return { tab: 'graph', label: 'Explore dependencies' };
  if (insight.id === 'onboarding') return { tab: 'reading_path', label: 'Follow reading path' };
  if (insight.id === 'multi-entry' || insight.id === 'single-entry') return { tab: 'graph', label: 'Inspect entry points' };
  if (insight.id === 'dense-repo' || insight.id === 'compact-repo') return { tab: 'graph', label: 'Explore structure' };
  if (insight.id === 'strong-docs' || insight.id === 'no-docs') return { tab: 'report', label: 'Review health report' };
  if (insight.id === 'tests-present' || insight.id === 'no-tests') return { tab: 'report', label: 'Inspect hygiene' };
  if (insight.id === 'acyclic' || insight.id === 'independent-modules') return { tab: 'graph', label: 'View topology' };
  return null;
}

// ── Main Component ──────────────────────────────────────────────────────────

export const RepositoryOverview: React.FC<RepositoryOverviewProps> = ({
  owner,
  repoSlug,
  repoName,
  summary,
  analysis,
  architecture,
  health,
  healthState,
  complexity,
  primaryLanguage,
  readingMinutes,
  readingSteps,
  fileCount,
  directoryCount,
  dependencyCount,
  componentCount,
  entryPoints,
  groupedEntryPoints,
  circularDependencies,
  insights,
  onNavigateTab,
  onSelectFile,
}) => {
  const [depQuery, setDepQuery] = useState('');

  // ── Derived Data Computations ─────────────────────────────────────────────

  // Grounded Repository Briefing & Capability Inference
  const brief: RepoBrief = useMemo(() => {
    return deriveRepoBrief({
      repoName: repoName || (owner && repoSlug ? `${owner}/${repoSlug}` : 'Repository'),
      summary: summary || architecture?.summary || '',
      techStack: analysis?.tech_stack || [],
      dependencies: analysis?.dependencies || [],
      structure: analysis?.structure || {},
      entryPoints: entryPoints || [],
      relationships: architecture?.relationships || [],
    });
  }, [repoName, owner, repoSlug, summary, architecture, analysis, entryPoints]);

  const tone = healthTone(health ? health.score : null);

  // Split insights into Attention (risks & warnings) and Healthy/Info signals
  const attentionInsights = useMemo(() => {
    return insights.filter((i) => i.severity === 'risk' || i.severity === 'warn');
  }, [insights]);

  const healthyInsights = useMemo(() => {
    return insights.filter((i) => i.severity === 'good' || i.severity === 'neutral');
  }, [insights]);

  const attentionCount = attentionInsights.length;

  // Grouped Tech Stack
  const techGroups = useMemo(() => groupTech(analysis?.tech_stack || []), [analysis?.tech_stack]);
  const totalTechDetected = useMemo(() => techGroups.reduce((acc, g) => acc + g.items.length, 0), [techGroups]);

  // Grouped Dependencies
  const depGroups = useMemo(() => groupTech(analysis?.dependencies || []), [analysis?.dependencies]);
  const totalDepsCount = analysis?.dependencies?.length || 0;

  // Filtered Dependencies for quick search
  const filteredDepGroups = useMemo(() => {
    const query = depQuery.trim().toLowerCase();
    if (!query) return depGroups;
    return depGroups
      .map((g) => ({
        ...g,
        items: g.items.filter((item) => item.toLowerCase().includes(query)),
      }))
      .filter((g) => g.items.length > 0);
  }, [depGroups, depQuery]);

  // Top Root Directories for Topology Shape Visualization
  const directoryTopology = useMemo(() => {
    const rootDirCounts: Record<string, number> = {};
    Object.entries(analysis?.structure || {}).forEach(([dir, files]) => {
      const normalized = dir.replace(/\\/g, '/').replace(/^\.\//, '');
      const root = normalized.split('/')[0] || './';
      const cleanRoot = root.endsWith('/') || root === './' ? root : `${root}/`;
      rootDirCounts[cleanRoot] = (rootDirCounts[cleanRoot] || 0) + files.length;
    });

    const entries = Object.entries(rootDirCounts)
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => b.count - a.count);

    const maxCount = entries[0]?.count || 1;
    return { entries: entries.slice(0, 6), maxCount, total: fileCount };
  }, [analysis?.structure, fileCount]);

  const avgFilesPerDir = directoryCount > 0 ? (fileCount / directoryCount).toFixed(1) : '0';

  // Reading Path Top Files Preview
  const readingPreviewFiles = useMemo(() => {
    const list = architecture?.reading_order || [];
    return list.slice(0, 3);
  }, [architecture?.reading_order]);

  return (
    <div className="w-full space-y-6 sm:space-y-7 pb-8 fade-up" aria-label="Repository Overview">
      {/* ── 1. HERO BRIEF — "WHAT IS THIS?" ─────────────────────────────────── */}
      <section aria-labelledby="repo-brief-heading" className="rounded-xl border border-white/[0.08] bg-surface-0/60 p-5 sm:p-6 backdrop-blur-sm shadow-xl relative overflow-hidden">
        {/* Subtle background ambient tint */}
        <div className="absolute top-0 right-0 w-96 h-96 bg-primary/5 blur-3xl pointer-events-none rounded-full" aria-hidden="true" />

        <div className="flex items-baseline justify-between gap-3 pb-3 border-b border-white/[0.06] mb-4">
          <div className="flex items-center gap-2">
            <BookOpen className="h-4 w-4 text-primary" aria-hidden="true" />
            <h2 id="repo-brief-heading" className="mono-label text-text font-semibold tracking-[0.16em] text-xs sm:text-sm">
              ABOUT THIS REPOSITORY
            </h2>
          </div>
          <span className={`inline-flex items-center gap-1 text-[10px] font-mono font-bold px-2 py-0.5 rounded border uppercase tracking-wider ${
            brief.confidenceState === 'VERIFIED'
              ? 'bg-success/10 border-success/30 text-success'
              : brief.confidenceState === 'INFERRED'
                ? 'bg-primary/10 border-primary/30 text-primary'
                : 'bg-white/[0.05] border-white/[0.1] text-text-subtle'
          }`}>
            {brief.confidenceState === 'VERIFIED' ? 'VERIFIED EVIDENCE' : brief.confidenceState === 'INFERRED' ? 'INFERRED CONTEXT' : 'UNKNOWN PURPOSE'}
          </span>
        </div>

        {/* Narrative Description & Purpose Block */}
        <div className="space-y-4">
          <p className="text-sm sm:text-base text-text font-sans leading-relaxed">
            {brief.about}
          </p>

          {(brief.purpose || brief.primaryUse) && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
              {brief.purpose && (
                <div className="p-3.5 rounded-lg bg-surface-1/40 border border-white/[0.04] space-y-1">
                  <span className="mono-label text-[9.5px] text-text-subtle tracking-[0.16em] uppercase block">
                    PURPOSE
                  </span>
                  <p className="text-xs sm:text-sm font-sans font-medium text-text leading-snug">
                    {brief.purpose}
                  </p>
                </div>
              )}
              {brief.primaryUse && (
                <div className="p-3.5 rounded-lg bg-surface-1/40 border border-white/[0.04] space-y-1">
                  <span className="mono-label text-[9.5px] text-text-subtle tracking-[0.16em] uppercase block">
                    PRIMARY USE
                  </span>
                  <p className="text-xs sm:text-sm font-sans font-medium text-text leading-snug">
                    {brief.primaryUse}
                  </p>
                </div>
              )}
            </div>
          )}

          {brief.confidenceState === 'UNKNOWN' && (
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3.5 rounded-lg bg-surface-1/30 border border-white/[0.05] text-xs">
              <span className="text-text-muted font-sans leading-relaxed">
                Purpose could not be confidently inferred from the available repository evidence.
              </span>
              <div className="flex items-center gap-2 shrink-0">
                <button
                  type="button"
                  onClick={() => onNavigateTab('chat')}
                  className="btn-ghost text-xs text-primary inline-flex items-center gap-1.5 font-sans font-semibold"
                >
                  <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>Ask ARIA</span>
                </button>
                <button
                  type="button"
                  onClick={() => onNavigateTab('graph')}
                  className="btn-ghost text-xs text-text inline-flex items-center gap-1.5 font-sans font-semibold"
                >
                  <Code2 className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>Explore Architecture</span>
                </button>
              </div>
            </div>
          )}

          {/* Key Capabilities */}
          {brief.capabilities.length > 0 && (
            <div className="pt-4 border-t border-white/[0.05]">
              <div className="flex items-center justify-between gap-2 mb-3">
                <div className="flex items-center gap-2">
                  <Zap className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
                  <span className="mono-label text-[10.5px] text-text-muted tracking-[0.16em] uppercase">
                    KEY CAPABILITIES ({brief.capabilities.length})
                  </span>
                </div>
                <span className="mono-detail text-[10px] text-text-subtle">
                  DERIVED FROM ARTIFACTS
                </span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {brief.capabilities.map((cap, idx) => (
                  <div
                    key={cap.title}
                    className="p-3.5 rounded-lg bg-surface-1/30 border border-white/[0.035] flex flex-col justify-between hover:border-white/[0.09] transition-colors"
                  >
                    <div>
                      <div className="flex items-start justify-between gap-2 mb-1.5">
                        <div className="flex items-baseline gap-1.5 min-w-0">
                          <span className="font-mono text-[11px] font-bold text-primary">
                            {String(idx + 1).padStart(2, '0')}
                          </span>
                          <span className="font-sans text-xs font-semibold text-text truncate" title={cap.title}>
                            {cap.title}
                          </span>
                        </div>
                        <span className="text-[9px] font-mono uppercase px-1.5 py-0.2 rounded bg-white/[0.04] text-text-subtle shrink-0">
                          {cap.confidence === 'strong' ? 'Verified' : 'Inferred'}
                        </span>
                      </div>
                      <p className="text-xs text-text-muted font-sans leading-relaxed">
                        {cap.detail}
                      </p>
                    </div>
                    <span className="mono-detail text-[9.5px] text-text-subtle truncate mt-2.5 pt-1.5 border-t border-white/[0.03] block" title={cap.evidence}>
                      {cap.evidence}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* High-Level Execution Flow */}
          <div className="pt-4 border-t border-white/[0.05]">
            <div className="flex items-center justify-between gap-2 mb-2.5">
              <div className="flex items-center gap-2">
                <Terminal className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
                <span className="mono-label text-[10.5px] text-text-muted tracking-[0.16em] uppercase">
                  HOW IT WORKS (HIGH-LEVEL EXECUTION FLOW)
                </span>
              </div>
            </div>

            {brief.pipelineSteps && brief.pipelineSteps.length > 0 ? (
              <div className="flex items-center gap-2 overflow-x-auto py-2 pr-2 scrollbar-thin">
                {brief.pipelineSteps.map((step, idx) => (
                  <React.Fragment key={step}>
                    <div className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-surface-1/60 border border-white/[0.06] shrink-0">
                      <span className="text-[10px] font-mono text-primary font-bold">{String(idx + 1).padStart(2, '0')}</span>
                      <span className="font-sans text-xs font-medium text-text">{step}</span>
                    </div>
                    {idx < brief.pipelineSteps!.length - 1 && (
                      <ArrowRight className="h-3.5 w-3.5 text-text-subtle shrink-0" aria-hidden="true" />
                    )}
                  </React.Fragment>
                ))}
              </div>
            ) : (
              <div className="p-3 rounded-lg bg-surface-1/30 border border-white/[0.03] flex items-center justify-between gap-3 text-xs">
                <span className="text-text-subtle font-sans">
                  Execution flow could not be confidently inferred from available manifests.
                </span>
                <button
                  type="button"
                  onClick={() => onNavigateTab('graph')}
                  className="mono-label text-[10px] text-primary hover:underline inline-flex items-center gap-1 shrink-0 focus-visible:outline-none"
                >
                  Inspect Architecture
                  <ArrowRight className="h-2.5 w-2.5" aria-hidden="true" />
                </button>
              </div>
            )}
          </div>
        </div>
      </section>

      {/* ── 2. TECHNOLOGY + DEPENDENCY PROFILE ───────────────────────────────── */}
      <section aria-labelledby="tech-and-deps-heading" className="grid grid-cols-1 lg:grid-cols-2 gap-5 items-stretch">
        <h2 id="tech-and-deps-heading" className="sr-only">Technology and Dependency Profile</h2>

        {/* ── LEFT: Technology Profile ── */}
        <div className="p-5 sm:p-6 rounded-xl border border-white/[0.07] bg-surface-0/50 backdrop-blur-sm flex flex-col justify-between min-w-0">
          <div>
            <div className="flex items-baseline justify-between gap-3 pb-3 border-b border-white/[0.06] mb-4">
              <span className="mono-label tracking-[0.16em]">TECHNOLOGY PROFILE</span>
              <span className="mono-detail text-[10px] tabular-nums">
                {totalTechDetected} DETECTED · {techGroups.length} {techGroups.length === 1 ? 'CATEGORY' : 'CATEGORIES'}
              </span>
            </div>

            {/* Primary Language Highlight */}
            {primaryLanguage && (
              <div className="mb-4 p-3 rounded-lg bg-surface-1/40 border border-white/[0.04] flex items-center justify-between">
                <div>
                  <span className="mono-label text-[9.5px] text-text-subtle uppercase block mb-0.5 tracking-[0.16em]">PRIMARY LANGUAGE</span>
                  <span className="font-sans text-sm sm:text-base font-bold text-text">{primaryLanguage}</span>
                </div>
                <span className="text-xs font-mono text-text-muted bg-white/[0.04] px-2 py-0.5 rounded border border-white/[0.06]">
                  {analysis?.tech_stack?.length || 1} Languages
                </span>
              </div>
            )}

            {techGroups.length === 0 ? (
              <p className="text-xs text-text-muted py-4 font-sans">No specific frameworks or languages detected in manifests.</p>
            ) : (
              <div className="space-y-3">
                {techGroups.map(({ meta, items }) => (
                  <div key={meta.id} className="min-w-0 pb-2.5 border-b border-white/[0.035] last:border-b-0 last:pb-0">
                    <div className="flex items-center gap-2 mb-1.5">
                      <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${TONE_DOT[meta.tone]}`} aria-hidden="true" />
                      <span className="mono-label text-[10px] text-text-muted tracking-[0.16em]">{meta.label}</span>
                      <span className="mono-detail text-[10px] text-text-subtle">({items.length})</span>
                    </div>

                    <div className="flex flex-wrap gap-1.5">
                      {items.map((item) => (
                        <span
                          key={item}
                          className={`text-[11px] font-mono px-2 py-0.5 rounded border ${TONE_CHIP[meta.tone]} truncate max-w-[14rem]`}
                          title={item}
                        >
                          {item}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* ── RIGHT: Dependency Profile ── */}
        <div className="p-5 sm:p-6 rounded-xl border border-white/[0.07] bg-surface-0/50 backdrop-blur-sm flex flex-col justify-between min-w-0">
          <div>
            <div className="flex items-baseline justify-between gap-3 pb-3 border-b border-white/[0.06] mb-4">
              <span className="mono-label tracking-[0.16em]">DEPENDENCY PROFILE</span>
              <span className="mono-detail text-[10px] tabular-nums">
                {totalDepsCount} {totalDepsCount === 1 ? 'PACKAGE' : 'PACKAGES'}
              </span>
            </div>

            {totalDepsCount === 0 ? (
              <p className="text-xs text-text-muted py-4 font-sans">No dependency manifest resolved.</p>
            ) : (
              <div className="space-y-3.5">
                {/* Search / Filter Input */}
                <div className="relative">
                  <span className="absolute inset-y-0 left-2.5 flex items-center text-text-subtle pointer-events-none" aria-hidden="true">
                    <Search className="h-3.5 w-3.5" />
                  </span>
                  <input
                    type="search"
                    value={depQuery}
                    onChange={(e) => setDepQuery(e.target.value)}
                    placeholder="Filter packages…"
                    className="w-full bg-surface-1/60 border border-white/[0.08] rounded-md px-8 py-1.5 text-xs text-text placeholder-text-subtle focus:outline-none focus:border-primary/50 font-mono"
                    aria-label="Filter packages"
                  />
                  {depQuery && (
                    <button
                      type="button"
                      onClick={() => setDepQuery('')}
                      className="absolute inset-y-0 right-2 flex items-center text-text-subtle hover:text-text"
                      aria-label="Clear filter"
                    >
                      <X className="h-3.5 w-3.5" aria-hidden="true" />
                    </button>
                  )}
                </div>

                {/* Category Summary List */}
                <div className="space-y-2 max-h-[14rem] overflow-y-auto pr-1">
                  {filteredDepGroups.map(({ meta, items }) => {
                    const percentage = totalDepsCount > 0 ? (items.length / totalDepsCount) * 100 : 0;
                    return (
                      <div key={meta.id} className="p-2.5 rounded-md bg-surface-1/40 border border-white/[0.035] min-w-0">
                        <div className="flex items-center justify-between gap-2 text-xs mb-1">
                          <div className="flex items-center gap-1.5 min-w-0">
                            <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${TONE_DOT[meta.tone]}`} aria-hidden="true" />
                            <span className="font-sans text-xs text-text font-semibold truncate">{meta.label}</span>
                          </div>
                          <span className="font-mono text-[11px] text-text-muted tabular-nums">{items.length}</span>
                        </div>

                        {/* Bar */}
                        <div className="w-full h-1 bg-white/[0.06] rounded-full overflow-hidden mb-1.5">
                          <div
                            className={`h-full ${TONE_DOT[meta.tone]}`}
                            style={{ width: `${Math.max(4, percentage)}%` }}
                            aria-hidden="true"
                          />
                        </div>

                        {/* Chip snippet */}
                        <div className="flex flex-wrap gap-1">
                          {items.slice(0, 6).map((item) => (
                            <span key={item} className="text-[9.5px] font-mono text-text-subtle bg-white/[0.03] px-1.5 py-0.5 rounded truncate max-w-[8rem]" title={item}>
                              {item}
                            </span>
                          ))}
                          {items.length > 6 && (
                            <span className="text-[9.5px] font-mono text-primary px-1 py-0.5">
                              +{items.length - 6} more
                            </span>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>

          <div className="mt-4 pt-3.5 border-t border-white/[0.06] flex items-center justify-between">
            <span className="mono-detail text-[10px]">Audit vulnerabilities & hotspots</span>
            <button
              type="button"
              onClick={() => onNavigateTab('graph')}
              className="mono-label text-[10px] text-primary hover:underline inline-flex items-center gap-1 focus-visible:outline-none"
            >
              View in File Graph
              <ArrowRight className="h-2.5 w-2.5" aria-hidden="true" />
            </button>
          </div>
        </div>
      </section>

      {/* ── 3. ARCHITECTURE SUMMARY + ENTRY POINTS ──────────────────────────── */}
      <section aria-labelledby="architecture-and-entry-heading" className="grid grid-cols-1 lg:grid-cols-2 gap-5 items-stretch">
        <h2 id="architecture-and-entry-heading" className="sr-only">Architecture Summary and Entry Points</h2>

        {/* ── LEFT: Architecture Summary ── */}
        <div className="p-5 sm:p-6 rounded-xl border border-white/[0.07] bg-surface-0/50 backdrop-blur-sm flex flex-col justify-between min-w-0">
          <div>
            <div className="flex items-baseline justify-between gap-3 pb-3 border-b border-white/[0.06] mb-4">
              <span className="mono-label tracking-[0.16em]">ARCHITECTURE</span>
              <span className="mono-detail text-[10px] tabular-nums">
                {componentCount} COMPONENTS · {architecture?.relationships?.length || 0} EDGES
              </span>
            </div>

            {architecture?.relationships && architecture.relationships.length > 0 ? (
              <div className="space-y-3">
                <div className="flex items-center gap-2 mb-2">
                  <span className={`h-1.5 w-1.5 rounded-full ${circularDependencies.length > 0 ? 'bg-warn' : 'bg-success'}`} aria-hidden="true" />
                  <span className="font-mono text-xs font-semibold text-text uppercase">
                    {circularDependencies.length > 0 ? `${circularDependencies.length} cycles detected` : 'Acyclic / Stable'}
                  </span>
                </div>

                <div className="space-y-2 max-h-[14rem] overflow-y-auto pr-1">
                  {architecture.relationships.slice(0, 4).map((rel, idx) => (
                    <div key={idx} className="p-2.5 rounded-md bg-surface-1/50 border border-white/[0.035] text-xs">
                      <div className="flex items-center gap-2 flex-wrap font-mono text-[11px]">
                        <span className="text-primary font-medium truncate max-w-[10rem]">{rel.source}</span>
                        <span className="text-[9px] uppercase tracking-[0.16em] text-text-subtle px-1.5 py-0.5 rounded bg-white/[0.04]">
                          {rel.relationship_type}
                        </span>
                        <span className="text-text-subtle">→</span>
                        <span className="text-text-muted font-medium truncate max-w-[10rem]">{rel.target}</span>
                      </div>
                      {rel.description && (
                        <p className="text-xs text-text-muted mt-1 font-sans leading-relaxed">
                          {rel.description}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="py-4">
                <EmptyState
                  compact
                  icon={<NetworkIcon className="h-5 w-5" />}
                  title="No component relationships detected"
                  description="The repository currently appears largely modular or cross-component relationships could not be inferred. File-level structure is still fully indexed."
                  action={
                    <div className="flex flex-wrap gap-2 justify-center mt-2">
                      <button
                        type="button"
                        onClick={() => onNavigateTab('graph')}
                        className="btn-ghost text-xs inline-flex items-center gap-1.5 font-sans font-medium"
                      >
                        <Code2 className="h-3.5 w-3.5" aria-hidden="true" />
                        Inspect File Graph
                      </button>
                      <button
                        type="button"
                        onClick={() => onNavigateTab('call_graph')}
                        className="btn-ghost text-xs inline-flex items-center gap-1.5 font-sans font-medium"
                      >
                        <Workflow className="h-3.5 w-3.5" aria-hidden="true" />
                        Trace Call Graph
                      </button>
                    </div>
                  }
                />
              </div>
            )}
          </div>

          {architecture?.relationships && architecture.relationships.length > 0 && (
            <div className="mt-4 pt-3.5 border-t border-white/[0.06] flex items-center justify-between">
              <span className="mono-detail text-[10px]">
                {architecture.relationships.length > 4 ? `+${architecture.relationships.length - 4} more edges in graph` : 'Full component topology'}
              </span>
              <button
                type="button"
                onClick={() => onNavigateTab('graph')}
                className="mono-label text-[10px] text-primary hover:underline inline-flex items-center gap-1 focus-visible:outline-none"
              >
                Open Architecture Graph
                <ArrowRight className="h-2.5 w-2.5" aria-hidden="true" />
              </button>
            </div>
          )}
        </div>

        {/* ── RIGHT: Entry Points ── */}
        <div className="p-5 sm:p-6 rounded-xl border border-white/[0.07] bg-surface-0/50 backdrop-blur-sm flex flex-col justify-between min-w-0">
          <div>
            <div className="flex items-baseline justify-between gap-3 pb-3 border-b border-white/[0.06] mb-4">
              <span className="mono-label tracking-[0.16em]">ENTRY POINTS</span>
              <span className="mono-detail text-[10px] tabular-nums">
                {entryPoints.length} DETECTED
              </span>
            </div>

            {entryPoints.length === 0 ? (
              <p className="text-xs text-text-muted py-4 font-sans">No conventional application entry points inferred from filenames.</p>
            ) : (
              <div className="space-y-2">
                <p className="text-xs text-text-muted mb-2 font-sans">
                  Executable application starting points inferred from repository filenames:
                </p>

                <ul className="space-y-1.5 max-h-[14rem] overflow-y-auto pr-1">
                  {groupedEntryPoints.slice(0, 6).map((group) => (
                    <li key={group.name} className="min-w-0">
                      <button
                        type="button"
                        onClick={() => {
                          if (onSelectFile && group.paths[0]) {
                            onSelectFile(group.paths[0]);
                          }
                          onNavigateTab('graph', group.paths[0]);
                        }}
                        title={group.paths.join('\n')}
                        className="w-full flex items-center justify-between gap-3 p-2 rounded-md bg-surface-1/40 border border-white/[0.035] text-left hover:border-primary/40 transition-colors focus-visible:outline-none"
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <DoorOpen className="h-3.5 w-3.5 text-primary shrink-0" aria-hidden="true" />
                          <FilePath path={group.name} tone="primary" size="sm" />
                        </div>
                        {group.count > 1 && (
                          <span className="mono-detail text-[10px] text-text-subtle shrink-0">
                            × {group.count}
                          </span>
                        )}
                      </button>
                    </li>
                  ))}
                </ul>

                {groupedEntryPoints.length > 6 && (
                  <p className="mono-detail text-[10px] text-text-subtle pt-1">
                    +{groupedEntryPoints.length - 6} more entry files detected
                  </p>
                )}
              </div>
            )}
          </div>

          <div className="mt-4 pt-3.5 border-t border-white/[0.06] flex items-center justify-between">
            <span className="mono-detail text-[10px]">Click to inspect file neighbourhood</span>
            <button
              type="button"
              onClick={() => onNavigateTab('reading_path')}
              className="mono-label text-[10px] text-primary hover:underline inline-flex items-center gap-1 focus-visible:outline-none"
            >
              Follow Reading Path
              <ArrowRight className="h-2.5 w-2.5" aria-hidden="true" />
            </button>
          </div>
        </div>
      </section>

      {/* ── 4. REPOSITORY HEALTH + KEY ENGINEERING METRICS ───────────────────── */}
      <section aria-labelledby="health-and-metrics-heading" className="rounded-xl border border-white/[0.07] bg-surface-0/70 overflow-hidden shadow-2xl backdrop-blur-sm">
        <h2 id="health-and-metrics-heading" className="sr-only">Repository Health and Key Metrics</h2>

        <div className="grid grid-cols-1 lg:grid-cols-12 items-stretch divide-y lg:divide-y-0 lg:divide-x divide-white/[0.06]">
          {/* ── LEFT: Executive Health Panel (5 cols) ── */}
          <div className="lg:col-span-5 p-5 sm:p-6 flex flex-col justify-between relative overflow-hidden bg-canvas/30">
            {/* Subtle tone ambient aura */}
            <div
              className={`absolute -top-12 -right-12 w-40 h-40 blur-3xl opacity-15 pointer-events-none rounded-full ${
                health && health.score >= 80 ? 'bg-success' : health && health.score >= 60 ? 'bg-warn' : 'bg-primary'
              }`}
              aria-hidden="true"
            />

            <div>
              <div className="flex items-baseline justify-between gap-3 pb-3 border-b border-white/[0.06]">
                <span className="mono-label mono-label-accent tracking-[0.16em]">REPOSITORY HEALTH</span>
                <span className="mono-detail text-[10px] uppercase text-text-subtle">
                  {healthState === 'loading' ? 'Evaluating…' : 'DETERMINISTIC SCORE'}
                </span>
              </div>

              {/* Overall Score & Grade Anchor */}
              <div className="mt-5 flex items-baseline gap-3.5 flex-wrap">
                <span className={`text-4xl sm:text-5xl font-sans font-bold tracking-tight ${tone.text}`}>
                  {health ? (
                    <AnimatedNumber value={health.score} suffix="%" duration={800} />
                  ) : healthState === 'loading' ? (
                    '··'
                  ) : (
                    '—'
                  )}
                </span>
                {health && (
                  <span className={`inline-flex items-center px-2.5 py-1 rounded-md font-mono text-xs uppercase tracking-wider font-bold border border-white/[0.1] bg-surface-1/60 ${tone.text}`}>
                    Grade {health.grade}
                  </span>
                )}
              </div>

              {/* Score Progress Meter */}
              <div className="mt-3.5">
                <Meter
                  value={health ? health.score / 100 : 0}
                  barClassName={tone.bar}
                  className="h-1.5 w-full bg-white/[0.06] rounded-full"
                  delay={100}
                />
              </div>

              {/* Stability & Cycle Status */}
              <div className="mt-5 space-y-1.5">
                <div className="flex items-center gap-2">
                  <span
                    className={`h-2 w-2 rounded-full shrink-0 ${
                      circularDependencies.length > 0 ? 'bg-warn' : 'bg-success'
                    }`}
                    aria-hidden="true"
                  />
                  <span
                    className={`font-mono text-xs font-semibold uppercase tracking-wider ${
                      circularDependencies.length > 0 ? 'text-warn' : 'text-success'
                    }`}
                  >
                    {circularDependencies.length > 0
                      ? `${circularDependencies.length} cycle${circularDependencies.length === 1 ? '' : 's'} detected`
                      : 'Acyclic / Stable'}
                  </span>
                </div>
                <p className="text-xs text-text-muted leading-relaxed font-sans">
                  {circularDependencies.length > 0
                    ? 'Circular component dependencies detected in topology traversal.'
                    : 'No circular component relationships detected across the codebase.'}
                </p>
              </div>
            </div>

            {/* Finding summary signal footer */}
            <div className="mt-6 pt-3.5 border-t border-white/[0.06] flex items-center justify-between gap-3 text-xs">
              <span className="mono-detail text-[10px]">
                {attentionCount > 0 ? (
                  <span className="text-warn font-mono font-medium">
                    {String(attentionCount).padStart(2, '0')} / {String(insights.length).padStart(2, '0')} SIGNALS NEED ATTENTION
                  </span>
                ) : (
                  <span className="text-success font-mono font-medium">
                    {String(insights.length).padStart(2, '0')} SIGNALS · ALL HEALTHY
                  </span>
                )}
              </span>
              <button
                type="button"
                onClick={() => onNavigateTab('report')}
                className="mono-label text-[10px] text-primary hover:underline inline-flex items-center gap-1 focus-visible:outline-none"
              >
                Health Report
                <ArrowRight className="h-2.5 w-2.5" aria-hidden="true" />
              </button>
            </div>
          </div>

          {/* ── RIGHT: Key Engineering Metrics Grid (7 cols) ── */}
          <div className="lg:col-span-7 p-5 sm:p-6 flex flex-col justify-between bg-canvas/15">
            <div>
              <div className="flex items-baseline justify-between gap-3 pb-3 border-b border-white/[0.06]">
                <span className="mono-label tracking-[0.16em]">KEY ENGINEERING METRICS</span>
                <span className="mono-detail text-[10px] uppercase text-text-subtle">
                  INDEXED VALUES
                </span>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 sm:gap-5 mt-4">
                {/* FILES */}
                <div className="min-w-0">
                  <span className="mono-label block text-[9.5px] text-text-subtle mb-1 tracking-[0.16em]">FILES</span>
                  <span className="text-2xl sm:text-3xl font-sans font-bold text-text tabular-nums tracking-tight block">
                    <AnimatedNumber value={fileCount} startOnView />
                  </span>
                  <span className="text-[11px] text-text-muted truncate block mt-0.5 font-sans">
                    {directoryCount} dirs
                  </span>
                </div>

                {/* DIRECTORIES */}
                <div className="min-w-0">
                  <span className="mono-label block text-[9.5px] text-text-subtle mb-1 tracking-[0.16em]">DIRECTORIES</span>
                  <span className="text-2xl sm:text-3xl font-sans font-bold text-text tabular-nums tracking-tight block">
                    <AnimatedNumber value={directoryCount} startOnView />
                  </span>
                  <span className="text-[11px] text-text-muted truncate block mt-0.5 font-sans">
                    ~{avgFilesPerDir} f/dir
                  </span>
                </div>

                {/* DEPENDENCIES */}
                <div className="min-w-0">
                  <span className="mono-label block text-[9.5px] text-text-subtle mb-1 tracking-[0.16em]">DEPENDENCIES</span>
                  <span className="text-2xl sm:text-3xl font-sans font-bold text-text tabular-nums tracking-tight block">
                    <AnimatedNumber value={dependencyCount} startOnView />
                  </span>
                  <span className="text-[11px] text-text-muted truncate block mt-0.5 font-sans">
                    {dependencyCount === 0 ? 'None resolved' : 'Declared'}
                  </span>
                </div>

                {/* ENTRY POINTS */}
                <div className="min-w-0">
                  <span className="mono-label block text-[9.5px] text-text-subtle mb-1 tracking-[0.16em]">ENTRY POINTS</span>
                  <span className="text-2xl sm:text-3xl font-sans font-bold text-text tabular-nums tracking-tight block">
                    <AnimatedNumber value={entryPoints.length} startOnView />
                  </span>
                  <span className="text-[11px] text-text-muted truncate block mt-0.5 font-sans">
                    Roots
                  </span>
                </div>

                {/* LANGUAGES */}
                <div className="min-w-0">
                  <span className="mono-label block text-[9.5px] text-text-subtle mb-1 tracking-[0.16em]">LANGUAGES</span>
                  <span className="text-2xl sm:text-3xl font-sans font-bold text-text tabular-nums tracking-tight block">
                    <AnimatedNumber value={analysis?.tech_stack?.length || 0} startOnView />
                  </span>
                  <span className="text-[11px] text-text-muted truncate block mt-0.5 font-sans" title={primaryLanguage || undefined}>
                    {primaryLanguage || '—'}
                  </span>
                </div>

                {/* READING TIME */}
                <div className="min-w-0">
                  <span className="mono-label block text-[9.5px] text-text-subtle mb-1 tracking-[0.16em]">READING</span>
                  <span className="text-2xl sm:text-3xl font-sans font-bold text-text tabular-nums tracking-tight block">
                    {formatDuration(readingMinutes)}
                  </span>
                  <span className="text-[11px] text-text-muted truncate block mt-0.5 font-sans">
                    {readingSteps} steps
                  </span>
                </div>

                {/* COMPLEXITY */}
                <div className="min-w-0">
                  <span className="mono-label block text-[9.5px] text-text-subtle mb-1 tracking-[0.16em]">COMPLEXITY</span>
                  <span className="text-2xl sm:text-3xl font-sans font-bold text-text tabular-nums tracking-tight block">
                    <AnimatedNumber value={complexity.score} startOnView />
                  </span>
                  <span className="text-[11px] text-text-muted truncate block mt-0.5 font-sans">
                    {complexity.label}
                  </span>
                </div>

                {/* COMPONENTS */}
                <div className="min-w-0">
                  <span className="mono-label block text-[9.5px] text-text-subtle mb-1 tracking-[0.16em]">COMPONENTS</span>
                  <span className="text-2xl sm:text-3xl font-sans font-bold text-text tabular-nums tracking-tight block">
                    <AnimatedNumber value={componentCount} startOnView />
                  </span>
                  <span className="text-[11px] text-text-muted truncate block mt-0.5 font-sans">
                    Modules
                  </span>
                </div>
              </div>
            </div>

            {/* Quick navigation action strip */}
            <div className="mt-5 pt-3.5 border-t border-white/[0.06] flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => onNavigateTab('graph')}
                className="action-chip text-[11px] px-2.5 py-1 inline-flex items-center gap-1.5 font-sans font-medium hover:border-primary/40 transition-colors focus-visible:outline-none"
              >
                <Code2 className="h-3 w-3 text-primary" aria-hidden="true" />
                <span>Explore File Graph</span>
              </button>
              <button
                type="button"
                onClick={() => onNavigateTab('reading_path')}
                className="action-chip text-[11px] px-2.5 py-1 inline-flex items-center gap-1.5 font-sans font-medium hover:border-primary/40 transition-colors focus-visible:outline-none"
              >
                <Clock className="h-3 w-3 text-primary" aria-hidden="true" />
                <span>Reading Path</span>
              </button>
              <button
                type="button"
                onClick={() => onNavigateTab('chat')}
                className="action-chip text-[11px] px-2.5 py-1 inline-flex items-center gap-1.5 font-sans font-medium hover:border-primary/40 transition-colors focus-visible:outline-none"
              >
                <Sparkles className="h-3 w-3 text-primary" aria-hidden="true" />
                <span>Ask ARIA</span>
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* ── 5. WHAT NEEDS ATTENTION (Structured Findings & Baseline) ─────────── */}
      <section aria-labelledby="what-needs-attention-heading" className="rounded-xl border border-white/[0.07] bg-surface-0/50 p-5 sm:p-6 backdrop-blur-sm">
        <div className="flex items-baseline justify-between gap-4 pb-3 border-b border-white/[0.06] mb-4">
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-primary" aria-hidden="true" />
            <h2 id="what-needs-attention-heading" className="mono-label text-text font-semibold tracking-[0.16em]">
              WHAT NEEDS ATTENTION
            </h2>
          </div>
          <span className="mono-detail text-[10px] tabular-nums">
            {attentionCount > 0 ? (
              <>
                <span className="text-warn font-bold">{String(attentionCount).padStart(2, '0')}</span>
                <span className="text-text-subtle"> / {String(insights.length).padStart(2, '0')} SIGNALS</span>
              </>
            ) : (
              <span className="text-success font-semibold">{String(insights.length).padStart(2, '0')} / {String(insights.length).padStart(2, '0')} ALL HEALTHY</span>
            )}
          </span>
        </div>

        {insights.length === 0 ? (
          <p className="text-xs text-text-muted py-3 font-sans">No architectural findings detected.</p>
        ) : (
          <div className="space-y-4">
            {/* High-priority Attention Findings (What / Evidence / Caveat / Action) */}
            {attentionInsights.length > 0 && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
                {attentionInsights.map((insight) => {
                  const Icon = INSIGHT_ICONS[insight.icon] ?? Info;
                  const config = SEVERITY_CONFIG[insight.severity];
                  const Glyph = config.glyph;
                  const navAction = resolveInsightTab(insight);

                  return (
                    <div
                      key={insight.id}
                      className={`group relative p-4 rounded-lg border ${config.border} ${config.bg} flex flex-col justify-between transition-all duration-150 hover:border-primary/50 shadow-sm`}
                    >
                      <div className="space-y-2.5">
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex items-center gap-2 min-w-0">
                            <Icon className={`h-4 w-4 shrink-0 ${config.accent}`} aria-hidden="true" />
                            <h3 className="font-sans text-xs sm:text-sm font-bold text-text truncate" title={insight.title}>
                              {insight.title}
                            </h3>
                          </div>
                          <span className={`inline-flex items-center gap-1 text-[10px] font-mono font-bold px-1.5 py-0.5 rounded border ${config.border} ${config.accent}`}>
                            <Glyph className="h-3 w-3 shrink-0" aria-hidden="true" />
                            <span>{config.badge}</span>
                          </span>
                        </div>

                        {/* What */}
                        <div>
                          <span className="mono-label text-[9px] text-text-subtle uppercase block mb-0.5 tracking-[0.16em]">WHAT</span>
                          <p className="text-xs text-text font-sans leading-relaxed font-medium">
                            {insight.detail}
                          </p>
                        </div>

                        {/* Evidence */}
                        {insight.evidence && (
                          <div className="pt-2 border-t border-white/[0.04]">
                            <span className="mono-label text-[9px] text-text-subtle uppercase block mb-0.5 tracking-[0.16em]">EVIDENCE</span>
                            <p className="text-[11px] text-text-muted font-sans leading-relaxed">
                              {insight.evidence}
                            </p>
                          </div>
                        )}

                        {/* Caveat */}
                        {insight.caveat && (
                          <div className="pt-1.5">
                            <span className="mono-label text-[9px] text-text-subtle uppercase block mb-0.5 tracking-[0.16em]">CAVEAT</span>
                            <p className="text-[11px] text-text-muted/80 font-sans leading-relaxed">
                              {insight.caveat}
                            </p>
                          </div>
                        )}
                      </div>

                      {navAction && (
                        <button
                          type="button"
                          onClick={() => onNavigateTab(navAction.tab)}
                          className="mt-4 pt-2.5 border-t border-white/[0.06] text-xs font-sans font-semibold text-primary hover:underline flex items-center justify-between gap-1.5 transition-colors focus-visible:outline-none"
                        >
                          <span className="truncate">{navAction.label}</span>
                          <ArrowRight className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            {/* Healthy Baseline (Clean, calm secondary subgrid) */}
            {healthyInsights.length > 0 && (
              <div className="space-y-2">
                {attentionInsights.length > 0 && (
                  <div className="pt-2">
                    <span className="mono-label text-[9.5px] text-text-subtle tracking-[0.16em] uppercase block mb-2">
                      HEALTHY BASELINE ({healthyInsights.length})
                    </span>
                  </div>
                )}
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
                  {healthyInsights.map((insight) => {
                    const Icon = INSIGHT_ICONS[insight.icon] ?? Info;
                    const config = SEVERITY_CONFIG[insight.severity];
                    const navAction = resolveInsightTab(insight);

                    return (
                      <div
                        key={insight.id}
                        className="group p-3 rounded-md border border-white/[0.05] bg-surface-1/30 hover:border-white/[0.12] hover:bg-surface-1/50 transition-all duration-150 flex flex-col justify-between min-w-0"
                      >
                        <div>
                          <div className="flex items-center gap-2 mb-1.5 min-w-0">
                            <Icon className={`h-3.5 w-3.5 shrink-0 ${config.accent}`} aria-hidden="true" />
                            <h3 className="font-sans text-xs font-semibold text-text truncate" title={insight.title}>
                              {insight.title}
                            </h3>
                          </div>
                          <p className="text-[11px] text-text-muted font-sans leading-relaxed line-clamp-2">
                            {insight.detail}
                          </p>
                        </div>

                        {navAction && (
                          <button
                            type="button"
                            onClick={() => onNavigateTab(navAction.tab)}
                            className="mt-2.5 pt-1.5 border-t border-white/[0.03] text-[10px] font-sans text-text-subtle group-hover:text-primary flex items-center justify-between gap-1 transition-colors focus-visible:outline-none"
                          >
                            <span className="truncate">{navAction.label}</span>
                            <ArrowRight className="h-2.5 w-2.5 shrink-0" aria-hidden="true" />
                          </button>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}
      </section>

      {/* ── 6. CODEBASE SHAPE (Structural Metrics & Root Distribution) ───────── */}
      <section aria-labelledby="structural-snapshot-heading" className="rounded-xl border border-white/[0.07] bg-surface-0/50 p-5 sm:p-6 backdrop-blur-sm">
        <div className="flex items-baseline justify-between gap-3 pb-3 border-b border-white/[0.06] mb-4">
          <span className="mono-label tracking-[0.16em]">CODEBASE SHAPE</span>
          <span className="mono-detail text-[10px] uppercase text-text-subtle">
            TOPOLOGICAL DISTRIBUTION
          </span>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* Structural Metric Table (5 cols) */}
          <div className="lg:col-span-5 space-y-2">
            <h3 id="structural-snapshot-heading" className="mono-label text-[10px] text-text-subtle mb-2 tracking-[0.16em]">
              CODEBASE INVENTORY
            </h3>
            <div className="space-y-1 font-mono text-xs">
              <div className="flex justify-between py-1.5 border-b border-white/[0.04]">
                <span className="text-text-muted">FILES</span>
                <span className="text-text font-semibold tabular-nums">{fileCount.toLocaleString()}</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-white/[0.04]">
                <span className="text-text-muted">DIRECTORIES</span>
                <span className="text-text font-semibold tabular-nums">{directoryCount.toLocaleString()}</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-white/[0.04]">
                <span className="text-text-muted">AVG FILES / DIR</span>
                <span className="text-text font-semibold tabular-nums">{avgFilesPerDir}</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-white/[0.04]">
                <span className="text-text-muted">PRIMARY LANGUAGE</span>
                <span className="text-text font-semibold truncate max-w-[10rem]">{primaryLanguage || '—'}</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-white/[0.04]">
                <span className="text-text-muted">COMPONENTS</span>
                <span className="text-text font-semibold tabular-nums">{componentCount}</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-white/[0.04]">
                <span className="text-text-muted">DEPENDENCIES</span>
                <span className="text-text font-semibold tabular-nums">{dependencyCount}</span>
              </div>
              <div className="flex justify-between py-1.5">
                <span className="text-text-muted">READING STEPS</span>
                <span className="text-text font-semibold tabular-nums">{readingSteps}</span>
              </div>
            </div>
          </div>

          {/* Root Directory Distribution (7 cols) */}
          <div className="lg:col-span-7 space-y-3 min-w-0">
            <div className="flex items-baseline justify-between gap-2">
              <h3 className="mono-label text-[10px] text-text-subtle tracking-[0.16em]">
                ROOT DIRECTORY DISTRIBUTION
              </h3>
              <span className="mono-detail text-[10px] text-text-subtle">
                BY FILE COUNT
              </span>
            </div>

            <div className="space-y-2.5">
              {directoryTopology.entries.map(({ name, count }) => {
                const pct = directoryTopology.total > 0 ? (count / directoryTopology.total) * 100 : 0;
                return (
                  <div key={name} className="space-y-1 min-w-0">
                    <div className="flex items-center justify-between gap-2 text-xs font-mono">
                      <span className="text-text truncate flex items-center gap-1.5">
                        <FolderTree className="h-3.5 w-3.5 text-primary shrink-0" aria-hidden="true" />
                        {name}
                      </span>
                      <span className="text-text-muted shrink-0 tabular-nums">
                        {count.toLocaleString()} files ({pct.toFixed(0)}%)
                      </span>
                    </div>
                    <div className="h-1.5 w-full bg-white/[0.05] rounded-full overflow-hidden">
                      <div
                        className="h-full bg-primary/70 rounded-full transition-all duration-500"
                        style={{ width: `${Math.max(3, pct)}%` }}
                        aria-hidden="true"
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </section>

      {/* ── 7. READING PATH PREVIEW ─────────────────────────────────────────── */}
      {readingSteps > 0 && (
        <section aria-labelledby="reading-preview-heading" className="rounded-xl border border-white/[0.08] bg-surface-0/60 p-5 sm:p-6 backdrop-blur-sm shadow-lg">
          <div className="flex items-baseline justify-between gap-3 pb-3 border-b border-white/[0.06] mb-4">
            <div className="flex items-center gap-2">
              <Clock className="h-4 w-4 text-primary" aria-hidden="true" />
              <h2 id="reading-preview-heading" className="mono-label text-text font-semibold tracking-[0.16em]">
                READING PATH PREVIEW
              </h2>
            </div>
            <span className="mono-detail text-[10px] text-text-subtle">
              {readingSteps} STEPS · ~{formatDuration(readingMinutes)}
            </span>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-center">
            <div className="lg:col-span-8 space-y-2">
              <p className="text-xs sm:text-sm text-text-muted font-sans leading-relaxed">
                ARIA derived a ranked onboarding sequence respecting application entry roots and component centrality:
              </p>

              <div className="space-y-1.5 pt-1">
                {readingPreviewFiles.map((file, idx) => (
                  <div key={file} className="flex items-center gap-2.5 p-2 rounded bg-surface-1/40 border border-white/[0.03] text-xs font-mono">
                    <span className="text-primary font-bold text-[11px] shrink-0">
                      {String(idx + 1).padStart(2, '0')}
                    </span>
                    <span className="text-text truncate flex-1" title={file}>
                      {file}
                    </span>
                    {idx === 0 && (
                      <span className="text-[9px] uppercase px-1.5 py-0.2 rounded bg-success/10 border border-success/30 text-success shrink-0 font-bold">
                        Start Here
                      </span>
                    )}
                  </div>
                ))}
                {readingSteps > 3 && (
                  <span className="text-[11px] font-mono text-text-subtle block pt-0.5">
                    +{readingSteps - 3} additional sequence steps
                  </span>
                )}
              </div>
            </div>

            <div className="lg:col-span-4 flex flex-col justify-center items-start lg:items-end gap-2 pt-2 lg:pt-0">
              <button
                type="button"
                onClick={() => onNavigateTab('reading_path')}
                className="btn-primary text-xs px-4 py-2 inline-flex items-center gap-2 font-sans font-semibold w-full sm:w-auto justify-center"
              >
                <span>Follow Reading Path</span>
                <ArrowRight className="h-3.5 w-3.5" />
              </button>
              <span className="text-[11px] text-text-subtle font-sans">
                Full guided onboarding workflow
              </span>
            </div>
          </div>
        </section>
      )}

      {/* ── 8. WHAT SHOULD YOU INSPECT NEXT? (Intelligent Action Rail) ───────── */}
      <section aria-labelledby="recommended-next-heading" className="rounded-xl border border-primary/20 bg-surface-0/60 p-5 sm:p-6 backdrop-blur-sm">
        <div className="flex items-baseline justify-between gap-3 pb-3 border-b border-primary/15 mb-4">
          <div className="flex items-center gap-2">
            <Compass className="h-4 w-4 text-primary" aria-hidden="true" />
            <h2 id="recommended-next-heading" className="mono-label text-text font-semibold tracking-[0.16em]">
              WHAT SHOULD YOU INSPECT NEXT?
            </h2>
          </div>
          <span className="mono-detail text-[10px] text-primary tracking-[0.16em] font-semibold">
            SIGNAL-DRIVEN ACTIONS
          </span>
        </div>

        <p className="text-xs sm:text-sm text-text-muted leading-relaxed mb-4 font-sans">
          Based on computed repository signals, follow the prioritized action rail:
        </p>

        <div className="space-y-2">
          {/* Action 01: Dependencies */}
          {dependencyCount > 0 && (
            <button
              type="button"
              onClick={() => onNavigateTab('graph')}
              className="w-full p-3 sm:p-3.5 rounded-lg border border-primary/25 bg-primary/[0.03] hover:border-primary/60 hover:bg-primary/[0.07] text-left transition-all duration-150 flex items-center justify-between gap-3 sm:gap-4 group focus-visible:outline-none"
            >
              <div className="flex items-center gap-3 sm:gap-4 min-w-0">
                <span className="font-mono text-xs font-bold text-primary shrink-0">01</span>
                <div className="p-1.5 rounded bg-primary/10 text-primary shrink-0">
                  <Package className="h-4 w-4" aria-hidden="true" />
                </div>
                <div className="min-w-0">
                  <div className="font-sans text-xs sm:text-sm font-semibold text-text group-hover:text-primary transition-colors truncate">
                    Explore Dependency Hotspots
                  </div>
                  <p className="text-[11px] text-text-muted font-sans truncate mt-0.5">
                    Audit {dependencyCount} declared packages and trace cross-module import chains.
                  </p>
                </div>
              </div>
              <span className="mono-detail text-[11px] text-primary shrink-0 flex items-center gap-1 font-semibold">
                <span className="hidden sm:inline">Open File Graph</span>
                <ArrowRight className="h-3 w-3 group-hover:translate-x-0.5 transition-transform" />
              </span>
            </button>
          )}

          {/* Action 02: Architecture Graph */}
          <button
            type="button"
            onClick={() => onNavigateTab('graph')}
            className="w-full p-3 sm:p-3.5 rounded-lg border border-white/[0.05] bg-surface-1/30 hover:border-primary/40 hover:bg-surface-1/60 text-left transition-all duration-150 flex items-center justify-between gap-3 sm:gap-4 group focus-visible:outline-none"
          >
            <div className="flex items-center gap-3 sm:gap-4 min-w-0">
              <span className="font-mono text-xs font-bold text-text-subtle shrink-0">
                {dependencyCount > 0 ? '02' : '01'}
              </span>
              <div className="p-1.5 rounded bg-white/[0.05] text-text-muted group-hover:text-primary transition-colors shrink-0">
                <Code2 className="h-4 w-4" aria-hidden="true" />
              </div>
              <div className="min-w-0">
                <div className="font-sans text-xs sm:text-sm font-semibold text-text group-hover:text-primary transition-colors truncate">
                  Inspect Architecture Graph
                </div>
                <p className="text-[11px] text-text-muted font-sans truncate mt-0.5">
                  {circularDependencies.length > 0
                    ? `Investigate ${circularDependencies.length} cycles detected in component graph.`
                    : `Explore ${componentCount} components across the full file topology.`}
                </p>
              </div>
            </div>
            <span className="mono-detail text-[11px] text-text-subtle group-hover:text-primary shrink-0 flex items-center gap-1 font-semibold">
              <span className="hidden sm:inline">Inspect Topology</span>
              <ArrowRight className="h-3 w-3 group-hover:translate-x-0.5 transition-transform" />
            </span>
          </button>

          {/* Action 03: Reading Path */}
          {readingSteps > 0 && (
            <button
              type="button"
              onClick={() => onNavigateTab('reading_path')}
              className="w-full p-3 sm:p-3.5 rounded-lg border border-white/[0.05] bg-surface-1/30 hover:border-primary/40 hover:bg-surface-1/60 text-left transition-all duration-150 flex items-center justify-between gap-3 sm:gap-4 group focus-visible:outline-none"
            >
              <div className="flex items-center gap-3 sm:gap-4 min-w-0">
                <span className="font-mono text-xs font-bold text-text-subtle shrink-0">
                  {dependencyCount > 0 ? '03' : '02'}
                </span>
                <div className="p-1.5 rounded bg-white/[0.05] text-text-muted group-hover:text-primary transition-colors shrink-0">
                  <Clock className="h-4 w-4" aria-hidden="true" />
                </div>
                <div className="min-w-0">
                  <div className="font-sans text-xs sm:text-sm font-semibold text-text group-hover:text-primary transition-colors truncate">
                    Follow Reading Path
                  </div>
                  <p className="text-[11px] text-text-muted font-sans truncate mt-0.5">
                    Onboard through {readingSteps} topologically ranked files (~{formatDuration(readingMinutes)}).
                  </p>
                </div>
              </div>
              <span className="mono-detail text-[11px] text-text-subtle group-hover:text-primary shrink-0 flex items-center gap-1 font-semibold">
                <span className="hidden sm:inline">Start Reading Order</span>
                <ArrowRight className="h-3 w-3 group-hover:translate-x-0.5 transition-transform" />
              </span>
            </button>
          )}

          {/* Action 04: Health Report */}
          <button
            type="button"
            onClick={() => onNavigateTab('report')}
            className="w-full p-3 sm:p-3.5 rounded-lg border border-white/[0.05] bg-surface-1/30 hover:border-primary/40 hover:bg-surface-1/60 text-left transition-all duration-150 flex items-center justify-between gap-3 sm:gap-4 group focus-visible:outline-none"
          >
            <div className="flex items-center gap-3 sm:gap-4 min-w-0">
              <span className="font-mono text-xs font-bold text-text-subtle shrink-0">
                {dependencyCount > 0 && readingSteps > 0 ? '04' : dependencyCount > 0 || readingSteps > 0 ? '03' : '02'}
              </span>
              <div className="p-1.5 rounded bg-white/[0.05] text-text-muted group-hover:text-primary transition-colors shrink-0">
                <FileText className="h-4 w-4" aria-hidden="true" />
              </div>
              <div className="min-w-0">
                <div className="font-sans text-xs sm:text-sm font-semibold text-text group-hover:text-primary transition-colors truncate">
                  Review Health Report
                </div>
                <p className="text-[11px] text-text-muted font-sans truncate mt-0.5">
                  Full deterministic evaluation covering stability, hygiene, and API contracts.
                </p>
              </div>
            </div>
            <span className="mono-detail text-[11px] text-text-subtle group-hover:text-primary shrink-0 flex items-center gap-1 font-semibold">
              <span className="hidden sm:inline">View Report</span>
              <ArrowRight className="h-3 w-3 group-hover:translate-x-0.5 transition-transform" />
            </span>
          </button>

          {/* Action 05: Chat with ARIA */}
          <button
            type="button"
            onClick={() => onNavigateTab('chat')}
            className="w-full p-3 sm:p-3.5 rounded-lg border border-white/[0.05] bg-surface-1/30 hover:border-primary/40 hover:bg-surface-1/60 text-left transition-all duration-150 flex items-center justify-between gap-3 sm:gap-4 group focus-visible:outline-none"
          >
            <div className="flex items-center gap-3 sm:gap-4 min-w-0">
              <span className="font-mono text-xs font-bold text-text-subtle shrink-0">
                {dependencyCount > 0 && readingSteps > 0 ? '05' : '04'}
              </span>
              <div className="p-1.5 rounded bg-white/[0.05] text-text-muted group-hover:text-primary transition-colors shrink-0">
                <Sparkles className="h-4 w-4" aria-hidden="true" />
              </div>
              <div className="min-w-0">
                <div className="font-sans text-xs sm:text-sm font-semibold text-text group-hover:text-primary transition-colors truncate">
                  Ask ARIA
                </div>
                <p className="text-[11px] text-text-muted font-sans truncate mt-0.5">
                  Ask questions grounded in symbols, graphs, dependencies, and code.
                </p>
              </div>
            </div>
            <span className="mono-detail text-[11px] text-text-subtle group-hover:text-primary shrink-0 flex items-center gap-1 font-semibold">
              <span className="hidden sm:inline">Open AI Chat</span>
              <ArrowRight className="h-3 w-3 group-hover:translate-x-0.5 transition-transform" />
            </span>
          </button>
        </div>
      </section>
    </div>
  );
};

function NetworkIcon(props: { className?: string }) {
  return (
    <svg className={props.className || 'h-5 w-5'} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
      <circle cx="6" cy="6" r="3" />
      <circle cx="18" cy="18" r="3" />
      <circle cx="18" cy="6" r="3" />
      <path d="M8.5 7.5L15.5 16.5M8.5 6h7M18 8.5v7" />
    </svg>
  );
}

export default RepositoryOverview;
