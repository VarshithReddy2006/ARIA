/**
 * DeadCodeAnalyzer — reachability audit.
 *
 * Reads as one forensic engineering report rather than a stack of cards:
 *
 *   HEADER → SPECIFICATION STRIP → RECOMMENDATIONS (editorial list)
 *   → UNUSED FILES (column registry) → ORPHAN MODULES (labelled records)
 *   → DEAD CHAINS (directional trace) → RUN SUMMARY
 *
 * The four evidence types are deliberately given four different shapes — a
 * ranked list, a tabular registry, labelled key/value records and a directional
 * trace — so a reader can tell which kind of finding they are looking at from
 * the layout alone.
 *
 * Typography rule: uppercase monospace is reserved for labels, statuses,
 * telemetry and paths. Titles, explanations and reasoning keep the backend's own
 * readable casing.
 *
 * Every figure comes from `POST /api/v1/dead-code/analyze` unchanged. The score
 * is presented as a measured value, not a pass/fail verdict, and red is reserved
 * for genuine risk — "unused" and "orphaned" are findings, not failures.
 */

import React, { useCallback, useMemo, useState } from 'react';
import { apiUrl, extractErrorMessage } from '../../lib/api';
import { AlertTriangle, ArrowRight, Loader2 } from 'lucide-react';
import { PrerequisitesBanner } from './pr/PrerequisitesBanner';
import { usePrerequisites } from './pr/usePrerequisites';
import { SkeletonCard, SkeletonGroup } from '../ui/Skeleton';
import { FilePath } from '../ui/FilePath';
import { SectionSeam } from '../ui/SectionSeam';
import { Reveal } from '../ui/Reveal';

interface DeadFile {
  file_path: string;
  confidence: number;
  risk_level: string;
  recommendation: string;
}

interface OrphanModule {
  file_path: string;
  confidence: number;
  risk_level: string;
  recommendation: string;
  last_reachable_parent?: string;
}

interface DeadDependencyChain {
  chain: string[];
  confidence: number;
  risk_level: string;
  recommendation: string;
  length: number;
  total_nodes: number;
  max_centrality: number;
}

