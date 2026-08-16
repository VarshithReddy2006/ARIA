/**
 * ArchitectureDrift — PR architecture drift.
 *
 * Answers one question: how does this pull request change the architecture? The
 * surface reads in that order:
 *
 *   PR → ARCHITECTURAL DELTA → SCORES → FINDINGS → HOTSPOTS → CHANGE MATRIX
 *
 * Every figure comes from `POST /api/v1/architecture/drift` unchanged. The eight
 * delta categories are collapsed into one change matrix rather than eight
 * half-empty panels, and a zero row stays quiet so it cannot compete with a real
 * finding.
 *
 * Typography rule: uppercase monospace is reserved for labels, statuses, paths
 * and telemetry. Findings keep the backend's readable casing.
 */

import React, { useState } from 'react';
import { apiUrl, extractErrorMessage } from '../../lib/api';
import { AlertTriangle, ArrowRight, Loader2, Zap } from 'lucide-react';
import { PRReferenceForm } from './pr/PRReferenceForm';
import { RiskGauge } from './pr/RiskGauge';
import { PrerequisitesBanner } from './pr/PrerequisitesBanner';
import { DiagnosticsPanel } from './pr/DiagnosticsPanel';
import { usePrerequisites } from './pr/usePrerequisites';
import { riskTextClass } from './pr/risk';
import {
  CommandWorkspace, WaitingState, PRIdentity, SectionHead, MatrixRow,
} from './pr/instrument';
import { SkeletonCard, SkeletonGroup } from '../ui/Skeleton';
import { FilePath } from '../ui/FilePath';
import { SectionSeam } from '../ui/SectionSeam';

interface DependencyEdge { source: string; target: string }
interface CouplingChange { file: string; before: number; after: number }

