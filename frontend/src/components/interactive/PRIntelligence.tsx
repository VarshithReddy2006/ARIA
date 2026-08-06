import React, { useState, useEffect } from 'react';
import { apiUrl, extractErrorMessage } from '../../lib/api';
import {
  GitPullRequest, AlertTriangle, Loader2, CheckCircle2, FileCode, Code2,
  Activity, CornerDownRight, Layers, BookOpen, AlertOctagon,
} from 'lucide-react';
import { PRReferenceForm } from './pr/PRReferenceForm';
import { RiskGauge } from './pr/RiskGauge';
import { PrerequisitesBanner } from './pr/PrerequisitesBanner';
import { DiagnosticsPanel } from './pr/DiagnosticsPanel';
import { usePrerequisites } from './pr/usePrerequisites';
import { riskBadgeClass, sizeBadgeClass } from './pr/risk';
import { EmptyState } from '../ui/EmptyState';
import { SkeletonCard, SkeletonGroup, Skeleton } from '../ui/Skeleton';

interface ChangedFile {
  filename: string;
  status: string;
  additions: number;
  deletions: number;
  changes: number;
}

interface SymbolChange {
  name: string;
  type: string;
  file_path: string;
  line_number: number;
  language: string;
  change_type: string;
  parent_class?: string;
}

interface PropagationPath {
  source: string;
  target: string;
  path: string[];
  depth: number;
}

interface RiskBreakdown {
  factor: string;
  score: number;
  detail: string;
}

interface ReviewFocusArea {
  area: string;
  reason: string;
  files: string[];
  priority: 'HIGH' | 'MEDIUM' | 'LOW';
}

interface PRAnalysisResult {
  repo: string;
  pr_number: number;
  pr_url: string;
  pr_title: string;
  pr_state: string;
  pr_size: 'XS' | 'S' | 'M' | 'L' | 'XL';
  risk_score: number;
  risk_level: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  risk_breakdown: RiskBreakdown[];
  top_risks: string[];
  changed_files: ChangedFile[];
  total_additions: number;
  total_deletions: number;
  added_symbols: SymbolChange[];
  modified_symbols: SymbolChange[];
  removed_symbols: SymbolChange[];
  affected_files: string[];
  impact_radius: number;
  blast_radius: 'LOW' | 'MEDIUM' | 'HIGH' | 'EXTREME';
  max_depth: number;
  propagation_paths: PropagationPath[];
  affected_components: string[];
  changed_entry_points: string[];
  changed_core_files: string[];
  changed_high_coupling_files: string[];
  review_focus_areas: ReviewFocusArea[];
  analyzed_at: string;
}

interface PRIntelligenceProps {
  repoName?: string;
}

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