interface DeadCodeResult {
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

interface Props { repoName?: string }

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

/**
 * Risk tone. Only genuinely risky levels reach red; "safe" is informational
 * green and "review" is amber. Unknown levels stay neutral rather than guessing.
 */
function riskToneClass(level: string): string {
  const l = (level || '').toLowerCase();
  if (l === 'safe' || l === 'low') return 'text-success';
  if (l === 'review' || l === 'medium' || l === 'moderate') return 'text-warn';
  if (l === 'high' || l === 'critical' || l === 'danger') return 'text-danger';
  return 'text-text-muted';
}

/** Effort is not risk, so high effort reads amber rather than red. */
function effortToneClass(effort: string): string {
  const e = (effort || '').toLowerCase();
  if (e === 'high') return 'text-warn';
  if (e === 'low') return 'text-success';
  return 'text-text';
}

function pct(value: number): string {
  return `${(value * 100).toFixed(0)}%`;
}

/** `15 AUG 2026 · 09:00` — compact enough to sit in a strip cell on one line. */
function formatAnalyzed(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const day = String(d.getDate()).padStart(2, '0');
  const month = d.toLocaleString('en-US', { month: 'short' }).toUpperCase();
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  return `${day} ${month} ${d.getFullYear()} · ${hh}:${mm}`;
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

/** Cross-surface navigation via the contracts the dashboard already listens for. */
function openInGraph(repoSlug: string, path: string) {
  const [owner, repo] = repoSlug.split('/');
  window.dispatchEvent(
    new CustomEvent('aria-open-graph', {
      detail: { owner, repo, path, source: 'dead-code' },
    })
  );
}

function openInChat(repoSlug: string, path: string, prompt: string) {
  const [owner, repo] = repoSlug.split('/');
  window.dispatchEvent(
    new CustomEvent('aria-open-chat', {
      detail: { owner, repo, path, source: 'dead-code', prompt },
    })
  );
}

const PATH_RE = /([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)/;

/**
 * Splits a recommendation string into a title, an optional path and the
 * remaining explanation. Purely a display split of the backend string — the
 * casing is left exactly as the backend wrote it and the full original text is
 * preserved on the row via `title`.
 */
function splitRecommendation(text: string): { action: string; path: string | null; rest: string } {
  const colon = text.indexOf(':');
  const action = colon > 0 ? text.slice(0, colon).trim() : text.trim();
  const remainder = colon > 0 ? text.slice(colon + 1).trim() : '';
  const match = PATH_RE.exec(remainder) || (colon > 0 ? null : PATH_RE.exec(text));
  const path = match ? match[1] : null;
  const rest = path ? remainder.replace(path, '').replace(/^[\s·—-]+/, '').trim() : remainder;
  return { action, path, rest };
}

/**
 * Bounded evidence registry: a preview, then a fixed-height scroll region.
 *
 * Bounded rather than growing so a repository with 1,000 findings does not turn
 * the page into an unnavigable column. The continuation control names what it
 * expands so it reads as "keep going", not as a button.
 */
const BoundedRegistry: React.FC<{
  total: number;
  preview: number;
  noun: string;
  children: (limit: number | null) => React.ReactNode;
}> = ({ total, preview, noun, children }) => {
  const [expanded, setExpanded] = useState(false);
  const overflow = total > preview;
  const shown = expanded ? total : Math.min(preview, total);

  return (
    <>
      <p className="mono-detail mb-2.5 tabular-nums" style={{ fontSize: 10 }}>
        SHOWING {shown.toLocaleString()} OF {total.toLocaleString()}
      </p>

      <div className={expanded ? 'max-h-[24rem] overflow-y-auto pr-1 -mr-1 min-w-0' : 'min-w-0'}>
        {children(expanded ? null : preview)}
      </div>

      {overflow && (
        <button
          type="button"
          onClick={() => setExpanded((p) => !p)}
          className="api-action link-arrow mt-4"
          aria-expanded={expanded}
        >
          {expanded ? `SHOW FEWER ${noun}` : `VIEW ALL ${total.toLocaleString()} ${noun}`}
          <ArrowRight className="h-3 w-3 arrow" aria-hidden="true" />
        </button>
      )}
    </>
  );
};

/**
 * Evidence row actions. Arrowed so they read as navigation into another
 * instrument rather than as another piece of metadata on the row.
 */
const RowActions: React.FC<{ repoSlug: string; path: string; question: string }> = ({
  repoSlug,
  path,
  question,
}) => (
  <span className="flex items-center gap-x-4 gap-y-1 flex-wrap">
    <button
      type="button"
      onClick={() => openInGraph(repoSlug, path)}
      className="api-action link-arrow"
      aria-label={`View ${path} in the file graph`}
    >
      GRAPH
      <ArrowRight className="h-2.5 w-2.5 arrow ml-1" aria-hidden="true" />
    </button>
    <button
      type="button"
      onClick={() => openInChat(repoSlug, path, question)}
      className="api-action link-arrow"
      aria-label={`Ask ARIA about ${path}`}
    >
      CHAT
      <ArrowRight className="h-2.5 w-2.5 arrow ml-1" aria-hidden="true" />
    </button>
  </span>
);

/** A registry section title with a subordinate count. */
const RegistryHeading: React.FC<{
  id: string;
  title: string;
  criterion: string;
  count?: string;
}> = ({ id, title, criterion, count }) => (
  <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1 pb-3 hair-b">
    <h3 id={id} className="mono-label">
      {title}
    </h3>
    <span className="flex items-baseline gap-4 shrink-0">
      {count && <span className="text-[11px] text-text-subtle tabular-nums">{count}</span>}
      <span className="mono-detail" style={{ fontSize: 10 }}>
        {criterion}
      </span>
    </span>
  </div>
);

/** One labelled field inside an orphan record. */
const RecordField: React.FC<{ label: string; children: React.ReactNode; className?: string }> = ({
  label,
  children,
  className = '',
}) => (
  <div className={`min-w-0 ${className}`}>
    <dt className="mono-label mb-1" style={{ fontSize: 9 }}>
      {label}
    </dt>
    <dd className="min-w-0">{children}</dd>
  </div>
);

export const DeadCodeAnalyzer: React.FC<Props> = ({ repoName }) => {
  const [activeRepo, setActiveRepo] = useState(() => resolveRepo(repoName));
  const { healthStatus, hasPrerequisites, isRepairing, repair } = usePrerequisites(activeRepo);

  const [isLoading, setIsLoading] = useState(false);
  const [analyzerResult, setAnalyzerResult] = useState<DeadCodeResult | null>(null);
  const [errorMsg, setErrorMsg] = useState('');

  // Sync activeRepo with repoName prop changes and clear stale results
  React.useEffect(() => {
    const nextRepo = resolveRepo(repoName);
    setActiveRepo(nextRepo);
    setAnalyzerResult(null);
    setErrorMsg('');
  }, [repoName]);

  const handleRunAnalysis = useCallback(async () => {
    if (!activeRepo) { setErrorMsg('No active repository loaded.'); return; }
    const [owner, repo] = activeRepo.split('/');
    if (!owner || !repo) { setErrorMsg('Invalid repository identifier.'); return; }

    setIsLoading(true);
    setErrorMsg('');
    setAnalyzerResult(null);

    try {
      const res = await fetch(apiUrl('/api/v1/dead-code/analyze'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ owner, repo }),
      });
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(extractErrorMessage(errorData));
      }
      setAnalyzerResult(await res.json());
    } catch (err: any) {
      setErrorMsg(extractErrorMessage(err));
    } finally {
      setIsLoading(false);
    }
  }, [activeRepo]);

