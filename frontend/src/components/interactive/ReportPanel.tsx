/**
 * ReportPanel — Health Report.
 *
 * Reads as a structured audit rather than a dashboard:
 *
 *   AUDIT (header + score anchor + diagnostic strip)
 *   → FINDINGS (mode rail: architecture / api / hygiene / onboarding)
 *   → EVIDENCE (bounded lists, progressive disclosure)
 *   → PRIORITIES (ranked action issues)
 *   → ACTION (export)
 *
 * Every number comes from `/report/{owner}/{repo}/build` unchanged. The one
 * score visualisation is the donut; the strip reports the other dimensions so
 * the overall figure is never repeated three times.
 */

import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { apiUrl, extractErrorMessage } from '../../lib/api';
import {
  FileText, Download, Printer, AlertTriangle, ChevronDown,
  Layers, Globe, Trash2, BookOpen, ArrowRight, RefreshCw,
} from 'lucide-react';
import { Button } from '../ui/Button';
import { EmptyState } from '../ui/EmptyState';
import { SkeletonCard, SkeletonGroup, Skeleton } from '../ui/Skeleton';
import { SVGDonut } from '../ui/SVGDonut';
import { AnimatedNumber } from '../ui/AnimatedNumber';
import { FilePath } from '../ui/FilePath';
import { Meter } from '../ui/Meter';
import { Reveal } from '../ui/Reveal';
import { SectionSeam } from '../ui/SectionSeam';

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

interface ArchReportSection {
  cycles_count: number;
  cycles: string[][];
  strongly_connected_components: number;
  smells_count: number;
  smells: string[];
}

interface ApiReportSection {
  total_exported_symbols: number;
  public_private_ratio: number;
  average_distance_main_sequence: number;
  unstable_modules_count: number;
}

interface HygieneReportSection {
  dead_functions_count: number;
  dead_functions: string[];
  dead_code_ratio: number;
}

interface OnboardingReportSection {
  reading_path_completeness: number;
  core_entry_points: string[];
  recommended_reading_path: string[];
}

interface ReportDataModel {
  metadata: ReportMetadata;
  scores: ScoreBreakdown;
  architecture: ArchReportSection;
  api_surface: ApiReportSection;
  hygiene: HygieneReportSection;
  onboarding: OnboardingReportSection;
  refactoring_priorities: string[];
  ai_summary?: string;
}

interface ReportPanelProps {
  repoName: string;
  /**
   * Switches the parent dashboard tab. Wired to the dashboard's existing
   * `handleTabChange`, so cross-surface links reuse current navigation rather
   * than introducing a second mechanism.
   */
  onNavigate?: (tab: string) => void;
}

type SubTabId = 'architecture' | 'api' | 'hygiene' | 'onboarding';

const MODES: [SubTabId, string, React.ComponentType<{ className?: string }>][] = [
  ['architecture', 'ARCHITECTURE', Layers],
  ['api',          'API SURFACE',  Globe],
  ['hygiene',      'HYGIENE',      Trash2],
  ['onboarding',   'ONBOARDING',   BookOpen],
];

function gradeToneClass(grade: string): string {
  if (grade === 'A') return 'text-success';
  if (grade === 'B') return 'text-primary';
  if (grade === 'C') return 'text-warn';
  return 'text-danger';
}

function getScoreTone(score: number): 'success' | 'warn' | 'danger' {
  if (score >= 80) return 'success';
  if (score >= 60) return 'warn';
  return 'danger';
}

function scoreBarClass(score: number): string {
  if (score >= 80) return 'bg-success';
  if (score >= 60) return 'bg-warn';
  return 'bg-danger';
}

function relativeTime(iso: string): string {
  try {
    const diff = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
    if (diff < 1) return 'just now';
    if (diff < 60) return `${diff} min ago`;
    return `${Math.round(diff / 60)}h ago`;
  } catch {
    return iso;
  }
}

/** Cross-surface actions. Both use contracts the dashboard already listens for. */
function openInGraph(owner: string, repo: string, path: string) {
  window.dispatchEvent(
    new CustomEvent('aria-open-graph', {
      detail: { owner, repo, path, source: 'health-report' },
    })
  );
}

function openInChat(owner: string, repo: string, path: string, prompt: string) {
  window.dispatchEvent(
    new CustomEvent('aria-open-chat', {
      detail: { owner, repo, path, source: 'health-report', prompt },
    })
  );
}

// ── Small building blocks ──────────────────────────────────────────────────