export const PRIntelligence: React.FC<PRIntelligenceProps> = ({ repoName }) => {
  const [activeRepo, setActiveRepo] = useState(() => resolveRepo(repoName));
  const { healthStatus, hasPrerequisites, isRepairing, repair } = usePrerequisites(activeRepo);

  const [useUrl, setUseUrl] = useState(true);
  const [prUrlInput, setPrUrlInput] = useState('');
  const [ownerInput, setOwnerInput] = useState('');
  const [repoInput, setRepoInput] = useState('');
  const [prNumberInput, setPrNumberInput] = useState('');

  const [isLoading, setIsLoading] = useState(false);
  const [analysisResult, setAnalysisResult] = useState<PRAnalysisResult | null>(null);
  const [errorMsg, setErrorMsg] = useState('');

  // Sync activeRepo with repoName prop changes and clear stale results
  useEffect(() => {
    const nextRepo = resolveRepo(repoName);
    setActiveRepo(nextRepo);
    setAnalysisResult(null);
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
    setAnalysisResult(null);

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
      const res = await fetch(apiUrl('/api/v1/pr/analyze'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(extractErrorMessage(errorData));
      }
      const data = await res.json();
      setAnalysisResult(data);
      if (data.repo) setActiveRepo(data.repo);
    } catch (err: any) {
      setErrorMsg(extractErrorMessage(err));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col gap-6 text-text">
      {/* Inputs + Diagnostics */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 card-padded">
          <div className="flex items-center gap-3 mb-6">
            <GitPullRequest className="w-6 h-6 text-primary" aria-hidden="true" />
            <h2 className="text-lg font-semibold tracking-tight text-text">Pull Request Intelligence</h2>
          </div>

          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <PRReferenceForm
              idPrefix="pri"
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
                  Analyzing Pull Request...
                </>
              ) : 'Analyze Pull Request'}
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
          healthStatus={healthStatus}
          description="Ensure the target repository is loaded and indexed via the Overview tab before requesting PR reports."
        />
      </div>

      {/* Loading skeleton */}
      {isLoading && (
        <SkeletonGroup label="Analyzing pull request">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <SkeletonCard />
            <SkeletonCard className="md:col-span-2" />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 mt-6">
            {Array.from({ length: 4 }, (_, i) => <SkeletonCard key={i} />)}
          </div>
        </SkeletonGroup>
      )}

      {/* Initial empty state */}
      {!analysisResult && !isLoading && !errorMsg && (
        <EmptyState
          icon={<GitPullRequest className="w-6 h-6" aria-hidden="true" />}
          title="No pull request analyzed yet"
          description="Paste a GitHub PR URL or enter repository coordinates above to compute risk, blast radius, and review focus areas."
        />
      )}

      {/* Results */}
      {analysisResult && (
        <div className="flex flex-col gap-6 animate-in fade-in slide-in-from-bottom-2 duration-300">
          {/* PR header */}
          <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-4 card-padded">
            <div>
              <div className="flex items-center gap-2.5 mb-1.5 flex-wrap">
                <span className="text-primary font-bold text-lg font-mono">#{analysisResult.pr_number}</span>
                <span className="badge-info">{analysisResult.pr_state}</span>
              </div>
              <h1 className="text-xl font-semibold text-text tracking-tight">{analysisResult.pr_title}</h1>
              <p className="text-xs text-text-subtle mt-2 font-mono">
                Analyzed at {new Date(analysisResult.analyzed_at).toLocaleString()}
              </p>
            </div>
            <a
              href={analysisResult.pr_url}
              target="_blank" rel="noopener noreferrer"
              className="btn-ghost shrink-0"
            >
              <GitPullRequest className="w-4 h-4" aria-hidden="true" />
              View on GitHub
            </a>
          </div>

          {/* Risk gauge + Top risks */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <RiskGauge
              score={analysisResult.risk_score}
              label="Risk Assessment"
              level={`${analysisResult.risk_level} risk`}
              caption={
                <div className={`badge ${riskBadgeClass(analysisResult.risk_level)}`}>
                  {analysisResult.risk_level} Risk
                </div>
              }
            />

            <div className="card-padded flex flex-col gap-4 md:col-span-2">
              <h3 className="panel-title">
                <AlertOctagon className="w-4 h-4 text-warn" aria-hidden="true" />
                Key Risk Explanations
              </h3>

              <div className="flex flex-col gap-3 my-auto">
                {analysisResult.top_risks.length > 0 ? (
                  analysisResult.top_risks.map((risk, idx) => (
                    <div key={idx} className="flex items-start gap-3 bg-canvas/60 border border-border rounded-lg p-3 text-sm font-sans">
                      <AlertTriangle className="w-4 h-4 text-warn shrink-0 mt-0.5" aria-hidden="true" />
                      <span className="text-text">{risk}</span>
                    </div>
                  ))
                ) : (
                  <EmptyState
                    compact
                    tone="success"
                    icon={<CheckCircle2 className="w-6 h-6" aria-hidden="true" />}
                    title="No critical risks detected"
                    description="This change payload looks safe to merge."
                  />
                )}
              </div>
            </div>
          </div>

          {/* Stat row */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            <StatTile icon={<Layers className="w-5 h-5" />} iconClass="text-primary bg-primary/10 border-primary/20" label="PR Size">
              <span className="text-xl font-bold text-text">{analysisResult.pr_size}</span>
              <span className={`badge ${sizeBadgeClass(analysisResult.pr_size)}`}>Score</span>
            </StatTile>

            <StatTile icon={<Activity className="w-5 h-5" />} iconClass="text-warn bg-warn/10 border-warn/30" label="Blast Radius">
              <span className="text-xl font-bold text-text">{analysisResult.blast_radius}</span>
              <span className="text-xs text-text-muted">({analysisResult.impact_radius} downstream)</span>
            </StatTile>

            <StatTile icon={<FileCode className="w-5 h-5" />} iconClass="text-success bg-success/10 border-success/30" label="Files Modified">
              <div className="text-xl font-bold text-text">
                {analysisResult.changed_files.length} <span className="text-xs text-text-muted font-normal">files</span>
              </div>
            </StatTile>

            <StatTile icon={<Code2 className="w-5 h-5" />} iconClass="text-warn bg-warn/10 border-warn/30" label="Diff Summary">
              <div className="text-xl font-bold">
                <span className="text-success">+{analysisResult.total_additions}</span>
                <span className="text-text-muted mx-1">/</span>
                <span className="text-danger">-{analysisResult.total_deletions}</span>
              </div>
            </StatTile>
          </div>

          {/* Critical architecture detections */}
          <div className="card-padded flex flex-col gap-4">
            <h3 className="text-base font-semibold text-text flex items-center gap-2 border-b border-border pb-3">
              <BookOpen className="w-4 h-4 text-primary" aria-hidden="true" />
              Critical Architecture Detections
            </h3>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <FileBucket
                title="Entry Points Changed"
                dotClass="bg-danger"
                files={analysisResult.changed_entry_points}
                emptyText="No entry point files modified."
              />
              <FileBucket
                title="Core Files Changed"
                dotClass="bg-warn"
                files={analysisResult.changed_core_files}
                emptyText="No core modules modified."
              />
              <FileBucket
                title="High-Coupling Changed"
                dotClass="bg-yellow-400"
                files={analysisResult.changed_high_coupling_files}
                emptyText="No high-coupling files modified."
              />
            </div>
          </div>

          {/* Review focus areas */}
          <div className="card-padded flex flex-col gap-4">
            <h3 className="text-base font-semibold text-text flex items-center gap-2 border-b border-border pb-3">
              <CheckCircle2 className="w-4 h-4 text-success" aria-hidden="true" />
              Prioritized Review Focus Areas
            </h3>

            <div className="flex flex-col gap-4">
              {analysisResult.review_focus_areas.length > 0 ? (
                analysisResult.review_focus_areas.map((area, idx) => (
                  <div key={idx} className="bg-canvas/60 border border-border rounded-lg p-4 flex flex-col sm:flex-row sm:items-start justify-between gap-4">
                    <div className="flex flex-col gap-1.5">
                      <div className="flex items-center gap-2.5">
                        <span className="font-semibold text-text">{area.area}</span>
                        <span className={`badge ${
                          area.priority === 'HIGH' ? 'bg-danger/10 text-danger border-danger/30' :
                          area.priority === 'MEDIUM' ? 'bg-warn/10 text-warn border-warn/30' :
                          'bg-surface-2 text-text-muted border-border'
                        }`}>
                          {area.priority}
                        </span>
                      </div>
                      <p className="text-xs text-text-muted leading-relaxed font-sans max-w-2xl">{area.reason}</p>
                    </div>
                    {area.files.length > 0 && (
                      <div className="flex flex-col gap-1 shrink-0 max-w-xs">
                        <span className="text-[10px] font-bold uppercase tracking-wider text-text-subtle mb-1 font-mono">Target Files</span>
                        {area.files.map((file, fIdx) => (
                          <span key={fIdx} className="font-mono text-[10px] text-primary bg-canvas border border-border px-1.5 py-0.5 rounded truncate max-w-[200px]" title={file}>
                            {file.split('/').pop()}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))
              ) : (
                <EmptyState
                  compact
                  icon={<CheckCircle2 className="w-6 h-6" aria-hidden="true" />}
                  title="No review focus areas triggered"
                  description="Standard review process is sufficient for this PR."
                />
              )}
            </div>
          </div>

          {/* Files and symbols */}
          <div className="card-padded flex flex-col gap-5">
            <h3 className="text-base font-semibold text-text pb-3 border-b border-border">
              Files &amp; Symbol Changes
            </h3>

            <div>
              <div className="panel-title mb-3">Changed Files ({analysisResult.changed_files.length})</div>
              <div className="table-scroll">
                <table className="table-base">
                  <thead>
                    <tr>
                      <th scope="col">File Path</th>
                      <th scope="col" className="text-center">Status</th>
                      <th scope="col" className="text-right">+</th>
                      <th scope="col" className="text-right">−</th>
                      <th scope="col" className="text-right">Δ</th>
                    </tr>
                  </thead>
                  <tbody>
                    {analysisResult.changed_files.map((file, idx) => (
                      <tr key={idx}>
                        <td className="truncate max-w-md">{file.filename}</td>
                        <td className="text-center">
                          <span className={`badge ${
                            file.status === 'added' ? 'bg-success/10 text-success border-success/30' :
                            file.status === 'removed' ? 'bg-danger/10 text-danger border-danger/30' :
                            'bg-info/10 text-info border-info/30'
                          }`}>{file.status}</span>
                        </td>
                        <td className="text-right text-success font-medium">+{file.additions}</td>
                        <td className="text-right text-danger font-medium">-{file.deletions}</td>
                        <td className="text-right text-text font-semibold">{file.changes}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <SymbolBucket title="Symbols Added"    accentClass="text-success" badgeBg="bg-success/10" symbols={analysisResult.added_symbols}    empty="No added symbols extracted." />
              <SymbolBucket title="Symbols Modified" accentClass="text-primary" badgeBg="bg-primary/10" symbols={analysisResult.modified_symbols} empty="No modified symbols found." />
              <SymbolBucket title="Symbols Removed"  accentClass="text-danger"  badgeBg="bg-danger/10"  symbols={analysisResult.removed_symbols}  empty="No removed symbols detected." />
            </div>

            <div>
              <div className="panel-title mb-3">Dependency Propagation Paths ({analysisResult.propagation_paths.length})</div>
              <div className="flex flex-col gap-2">
                {analysisResult.propagation_paths.length > 0 ? (
                  analysisResult.propagation_paths.map((path, idx) => (
                    <div key={idx} className="bg-canvas/40 border border-border rounded-lg p-3 text-xs">
                      <div className="flex justify-between items-center mb-2.5 text-text-subtle font-semibold font-mono">
                        <span>Path #{idx + 1}</span>
                        <span>{path.depth} hops</span>
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        {path.path.map((node, nIdx) => (
                          <React.Fragment key={nIdx}>
                            {nIdx > 0 && <CornerDownRight className="w-3.5 h-3.5 text-primary shrink-0 -rotate-90" aria-hidden="true" />}
                            <span className={`font-mono px-2 py-1 rounded text-[10px] ${
                              nIdx === 0 ? 'bg-surface-2 border border-border-strong text-text font-bold' :
                              nIdx === path.path.length - 1 ? 'bg-primary/10 border border-primary/30 text-primary font-bold' :
                              'bg-canvas border border-border text-text-muted'
                            }`}>
                              {node.split('/').pop()}
                            </span>
                          </React.Fragment>
                        ))}
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="text-text-muted text-xs italic py-3 text-center border border-dashed border-border rounded-lg bg-canvas/30 font-sans">
                    No multi-level import cascades found.
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// ---- helpers ----

const StatTile: React.FC<{
  icon: React.ReactNode;
  iconClass: string;
  label: string;
  children: React.ReactNode;
}> = ({ icon, iconClass, label, children }) => (
  <div className="card p-5 flex items-center gap-4">
    <div className={`p-3 border rounded-lg ${iconClass}`} aria-hidden="true">{icon}</div>
    <div>
      <div className="text-xs text-text-subtle font-semibold uppercase tracking-wider font-mono">{label}</div>
      <div className="flex items-center gap-2 mt-1">{children}</div>
    </div>
  </div>
);

const FileBucket: React.FC<{
  title: string;
  dotClass: string;
  files: string[];
  emptyText: string;
}> = ({ title, dotClass, files, emptyText }) => (
  <div className="bg-canvas/60 border border-border rounded-lg p-4 flex flex-col gap-2.5">
    <div className="text-xs font-bold uppercase tracking-wider text-text-muted flex items-center gap-1.5 font-mono">
      <span className={`w-1.5 h-1.5 rounded-full ${dotClass}`} aria-hidden="true" />
      {title} ({files.length})
    </div>
    <div className="flex flex-col gap-1.5 mt-1">
      {files.length > 0 ? files.map((file, idx) => (
        <span key={idx} className="font-mono text-xs text-text bg-surface-2 border border-border px-2.5 py-1.5 rounded break-all">
          {file}
        </span>
      )) : (
        <span className="text-xs text-text-subtle italic py-2 font-sans">{emptyText}</span>
      )}
    </div>
  </div>
);

const SymbolBucket: React.FC<{
  title: string;
  accentClass: string;
  badgeBg: string;
  symbols: { name: string; type: string; file_path: string; line_number: number }[];
  empty: string;
}> = ({ title, accentClass, badgeBg, symbols, empty }) => (
  <div className="border border-border rounded-lg p-4 bg-canvas/40 flex flex-col gap-3">
    <div className={`text-xs font-bold uppercase tracking-wider flex justify-between items-center pb-2 border-b border-border font-mono ${accentClass}`}>
      <span>{title}</span>
      <span className={`${badgeBg} px-2 py-0.5 rounded text-[10px]`}>{symbols.length}</span>
    </div>
    <div className="max-h-56 overflow-y-auto flex flex-col gap-2 mt-1">
      {symbols.length > 0 ? symbols.map((sym, idx) => (
        <div key={idx} className="bg-surface-2 border border-border px-2.5 py-2 rounded text-xs flex flex-col gap-0.5">
          <div className="flex items-center justify-between gap-2">
            <span className="font-bold text-text font-mono break-all">{sym.name}</span>
            <span className="text-[9px] text-text-subtle uppercase">{sym.type}</span>
          </div>
          <span className="text-[10px] text-text-muted font-mono truncate">
            {sym.file_path.split('/').pop()}:{sym.line_number}
          </span>
        </div>
      )) : (
        <div className="text-text-subtle text-xs italic py-2 font-sans">{empty}</div>
      )}
    </div>
  </div>
);

export default PRIntelligence;
