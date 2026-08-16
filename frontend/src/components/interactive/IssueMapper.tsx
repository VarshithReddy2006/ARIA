/**
 * IssueMapper — issue intelligence.
 *
 * One continuous workspace rather than two cards side by side:
 *
 *   HEADER → ISSUE COMMAND (left) │ GENERATED PLAN (right)
 *
 * and the plan itself reads as the transformation it performs:
 *
 *   ISSUE → MODULES → SYMBOLS → DEPENDENCIES → PLAN
 *
 * Every value shown comes from `POST /api/v1/issues/map` unchanged — complexity,
 * confidence, affected components, target files, steps and citations are all
 * backend fields. Nothing here derives or invents a metric.
 *
 * Typography rule: uppercase monospace is reserved for labels, paths, metadata
 * and step numbers. Issue titles and generated instructions keep readable casing.
 */

import React, { useState, useEffect, useRef } from 'react';
import { apiUrl, extractErrorMessage } from '../../lib/api';
import { AlertTriangle, ArrowRight, Loader2, ShieldCheck, ShieldAlert } from 'lucide-react';
import { FilePath } from '../ui/FilePath';

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

/**
 * Issue type tone. Red is reserved for an actual defect; a refactor is a
 * caution, and anything else is ordinary intelligence rather than a warning.
 */
function typeToneClass(type: string): string {
  const t = (type || '').toLowerCase();
  if (t === 'bug') return 'text-danger';
  if (t === 'refactor') return 'text-warn';
  return 'text-primary';
}

/**
 * Complexity is an estimate of effort, not a fault, so it never reaches red.
 * Medium stays neutral — colouring every reading would make none of them mean
 * anything.
 */
function complexityToneClass(complexity: string): string {
  const c = (complexity || '').toLowerCase();
  if (c === 'high') return 'text-warn';
  if (c === 'low') return 'text-success';
  return 'text-text';
}