/** A hairline-separated diagnostic cell. */
const Readout: React.FC<{
  label: string;
  value: React.ReactNode;
  detail?: React.ReactNode;
  tone?: string;
  index?: number;
}> = ({ label, value, detail, tone = 'text-text', index = 0 }) => (
  <div
    className="min-w-0 px-4 sm:px-5 py-4 border-b border-white/[0.055]
               border-l border-white/[0.055]
               [&:nth-child(2n+1)]:border-l-0
               md:[&:nth-child(2n+1)]:border-l md:[&:nth-child(3n+1)]:border-l-0"
    style={{ ['--reveal-delay' as string]: `${index * 60}ms` }}
  >
    <dt className="mono-label mb-2">{label}</dt>
    <dd>
      <span className={`readout-value block ${tone}`}>{value}</span>
      {detail && (
        <span className="mono-detail block mt-1.5 truncate" style={{ fontSize: 10 }}>
          {detail}
        </span>
      )}
    </dd>
  </div>
);

/** Top-N list with a bounded scroll region behind "view all". */
const BoundedList: React.FC<{
  total: number;
  preview: number;
  label: string;
  children: (limit: number | null) => React.ReactNode;
}> = ({ total, preview, label, children }) => {
  const [expanded, setExpanded] = useState(false);
  const overflow = total > preview;

  return (
    <>
      <div
        className={
          expanded
            ? 'max-h-[22rem] overflow-y-auto pr-1 -mr-1 min-w-0'
            : 'min-w-0'
        }
      >
        {children(expanded ? null : preview)}
      </div>

      {overflow && (
        <button
          type="button"
          onClick={() => setExpanded((p) => !p)}
          className="api-action link-arrow mt-4"
          aria-expanded={expanded}
        >
          {expanded ? 'SHOW FEWER' : `VIEW ALL ${total.toLocaleString()} ${label}`}
          <ArrowRight className="h-3 w-3 arrow" aria-hidden="true" />
        </button>
      )}
    </>
  );
};

// ── Prioritized issue row ──────────────────────────────────────────────────

interface ParsedIssue {
  id: string;
  title: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  category: string;
  icon: React.ComponentType<{ className?: string }>;
  affectedFile: string;
  impact: string;
  fix: string;
}

const SEVERITY_CLASS: Record<ParsedIssue['severity'], string> = {
  critical: 'text-danger',
  high: 'text-warn',
  medium: 'text-primary',
  low: 'text-text-muted',
};