  /** Reachability movement, stated only from what the payload reports. */
  const scoreNote = useMemo(() => {
    if (!analyzerResult) return null;
    const { cleanup_score: now, previous_cleanup_score: prev } = analyzerResult;
    if (prev === undefined || prev === null) return 'NO HISTORICAL BASELINE';
    if (now === prev) return 'NO REACHABILITY IMPROVEMENT DETECTED';
    return now > prev ? 'REACHABILITY IMPROVED' : 'REACHABILITY REGRESSED';
  }, [analyzerResult]);

  /**
   * The previous score is only worth a line when it actually differs — a
   * "PREVIOUS 00 → 00" caption above a "NO REACHABILITY IMPROVEMENT DETECTED"
   * note says the same thing twice. The data itself is untouched.
   */
  const scoreDelta = useMemo(() => {
    if (!analyzerResult) return null;
    const { cleanup_score: now, previous_cleanup_score: prev } = analyzerResult;
    if (prev === undefined || prev === null || prev === now) return null;
    return `PREVIOUS ${String(prev).padStart(2, '0')} → ${String(now).padStart(2, '0')}`;
  }, [analyzerResult]);

  const runControl = (
    <button
      type="button"
      onClick={handleRunAnalysis}
      disabled={isLoading || !activeRepo || !hasPrerequisites}
      className="action-chip shrink-0 disabled:opacity-40 disabled:cursor-not-allowed"
    >
      {isLoading ? (
        <>
          <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
          Analyzing
        </>
      ) : (
        <>
          Run Analysis
          <ArrowRight className="h-3 w-3" aria-hidden="true" />
        </>
      )}
    </button>
  );