interface PRDriftResult {
  repo: string;
  pr_number: number;
  architecture_risk_score: number;
  architecture_risk_level: string;
  architecture_improvement_score: number;
  top_findings: string[];
  drift_categories: string[];
  architectural_hotspots: string[];
  added_dependencies: DependencyEdge[];
  removed_dependencies: DependencyEdge[];
  new_cycles: string[][];
  resolved_cycles: string[][];
  coupling_increase: CouplingChange[];
  coupling_decrease: CouplingChange[];
  new_entry_points: string[];
  removed_entry_points: string[];
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

/** Drift category labels and tones — same mapping, text instead of filled badges. */
function categoryLabel(cat: string): { label: string; tone: string } {
  switch ((cat || '').toUpperCase()) {
    case 'CYCLE_INTRODUCED':    return { label: 'CYCLE INTRODUCED',    tone: 'text-danger' };
    case 'CYCLE_RESOLVED':      return { label: 'CYCLE RESOLVED',      tone: 'text-success' };
    case 'COUPLING_INCREASED':  return { label: 'COUPLING INCREASED',  tone: 'text-warn' };
    case 'COUPLING_DECREASED':  return { label: 'COUPLING DECREASED',  tone: 'text-success' };
    case 'ENTRY_POINT_ADDED':   return { label: 'ENTRY POINT ADDED',   tone: 'text-primary' };
    case 'ENTRY_POINT_REMOVED': return { label: 'ENTRY POINT REMOVED', tone: 'text-primary' };
    case 'DEPENDENCY_ADDED':    return { label: 'DEPENDENCY ADDED',    tone: 'text-primary' };
    case 'DEPENDENCY_REMOVED':  return { label: 'DEPENDENCY REMOVED',  tone: 'text-text-muted' };
    default:                    return { label: (cat || '').replace(/_/g, ' '), tone: 'text-text-muted' };
  }
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

/** A cycle rendered as a closed loop of paths. */
const CycleTrace: React.FC<{ cycle: string[]; index: number; tone: string }> = ({
  cycle, index, tone,
}) => (
  <div className="min-w-0">
    <span className={`mono-label block mb-1.5 ${tone}`} style={{ fontSize: 9 }}>
      LOOP #{index + 1}
    </span>
    <ol className="min-w-0">
      {cycle.map((node, nIdx) => (
        <li key={nIdx} className="min-w-0">
          <FilePath path={node} tone={nIdx === 0 ? 'primary' : 'secondary'} size="sm" />
          <span className="flex items-center gap-2 my-1 ml-0.5" aria-hidden="true">
            <span
              className="text-[10px] leading-none"
              style={{ color: 'rgba(94, 106, 210, 0.7)' }}
            >
              ↳
            </span>
            <span className="topo-edge h-px w-8 shrink-0" />
          </span>
        </li>
      ))}
      {/* Closes the loop back to its origin. */}
      <li className="min-w-0">
        <FilePath path={cycle[0]} tone="metadata" size="sm" />
      </li>
    </ol>
  </div>
);

/** Coupling changes as compact before → after readings. */
const CouplingList: React.FC<{ rows: CouplingChange[]; tone: string }> = ({ rows, tone }) => (
  <ul className="min-w-0 space-y-2">
    {rows.map((c, idx) => (
      <li key={`${c.file}-${idx}`} className="min-w-0">
        <FilePath path={c.file} tone="primary" size="sm" />
        <span className="mono-detail block mt-0.5 tabular-nums" style={{ fontSize: 10 }}>
          {c.before} → <span className={tone}>{c.after}</span>
          <span className="text-text-subtle">
            {' '}({c.after - c.before > 0 ? '+' : ''}{c.after - c.before})
          </span>
        </span>
      </li>
    ))}
  </ul>
);

/** Dependency edges as source → target pairs. */
const EdgeTraceList: React.FC<{ edges: DependencyEdge[] }> = ({ edges }) => (
  <ul className="min-w-0 space-y-2">
    {edges.map((edge, idx) => (
      <li key={idx} className="min-w-0">
        <FilePath path={edge.source} tone="primary" size="sm" />
        <span className="flex items-center gap-2 my-0.5 ml-0.5" aria-hidden="true">
          <span className="text-[10px] leading-none" style={{ color: 'rgba(94, 106, 210, 0.7)' }}>
            ↳
          </span>
          <span className="topo-edge h-px w-6 shrink-0" />
        </span>
        <FilePath path={edge.target} tone="secondary" size="sm" />
      </li>
    ))}
  </ul>
);

/** A plain list of paths, used by the entry-point matrix rows. */
const PathList: React.FC<{ paths: string[] }> = ({ paths }) => (
  <ul className="min-w-0 space-y-0.5">
    {paths.map((p, idx) => (
      <li key={`${p}-${idx}`} className="min-w-0">
        <FilePath path={p} tone="primary" size="sm" />
      </li>
    ))}
  </ul>
);

export const ArchitectureDrift: React.FC<Props> = ({ repoName }) => {
  const [activeRepo, setActiveRepo] = useState(() => resolveRepo(repoName));
  const { healthStatus, hasPrerequisites, isRepairing, repair } = usePrerequisites(activeRepo);

  const [useUrl, setUseUrl] = useState(true);
  const [prUrlInput, setPrUrlInput] = useState('');
  const [ownerInput, setOwnerInput] = useState('');
  const [repoInput, setRepoInput] = useState('');
  const [prNumberInput, setPrNumberInput] = useState('');

  const [isLoading, setIsLoading] = useState(false);
  const [driftResult, setDriftResult] = useState<PRDriftResult | null>(null);
  const [errorMsg, setErrorMsg] = useState('');

  // Sync activeRepo with repoName prop changes and clear stale results
  React.useEffect(() => {
    const nextRepo = resolveRepo(repoName);
    setActiveRepo(nextRepo);
    setDriftResult(null);
    setErrorMsg('');
    setPrUrlInput('');
    setOwnerInput('');
    setRepoInput('');
    setPrNumberInput('');
  }, [repoName]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setErrorMsg('');
    setDriftResult(null);

    const payload: any = {};
    if (useUrl) {
      if (!prUrlInput.trim()) { setErrorMsg('Please enter a GitHub Pull Request URL.'); setIsLoading(false); return; }
      payload.pr_url = prUrlInput.trim();
    } else {
      if (!ownerInput.trim() || !repoInput.trim() || !prNumberInput.trim()) {
        setErrorMsg('Please fill in Owner, Repo, and PR Number.'); setIsLoading(false); return;
      }
      payload.owner = ownerInput.trim();
      payload.repo = repoInput.trim();
      payload.pr_number = parseInt(prNumberInput.trim(), 10);
    }

    try {
      const res = await fetch(apiUrl('/api/v1/architecture/drift'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(extractErrorMessage(errorData));
      }
      const data = await res.json();
      setDriftResult(data);
      if (data.repo) setActiveRepo(data.repo);
    } catch (err: any) {
      setErrorMsg(extractErrorMessage(err));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col text-text min-w-0">
      {/* ── 01 · Header ───────────────────────────────────────────────────── */}
      <header className="min-w-0">
        <span className="mono-label mono-label-accent block mb-2.5">
          PR INTELLIGENCE / ARCHITECTURE DRIFT
        </span>
        <h2 className="display-3 text-text">See how this pull request changes the architecture.</h2>
        <p className="text-[13px] text-text-muted leading-relaxed mt-3 max-w-2xl">
          Compare the indexed baseline against this PR to surface cycles, coupling changes,
          dependency movement, and entry-point drift.
        </p>
        {activeRepo && (
          <p className="mono-label mt-5" style={{ letterSpacing: '0.2em' }}>
            REPOSITORY · {activeRepo}
          </p>
        )}
      </header>

      {/* ── 02 · Command workspace ────────────────────────────────────────── */}
      <div className="mt-9 min-w-0">
        <CommandWorkspace
          input={
            <div className="min-w-0">
              <h3 className="mono-label mono-label-accent pb-3 hair-b">PULL REQUEST</h3>

              <form onSubmit={handleSubmit} className="mt-5 flex flex-col gap-5 min-w-0">
                <PRReferenceForm
                  idPrefix="drift"
                  useUrl={useUrl} setUseUrl={setUseUrl}
                  prUrl={prUrlInput} setPrUrl={setPrUrlInput}
                  owner={ownerInput} setOwner={setOwnerInput}
                  repo={repoInput} setRepo={setRepoInput}
                  prNumber={prNumberInput} setPrNumber={setPrNumberInput}
                />

                {!hasPrerequisites && healthStatus && (
                  <PrerequisitesBanner
                    activeRepo={activeRepo}
                    healthStatus={healthStatus}
                    onRepair={repair}
                    isRepairing={isRepairing}
                  />
                )}

                <div className="min-w-0">
                  <button
                    type="submit"
                    disabled={isLoading || !hasPrerequisites}
                    className="action-chip w-full justify-center disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {isLoading ? (
                      <>
                        <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                        Analyzing architecture drift
                      </>
                    ) : (
                      <>
                        Analyze Drift
                        <ArrowRight className="h-3 w-3" aria-hidden="true" />
                      </>
                    )}
                  </button>
                  <div className="mt-2.5" aria-hidden="true">
                    {isLoading ? <div className="activity-line" /> : <div className="h-px" />}
                  </div>
                </div>
              </form>

              {errorMsg && (
                <div role="alert" className="mt-6 flex items-start gap-3">
                  <AlertTriangle
                    className="h-4 w-4 shrink-0 mt-0.5 text-danger"
                    aria-hidden="true"
                  />
                  <div className="min-w-0">
                    <span className="mono-label block mb-1.5" style={{ color: 'var(--danger)' }}>
                      DRIFT ANALYSIS FAILED
                    </span>
                    <p className="text-[12px] text-text-muted leading-relaxed">{errorMsg}</p>
                  </div>
                </div>
              )}
            </div>
          }
          diagnostics={
            <DiagnosticsPanel
              title="SYSTEM DIAGNOSTICS"
              healthStatus={healthStatus}
              showSymbolIndex={false}
              description="Architecture drift detects cycles, coupling changes, and structural degradation by comparing the baseline indexed graph against modifications in this PR."
            />
          }
        />
      </div>

      {/* ── Loading ───────────────────────────────────────────────────────── */}
      {isLoading && (
        <div className="mt-9">
          <SkeletonGroup label="Analyzing architecture drift">
            <div className="space-y-4">
              <SkeletonCard />
              <SkeletonCard />
            </div>
          </SkeletonGroup>
        </div>
      )}

      {/* ── Compact waiting state ─────────────────────────────────────────── */}
      {!driftResult && !isLoading && !errorMsg && (
        <div className="mt-9 pt-6 hair-t">
          <WaitingState
            label="WAITING FOR ARCHITECTURE DIFF"
            pipeline="BASELINE GRAPH + PR CHANGES → DRIFT ANALYSIS"
          >
            Submit a pull request to detect new cycles, coupling shifts, hotspots, and entry-point
            changes between the baseline graph and the proposed delta.
          </WaitingState>
        </div>
      )}

      {/* ── Results ───────────────────────────────────────────────────────── */}
      {driftResult && (
        <div className="min-w-0">
          <SectionSeam label="COMMAND → ARCHITECTURAL DELTA" />

          <PRIdentity
            prNumber={driftResult.pr_number}
            state="ARCHITECTURE DRIFT DELTA"
            subject={
              <p className="font-mono text-[15px] text-text break-all">{driftResult.repo}</p>
            }
            metadata={<>ANALYZED {relativeTime(driftResult.analyzed_at).toUpperCase()}</>}
          />

          {driftResult.drift_categories?.length > 0 && (
            <p className="mono-detail mt-4 min-w-0" style={{ fontSize: 10, letterSpacing: '0.14em' }}>
              {driftResult.drift_categories.map((cat, idx) => {
                const c = categoryLabel(cat);
                return (
                  <React.Fragment key={idx}>
                    {idx > 0 && <span className="text-text-subtle">{'  ·  '}</span>}
                    <span className={c.tone}>{c.label}</span>
                  </React.Fragment>
                );
              })}
            </p>
          )}

          {/* ── 03 · Score band ───────────────────────────────────────────── */}
          <SectionSeam label="DELTA → SCORES" />

          <div
            className="grid grid-cols-1 gap-y-8 items-start min-w-0
                       lg:grid-cols-2 lg:gap-x-8"
          >
            <RiskGauge
              score={driftResult.architecture_risk_score}
              label="ARCHITECTURE RISK"
              level={driftResult.architecture_risk_level}
              levelTone={riskTextClass(driftResult.architecture_risk_level)}
            />

            <div className="min-w-0 lg:pl-8 lg:border-l lg:border-white/[0.055]">
              <RiskGauge
                score={driftResult.architecture_improvement_score}
                label="ARCHITECTURE IMPROVEMENT"
                stroke="#10b981"
                /* Existing thresholds, unchanged. */
                level={
                  driftResult.architecture_improvement_score > 50 ? 'HIGH REFACTOR QUALITY' :
                  driftResult.architecture_improvement_score > 20 ? 'MODERATE IMPROVEMENTS' :
                  'NO SIGNIFICANT IMPROVEMENTS'
                }
                levelTone={
                  driftResult.architecture_improvement_score > 20
                    ? 'text-success'
                    : 'text-text-muted'
                }
              />
            </div>
          </div>

          {/* ── 04 · Prioritized findings ─────────────────────────────────── */}
          <SectionSeam label="SCORES → FINDINGS" />

          <section aria-labelledby="drift-findings" className="min-w-0">
            <SectionHead
              id="drift-findings"
              title="PRIORITIZED FINDINGS"
              accent
              aside={
                driftResult.top_findings?.length ? (
                  <span className="text-[11px] text-text-subtle tabular-nums">
                    {driftResult.top_findings.length} findings
                  </span>
                ) : undefined
              }
            />

            {driftResult.top_findings?.length ? (
              <ol className="min-w-0">
                {driftResult.top_findings.map((finding, idx) => (
                  <li
                    key={idx}
                    className="spec-row spec-row--slide group flex items-start gap-4 py-3.5
                               border-b border-white/[0.055] hover:border-white/[0.09]
                               min-w-0 transition-colors duration-200"
                  >
                    <span
                      className="mono-label shrink-0 mt-0.5 tabular-nums
                                 group-hover:text-primary transition-colors duration-200"
                      style={{ letterSpacing: '0.16em' }}
                    >
                      {String(idx + 1).padStart(2, '0')}
                    </span>
                    <span
                      className="text-[13px] text-text leading-relaxed min-w-0
                                 group-hover:text-white transition-colors duration-200"
                    >
                      {finding}
                    </span>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="mono-label py-4" style={{ letterSpacing: '0.2em' }}>
                NO SIGNIFICANT ARCHITECTURAL CHANGES DETECTED
              </p>
            )}
          </section>

          {/* ── 05 · Architectural hotspots ───────────────────────────────── */}
          <section aria-labelledby="drift-hotspots" className="mt-9 min-w-0">
            <SectionHead
              id="drift-hotspots"
              title="ARCHITECTURAL HOTSPOTS IMPACTED"
              aside={
                driftResult.architectural_hotspots?.length ? (
                  <span className="text-[11px] text-text-subtle tabular-nums">
                    {driftResult.architectural_hotspots.length} impacted
                  </span>
                ) : undefined
              }
            />

            {driftResult.architectural_hotspots?.length ? (
              <ul className="min-w-0">
                {driftResult.architectural_hotspots.map((hotspot, idx) => (
                  <li
                    key={`${hotspot}-${idx}`}
                    className="api-row flex items-baseline gap-3 py-2.5
                               border-b border-white/[0.055] min-w-0"
                  >
                    <Zap className="h-3 w-3 shrink-0 text-danger" aria-hidden="true" />
                    <span className="min-w-0">
                      <FilePath path={hotspot} tone="primary" size="sm" />
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-[13px] text-text-muted leading-relaxed py-4 max-w-lg">
                No modified architectural hotspots impacted by this PR.
              </p>
            )}

            <p className="text-[12px] text-text-subtle leading-relaxed mt-4 max-w-2xl">
              Hotspots are modules at the intersection of entry points, core codebases, high
              centrality nodes, and top coupling nodes. Changes here increase regression risk.
            </p>
          </section>

          {/* ── 06 · Change matrix ────────────────────────────────────────── */}
          <SectionSeam label="HOTSPOTS → CHANGE MATRIX" />

          <section aria-labelledby="drift-matrix" className="min-w-0">
            <SectionHead
              id="drift-matrix"
              title="CHANGE MATRIX"
              aside={
                <span className="mono-detail" style={{ fontSize: 10 }}>
                  BASELINE → PR
                </span>
              }
            />

            {/* Column captions from `sm`; the matrix is a single-column list below that. */}
            <div
              className="hidden sm:grid sm:grid-cols-[minmax(0,34fr)_auto_minmax(0,58fr)]
                         gap-x-5 pb-2 border-b border-white/[0.055]"
              aria-hidden="true"
            >
              <span className="mono-label" style={{ fontSize: 9 }}>CHANGE TYPE</span>
              <span className="mono-label text-right" style={{ fontSize: 9 }}>COUNT</span>
              <span className="mono-label" style={{ fontSize: 9 }}>EVIDENCE</span>
            </div>

            <ul className="min-w-0">
              <MatrixRow
                label="NEW CYCLES"
                count={driftResult.new_cycles?.length ?? 0}
                tone="text-danger"
                quietEvidence="Clean build. No new dependency cycles introduced."
              >
                <div className="space-y-3">
                  {driftResult.new_cycles.map((cycle, idx) => (
                    <CycleTrace key={idx} cycle={cycle} index={idx} tone="text-danger" />
                  ))}
                </div>
              </MatrixRow>

              <MatrixRow
                label="RESOLVED CYCLES"
                count={driftResult.resolved_cycles?.length ?? 0}
                tone="text-success"
                quietEvidence="No existing dependency cycles resolved."
              >
                <div className="space-y-3">
                  {driftResult.resolved_cycles.map((cycle, idx) => (
                    <CycleTrace key={idx} cycle={cycle} index={idx} tone="text-success" />
                  ))}
                </div>
              </MatrixRow>

              <MatrixRow
                label="COUPLING INCREASED"
                count={driftResult.coupling_increase?.length ?? 0}
                tone="text-warn"
                quietEvidence="No significant coupling increases detected."
              >
                <CouplingList rows={driftResult.coupling_increase} tone="text-warn" />
              </MatrixRow>

              <MatrixRow
                label="COUPLING DECREASED"
                count={driftResult.coupling_decrease?.length ?? 0}
                tone="text-success"
                quietEvidence="No coupling decreases (cleanups) observed."
              >
                <CouplingList rows={driftResult.coupling_decrease} tone="text-success" />
              </MatrixRow>

              <MatrixRow
                label="DEPENDENCIES ADDED"
                count={driftResult.added_dependencies?.length ?? 0}
                tone="text-primary"
                quietEvidence="No new dependency edges established."
              >
                <EdgeTraceList edges={driftResult.added_dependencies} />
              </MatrixRow>

              <MatrixRow
                label="DEPENDENCIES REMOVED"
                count={driftResult.removed_dependencies?.length ?? 0}
                tone="text-text-muted"
                quietEvidence="No dependency edges deleted."
              >
                <EdgeTraceList edges={driftResult.removed_dependencies} />
              </MatrixRow>

              <MatrixRow
                label="ENTRY POINTS ADDED"
                count={driftResult.new_entry_points?.length ?? 0}
                tone="text-primary"
                quietEvidence="No new modules qualified as application entry points."
              >
                <PathList paths={driftResult.new_entry_points} />
              </MatrixRow>

              <MatrixRow
                label="ENTRY POINTS REMOVED"
                count={driftResult.removed_entry_points?.length ?? 0}
                tone="text-text-muted"
                quietEvidence="No existing application entry points were removed."
              >
                <PathList paths={driftResult.removed_entry_points} />
              </MatrixRow>
            </ul>
          </section>

          {/*
            A neutral run summary, not a completion badge: the dashboard shell
            owns the single authoritative ANALYSIS COMPLETE indicator, so a green
            "READY" here would be a second one competing with it.
          */}
          <footer className="mt-10 pt-5 border-t border-white/[0.055]" aria-label="Drift analysis summary">
            <p className="mono-detail tabular-nums" style={{ fontSize: 10, letterSpacing: '0.16em' }}>
              DRIFT ANALYSIS ·{' '}
              {driftResult.top_findings?.length ?? 0}{' '}
              {(driftResult.top_findings?.length ?? 0) === 1 ? 'FINDING' : 'FINDINGS'} ·{' '}
              {driftResult.architectural_hotspots?.length ?? 0} HOTSPOTS · ANALYZED{' '}
              {relativeTime(driftResult.analyzed_at).toUpperCase()}
            </p>
          </footer>
        </div>
      )}
    </div>
  );
};

export default ArchitectureDrift;