const IssueRow: React.FC<{
  issue: ParsedIssue;
  owner: string;
  repo: string;
}> = ({ issue, owner, repo }) => {
  const [open, setOpen] = useState(false);
  const Icon = issue.icon;
  const hasFile = issue.affectedFile !== 'multiple files';

  return (
    <div className="api-row hair-t last:border-b last:border-white/[0.055] min-w-0">
      <button
        type="button"
        onClick={() => setOpen((p) => !p)}
        aria-expanded={open}
        className="w-full flex items-start gap-4 py-3.5 px-1 text-left min-w-0
                   focus-visible:outline-none focus-visible:shadow-ring"
      >
        {/* Severity + category lead the row */}
        <span className="flex items-center gap-2.5 shrink-0 w-32 sm:w-44 pt-0.5">
          <span
            className={`font-mono text-[10px] uppercase tracking-[0.16em] ${SEVERITY_CLASS[issue.severity]}`}
          >
            {issue.severity}
          </span>
          <Icon className="h-3 w-3 shrink-0 text-text-subtle" aria-hidden="true" />
        </span>

        <span className="min-w-0 flex-1">
          <span className="block text-[13px] text-text leading-snug break-words">
            {issue.title}
          </span>
          <span className="mono-label block mt-1.5">{issue.category}</span>
        </span>

        <ChevronDown
          className={`h-3.5 w-3.5 shrink-0 mt-1 text-text-subtle transition-transform duration-200 ${
            open ? 'rotate-180' : ''
          }`}
          aria-hidden="true"
        />
      </button>

      {open && (
        <div className="api-evidence px-1 pb-5 space-y-4 min-w-0 sm:pl-36">
          {hasFile && (
            <div className="min-w-0">
              <span className="mono-label block mb-2">FILE PATH</span>
              <FilePath path={issue.affectedFile} tone="primary" size="sm" />
            </div>
          )}

          <div className="pt-4 hair-t">
            <span className="mono-label block mb-2">ESTIMATED IMPACT</span>
            <p className="text-[12px] text-text-muted leading-relaxed max-w-[70ch]">
              {issue.impact}
            </p>
          </div>

          <div className="pt-4 hair-t">
            <span className="mono-label block mb-2">RECOMMENDED FIX</span>
            <p className="text-[12px] text-text-muted leading-relaxed max-w-[70ch]">
              {issue.fix}
            </p>
          </div>

          {hasFile && (
            <div className="flex flex-wrap items-center gap-x-6 gap-y-2 pt-4 hair-t">
              <button
                type="button"
                onClick={() => openInGraph(owner, repo, issue.affectedFile)}
                className="api-action link-arrow"
              >
                View in Graph
                <ArrowRight className="h-3 w-3 arrow" aria-hidden="true" />
              </button>
              <button
                type="button"
                onClick={() =>
                  openInChat(
                    owner,
                    repo,
                    issue.affectedFile,
                    `Regarding \`${issue.affectedFile}\`: ${issue.title}. How should I approach this?`
                  )
                }
                className="api-action link-arrow"
              >
                Open in Chat
                <ArrowRight className="h-3 w-3 arrow" aria-hidden="true" />
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// ── Main component ─────────────────────────────────────────────────────────

export const ReportPanel: React.FC<ReportPanelProps> = ({ repoName, onNavigate }) => {
  const [report, setReport]   = useState<ReportDataModel | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);
  const [subTab, setSubTab]   = useState<SubTabId>('architecture');

  const [owner, repo] = repoName.split('/');

  /** Same endpoint and method as before; extracted so Refresh can re-run it. */
  const loadReport = useCallback(() => {
    if (!owner || !repo) {
      setError('Invalid repository name');
      setReport(null);
      setLoading(false);
      return;
    }

    setReport(null);
    setLoading(true);
    setError(null);

    fetch(apiUrl(`/api/v1/report/${owner}/${repo}/build`), { method: 'POST' })
      .then((res) => {
        if (!res.ok) throw new Error('Failed to generate intelligence report');
        return res.json();
      })
      .then((data) => { setReport(data); setLoading(false); })
      .catch((err) => { setError(extractErrorMessage(err)); setLoading(false); });
  }, [owner, repo]);

  useEffect(() => { loadReport(); }, [loadReport]);

  const handleExport = (format: 'html' | 'pdf' | 'markdown') => {
    if (!owner || !repo) return;
    const downloadUrl = apiUrl(`/api/v1/report/${owner}/${repo}/download?format=${format}`);
    window.open(downloadUrl, '_blank');
  };

  // Severity mapping preserved exactly as before.
  const parsedIssues = useMemo<ParsedIssue[]>(() => {
    if (!report || !report.refactoring_priorities) return [];

    return report.refactoring_priorities.map((item, idx) => {
      const lower = item.toLowerCase();

      let severity: 'critical' | 'high' | 'medium' | 'low' = 'low';
      let category = 'Code Hygiene';
      let icon: React.ComponentType<{ className?: string }> = Trash2;
      let impact = 'Optimizes code execution path and minimizes static memory leaks';
      let fix = 'Refactor local calls and safely delete the unused function symbol';

      if (lower.includes('volatile') || lower.includes('cycle') || lower.includes('coupling')) {
        severity = lower.includes('volatile') ? 'critical' : 'high';
        category = 'Architecture';
        icon = Layers;
        impact = 'Averts cycle propagation and compiler dependency locks';
        fix = 'Abstract call layers into utilities or register interface handlers';
      } else if (lower.includes('dead') || lower.includes('unused') || lower.includes('hygiene')) {
        severity = 'medium';
        category = 'Code Hygiene';
        icon = Trash2;
        impact = 'Cleans up orphan logic branches and improves project code cleanliness';
        fix = 'Locate caller references and safely clean up dead function definitions';
      } else if (lower.includes('api') || lower.includes('public') || lower.includes('export')) {
        severity = 'medium';
        category = 'API Surface';
        icon = Globe;
        impact = 'Tightens system boundary encapsulation and module stability';
        fix = 'Mark exports as private or document usage metrics';
      } else if (lower.includes('read') || lower.includes('onboard') || lower.includes('path')) {
        severity = 'low';
        category = 'Onboarding';
        icon = BookOpen;
        impact = 'Speeds up developer onboarding paths and code search indexing';
        fix = 'Supplement code comments or update recommended reading lists';
      }

      const pathMatch = item.match(/([a-zA-Z0-9_\-\/]+\.[a-zA-Z0-9]+)/);
      const affectedFile = pathMatch ? pathMatch[1] : 'multiple files';

      return { id: `issue-${idx}`, title: item, severity, category, icon, affectedFile, impact, fix };
    });
  }, [report]);

  const attentionCount = useMemo(
    () => parsedIssues.filter((i) => i.severity === 'critical' || i.severity === 'high' || i.severity === 'medium').length,
    [parsedIssues]
  );

  if (loading) {
    return (
      <div className="space-y-6 select-none">
        <div className="flex items-center gap-3 py-4">
          <RefreshCw className="h-4 w-4 text-primary animate-spin" aria-hidden="true" />
          <span className="mono-label">COMPILING REPOSITORY INTELLIGENCE REPORT</span>
        </div>
        <SkeletonGroup label="Generating report">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            <div className="lg:col-span-4 space-y-4"><SkeletonCard /><SkeletonCard /></div>
            <div className="lg:col-span-8 space-y-4">
              <Skeleton size="h-6 w-1/3" />
              <Skeleton size="h-4 w-full" />
              <Skeleton size="h-4 w-5/6" />
              <Skeleton size="h-4 w-4/5" />
            </div>
          </div>
        </SkeletonGroup>
      </div>
    );
  }

  if (error || !report) {
    return (
      <EmptyState
        tone="danger"
        icon={<AlertTriangle className="h-6 w-6" />}
        title="Report Generation Failed"
        description={error || 'Could not compile report metadata.'}
        action={<Button onClick={loadReport}>Retry</Button>}
      />
    );
  }

  const scoreTone = getScoreTone(report.scores.overall);
  const isHighDebt = report.hygiene.dead_functions_count > 10;
  const isHighComplexity = report.scores.architecture < 70;

  const api = report.api_surface;
  const distanceOutOfRange = api.average_distance_main_sequence > 0.3;
  const ratioOutOfRange =
    api.public_private_ratio < 0.1 || api.public_private_ratio > 0.5;

  const ladder = [
    { label: 'Architecture Stability',       value: report.scores.architecture },
    { label: 'API Quality & Encapsulation',  value: report.scores.api },
    { label: 'Code Hygiene & Pruning',       value: report.scores.hygiene },
    { label: 'Hotspot & Churn Control',      value: report.scores.churn },
    { label: 'Onboarding Clarity',           value: report.scores.readability },
  ];

  return (
    /* pb-24 keeps the sticky footer from ever covering the last section */
    <div className="min-w-0 pb-24">
      {/* ── Header ───────────────────────────────────────────────────────── */}
      <header className="min-w-0">
        <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-5">
          <div className="min-w-0 max-w-2xl">
            <span className="mono-label mono-label-accent block mb-3">AUDIT / HEALTH REPORT</span>
            <h2 className="display-3 text-text">Health Report</h2>
            <p className="text-[13px] text-text-muted leading-relaxed mt-3 max-w-xl">
              Repository architecture, API quality, hygiene, and onboarding readiness.
            </p>

            <div className="flex flex-wrap items-center gap-x-4 gap-y-2 mt-5">
              <span className="font-mono text-[11px] text-text">{report.metadata.repo_name}</span>
              <span className="h-2.5 w-px bg-white/[0.09]" aria-hidden="true" />
              <span className="mono-label" style={{ color: 'var(--success)' }}>INDEXED</span>
              <span className="h-2.5 w-px bg-white/[0.09]" aria-hidden="true" />
              <span className="mono-label">
                GENERATED {relativeTime(report.metadata.generated_at).toUpperCase()}
              </span>
            </div>
          </div>

          <button
            type="button"
            onClick={loadReport}
            className="flex items-center gap-2 mono-label hover:text-text transition-colors
                       focus-visible:outline-none shrink-0"
          >
            <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
            REBUILD
          </button>
        </div>
      </header>

      {/* ── Score anchor + diagnostic strip ──────────────────────────────── */}
      <div className="mt-10 grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-10 items-start">
        {/* The single score visualisation */}
        <Reveal className="lg:col-span-4 min-w-0">
          <div className="flex items-center gap-6">
            <SVGDonut
              value={report.scores.overall}
              size={104}
              strokeWidth={8}
              tone={scoreTone}
              label={
                <>
                  <span className="text-2xl font-bold text-text font-mono leading-none tabular-nums">
                    <AnimatedNumber value={report.scores.overall} duration={900} />
                  </span>
                  <span className="mono-label mt-1" style={{ letterSpacing: '0.2em' }}>
                    HEALTH
                  </span>
                </>
              }
            />
            <div className="min-w-0">
              <span className="mono-label block mb-2">GRADE</span>
              <span
                className={`font-mono font-bold leading-none ${gradeToneClass(report.scores.grade)}`}
                style={{ fontSize: 'clamp(2.25rem, 5vw, 3rem)' }}
              >
                {report.scores.grade}
              </span>
            </div>
          </div>

          {/* Diagnostic ladder */}
          <dl className="mt-8 pt-6 hair-t">
            {ladder.map((item, i) => (
              <div key={item.label} className="py-2.5">
                <div className="flex items-baseline justify-between gap-4">
                  <dt className="text-[12px] text-text-muted truncate">{item.label}</dt>
                  <dd className="font-mono text-[12px] text-text tabular-nums shrink-0">
                    <AnimatedNumber value={item.value} duration={700} startOnView />
                    <span className="text-text-subtle">/100</span>
                  </dd>
                </div>
                <Meter
                  value={item.value / 100}
                  barClassName={scoreBarClass(item.value)}
                  className="mt-2"
                  delay={i * 70}
                />
              </div>
            ))}
          </dl>
        </Reveal>

        {/* Remaining dimensions — hairline cells, not cards */}
        <dl className="lg:col-span-8 grid grid-cols-2 md:grid-cols-3 border-t border-white/[0.055] min-w-0">
          <Readout
            index={0}
            label="MAINTAINABILITY"
            value={<><AnimatedNumber value={report.scores.readability} startOnView />%</>}
            detail="onboarding path coverage"
          />
          <Readout
            index={1}
            label="COMPLEXITY"
            value={isHighComplexity ? 'HIGH' : 'MODERATE'}
            detail="AST call-link density"
          />
          <Readout
            index={2}
            label="ARCHITECTURE HEALTH"
            value={<><AnimatedNumber value={report.scores.architecture} startOnView />%</>}
            detail={report.architecture.cycles_count > 0 ? 'cycles found' : 'acyclic graph'}
            tone={report.architecture.cycles_count > 0 ? 'text-warn' : 'text-success'}
          />
          <Readout
            index={3}
            label="TECHNICAL DEBT"
            value={isHighDebt ? 'MEDIUM' : 'LOW'}
            detail={`${report.hygiene.dead_functions_count.toLocaleString()} orphan / dead symbols`}
            tone={isHighDebt ? 'text-warn' : 'text-text'}
          />
          {/*
            The backend report carries no security scan or performance analysis,
            so these are reported as not measured rather than asserting a pass.
          */}
          <Readout index={4} label="SECURITY" value="—" detail="not measured" tone="text-text-subtle" />
          <Readout index={5} label="PERFORMANCE" value="—" detail="not measured" tone="text-text-subtle" />
        </dl>
      </div>

      <SectionSeam label="DIAGNOSTIC → EVIDENCE" />

      {/* ── Mode rail ────────────────────────────────────────────────────── */}
      <div
        className="inner-scroll-x relative flex items-stretch gap-6 border-y border-white/[0.055]"
        role="tablist"
        aria-label="Report sections"
      >
        {MODES.map(([id, label, Icon]) => {
          const isActive = subTab === id;
          return (
            <button
              key={id}
              role="tab"
              type="button"
              aria-selected={isActive}
              aria-controls={`report-panel-${id}`}
              onClick={() => setSubTab(id)}
              className={`group relative shrink-0 flex items-center gap-2 py-3
                          font-mono text-[11px] uppercase tracking-[0.14em] whitespace-nowrap
                          transition-colors duration-200 focus-visible:outline-none ${
                            isActive ? 'text-text' : 'text-text-subtle hover:text-text-muted'
                          }`}
            >
              <Icon
                className={`h-3.5 w-3.5 shrink-0 ${
                  isActive ? 'text-primary' : 'text-text-subtle group-hover:text-text-muted'
                }`}
                aria-hidden="true"
              />
              {label}
              <span
                aria-hidden="true"
                className="absolute -bottom-px left-0 right-0 h-px origin-left bg-primary"
                style={{
                  transform: `scaleX(${isActive ? 1 : 0})`,
                  transition: 'transform 240ms cubic-bezier(0.16,1,0.3,1)',
                }}
              />
            </button>
          );
        })}
      </div>

      <div id={`report-panel-${subTab}`} role="tabpanel" className="mt-8 min-w-0 panel-enter">
        {/* ── Architecture ───────────────────────────────────────────────── */}
        {subTab === 'architecture' && (
          <div className="space-y-9 min-w-0">
            <dl className="grid grid-cols-2 md:grid-cols-3 border-t border-white/[0.055]">
              <Readout
                index={0}
                label="CIRCULAR IMPORTS"
                value={<AnimatedNumber value={report.architecture.cycles_count} startOnView />}
                tone={report.architecture.cycles_count > 0 ? 'text-warn' : 'text-success'}
              />
              <Readout
                index={1}
                label="SCC CLUSTERS"
                value={<AnimatedNumber value={report.architecture.strongly_connected_components} startOnView />}
              />
              <Readout
                index={2}
                label="DESIGN SMELLS"
                value={<AnimatedNumber value={report.architecture.smells_count} startOnView />}
              />
            </dl>

            <section className="min-w-0">
              <h4 className="mono-label pb-3 hair-b">DEPENDENCY DESIGN VIOLATIONS</h4>
              {report.architecture.smells.length > 0 ? (
                <ul className="min-w-0">
                  {report.architecture.smells.map((smell, idx) => (
                    <li
                      key={idx}
                      className="spec-row flex items-start gap-3 py-3 hair-t last:border-b last:border-white/[0.055]"
                    >
                      <span className="mono-label shrink-0 pt-0.5" style={{ letterSpacing: '0.16em' }}>
                        {String(idx + 1).padStart(2, '0')}
                      </span>
                      <span className="text-[12px] text-text-muted leading-relaxed max-w-[74ch]">
                        {smell}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-[12px] text-text-subtle py-4">No dependency smells detected.</p>
              )}
            </section>

            <section className="min-w-0">
              <h4 className="mono-label pb-3 hair-b">CIRCULAR IMPORT PATHS</h4>
              {report.architecture.cycles.length > 0 ? (
                <BoundedList total={report.architecture.cycles.length} preview={6} label="CYCLES">
                  {(limit) => (
                    <ul className="min-w-0">
                      {(limit === null
                        ? report.architecture.cycles
                        : report.architecture.cycles.slice(0, limit)
                      ).map((cycle, idx) => {
                        const entry = cycle[0];
                        const exit = cycle[cycle.length - 1] ?? entry;
                        return (
                          <li
                            key={idx}
                            className="topo-item spec-row py-4 hair-t last:border-b last:border-white/[0.055] min-w-0"
                          >
                            {/* The loop stated explicitly: source → target → back */}
                            <FilePath path={entry} tone="primary" size="sm" />
                            <div className="flex items-center gap-2.5 my-2">
                              <span className="topo-type font-mono text-[10px] uppercase tracking-[0.24em]">
                                imports
                              </span>
                              <span className="topo-edge h-px flex-1" aria-hidden="true" />
                              <span className="topo-type text-[10px] shrink-0" aria-hidden="true">↓</span>
                            </div>
                            <FilePath path={exit} tone="secondary" size="sm" marker="target" />

                            {cycle.length > 2 && (
                              <p className="mono-detail mt-2" style={{ fontSize: 10 }}>
                                VIA {cycle.length - 2} INTERMEDIATE{cycle.length - 2 === 1 ? '' : 'S'}
                              </p>
                            )}

                            <div className="flex flex-wrap items-center gap-x-6 gap-y-2 mt-3">
                              <button
                                type="button"
                                onClick={() => openInGraph(owner, repo, entry)}
                                className="api-action link-arrow"
                              >
                                View in Graph
                                <ArrowRight className="h-3 w-3 arrow" aria-hidden="true" />
                              </button>
                              <button
                                type="button"
                                onClick={() =>
                                  openInChat(
                                    owner,
                                    repo,
                                    entry,
                                    `There is a circular import involving \`${entry}\`. How should I break this cycle?`
                                  )
                                }
                                className="api-action link-arrow"
                              >
                                Open in Chat
                                <ArrowRight className="h-3 w-3 arrow" aria-hidden="true" />
                              </button>
                            </div>
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </BoundedList>
              ) : (
                <p className="text-[12px] text-text-subtle py-4">
                  No circular import loops detected.
                </p>
              )}
            </section>
          </div>
        )}

        {/* ── API Surface ────────────────────────────────────────────────── */}
        {subTab === 'api' && (
          <div className="space-y-9 min-w-0">
            <dl className="grid grid-cols-2 md:grid-cols-3 border-t border-white/[0.055]">
              <Readout
                index={0}
                label="EXPORTED SYMBOLS"
                value={<AnimatedNumber value={api.total_exported_symbols} startOnView />}
              />
              <Readout
                index={1}
                label="PUBLIC / PRIVATE RATIO"
                value={<AnimatedNumber value={api.public_private_ratio} decimals={2} startOnView />}
                tone={ratioOutOfRange ? 'text-warn' : 'text-success'}
              />
              <Readout
                index={2}
                label="AVG DISTANCE"
                value={
                  <AnimatedNumber value={api.average_distance_main_sequence} decimals={2} startOnView />
                }
                tone={distanceOutOfRange ? 'text-warn' : 'text-success'}
              />
            </dl>

            <section className="min-w-0">
              <h4 className="mono-label pb-3 hair-b">API PACKAGING STABILITY</h4>
              <p className="text-[12px] text-text-muted leading-relaxed mt-4 max-w-[74ch]">
                A stable design aligns packaging along the main sequence. A public-to-private symbol
                ratio below 0.5 suggests healthy encapsulation.
              </p>

              {/* Evidence table — emphasis only where a value is out of range */}
              <div className="mt-5 min-w-0">
                <div className="grid grid-cols-[1fr_auto_auto] gap-x-4 sm:gap-x-8 pb-2 hair-b">
                  <span className="mono-label">CATEGORY</span>
                  <span className="mono-label text-right">VALUE</span>
                  <span className="mono-label text-right">TARGET</span>
                </div>
                {[
                  {
                    k: 'Average Distance',
                    v: api.average_distance_main_sequence.toFixed(2),
                    t: '≤ 0.3',
                    bad: distanceOutOfRange,
                  },
                  {
                    k: 'Public / Private Ratio',
                    v: api.public_private_ratio.toFixed(2),
                    t: '0.1 – 0.5',
                    bad: ratioOutOfRange,
                  },
                ].map((row) => (
                  <div
                    key={row.k}
                    className="grid grid-cols-[1fr_auto_auto] gap-x-4 sm:gap-x-8 py-3 hair-t last:border-b last:border-white/[0.055] items-baseline"
                  >
                    <span className="text-[12px] text-text-muted truncate">{row.k}</span>
                    <span
                      className={`font-mono text-[13px] tabular-nums text-right ${
                        row.bad ? 'text-warn' : 'text-text'
                      }`}
                    >
                      {row.v}
                    </span>
                    <span className="mono-detail text-right" style={{ fontSize: 10 }}>
                      {row.t}
                    </span>
                  </div>
                ))}
              </div>

              {onNavigate && (
                <button
                  type="button"
                  onClick={() => onNavigate('api_surface')}
                  className="api-action link-arrow mt-5"
                >
                  View API Surface
                  <ArrowRight className="h-3 w-3 arrow" aria-hidden="true" />
                </button>
              )}
            </section>
          </div>
        )}

        {/* ── Hygiene ────────────────────────────────────────────────────── */}
        {subTab === 'hygiene' && (
          <div className="space-y-9 min-w-0">
            <dl className="grid grid-cols-2 border-t border-white/[0.055]">
              <Readout
                index={0}
                label="DEAD FUNCTIONS"
                value={<AnimatedNumber value={report.hygiene.dead_functions_count} startOnView />}
                tone={report.hygiene.dead_functions_count > 0 ? 'text-warn' : 'text-success'}
              />
              <Readout
                index={1}
                label="DEAD CODE RATIO"
                value={
                  <>
                    <AnimatedNumber value={report.hygiene.dead_code_ratio} decimals={1} startOnView />%
                  </>
                }
              />
            </dl>

            <section className="min-w-0">
              <h4 className="mono-label pb-3 hair-b">DEAD CODE REGISTRY</h4>
              {report.hygiene.dead_functions.length > 0 ? (
                <BoundedList
                  total={report.hygiene.dead_functions.length}
                  preview={8}
                  label="FINDINGS"
                >
                  {(limit) => (
                    <ul className="min-w-0">
                      {(limit === null
                        ? report.hygiene.dead_functions
                        : report.hygiene.dead_functions.slice(0, limit)
                      ).map((func, idx) => (
                        <li
                          key={idx}
                          className="spec-row flex items-center justify-between gap-4 py-3.5 hair-t last:border-b last:border-white/[0.055] min-w-0"
                        >
                          <FilePath path={func} tone="secondary" size="sm" />
                          <span className="mono-label shrink-0" style={{ color: 'var(--warn)' }}>
                            UNUSED
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </BoundedList>
              ) : (
                <p className="text-[12px] text-text-subtle py-4">
                  No unused functions detected in call graph sweep.
                </p>
              )}
            </section>
          </div>
        )}

        {/* ── Onboarding ─────────────────────────────────────────────────── */}
        {subTab === 'onboarding' && (
          <div className="space-y-9 min-w-0">
            <dl className="grid grid-cols-2 border-t border-white/[0.055]">
              <Readout
                index={0}
                label="READING PATH COVERAGE"
                value={
                  <>
                    <AnimatedNumber value={report.onboarding.reading_path_completeness} startOnView />%
                  </>
                }
                tone={report.onboarding.reading_path_completeness > 0 ? 'text-text' : 'text-warn'}
              />
              <Readout
                index={1}
                label="PRIMARY ENTRY POINTS"
                value={<AnimatedNumber value={report.onboarding.core_entry_points.length} startOnView />}
              />
            </dl>

            <section className="min-w-0">
              <h4 className="mono-label pb-3 hair-b">MAIN ENTRY POINTS</h4>
              {report.onboarding.core_entry_points.length > 0 ? (
                <BoundedList
                  total={report.onboarding.core_entry_points.length}
                  preview={10}
                  label="ENTRY POINTS"
                >
                  {(limit) => (
                    <ol className="min-w-0">
                      {(limit === null
                        ? report.onboarding.core_entry_points
                        : report.onboarding.core_entry_points.slice(0, limit)
                      ).map((entry, idx) => (
                        <li
                          key={`${entry}-${idx}`}
                          className="spec-row flex items-baseline gap-4 py-3 hair-t last:border-b last:border-white/[0.055] min-w-0"
                        >
                          <span className="mono-label shrink-0" style={{ letterSpacing: '0.16em' }}>
                            {String(idx + 1).padStart(2, '0')}
                          </span>
                          <FilePath path={entry} tone="secondary" size="sm" />
                        </li>
                      ))}
                    </ol>
                  )}
                </BoundedList>
              ) : (
                <p className="text-[12px] text-text-subtle py-4">
                  No main code entry points detected.
                </p>
              )}
            </section>

            <section className="min-w-0">
              <h4 className="mono-label pb-3 hair-b">TOPOLOGICAL READING ORDER</h4>
              <p className="text-[12px] text-text-muted leading-relaxed mt-4 max-w-[74ch]">
                Read these modules in sequence to move from base imports up to high-level
                controllers.
              </p>
              {report.onboarding.recommended_reading_path.length > 0 ? (
                <div className="mt-4">
                  <BoundedList
                    total={report.onboarding.recommended_reading_path.length}
                    preview={10}
                    label="STEPS"
                  >
                    {(limit) => (
                      <ol className="min-w-0">
                        {(limit === null
                          ? report.onboarding.recommended_reading_path
                          : report.onboarding.recommended_reading_path.slice(0, limit)
                        ).map((path, idx) => (
                          <li
                            key={`${path}-${idx}`}
                            className="spec-row flex items-baseline gap-4 py-3 hair-t last:border-b last:border-white/[0.055] min-w-0"
                          >
                            <span className="mono-label shrink-0" style={{ letterSpacing: '0.16em' }}>
                              {String(idx + 1).padStart(2, '0')}
                            </span>
                            <FilePath path={path} tone="secondary" size="sm" />
                          </li>
                        ))}
                      </ol>
                    )}
                  </BoundedList>
                </div>
              ) : (
                <p className="text-[12px] text-text-subtle py-4">No reading path compiled.</p>
              )}
            </section>
          </div>
        )}
      </div>

      <SectionSeam label="EVIDENCE → PRIORITIES" />

      {/* ── Prioritized action issues ────────────────────────────────────── */}
      <section aria-labelledby="priorities-heading" className="min-w-0">
        <div className="flex flex-wrap items-baseline justify-between gap-4 pb-3 hair-b">
          <h3 id="priorities-heading" className="mono-label mono-label-accent">
            PRIORITIZED ACTION ISSUES
          </h3>
          <span className="mono-detail tabular-nums shrink-0" style={{ fontSize: 10 }}>
            {attentionCount > 0
              ? `${String(attentionCount).padStart(2, '0')} NEED ATTENTION`
              : `${String(parsedIssues.length).padStart(2, '0')} ITEMS`}
          </span>
        </div>

        {parsedIssues.length > 0 ? (
          <div className="min-w-0">
            {parsedIssues.map((issue) => (
              <IssueRow key={issue.id} issue={issue} owner={owner} repo={repo} />
            ))}
          </div>
        ) : (
          <p className="text-[12px] text-text-subtle py-4">No action items required.</p>
        )}
      </section>

      {/* ── Sticky export footer ─────────────────────────────────────────── */}
      <div
        className="sticky bottom-0 z-30 mt-12 -mx-4 sm:-mx-6 lg:-mx-8 px-4 sm:px-6 lg:px-8
                   border-t border-white/[0.055] bg-canvas/85 backdrop-blur-sm
                   flex flex-wrap items-center justify-between gap-x-6 gap-y-2 py-2.5"
      >
        <span className="flex flex-wrap items-center gap-x-3 gap-y-1 min-w-0">
          <span className="mono-label">
            GRADE{' '}
            <span className={`font-bold ${gradeToneClass(report.scores.grade)}`}>
              {report.scores.grade}
            </span>
          </span>
          <span className="h-2.5 w-px bg-white/[0.09] hidden sm:block" aria-hidden="true" />
          <span className="mono-detail truncate hidden sm:inline" style={{ fontSize: 10 }}>
            {report.metadata.repo_name}
          </span>
          <span className="h-2.5 w-px bg-white/[0.09] hidden md:block" aria-hidden="true" />
          <span className="mono-detail hidden md:inline" style={{ fontSize: 10 }}>
            {relativeTime(report.metadata.generated_at)}
          </span>
        </span>

        <div className="flex items-center gap-4 shrink-0">
          <button
            type="button"
            onClick={() => handleExport('html')}
            className="api-action"
            aria-label="Export report as HTML"
          >
            <Download className="h-3.5 w-3.5" aria-hidden="true" />
            <span className="hidden sm:inline">HTML</span>
          </button>
          <button
            type="button"
            onClick={() => handleExport('markdown')}
            className="api-action"
            aria-label="Export report as Markdown"
          >
            <FileText className="h-3.5 w-3.5" aria-hidden="true" />
            <span className="hidden sm:inline">Markdown</span>
          </button>
          <button
            type="button"
            onClick={() => handleExport('pdf')}
            className="action-chip"
            aria-label="Print or save report as PDF"
          >
            <Printer className="h-3.5 w-3.5" aria-hidden="true" />
            <span className="hidden sm:inline">Print / PDF</span>
          </button>
        </div>
      </div>
    </div>
  );
};

export default ReportPanel;