  return (
    <div className="flex flex-col text-text min-w-0">
      {/* ── 01 · Audit header ────────────────────────────────────────────── */}
      <header className="min-w-0">
        <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-5">
          <div className="min-w-0 max-w-2xl">
            <span className="mono-label mono-label-accent block mb-2.5">
              DEAD CODE / REPOSITORY AUDIT
            </span>
            <h2 className="display-3 text-text">Find what the codebase no longer reaches.</h2>
            <p className="text-[13px] text-text-muted leading-relaxed mt-3 max-w-xl">
              Trace unreachable modules, isolated files, and dead dependency chains before they
              become maintenance weight.
            </p>
          </div>
          {runControl}
        </div>

        <p className="mono-label mt-5" style={{ letterSpacing: '0.2em' }}>
          DEPENDENCY GRAPH · REACHABILITY ANALYSIS · PATH FILTERS
        </p>

        {!hasPrerequisites && healthStatus && (
          <div className="mt-6">
            <PrerequisitesBanner
              activeRepo={activeRepo}
              healthStatus={healthStatus}
              onRepair={repair}
              isRepairing={isRepairing}
            />
          </div>
        )}
      </header>

      {errorMsg && (
        <div
          role="alert"
          className="mt-7 flex items-start gap-3 border border-danger/25 bg-danger/[0.04] p-4"
        >
          <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5 text-danger" aria-hidden="true" />
          <p className="text-[12px] text-text-muted leading-relaxed">{errorMsg}</p>
        </div>
      )}

      {/* ── Loading ──────────────────────────────────────────────────────── */}
      {isLoading && (
        <div className="mt-9">
          <SkeletonGroup label="Running dead code analysis">
            <div className="space-y-4">
              <SkeletonCard />
              <SkeletonCard />
            </div>
          </SkeletonGroup>
        </div>
      )}

      {/* ── Compact empty state, integrated with the audit ───────────────── */}
      {!analyzerResult && !isLoading && !errorMsg && hasPrerequisites && (
        <div className="mt-9 pt-6 hair-t">
          <span className="mono-label block mb-2.5">DEAD CODE ANALYSIS NOT RUN</span>
          <p className="text-[13px] text-text-muted leading-relaxed max-w-lg">
            The repository graph has not yet been scanned for unreachable modules, isolated files,
            or dead dependency chains.
          </p>
          <button
            type="button"
            onClick={handleRunAnalysis}
            disabled={isLoading || !activeRepo}
            className="api-action link-arrow mt-4"
          >
            RUN ANALYSIS
            <ArrowRight className="h-3 w-3 arrow" aria-hidden="true" />
          </button>
        </div>
      )}

      {/* ── Results ──────────────────────────────────────────────────────── */}
      {analyzerResult && (
        <div className="min-w-0">
          {/* ── 02 · Specification strip ─────────────────────────────────── */}
          <Reveal className="min-w-0 mt-10">
            {/*
              A real <dl>: these are term/value pairs, so the grid lives on the
              definition list itself rather than on a wrapper div — `dt`/`dd`
              are only valid inside a `dl` (or a `div` grouping within one).
              Vertical hairlines make the four readings one instrument face
              instead of four cards.
            */}
            <dl className="spec-strip grid grid-cols-2 md:grid-cols-4 border-y border-white/[0.055] min-w-0">
              {[
                {
                  k: 'REPOSITORY',
                  v: (
                    <span className="strip-value font-mono text-[14px] text-text break-all">
                      {analyzerResult.repo}
                    </span>
                  ),
                  d: null as string | null,
                },
                {
                  k: 'ANALYZED',
                  v: (
                    <span className="strip-value font-mono text-[14px] text-text tabular-nums">
                      {formatAnalyzed(analyzerResult.analyzed_at)}
                    </span>
                  ),
                  d: null,
                },
                {
                  k: 'ESTIMATED EFFORT',
                  v: (
                    // No `strip-value`: this reading carries a semantic colour,
                    // which hover must not overwrite.
                    <span
                      className={`font-mono text-[14px] uppercase tracking-[0.12em] ${effortToneClass(
                        analyzerResult.estimated_cleanup_effort,
                      )}`}
                    >
                      {analyzerResult.estimated_cleanup_effort}
                    </span>
                  ),
                  d: null,
                },
                {
                  k: 'CLEANUP SCORE',
                  v: (
                    <span className="strip-value font-mono text-[14px] text-text tabular-nums">
                      {String(analyzerResult.cleanup_score).padStart(2, '0')}
                      <span className="text-text-subtle"> / 100</span>
                    </span>
                  ),
                  d: scoreDelta,
                },
              ].map((cell) => (
                <div
                  key={cell.k}
                  className="min-w-0 px-4 sm:px-5 py-3.5
                             border-l border-white/[0.055]
                             [&:nth-child(2n+1)]:border-l-0
                             [&:nth-child(n+3)]:border-t [&:nth-child(n+3)]:border-white/[0.055]
                             md:[&:nth-child(2n+1)]:border-l md:[&:nth-child(4n+1)]:border-l-0
                             md:[&:nth-child(n+3)]:border-t-0"
                >
                  <dt className="mono-label mb-1.5">{cell.k}</dt>
                  <dd className="min-w-0">
                    {cell.v}
                    {cell.d && (
                      <span className="mono-detail block mt-1 truncate" style={{ fontSize: 10 }}>
                        {cell.d}
                      </span>
                    )}
                  </dd>
                </div>
              ))}
            </dl>
          </Reveal>

          {scoreNote && (
            <p className="mono-label mt-4" style={{ letterSpacing: '0.2em' }}>
              {scoreNote}
            </p>
          )}

          {/* ── 03 · Prioritized recommendations ─────────────────────────── */}
          <SectionSeam label="CONTEXT → RECOMMENDATIONS" />

          <section aria-labelledby="dc-recommendations" className="min-w-0">
            <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1 pb-3 hair-b">
              <h3 id="dc-recommendations" className="mono-label mono-label-accent">
                PRIORITIZED RECOMMENDATIONS
              </h3>
              <span className="text-[11px] text-text-subtle tabular-nums shrink-0">
                {analyzerResult.cleanup_recommendations?.length ?? 0} findings
              </span>
            </div>

            {analyzerResult.cleanup_recommendations?.length ? (
              <ol className="min-w-0">
                {analyzerResult.cleanup_recommendations.map((recommendation, idx) => {
                  const { action, path, rest } = splitRecommendation(recommendation);
                  return (
                    <li
                      key={idx}
                      title={recommendation}
                      className="spec-row spec-row--slide group flex items-start gap-4 sm:gap-5 py-4
                                 border-t border-white/[0.055] hover:border-white/[0.09]
                                 last:border-b last:border-white/[0.055] min-w-0
                                 transition-colors duration-200"
                    >
                      <input
                        type="checkbox"
                        className="mt-[7px] h-3 w-3 shrink-0 accent-primary bg-transparent
                                   border border-white/20 focus-visible:outline-none"
                        aria-label={`Mark recommendation ${idx + 1} done`}
                      />
                      <span
                        className="mono-label shrink-0 mt-1 tabular-nums
                                   group-hover:text-primary transition-colors duration-200"
                        style={{ letterSpacing: '0.16em' }}
                      >
                        {String(idx + 1).padStart(2, '0')}
                      </span>

                      <span className="min-w-0 flex-1">
                        {/* The title is the strongest element and keeps the
                            backend's own casing — an audit finding is a sentence,
                            not a status code. */}
                        <span
                          className="block text-[13px] font-medium leading-snug text-text
                                     group-hover:text-white transition-colors duration-200"
                        >
                          {action}
                        </span>
                        {path && (
                          <span className="block mt-1.5 min-w-0">
                            <FilePath path={path} tone="secondary" size="sm" />
                          </span>
                        )}
                        {rest && (
                          <span className="block text-[12px] text-text-muted leading-relaxed mt-1 max-w-[70ch]">
                            {rest}
                          </span>
                        )}
                      </span>
                    </li>
                  );
                })}
              </ol>
            ) : (
              <p className="text-[13px] text-text-muted leading-relaxed py-5 max-w-lg">
                No cleanup recommendations from this run — every module the graph reaches is
                accounted for.
              </p>
            )}
          </section>

          {/* ── 04 · Unused files: a column registry ─────────────────────── */}
          <SectionSeam label="RECOMMENDATIONS → EVIDENCE" />

          <section aria-labelledby="dc-unused" className="min-w-0">
            <RegistryHeading id="dc-unused" title="UNUSED FILES" criterion="IN-DEGREE = 0" />

            {analyzerResult.unused_files?.length ? (
              <BoundedRegistry
                total={analyzerResult.unused_files.length}
                preview={8}
                noun="UNUSED FILES"
              >
                {(limit) => (
                  <>
                    {/* Column captions, once — this is what makes the section
                        read as a registry rather than another prose list. */}
                    {/*
                      `minmax(0, Nfr)` rather than a bare `Nfr`: an `fr` track
                      keeps a min-content floor, and a one-word caption like
                      CONFIDENCE would then push the registry wider than the
                      column. The captions only appear from `lg` — below that the
                      readings are labelled inline instead.
                    */}
                    <div
                      className="hidden lg:grid gap-x-5 pb-2 border-b border-white/[0.055]
                                 lg:grid-cols-[minmax(0,58fr)_minmax(0,10fr)_minmax(0,10fr)_minmax(0,22fr)]"
                      aria-hidden="true"
                    >
                      <span className="mono-label" style={{ fontSize: 9 }}>PATH</span>
                      <span className="mono-label text-right" style={{ fontSize: 9 }}>CONFIDENCE</span>
                      <span className="mono-label" style={{ fontSize: 9 }}>RISK</span>
                      <span className="mono-label text-right" style={{ fontSize: 9 }}>ACTIONS</span>
                    </div>

                    <ul className="min-w-0">
                      {(limit === null
                        ? analyzerResult.unused_files
                        : analyzerResult.unused_files.slice(0, limit)
                      ).map((file, idx) => (
                        <li
                          key={`${file.file_path}-${idx}`}
                          className="api-row py-3 border-b border-white/[0.055] min-w-0"
                        >
                          <div
                            className="grid grid-cols-1 gap-x-5 gap-y-1.5 min-w-0 lg:items-baseline
                                       lg:grid-cols-[minmax(0,58fr)_minmax(0,10fr)_minmax(0,10fr)_minmax(0,22fr)]"
                          >
                            <span className="min-w-0">
                              <FilePath path={file.file_path} tone="primary" size="sm" />
                            </span>

                            {/* Below `lg` the readings stack in the same order but
                                carry their own labels, since the column captions
                                are hidden. */}
                            <span className="font-mono text-[11px] text-text-muted tabular-nums lg:text-right">
                              <span className="lg:hidden mono-label mr-2" style={{ fontSize: 9 }}>
                                CONFIDENCE
                              </span>
                              {pct(file.confidence)}
                            </span>

                            <span
                              className={`font-mono text-[10px] uppercase tracking-[0.16em] ${riskToneClass(
                                file.risk_level,
                              )}`}
                            >
                              <span
                                className="lg:hidden mono-label mr-2 text-text-subtle"
                                style={{ fontSize: 9 }}
                              >
                                RISK
                              </span>
                              {file.risk_level}
                            </span>

                            <span className="lg:justify-self-end">
                              <RowActions
                                repoSlug={analyzerResult.repo}
                                path={file.file_path}
                                question={`Is \`${file.file_path}\` safe to delete? Nothing appears to import it.`}
                              />
                            </span>
                          </div>

                          <p className="text-[12px] text-text-muted leading-relaxed mt-1.5 max-w-[70ch]">
                            {file.recommendation}
                          </p>
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </BoundedRegistry>
            ) : (
              <p className="text-[13px] text-text-muted leading-relaxed py-5 max-w-lg">
                Every top-level file in this repository is reachable from an entry point.
              </p>
            )}
          </section>

          {/* ── 05 · Orphan modules: labelled records ────────────────────── */}
          <SectionSeam label="UNUSED FILES → ORPHAN MODULES" />

          <section aria-labelledby="dc-orphans" className="min-w-0">
            <RegistryHeading
              id="dc-orphans"
              title="ORPHANED MODULES"
              criterion="REQUIRES HUMAN REVIEW"
            />

            {analyzerResult.orphan_modules?.length ? (
              <BoundedRegistry
                total={analyzerResult.orphan_modules.length}
                preview={8}
                noun="ORPHANED MODULES"
              >
                {(limit) => (
                  <ul className="min-w-0">
                    {(limit === null
                      ? analyzerResult.orphan_modules
                      : analyzerResult.orphan_modules.slice(0, limit)
                    ).map((mod, idx) => (
                      <li
                        key={`${mod.file_path}-${idx}`}
                        className="api-row py-3.5 border-b border-white/[0.055] min-w-0"
                      >
                        {/* Four labelled readings: the reasoning is scannable
                            without reading the sentence underneath. */}
                        <dl
                          className="grid grid-cols-2 gap-x-5 gap-y-2.5 min-w-0
                                     lg:grid-cols-[minmax(0,46fr)_minmax(0,26fr)_minmax(0,12fr)_minmax(0,16fr)]"
                        >
                          <RecordField label="MODULE" className="col-span-2 lg:col-span-1">
                            <FilePath path={mod.file_path} tone="primary" size="sm" />
                          </RecordField>

                          <RecordField label="REACHABILITY">
                            {mod.last_reachable_parent ? (
                              <FilePath
                                path={mod.last_reachable_parent}
                                tone="metadata"
                                size="sm"
                              />
                            ) : (
                              <span className="mono-detail" style={{ fontSize: 10 }}>
                                NONE · FULLY ISOLATED
                              </span>
                            )}
                          </RecordField>

                          <RecordField label="CONFIDENCE">
                            <span className="font-mono text-[11px] text-text-muted tabular-nums">
                              {pct(mod.confidence)}
                            </span>
                          </RecordField>

                          <RecordField label="STATUS">
                            <span
                              className={`font-mono text-[10px] uppercase tracking-[0.16em] ${riskToneClass(
                                mod.risk_level,
                              )}`}
                            >
                              {mod.risk_level}
                            </span>
                          </RecordField>
                        </dl>

                        <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2 mt-2.5">
                          <p className="text-[12px] text-text-muted leading-relaxed max-w-[70ch] min-w-0">
                            {mod.recommendation}
                          </p>
                          <RowActions
                            repoSlug={analyzerResult.repo}
                            path={mod.file_path}
                            question={`\`${mod.file_path}\` looks orphaned. What used to reach it, and can it be removed?`}
                          />
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </BoundedRegistry>
            ) : (
              <p className="text-[13px] text-text-muted leading-relaxed py-5 max-w-lg">
                No isolated subgraphs detected — every module is reachable.
              </p>
            )}
          </section>

          {/* ── 06 · Dead dependency chains: directional trace ───────────── */}
          <SectionSeam label="ORPHAN MODULES → DEAD CHAINS" />

          <section aria-labelledby="dc-chains" className="min-w-0">
            <RegistryHeading id="dc-chains" title="DEAD DEPENDENCY CHAINS" criterion="LENGTH ≥ 2" />

            {analyzerResult.dead_dependency_chains?.length ? (
              <BoundedRegistry
                total={analyzerResult.dead_dependency_chains.length}
                preview={6}
                noun="CHAINS"
              >
                {(limit) => (
                  <ul className="min-w-0">
                    {(limit === null
                      ? analyzerResult.dead_dependency_chains
                      : analyzerResult.dead_dependency_chains.slice(0, limit)
                    ).map((c, idx) => (
                      <li
                        key={idx}
                        className="topo-item api-row py-4 border-b border-white/[0.055] min-w-0"
                      >
                        <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1 mb-2.5">
                          <span className="mono-label topo-type">
                            CHAIN {String(idx + 1).padStart(2, '0')}
                          </span>
                          <span className="mono-detail tabular-nums shrink-0" style={{ fontSize: 10 }}>
                            {c.total_nodes} NODES · {c.length} {c.length === 1 ? 'HOP' : 'HOPS'}
                          </span>
                        </div>

                        {/* The trace is the point of the record: the source is
                            the strongest element and every hop descends from it. */}
                        <ol className="min-w-0">
                          {c.chain.map((node, nodeIdx) => (
                            <li key={nodeIdx} className="min-w-0">
                              <FilePath
                                path={node}
                                tone={nodeIdx === 0 ? 'primary' : 'secondary'}
                                size="sm"
                              />
                              {nodeIdx < c.chain.length - 1 && (
                                <span
                                  className="flex items-center gap-2 my-1 ml-0.5"
                                  aria-hidden="true"
                                >
                                  <span
                                    className="text-[10px] leading-none"
                                    style={{ color: 'rgba(94, 106, 210, 0.7)' }}
                                  >
                                    ↓
                                  </span>
                                  <span className="topo-edge h-px w-8 shrink-0" />
                                </span>
                              )}
                            </li>
                          ))}
                        </ol>

                        <p className="mono-detail tabular-nums mt-2.5" style={{ fontSize: 10 }}>
                          CENTRALITY {c.max_centrality} · CONFIDENCE {pct(c.confidence)} ·{' '}
                          <span className={riskToneClass(c.risk_level)}>
                            {(c.risk_level || '').toUpperCase()}
                          </span>
                        </p>

                        <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2 mt-2">
                          <p className="text-[12px] text-text-muted leading-relaxed max-w-[70ch] min-w-0">
                            {c.recommendation}
                          </p>
                          <RowActions
                            repoSlug={analyzerResult.repo}
                            path={c.chain[0]}
                            question={`This dependency chain starting at \`${c.chain[0]}\` looks unreachable. Can the whole chain be removed?`}
                          />
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </BoundedRegistry>
            ) : (
              <p className="text-[13px] text-text-muted leading-relaxed py-5 max-w-lg">
                No unreachable dependency chains identified.
              </p>
            )}
          </section>

          {/*
            ── 07 · Run summary ──────────────────────────────────────────────
            Deliberately not a second "ANALYSIS COMPLETE" indicator: the
            dashboard already closes the workspace with one. This line reports
            what only this run knows — the reachability scope and its counts.
          */}
          <footer className="mt-12 pt-5 border-t border-white/[0.055]" aria-label="Dead code run summary">
            <p className="mono-detail tabular-nums" style={{ fontSize: 10, letterSpacing: '0.16em' }}>
              REACHABILITY RUN · {analyzerResult.unused_files?.length ?? 0} UNUSED ·{' '}
              {analyzerResult.orphan_modules?.length ?? 0} ORPHANED ·{' '}
              {analyzerResult.dead_dependency_chains?.length ?? 0} CHAINS · ANALYZED{' '}
              {relativeTime(analyzerResult.analyzed_at).toUpperCase()}
            </p>
          </footer>
        </div>
      )}
    </div>
  );
};

export default DeadCodeAnalyzer;
