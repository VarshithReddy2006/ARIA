import React, { useState } from 'react';
import { apiUrl, extractErrorMessage } from '../../lib/api';
import {
  GitPullRequest, AlertTriangle, Loader2, CheckCircle2, Activity, Award,
  Zap, RefreshCw, Plus, Minus, DoorOpen, ArrowRight, Sparkles,
} from 'lucide-react';
import { PRReferenceForm } from './pr/PRReferenceForm';
import { RiskGauge } from './pr/RiskGauge';
import { PrerequisitesBanner } from './pr/PrerequisitesBanner';
import { DiagnosticsPanel } from './pr/DiagnosticsPanel';
import { usePrerequisites } from './pr/usePrerequisites';
import { riskTextClass } from './pr/risk';
import { EmptyState } from '../ui/EmptyState';
import { SkeletonCard, SkeletonGroup } from '../ui/Skeleton';

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

function categoryBadge(cat: string): { label: string; cls: string } {
  switch ((cat || '').toUpperCase()) {
    case 'CYCLE_INTRODUCED':   return { label: 'Cycle Introduced',   cls: 'bg-danger/10 text-danger border-danger/30' };
    case 'CYCLE_RESOLVED':     return { label: 'Cycle Resolved',     cls: 'bg-success/10 text-success border-success/30' };
    case 'COUPLING_INCREASED': return { label: 'Coupling Increased', cls: 'bg-warn/10 text-warn border-warn/30' };
    case 'COUPLING_DECREASED': return { label: 'Coupling Decreased', cls: 'bg-info/10 text-info border-info/30' };
    case 'ENTRY_POINT_ADDED':  return { label: 'Entry Point Added',  cls: 'bg-info/10 text-info border-info/30' };
    case 'ENTRY_POINT_REMOVED':return { label: 'Entry Point Removed',cls: 'bg-primary/10 text-primary border-primary/30' };
    case 'DEPENDENCY_ADDED':   return { label: 'Dependency Added',   cls: 'bg-primary/10 text-primary border-primary/30' };
    case 'DEPENDENCY_REMOVED': return { label: 'Dependency Removed', cls: 'bg-surface-2 text-text-muted border-border' };
    default: return { label: cat.replace('_', ' '), cls: 'bg-surface-2 text-text-muted border-border' };
  }
}

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
    <div className="flex flex-col gap-6 text-text">
      {/* Inputs & Diagnostics */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 card-padded">
          <div className="flex items-center gap-3 mb-6">
            <GitPullRequest className="w-6 h-6 text-primary" aria-hidden="true" />
            <h2 className="text-lg font-semibold tracking-tight text-text">Architecture Drift Detection</h2>
          </div>

          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
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

            <button
              type="submit"
              disabled={isLoading || !hasPrerequisites}
              className="btn-primary mt-2 py-2.5"
            >
              {isLoading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
                  Analyzing Architecture Drift...
                </>
              ) : 'Analyze Drift'}
            </button>
          </form>

          {errorMsg && (
            <div role="alert" className="mt-4 flex gap-2.5 items-start bg-danger/10 border border-danger/30 rounded-lg p-3 text-sm text-danger font-sans">
              <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5" aria-hidden="true" />
              <span>{errorMsg}</span>
            </div>
          )}
        </div>

        <DiagnosticsPanel
          title="System Diagnostics"
          healthStatus={healthStatus}
          showSymbolIndex={false}
          description="Architecture drift detects cycles, coupling changes, and structural degradation by comparing the baseline indexed graph against modifications in this PR."
        />
      </div>

      {/* Loading skeleton */}
      {isLoading && (
        <SkeletonGroup label="Analyzing architecture drift">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <SkeletonCard />
            <SkeletonCard />
          </div>
        </SkeletonGroup>
      )}

      {/* Initial empty state */}
      {!driftResult && !isLoading && !errorMsg && (
        <EmptyState
          icon={<GitCompareIcon />}
          title="No PR analyzed yet"
          description="Submit a pull request above to detect new cycles, coupling shifts, hotspots, and entry-point changes between the baseline graph and the proposed delta."
        />
      )}

      {/* Results */}
      {driftResult && (
        <div className="flex flex-col gap-6 animate-in fade-in slide-in-from-bottom-2 duration-300">
          {/* PR header */}
          <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-4 card-padded">
            <div>
              <div className="flex items-center gap-2.5 mb-1.5 flex-wrap">
                <span className="text-primary font-bold text-lg font-mono">#{driftResult.pr_number}</span>
                <span className="badge-neutral">Architecture Drift Delta</span>
              </div>
              <h1 className="text-lg font-semibold text-text tracking-tight font-mono">{driftResult.repo}</h1>
              <p className="text-xs text-text-subtle mt-2 font-mono">
                Analyzed at {new Date(driftResult.analyzed_at).toLocaleString()}
              </p>
            </div>

            <div className="flex flex-wrap gap-2 sm:max-w-md justify-start sm:justify-end">
              {driftResult.drift_categories?.map((cat, idx) => {
                const b = categoryBadge(cat);
                return <span key={idx} className={`badge ${b.cls}`}>{b.label}</span>;
              })}
            </div>
          </div>

          {/* Gauges */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <RiskGauge
              score={driftResult.architecture_risk_score}
              label="Architecture Risk Score"
              icon={<Activity className="w-4 h-4 text-warn" aria-hidden="true" />}
              level={driftResult.architecture_risk_level}
              caption={
                <div className="mt-2 font-mono flex items-center gap-1">
                  <span className="text-xs text-text-muted">Severity:</span>
                  <span className={`text-sm font-extrabold ${riskTextClass(driftResult.architecture_risk_level)}`}>
                    {driftResult.architecture_risk_level}
                  </span>
                </div>
              }
            />

            <RiskGauge
              score={driftResult.architecture_improvement_score}
              label="Architecture Improvement Score"
              icon={<Award className="w-4 h-4 text-success" aria-hidden="true" />}
              stroke="#10b981"
              caption={
                <div className="mt-2 font-mono flex items-center gap-1">
                  <Sparkles className="w-3.5 h-3.5 text-success animate-pulse" aria-hidden="true" />
                  <span className="text-xs text-text-muted">
                    {driftResult.architecture_improvement_score > 50 ? 'High Refactor Quality' :
                     driftResult.architecture_improvement_score > 20 ? 'Moderate Improvements' :
                     'No Significant Improvements'}
                  </span>
                </div>
              }
            />
          </div>

          {/* Top findings */}
          <section className="card-padded">
            <h3 className="text-base font-semibold text-text mb-4 flex items-center gap-2 border-b border-border pb-2">
              <Zap className="w-5 h-5 text-primary" aria-hidden="true" />
              Prioritized Top Findings
            </h3>

            {driftResult.top_findings?.length ? (
              <ol className="flex flex-col gap-2.5">
                {driftResult.top_findings.map((finding, idx) => (
                  <li key={idx} className="flex gap-2.5 items-start text-sm bg-canvas/40 border border-border p-3 rounded-lg hover:border-border-strong transition-colors font-sans">
                    <span className="text-primary font-bold shrink-0 mt-0.5 font-mono">[{idx + 1}]</span>
                    <span className="text-text">{finding}</span>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="text-xs font-sans text-text-subtle italic">No significant architectural changes detected.</p>
            )}
          </section>

          {/* Hotspots */}
          <section className="card-padded">
            <h3 className="text-base font-semibold text-text mb-3 flex items-center gap-2 border-b border-border pb-2">
              <AlertTriangle className="w-5 h-5 text-danger" aria-hidden="true" />
              Architectural Hotspots Impacted
            </h3>
            <p className="text-xs text-text-muted mb-4 font-sans">
              Hotspots represent key modules at the intersection of entry points, core codebases, high centrality nodes,
              and top coupling nodes. Changes here increase regression risk.
            </p>

            {driftResult.architectural_hotspots?.length ? (
              <div className="flex flex-wrap gap-2.5">
                {driftResult.architectural_hotspots.map((hotspot, idx) => (
                  <div key={idx} className="flex items-center gap-2 font-mono text-xs bg-danger/10 border border-danger/30 px-3 py-2 rounded-lg text-danger">
                    <Zap className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
                    <span>{hotspot}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs font-sans text-text-subtle italic">No modified architectural hotspots impacted by this PR.</p>
            )}
          </section>

          {/* Cycles */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <CyclePanel
              title="New Cycles Introduced"
              tone="danger"
              icon={<RefreshCw className="w-4 h-4 text-danger animate-spin-slow" aria-hidden="true" />}
              cycles={driftResult.new_cycles}
              empty="Clean build. No new dependency cycles introduced."
            />
            <CyclePanel
              title="Resolved Cycles (Cleaned Up)"
              tone="success"
              icon={<CheckCircle2 className="w-4 h-4 text-success" aria-hidden="true" />}
              cycles={driftResult.resolved_cycles}
              empty="No existing dependency cycles resolved."
            />
          </div>

          {/* Coupling */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <CouplingTable
              title="Node Coupling Increases"
              icon={<Plus className="w-4 h-4 text-warn" aria-hidden="true" />}
              accent="text-warn"
              column="Affected File"
              rows={driftResult.coupling_increase}
              direction="up"
              empty="No significant coupling increases detected."
            />
            <CouplingTable
              title="Node Coupling Decreases"
              icon={<Minus className="w-4 h-4 text-success" aria-hidden="true" />}
              accent="text-success"
              column="Cleaned File"
              rows={driftResult.coupling_decrease}
              direction="down"
              empty="No coupling decreases (cleanups) observed."
            />
          </div>

          {/* Dependency delta */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <EdgeList
              title="Dependency Links Added"
              icon={<Plus className="w-4 h-4 text-purple-400" aria-hidden="true" />}
              accent="text-purple-400"
              edges={driftResult.added_dependencies}
              empty="No new dependency edges established."
            />
            <EdgeList
              title="Dependency Links Removed"
              icon={<Minus className="w-4 h-4 text-text-muted" aria-hidden="true" />}
              accent="text-text-muted"
              edges={driftResult.removed_dependencies}
              empty="No dependency edges deleted."
            />
          </div>

          {/* Entry point changes */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <EntryPointList
              title="New Entry Points Added"
              icon={<DoorOpen className="w-4 h-4 text-info animate-pulse" aria-hidden="true" />}
              accent="text-info"
              items={driftResult.new_entry_points}
              empty="No new modules qualified as application entry points."
            />
            <EntryPointList
              title="Entry Points Removed"
              icon={<Minus className="w-4 h-4 text-text-muted" aria-hidden="true" />}
              accent="text-text-muted"
              items={driftResult.removed_entry_points}
              empty="No existing application entry points were removed."
            />
          </div>
        </div>
      )}
    </div>
  );
};

// ---- helpers ----

const CyclePanel: React.FC<{
  title: string;
  tone: 'danger' | 'success';
  icon: React.ReactNode;
  cycles: string[][];
  empty: string;
}> = ({ title, tone, icon, cycles, empty }) => {
  const accent = tone === 'danger' ? 'text-danger' : 'text-success';
  return (
    <section className="card-padded">
      <h3 className="text-base font-semibold text-text mb-3 flex items-center gap-2 border-b border-border pb-2">
        {icon}<span className={accent}>{title}</span>
      </h3>
      {cycles?.length ? (
        <div className="flex flex-col gap-3">
          {cycles.map((cycle, idx) => (
            <div key={idx} className="bg-canvas/50 border border-border rounded-lg p-3 font-mono text-xs">
              <div className={`text-[10px] font-bold uppercase tracking-wider mb-2 ${accent}`}>
                {tone === 'danger' ? 'Cycle' : 'Resolved'} Loop #{idx + 1}
              </div>
              <div className="flex flex-wrap items-center gap-1.5 text-text">
                {cycle.map((node, nIdx) => (
                  <React.Fragment key={nIdx}>
                    <span className="bg-surface-2 px-2 py-1 rounded border border-border text-text break-all">{node}</span>
                    {nIdx < cycle.length - 1 && <ArrowRight className="w-3 h-3 text-text-subtle shrink-0" aria-hidden="true" />}
                  </React.Fragment>
                ))}
                <ArrowRight className="w-3 h-3 text-text-subtle shrink-0" aria-hidden="true" />
                <span className="bg-surface-2 px-2 py-1 rounded border border-border text-text break-all">{cycle[0]}</span>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-xs font-sans text-text-subtle italic">{empty}</p>
      )}
    </section>
  );
};

const CouplingTable: React.FC<{
  title: string;
  icon: React.ReactNode;
  accent: string;
  column: string;
  rows: { file: string; before: number; after: number }[];
  direction: 'up' | 'down';
  empty: string;
}> = ({ title, icon, accent, column, rows, direction, empty }) => (
  <section className="card-padded">
    <h3 className="text-base font-semibold text-text mb-3 flex items-center gap-2 border-b border-border pb-2">
      {icon}<span className={`${accent} font-bold`}>{title}</span>
    </h3>
    {rows?.length ? (
      <div className="overflow-x-auto">
        <table className="w-full text-left font-mono text-xs text-text">
          <thead>
            <tr className="border-b border-border text-text-subtle text-[10px] uppercase font-bold">
              <th scope="col" className="py-2.5">{column}</th>
              <th scope="col" className="py-2.5 text-center">Before</th>
              <th scope="col" className="py-2.5 text-center">After</th>
              <th scope="col" className="py-2.5 text-center">Δ</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/50">
            {rows.map((c, idx) => {
              const delta = c.after - c.before;
              return (
                <tr key={idx} className="hover:bg-canvas/40">
                  <td className="py-3 pr-2 break-all text-text">{c.file}</td>
                  <td className="py-3 text-center">{c.before}</td>
                  <td className={`py-3 text-center font-semibold ${accent}`}>{c.after}</td>
                  <td className={`py-3 text-center font-bold ${accent}`}>
                    {direction === 'up' ? `+${delta}` : delta}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    ) : (
      <p className="text-xs font-sans text-text-subtle italic">{empty}</p>
    )}
  </section>
);

const EdgeList: React.FC<{
  title: string;
  icon: React.ReactNode;
  accent: string;
  edges: { source: string; target: string }[];
  empty: string;
}> = ({ title, icon, accent, edges, empty }) => (
  <section className="card-padded">
    <h3 className="text-base font-semibold text-text mb-3 flex items-center gap-2 border-b border-border pb-2">
      {icon}<span className={accent}>{title}</span>
    </h3>
    {edges?.length ? (
      <div className="flex flex-col gap-2.5 max-h-96 overflow-y-auto pr-1">
        {edges.map((edge, idx) => (
          <div key={idx} className="bg-canvas/40 border border-border p-2.5 rounded-lg flex items-center justify-between gap-4 font-mono text-xs">
            <div className="break-all text-text">{edge.source}</div>
            <ArrowRight className="w-4 h-4 text-text-subtle shrink-0" aria-hidden="true" />
            <div className="break-all text-text text-right">{edge.target}</div>
          </div>
        ))}
      </div>
    ) : (
      <p className="text-xs font-sans text-text-subtle italic">{empty}</p>
    )}
  </section>
);

const EntryPointList: React.FC<{
  title: string;
  icon: React.ReactNode;
  accent: string;
  items: string[];
  empty: string;
}> = ({ title, icon, accent, items, empty }) => (
  <section className="card-padded">
    <h3 className="text-base font-semibold text-text mb-3 flex items-center gap-2 border-b border-border pb-2">
      {icon}<span className={accent}>{title}</span>
    </h3>
    {items?.length ? (
      <ul className="flex flex-col gap-2">
        {items.map((ep, idx) => (
          <li key={idx} className="font-mono text-xs bg-canvas/40 border border-border p-2.5 rounded-lg text-text break-all">
            {ep}
          </li>
        ))}
      </ul>
    ) : (
      <p className="text-xs font-sans text-text-subtle italic">{empty}</p>
    )}
  </section>
);

// Small inline icon to avoid pulling another lucide import for one-off empty state
const GitCompareIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="5" cy="6" r="3" />
    <path d="M12 6h5a2 2 0 0 1 2 2v7" />
    <circle cx="19" cy="18" r="3" />
    <path d="M12 18H7a2 2 0 0 1-2-2V9" />
  </svg>
);

export default ArchitectureDrift;
