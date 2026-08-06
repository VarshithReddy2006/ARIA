import React, { useState, useEffect } from 'react';
import { apiUrl } from '../../lib/api';
import { Target, FileSpreadsheet, ListTodo, Wrench, AlertTriangle, Loader2, ShieldCheck, ShieldAlert, Cpu, BarChart } from 'lucide-react';

interface Step {
  step_number: number;
  description: string;
  files_to_modify: string[];
}

interface Plan {
  issue_summary: string;
  issue_type: string;
  relevant_files: string[];
  affected_components: string[];
  implementation_plan: Step[];
  complexity: string;
  confidence: number;
  verified: boolean;
  sources: string[];
}

interface IssueMapperProps {
  repoName?: string;
}

export const IssueMapper: React.FC<IssueMapperProps> = ({ repoName }) => {
  const [selectedRepo, setSelectedRepo] = useState(() => {
    if (repoName) return repoName;
    if (typeof window !== 'undefined') {
      const urlParams = new URLSearchParams(window.location.search);
      const owner = urlParams.get('owner');
      const repo = urlParams.get('repo');
      if (owner && repo) {
        return `${owner}/${repo}`;
      }
      const stored = localStorage.getItem('activeRepo');
      if (stored) return stored;
    }
    return '';
  });
  const [recentRepos, setRecentRepos] = useState<{ name: string }[]>([]);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [completedSteps, setCompletedSteps] = useState<Record<number, boolean>>({});

  // Sync selectedRepo with repoName prop changes and clear stale plan data on repository change
  useEffect(() => {
    if (repoName) {
      setSelectedRepo(repoName);
      setPlan(null);
      setCompletedSteps({});
    }
  }, [repoName]);

  // Sync global active-repo events (for standalone /issues page cross-island updates)
  useEffect(() => {
    const handleRepoChanged = (e: Event) => {
      const customEvent = e as CustomEvent<string>;
      if (customEvent.detail && customEvent.detail !== selectedRepo) {
        setSelectedRepo(customEvent.detail);
        setPlan(null);
        setCompletedSteps({});
      }
    };
    const handleRepoCleared = () => {
      setSelectedRepo('');
      setPlan(null);
      setCompletedSteps({});
    };

    window.addEventListener('active-repo-changed', handleRepoChanged);
    window.addEventListener('active-repo-cleared', handleRepoCleared);
    return () => {
      window.removeEventListener('active-repo-changed', handleRepoChanged);
      window.removeEventListener('active-repo-cleared', handleRepoCleared);
    };
  }, [selectedRepo]);

  // Fetch recent repositories if no repoName is locked
  useEffect(() => {
    if (!repoName) {
      fetch(apiUrl('/api/v1/repos/recent'))
        .then(res => res.json())
        .then(data => {
          if (Array.isArray(data)) {
            setRecentRepos(data);
            if (data.length > 0 && !selectedRepo) {
              setSelectedRepo(data[0].name);
            }
          }
        })
        .catch(err => console.error("Failed to fetch recent repos", err));
    }
  }, [repoName]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !selectedRepo.trim()) return;

    setIsLoading(true);
    try {
      const response = await fetch(apiUrl('/api/v1/issues/map'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          repo: selectedRepo,
          issue: `${title}\n${description}`.trim()
        })
      });

      if (response.ok) {
        const data = await response.json();
        setPlan(data);
        setCompletedSteps({});
      }
    } catch (err) {
      console.error("Failed to map issue", err);
    } finally {
      setIsLoading(false);
    }
  };

  const toggleStep = (stepNum: number) => {
    setCompletedSteps(prev => ({
      ...prev,
      [stepNum]: !prev[stepNum]
    }));
  };

  const getTypeBadgeColor = (type: string) => {
    switch (type.toLowerCase()) {
      case 'bug':
        return 'bg-red-500/10 border-red-500/20 text-red-400';
      case 'refactor':
        return 'bg-amber-500/10 border-amber-500/20 text-amber-400';
      default:
        return 'bg-primary/10 border-primary/20 text-primary';
    }
  };

  const getComplexityColor = (comp: string) => {
    switch (comp.toLowerCase()) {
      case 'high':
        return 'bg-red-500/10 border-red-500/20 text-red-400';
      case 'medium':
        return 'bg-amber-500/10 border-amber-500/20 text-amber-400';
      default:
        return 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400';
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 w-full items-start">
      {/* Input Panel */}
      <div className="lg:col-span-5 border border-border bg-card/10 rounded-lg p-5">
        <div className="flex items-center gap-2 mb-4 border-b border-border pb-3">
          <Target className="h-5 w-5 text-primary" />
          <h2 className="text-sm font-semibold tracking-wide uppercase font-mono">Issue Specification</h2>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {!repoName && (
            <div>
              <label className="block text-xs font-semibold text-text-muted uppercase tracking-wider mb-1.5 font-mono">
                Select Indexed Repository
              </label>
              {recentRepos.length > 0 ? (
                <select
                  value={selectedRepo}
                  onChange={(e) => setSelectedRepo(e.target.value)}
                  className="w-full bg-canvas border border-border rounded px-3 py-2 text-sm focus:outline-none focus:border-primary text-text font-mono"
                >
                  {recentRepos.map(r => (
                    <option key={r.name} value={r.name}>{r.name}</option>
                  ))}
                </select>
              ) : (
                <input
                  type="text"
                  required
                  value={selectedRepo}
                  onChange={(e) => setSelectedRepo(e.target.value)}
                  placeholder="owner/repo"
                  className="w-full bg-canvas border border-border rounded px-3 py-2 text-sm focus:outline-none focus:border-primary text-text font-mono"
                />
              )}
            </div>
          )}

          <div>
            <label className="block text-xs font-semibold text-text-muted uppercase tracking-wider mb-1.5 font-mono">
              Issue Title / URL
            </label>
            <input
              type="text"
              required
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Fix memory leaks in SQLite store"
              className="w-full bg-canvas border border-border rounded px-3 py-2 text-sm focus:outline-none focus:border-primary text-text placeholder:text-text-muted/40 font-sans"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-text-muted uppercase tracking-wider mb-1.5 font-mono">
              Issue Description / Error Logs
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Paste terminal logs, error stacktrace, or detailed requirements..."
              rows={6}
              className="w-full bg-canvas border border-border rounded px-3 py-2 text-sm focus:outline-none focus:border-primary text-text placeholder:text-text-muted/40 font-sans resize-none"
            />
          </div>

          <button
            type="submit"
            disabled={isLoading || !title.trim() || !selectedRepo.trim()}
            className="w-full bg-primary hover:bg-primary-hover text-text font-semibold py-2.5 rounded text-sm transition-colors flex items-center justify-center gap-2 disabled:opacity-50"
          >
            {isLoading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>Mapping Issue Relationships...</span>
              </>
            ) : (
              <span>Map Issue & Generate Plan</span>
            )}
          </button>
        </form>
      </div>

      {/* Output Panel */}
      <div className="lg:col-span-7 border border-border bg-card/10 rounded-lg p-5 min-h-[450px] flex flex-col">
        {plan ? (
          <div className="space-y-6">
            {/* Header / Summary */}
            <div className="border-b border-border pb-4 space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <ListTodo className="h-5 w-5 text-primary" />
                  <h2 className="text-sm font-semibold tracking-wide uppercase font-mono">Analysis Results</h2>
                </div>
                <div className="flex items-center gap-2">
                  {plan.verified ? (
                    <span className="flex items-center gap-1 text-[10px] font-mono bg-emerald-500/10 border border-emerald-500/20 text-emerald-500 px-2 py-0.5 rounded">
                      <ShieldCheck className="h-3 w-3" /> VERIFIED
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 text-[10px] font-mono bg-amber-500/10 border border-amber-500/20 text-amber-500 px-2 py-0.5 rounded">
                      <ShieldAlert className="h-3 w-3" /> UNVERIFIED
                    </span>
                  )}
                  <span className={`text-[10px] font-mono border px-2 py-0.5 rounded ${getTypeBadgeColor(plan.issue_type)}`}>
                    {plan.issue_type.toUpperCase()}
                  </span>
                </div>
              </div>
              <p className="text-sm text-text font-semibold leading-relaxed">
                {plan.issue_summary}
              </p>
            </div>

            {/* Metrics: Complexity & Confidence */}
            <div className="grid grid-cols-2 gap-4">
              <div className="border border-border bg-canvas/30 rounded p-3 flex items-center justify-between">
                <div className="space-y-0.5">
                  <span className="text-[10px] font-mono text-text-muted uppercase tracking-wider block">Complexity</span>
                  <span className="text-xs font-semibold capitalize">{plan.complexity}</span>
                </div>
                <span className={`text-[10px] font-mono border px-2.5 py-0.5 rounded ${getComplexityColor(plan.complexity)}`}>
                  {plan.complexity.toUpperCase()}
                </span>
              </div>

              <div className="border border-border bg-canvas/30 rounded p-3 flex items-center justify-between">
                <div className="space-y-0.5">
                  <span className="text-[10px] font-mono text-text-muted uppercase tracking-wider block">Confidence</span>
                  <span className="text-xs font-semibold">{plan.confidence}%</span>
                </div>
                <div className="w-12 bg-border h-2 rounded-full overflow-hidden">
                  <div 
                    className={`h-full ${plan.confidence >= 90 ? 'bg-emerald-500' : plan.confidence >= 70 ? 'bg-primary' : 'bg-red-500'}`} 
                    style={{ width: `${plan.confidence}%` }}
                  />
                </div>
              </div>
            </div>

            {/* Affected Components */}
            {plan.affected_components && plan.affected_components.length > 0 && (
              <div>
                <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2 font-mono flex items-center gap-1.5">
                  <Cpu className="h-4 w-4 text-primary" /> Affected Components
                </h3>
                <div className="flex flex-wrap gap-2">
                  {plan.affected_components.map(comp => (
                    <span key={comp} className="text-[10px] font-mono bg-canvas border border-border px-2 py-1 rounded-md text-text">
                      {comp}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Target Files (Impact Analysis) */}
            <div>
              <h3 className="text-xs font-semibold text-text uppercase tracking-wider mb-2 font-mono flex items-center gap-1.5">
                <FileSpreadsheet className="h-4 w-4 text-primary" /> Target Files (Impact Analysis)
              </h3>
              <div className="bg-card/40 border border-border rounded p-3 space-y-2">
                {plan.relevant_files.map((file) => (
                  <div key={file} className="flex items-center gap-2 font-mono text-xs text-text-muted bg-canvas/40 px-2 py-1.5 rounded border border-border/50">
                    <span className="h-1.5 w-1.5 rounded-full bg-primary"></span>
                    <span>{file}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Implementation Plan Steps */}
            <div>
              <h3 className="text-xs font-semibold text-text uppercase tracking-wider mb-3 font-mono flex items-center gap-1.5">
                <Wrench className="h-4 w-4 text-primary" /> Implementation Plan Steps
              </h3>
              <div className="space-y-3">
                {plan.implementation_plan.map((step) => {
                  const isDone = !!completedSteps[step.step_number];

                  return (
                    <label
                      key={step.step_number}
                      className={`block border rounded p-3.5 cursor-pointer transition-all duration-300 focus-within:shadow-ring ${
                        isDone
                          ? 'bg-success/5 border-success/30 opacity-70'
                          : 'bg-card/30 border-border hover:border-primary/50'
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        <input
                          type="checkbox"
                          checked={isDone}
                          onChange={() => toggleStep(step.step_number)}
                          className="mt-1 h-3.5 w-3.5 rounded border-border text-primary focus:ring-primary focus:ring-offset-0 accent-primary"
                        />
                        <div className="space-y-2">
                          <p className={`text-xs font-medium ${isDone ? 'line-through text-text-muted' : 'text-text'}`}>
                            <span className="font-mono text-primary font-bold mr-1">Step {step.step_number}:</span>
                            {step.description}
                          </p>

                          <div className="flex flex-wrap gap-1.5">
                            {step.files_to_modify.map((f) => (
                              <span key={f} className="text-[10px] font-mono bg-canvas border border-border px-1.5 py-0.5 rounded text-text-muted">
                                {f}
                              </span>
                            ))}
                          </div>
                        </div>
                      </div>
                    </label>
                  );
                })}
              </div>
            </div>

            {/* Sources cited */}
            {plan.sources && plan.sources.length > 0 && (
              <div className="border-t border-border pt-4">
                <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2 font-mono flex items-center gap-1.5">
                  <BarChart className="h-4 w-4 text-primary" /> Citations & Evidence Base
                </h3>
                <div className="flex flex-wrap gap-1.5">
                  {plan.sources.map((src) => (
                    <span key={src} className="text-[10px] font-mono bg-canvas border border-border/50 px-2 py-0.5 rounded text-text-muted">
                      {src}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="flex-grow flex flex-col items-center justify-center text-center p-8 opacity-65">
            <AlertTriangle className="h-8 w-8 text-text-muted mb-2" />
            <p className="text-sm font-semibold text-text mb-1">No plan generated</p>
            <p className="text-xs text-text-muted max-w-sm">
              Enter an issue description and trigger mapping to calculate relevant codebase components and tasks.
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

export default IssueMapper;
