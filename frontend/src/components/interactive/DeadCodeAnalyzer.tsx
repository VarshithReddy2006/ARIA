import React, { useState } from 'react';
import { apiUrl, extractErrorMessage } from '../../lib/api';
import {
  Trash2, AlertTriangle, Loader2, Award, ArrowRight, Sparkles,
  GitBranch, FileCode, FolderOpen,
} from 'lucide-react';
import { RiskGauge } from './pr/RiskGauge';
import { PrerequisitesBanner } from './pr/PrerequisitesBanner';
import { usePrerequisites } from './pr/usePrerequisites';
import { riskBadgeClass, effortBadgeClass } from './pr/risk';
import { EmptyState } from '../ui/EmptyState';
import { SkeletonCard, SkeletonGroup } from '../ui/Skeleton';

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

  const handleRunAnalysis = async () => {
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
  };

  return (
    <div className="flex flex-col gap-6 text-text">
      {/* Trigger */}
      <div className="card-padded flex flex-col gap-4">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2.5">
              <Trash2 className="w-6 h-6 text-primary" aria-hidden="true" />
              <h2 className="text-lg font-semibold tracking-tight text-text">Dead Code Intelligence</h2>
            </div>
            <p className="text-xs text-text-muted max-w-xl font-sans">
              Analyze the active repository's dependency graph for unreachable modules, isolated files, and dead dependency chains.
              Path filters are read from <code className="font-mono text-text">data/dead_code_ignore.json</code>.
            </p>
          </div>

          <button
            type="button"
            onClick={handleRunAnalysis}
            disabled={isLoading || !activeRepo || !hasPrerequisites}
            className="btn-primary shrink-0 px-6 py-3"
          >
            {isLoading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
                Running Dead Code Analysis...
              </>
            ) : 'Run Analysis'}
          </button>
        </div>

        {!hasPrerequisites && healthStatus && (
          <PrerequisitesBanner
            activeRepo={activeRepo}
            healthStatus={healthStatus}
            onRepair={repair}
            isRepairing={isRepairing}
          />
        )}
      </div>

      {errorMsg && (
        <div role="alert" className="flex gap-2.5 items-start bg-danger/10 border border-danger/30 rounded-lg p-4 text-sm text-danger font-sans">
          <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5" aria-hidden="true" />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* Loading skeleton */}
      {isLoading && (
        <SkeletonGroup label="Running dead code analysis">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <SkeletonCard />
            <SkeletonCard className="lg:col-span-2" />
          </div>
          <SkeletonCard className="mt-6" />
        </SkeletonGroup>
      )}

      {/* Initial empty state */}
      {!analyzerResult && !isLoading && !errorMsg && hasPrerequisites && (
        <EmptyState
          icon={<Trash2 className="w-6 h-6" aria-hidden="true" />}
          title="No analysis yet"
          description="Click Run Analysis to scan the dependency graph for unreachable modules, isolated files, and dead chains."
        />
      )}

      {/* Results */}
      {analyzerResult && (
        <div className="flex flex-col gap-6 animate-in fade-in slide-in-from-bottom-2 duration-300">
          {/* Header metadata */}
          <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-4 card-padded">
            <div>
              <span className="text-[10px] uppercase font-bold text-text-subtle tracking-wider font-mono">Repository Context</span>
              <h1 className="text-base font-semibold text-text tracking-tight font-mono mt-0.5">{analyzerResult.repo}</h1>
              <p className="text-xs text-text-subtle mt-1 font-mono">
                Completed at {new Date(analyzerResult.analyzed_at).toLocaleString()}
              </p>
            </div>

            <div className="flex flex-col items-start sm:items-end">
              <span className="text-[10px] font-bold text-text-subtle uppercase tracking-wider font-mono">
                Estimated Cleanup Effort
              </span>
              <span className={`badge mt-1 ${effortBadgeClass(analyzerResult.estimated_cleanup_effort)}`}>
                {analyzerResult.estimated_cleanup_effort}
              </span>
            </div>
          </div>

          {/* Score + recommendations */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <RiskGauge
              score={analyzerResult.cleanup_score}
              label="Codebase Cleanup Score"
              icon={<Award className="w-4 h-4 text-primary" aria-hidden="true" />}
              stroke={
                analyzerResult.cleanup_score > 80 ? '#10b981' :
                analyzerResult.cleanup_score > 60 ? '#eab308' :
                analyzerResult.cleanup_score > 40 ? '#f97316' : '#ef4444'
              }
              caption={
                analyzerResult.previous_cleanup_score !== undefined && analyzerResult.previous_cleanup_score !== null ? (
                  <div className="mt-2 font-mono text-xs text-text-muted flex items-center gap-1">
                    <span>Previous:</span>
                    <span className="font-bold text-text">{analyzerResult.previous_cleanup_score}</span>
                    <ArrowRight className="w-3 h-3" aria-hidden="true" />
                    <span className={`font-bold ${
                      analyzerResult.cleanup_score >= analyzerResult.previous_cleanup_score
                        ? 'text-success' : 'text-danger'
                    }`}>
                      {analyzerResult.cleanup_score}
                    </span>
                  </div>
                ) : (
                  <span className="mt-2 font-mono text-xs text-text-subtle italic">No historical records</span>
                )
              }
            />

            <div className="lg:col-span-2 card-padded flex flex-col">
              <h3 className="text-base font-semibold text-text mb-4 flex items-center gap-2 border-b border-border pb-2">
                <Sparkles className="w-5 h-5 text-warn" aria-hidden="true" />
                Top Cleanup Recommendations
              </h3>

              {analyzerResult.cleanup_recommendations?.length ? (
                <ol className="flex flex-col gap-2.5 flex-grow">
                  {analyzerResult.cleanup_recommendations.map((recommendation, idx) => (
                    <li key={idx} className="flex gap-3 items-start text-sm bg-canvas/40 border border-border p-3 rounded-lg hover:border-primary/40 transition-colors font-sans">
                      <label className="flex items-start gap-2.5 cursor-pointer w-full">
                        <input
                          type="checkbox"
                          className="mt-0.5 h-3.5 w-3.5 rounded border-border accent-primary shrink-0"
                          aria-label={`Mark recommendation ${idx + 1} done`}
                        />
                        <span className="text-warn font-bold shrink-0 mt-0.5 font-mono">[{idx + 1}]</span>
                        <span className="text-text">{recommendation}</span>
                      </label>
                    </li>
                  ))}
                </ol>
              ) : (
                <EmptyState
                  compact
                  tone="success"
                  icon={<Sparkles className="w-6 h-6" aria-hidden="true" />}
                  title="Codebase looks clean"
                  description="No cleanup recommendations from this run."
                />
              )}
            </div>
          </div>

          {/* Unused Files */}
          <section className="card-padded">
            <h3 className="text-base font-semibold text-text mb-3 flex items-center gap-2 border-b border-border pb-2">
              <FileCode className="w-5 h-5 text-primary" aria-hidden="true" />
              Unused Files (In-Degree = 0)
            </h3>

            {analyzerResult.unused_files?.length ? (
              <div className="table-scroll">
                <table className="table-base">
                  <thead>
                    <tr>
                      <th scope="col">File Path</th>
                      <th scope="col" className="text-center">Confidence</th>
                      <th scope="col" className="text-center">Risk</th>
                      <th scope="col">Advice</th>
                    </tr>
                  </thead>
                  <tbody>
                    {analyzerResult.unused_files.map((file, idx) => (
                      <tr key={idx}>
                        <td className="break-all">{file.file_path}</td>
                        <td className="text-center text-text-muted">{(file.confidence * 100).toFixed(0)}%</td>
                        <td className="text-center">
                          <span className={`badge ${riskBadgeClass(file.risk_level)}`}>{file.risk_level}</span>
                        </td>
                        <td className="text-text-muted font-sans">{file.recommendation}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState
                compact
                tone="success"
                icon={<FileCode className="w-6 h-6" aria-hidden="true" />}
                title="No unused root files"
                description="Every top-level file in this repository is reachable from an entry point."
              />
            )}
          </section>

          {/* Orphan Modules */}
          <section className="card-padded">
            <h3 className="text-base font-semibold text-text mb-3 flex items-center gap-2 border-b border-border pb-2">
              <FolderOpen className="w-5 h-5 text-warn" aria-hidden="true" />
              Orphan Modules (In-Degree &gt; 0)
            </h3>

            {analyzerResult.orphan_modules?.length ? (
              <div className="table-scroll">
                <table className="table-base">
                  <thead>
                    <tr>
                      <th scope="col">Module</th>
                      <th scope="col">Last Reachable Parent</th>
                      <th scope="col" className="text-center">Confidence</th>
                      <th scope="col" className="text-center">Risk</th>
                      <th scope="col">Recommendation</th>
                    </tr>
                  </thead>
                  <tbody>
                    {analyzerResult.orphan_modules.map((mod, idx) => (
                      <tr key={idx}>
                        <td className="break-all">{mod.file_path}</td>
                        <td className="break-all">
                          {mod.last_reachable_parent ? (
                            <span className="bg-surface-2 border border-border px-2 py-0.5 rounded text-[10px] text-text-muted">
                              {mod.last_reachable_parent}
                            </span>
                          ) : (
                            <span className="text-text-subtle italic text-[10px] font-sans">None (fully isolated)</span>
                          )}
                        </td>
                        <td className="text-center text-text-muted">{(mod.confidence * 100).toFixed(0)}%</td>
                        <td className="text-center">
                          <span className={`badge ${riskBadgeClass(mod.risk_level)}`}>{mod.risk_level}</span>
                        </td>
                        <td className="text-text-muted font-sans">{mod.recommendation}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState
                compact
                tone="success"
                icon={<FolderOpen className="w-6 h-6" aria-hidden="true" />}
                title="No orphan modules"
                description="No isolated subgraphs detected — every module is reachable."
              />
            )}
          </section>

          {/* Dead chains */}
          <section className="card-padded">
            <h3 className="text-base font-semibold text-text mb-3 flex items-center gap-2 border-b border-border pb-2">
              <GitBranch className="w-5 h-5 text-success" aria-hidden="true" />
              Dead Dependency Chains (Length ≥ 2)
            </h3>

            {analyzerResult.dead_dependency_chains?.length ? (
              <div className="flex flex-col gap-4">
                {analyzerResult.dead_dependency_chains.map((c, idx) => (
                  <div key={idx} className="bg-canvas/50 border border-border rounded-lg p-4 font-mono text-xs space-y-3">
                    <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border pb-2">
                      <div className="text-[10px] text-success font-bold uppercase tracking-wider flex items-center gap-1.5">
                        <Sparkles className="w-3.5 h-3.5" aria-hidden="true" />
                        <span>Chain #{idx + 1} ({c.total_nodes} nodes, {c.length} hops)</span>
                      </div>
                      <div className="flex items-center gap-4 text-[10px] text-text-subtle font-bold uppercase">
                        <span>Centrality: <span className="text-text">{c.max_centrality}</span></span>
                        <span>Confidence: <span className="text-text">{(c.confidence * 100).toFixed(0)}%</span></span>
                        <span>Risk: <span className={`badge ${riskBadgeClass(c.risk_level)}`}>{c.risk_level}</span></span>
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center gap-2 text-text pt-1">
                      {c.chain.map((node, nodeIdx) => (
                        <React.Fragment key={nodeIdx}>
                          <span className="bg-surface-2 px-2.5 py-1 rounded border border-border text-text break-all">{node}</span>
                          {nodeIdx < c.chain.length - 1 && <ArrowRight className="w-3.5 h-3.5 text-text-subtle shrink-0" aria-hidden="true" />}
                        </React.Fragment>
                      ))}
                    </div>

                    <p className="text-xs text-text-muted font-sans italic pt-1">{c.recommendation}</p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs font-sans text-text-subtle italic">No unreachable dependency chains identified.</p>
            )}
          </section>
        </div>
      )}
    </div>
  );
};

export default DeadCodeAnalyzer;