/** Low confidence is the uncertainty signal; high confidence reads as healthy. */
function confidenceToneClass(confidence: number): string {
  if (confidence < 70) return 'text-warn';
  if (confidence >= 90) return 'text-success';
  return 'text-text';
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
  /**
   * A failed mapping used to log to the console and otherwise look like nothing
   * had happened. The request itself is unchanged; the outcome is now reported.
   */
  const [errorMsg, setErrorMsg] = useState('');
  const titleRef = useRef<HTMLInputElement>(null);

  // Sync selectedRepo with repoName prop changes and clear stale plan data on repository change
  useEffect(() => {
    if (repoName) {
      setSelectedRepo(repoName);
      setPlan(null);
      setCompletedSteps({});
      setErrorMsg('');
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
        setErrorMsg('');
      }
    };
    const handleRepoCleared = () => {
      setSelectedRepo('');
      setPlan(null);
      setCompletedSteps({});
      setErrorMsg('');
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

  const runMapping = async () => {
    if (!title.trim() || !selectedRepo.trim()) return;

    setIsLoading(true);
    setErrorMsg('');
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
      } else {
        const errorData = await response.json().catch(() => ({}));
        setErrorMsg(extractErrorMessage(errorData));
      }
    } catch (err) {
      console.error("Failed to map issue", err);
      setErrorMsg(extractErrorMessage(err));
    } finally {
      setIsLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await runMapping();
  };

  const toggleStep = (stepNum: number) => {
    setCompletedSteps(prev => ({
      ...prev,
      [stepNum]: !prev[stepNum]
    }));
  };

  /** Opens a target file in the graph. Contract and fallback are unchanged. */
  const openInGraph = (file: string) => {
    if (typeof window === 'undefined') return;
    const [owner, repo] = (selectedRepo || '').split('/');
    window.dispatchEvent(
      new CustomEvent('aria-open-graph', {
        detail: {
          owner: owner || undefined,
          repo: repo || undefined,
          file,
          path: file,
          source: 'issues',
        },
      })
    );
    if (window.location.pathname === '/issues' && selectedRepo) {
      if (owner && repo) {
        window.location.href = `/analysis?owner=${owner}&repo=${repo}&tab=graph&file=${encodeURIComponent(file)}`;
      }
    }
  };

  /** Hands the generated plan to chat. Contract and fallback are unchanged. */
  const explainPlanInChat = (currentPlan: Plan) => {
    if (typeof window === 'undefined') return;
    window.dispatchEvent(
      new CustomEvent('aria-open-chat', {
        detail: {
          prompt: `Review this implementation plan for "${title}":\n\n${currentPlan.implementation_plan
            .map((s) => `Step ${s.step_number}: ${s.description} (Files: ${s.files_to_modify.join(', ')})`)
            .join('\n')}`,
        },
      })
    );
    if (window.location.pathname === '/issues' && selectedRepo) {
      const [owner, repo] = selectedRepo.split('/');
      if (owner && repo) {
        window.location.href = `/chat`;
      }
    }
  };

  const canSubmit = !isLoading && Boolean(title.trim()) && Boolean(selectedRepo.trim());

  // ── Left column · issue command console ───────────────────────────────────
  const commandConsole = (
    <div className="issue-command-sticky min-w-0">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 pb-3 hair-b">
        <h3 className="mono-label mono-label-accent">ISSUE COMMAND</h3>
        {selectedRepo && (
          // Truncates independently of the value the request actually sends.
          <span
            className="mono-detail truncate max-w-[16rem] min-w-0"
            style={{ fontSize: 10 }}
            title={selectedRepo}
          >
            {selectedRepo}
          </span>
        )}
      </div>

      <form onSubmit={handleSubmit} className="mt-5 space-y-5 min-w-0">
        {!repoName && (
          <div className="min-w-0">
            <label
              htmlFor="issue-repo"
              className="mono-label block mb-2"
            >
              TARGET REPOSITORY
            </label>
            {recentRepos.length > 0 ? (
              <select
                id="issue-repo"
                value={selectedRepo}
                onChange={(e) => setSelectedRepo(e.target.value)}
                className="console-field font-mono text-[11.5px]"
              >
                {recentRepos.map((r) => (
                  <option key={r.name} value={r.name}>
                    {r.name}
                  </option>
                ))}
              </select>
            ) : (
              <input
                id="issue-repo"
                type="text"
                required
                value={selectedRepo}
                onChange={(e) => setSelectedRepo(e.target.value)}
                placeholder="owner/repo"
                className="console-field font-mono text-[11.5px]"
              />
            )}
          </div>
        )}

        <div className="min-w-0">
          <label htmlFor="issue-title" className="mono-label block mb-2">
            ISSUE TITLE / URL
          </label>
          <input
            id="issue-title"
            ref={titleRef}
            type="text"
            required
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. Fix memory leaks in SQLite store"
            className="console-field text-[12.5px]"
          />
        </div>

        <div className="min-w-0">
          <label htmlFor="issue-logs" className="mono-label block mb-2">
            DESCRIPTION / ERROR LOGS
          </label>
          <textarea
            id="issue-logs"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Paste terminal logs, error stacktrace, or detailed requirements..."
            rows={7}
            className="console-field"
          />
        </div>

        <div className="min-w-0">
          <button
            type="submit"
            disabled={!canSubmit}
            className="action-chip w-full justify-center disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {isLoading ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                Mapping issue structure
              </>
            ) : (
              <>
                Map Issue &amp; Generate Plan
                <ArrowRight className="h-3 w-3" aria-hidden="true" />
              </>
            )}
          </button>
          {/*
            Occupies a fixed 1px band whether or not it is active, so starting a
            request never nudges the layout.
          */}
          <div className="mt-2.5" aria-hidden="true">
            {isLoading ? <div className="activity-line" /> : <div className="h-px" />}
          </div>
        </div>
      </form>
    </div>
  );

  // ── Right column · states ─────────────────────────────────────────────────
  const waitingState = (
    <div className="min-w-0">
      <span className="mono-label block mb-3">WAITING FOR ISSUE INPUT</span>
      <p className="mono-detail mb-4" style={{ fontSize: 10, letterSpacing: '0.16em' }}>
        ISSUE → MODULES → SYMBOLS → DEPENDENCIES → PLAN
      </p>
      <p className="text-[13px] text-text-muted leading-relaxed max-w-lg">
        Describe the issue or paste a stack trace in the command console. ARIA traces it to the
        modules and symbols it touches, then compiles an ordered implementation plan.
      </p>
    </div>
  );

  const errorState = (
    <div className="min-w-0" role="alert">
      <div className="flex items-start gap-3">
        <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5 text-danger" aria-hidden="true" />
        <div className="min-w-0">
          <span className="mono-label block mb-2" style={{ color: 'var(--danger)' }}>
            ISSUE MAPPING FAILED
          </span>
          <p className="text-[13px] text-text-muted leading-relaxed max-w-lg">
            {errorMsg || 'The issue could not be mapped to the repository.'}
          </p>
          <button
            type="button"
            onClick={() => runMapping()}
            disabled={!canSubmit}
            className="api-action link-arrow mt-4 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            RETRY
            <ArrowRight className="h-3 w-3 arrow" aria-hidden="true" />
          </button>
        </div>
      </div>
    </div>
  );

  const planSurface = (p: Plan) => (
    <div className="min-w-0">
      {/* ── Plan header: the strongest diagnostic region ─────────────────── */}
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2 pb-3 hair-b">
        <p className="mono-detail min-w-0" style={{ fontSize: 10, letterSpacing: '0.16em' }}>
          <span className="text-primary">ISSUE</span> → MODULES → SYMBOLS → DEPENDENCIES →{' '}
          <span style={{ color: 'var(--success)' }}>PLAN</span>
        </p>
        <span className="flex items-center gap-x-5 gap-y-1 flex-wrap shrink-0">
          <span
            className={`flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.16em] ${
              p.verified ? 'text-success' : 'text-warn'
            }`}
          >
            {p.verified ? (
              <ShieldCheck className="h-3 w-3" aria-hidden="true" />
            ) : (
              <ShieldAlert className="h-3 w-3" aria-hidden="true" />
            )}
            {p.verified ? 'VERIFIED' : 'UNVERIFIED'}
          </span>
          <span
            className={`font-mono text-[10px] uppercase tracking-[0.16em] ${typeToneClass(p.issue_type)}`}
          >
            {p.issue_type.toUpperCase()}
          </span>
        </span>
      </div>

      {/* ── Issue summary ─────────────────────────────────────────────────── */}
      <div className="mt-5 min-w-0">
        <span className="mono-label block mb-2">ISSUE SUMMARY</span>
        <p className="text-[15px] sm:text-base text-text font-medium leading-snug max-w-2xl break-words">
          {p.issue_summary}
        </p>
      </div>

      {/* ── Diagnostic readout ────────────────────────────────────────────── */}
      <dl className="grid grid-cols-2 border-y border-white/[0.055] mt-5 min-w-0">
        <div className="min-w-0 px-4 sm:px-5 py-3.5">
          <dt className="mono-label mb-1.5">COMPLEXITY</dt>
          <dd
            className={`font-mono text-[14px] uppercase tracking-[0.12em] ${complexityToneClass(
              p.complexity,
            )}`}
          >
            {p.complexity}
          </dd>
        </div>
        <div className="min-w-0 px-4 sm:px-5 py-3.5 border-l border-white/[0.055]">
          <dt className="mono-label mb-1.5">CONFIDENCE</dt>
          <dd
            className={`font-mono text-[14px] tabular-nums ${confidenceToneClass(p.confidence)}`}
          >
            {p.confidence}
            <span className="text-text-subtle">%</span>
          </dd>
        </div>
      </dl>

      {/* ── Affected components: quiet metadata, not cards ────────────────── */}
      {p.affected_components && p.affected_components.length > 0 && (
        <div className="mt-5 min-w-0">
          <span className="mono-label block mb-2">AFFECTED COMPONENTS</span>
          <p className="font-mono text-[12px] text-text-muted leading-relaxed break-words">
            {p.affected_components.join('  ·  ')}
          </p>
        </div>
      )}

      {/* ── Target files ──────────────────────────────────────────────────── */}
      <section aria-labelledby="im-targets" className="mt-8 min-w-0">
        <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1 pb-3 hair-b">
          <h3 id="im-targets" className="mono-label">
            TARGET FILES
          </h3>
          <span className="mono-detail shrink-0" style={{ fontSize: 10 }}>
            IMPACT ANALYSIS
          </span>
        </div>

        <ul className="min-w-0">
          {p.relevant_files.map((file) => (
            <li
              key={file}
              className="api-row spec-row--slide flex flex-col sm:flex-row sm:items-baseline
                         sm:justify-between gap-x-5 gap-y-1.5 py-3
                         border-b border-white/[0.055] min-w-0"
            >
              <span className="min-w-0 sm:flex-1">
                <FilePath path={file} tone="primary" size="sm" />
              </span>
              <button
                type="button"
                onClick={() => openInGraph(file)}
                className="api-action link-arrow shrink-0 self-start sm:self-auto"
                aria-label={`View ${file} in the file graph`}
              >
                VIEW IN GRAPH
                <ArrowRight className="h-2.5 w-2.5 arrow ml-1" aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      </section>

      {/* ── Implementation plan ───────────────────────────────────────────── */}
      <section aria-labelledby="im-plan" className="mt-8 min-w-0">
        <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2 pb-3 hair-b">
          <h3 id="im-plan" className="mono-label mono-label-accent">
            IMPLEMENTATION PLAN
          </h3>
          <button
            type="button"
            onClick={() => explainPlanInChat(p)}
            className="api-action link-arrow shrink-0"
          >
            ASK ARIA TO EXPLAIN THIS PLAN
            <ArrowRight className="h-2.5 w-2.5 arrow ml-1" aria-hidden="true" />
          </button>
        </div>

        <ol className="min-w-0">
          {p.implementation_plan.map((step) => {
            const isDone = Boolean(completedSteps[step.step_number]);

            return (
              <li
                key={step.step_number}
                className="spec-row spec-row--slide group border-t border-white/[0.055]
                           hover:border-white/[0.09] last:border-b last:border-white/[0.055]
                           min-w-0 transition-colors duration-200"
              >
                <label className="flex items-start gap-4 sm:gap-5 py-4 cursor-pointer min-w-0">
                  <input
                    type="checkbox"
                    checked={isDone}
                    onChange={() => toggleStep(step.step_number)}
                    className="mt-[7px] h-3 w-3 shrink-0 accent-primary bg-transparent
                               border border-white/20 focus-visible:outline-none"
                  />
                  <span
                    className={`mono-label shrink-0 mt-1 tabular-nums transition-colors duration-200 ${
                      isDone ? '' : 'group-hover:text-primary'
                    }`}
                    style={{ letterSpacing: '0.16em' }}
                  >
                    {String(step.step_number).padStart(2, '0')}
                  </span>

                  <span className="min-w-0 flex-1">
                    {/* A generated instruction is a sentence, so it keeps its casing. */}
                    <span
                      className={`block text-[13px] font-medium leading-snug transition-colors duration-200 ${
                        isDone
                          ? 'line-through text-text-subtle'
                          : 'text-text group-hover:text-white'
                      }`}
                    >
                      {step.description}
                    </span>

                    {step.files_to_modify.length > 0 && (
                      <span className="block mt-2 space-y-0.5 min-w-0">
                        {step.files_to_modify.map((f) => (
                          <span key={f} className="block min-w-0">
                            <FilePath path={f} tone="secondary" size="sm" />
                          </span>
                        ))}
                      </span>
                    )}
                  </span>
                </label>
              </li>
            );
          })}
        </ol>
      </section>

      {/* ── Citations ─────────────────────────────────────────────────────── */}
      {p.sources && p.sources.length > 0 && (
        <div className="mt-7 min-w-0">
          <span className="mono-label block mb-2">CITATIONS</span>
          <ul className="min-w-0 space-y-0.5">
            {p.sources.map((src) => (
              <li key={src} className="min-w-0">
                <FilePath path={src} tone="metadata" size="sm" />
              </li>
            ))}
          </ul>
        </div>
      )}

      {/*
        A neutral run summary, not a completion badge: the dashboard shell owns
        the single authoritative ANALYSIS COMPLETE indicator, so a green "READY"
        here would be a second one competing with it.
      */}
      <footer className="mt-10 pt-5 border-t border-white/[0.055]" aria-label="Plan summary">
        <p className="mono-detail tabular-nums" style={{ fontSize: 10, letterSpacing: '0.16em' }}>
          IMPLEMENTATION PLAN ·{' '}
          {p.implementation_plan.length} {p.implementation_plan.length === 1 ? 'STEP' : 'STEPS'} ·{' '}
          {p.relevant_files.length} TARGET {p.relevant_files.length === 1 ? 'FILE' : 'FILES'} ·{' '}
          {(p.sources?.length ?? 0)} {(p.sources?.length ?? 0) === 1 ? 'CITATION' : 'CITATIONS'}
        </p>
      </footer>
    </div>
  );

  return (
    <div className="flex flex-col text-text min-w-0">
      {/* ── Header ────────────────────────────────────────────────────────── */}
      <header className="min-w-0">
        <span className="mono-label mono-label-accent block mb-2.5">
          ISSUE INTELLIGENCE / ISSUE MAPPER
        </span>
        <h2 className="display-3 text-text">Map the issue to the codebase.</h2>
        <p className="text-[13px] text-text-muted leading-relaxed mt-3 max-w-xl">
          Trace the affected modules, symbols, dependencies, and implementation path.
        </p>
        {selectedRepo && (
          <p className="mono-label mt-5" style={{ letterSpacing: '0.2em' }}>
            REPOSITORY · {selectedRepo}
          </p>
        )}
      </header>

      {/*
        One workspace, not two cards: a single vertical hairline divides the
        console from the intelligence surface at desktop width, and the columns
        stack below `lg`. 36/64 split, with the gap shrinking before the content.
      */}
      <div
        className="mt-9 grid grid-cols-1 gap-y-10 items-start min-w-0
                   lg:grid-cols-[minmax(0,36fr)_minmax(0,64fr)] lg:gap-x-8 xl:gap-x-10"
      >
        {commandConsole}

        <div className="min-w-0 lg:pl-8 xl:pl-10 lg:border-l lg:border-white/[0.055]">
          {plan ? planSurface(plan) : errorMsg ? errorState : waitingState}
        </div>
      </div>
    </div>
  );
};

export default IssueMapper;
