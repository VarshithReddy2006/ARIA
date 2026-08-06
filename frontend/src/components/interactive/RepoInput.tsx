import React, { useState, useEffect, useMemo, useRef } from 'react';
import { Timeline } from './Timeline';
import type { TimelineStep } from './Timeline';
import {
  Search, ArrowRight, BookOpen, AlertCircle, CheckCircle2, Loader2, CornerDownLeft,
} from 'lucide-react';
import { apiUrl } from '../../lib/api';
import { parseGitHubUrl, describeInvalidUrl, type ValidationState } from '../../lib/repoUrl';

interface ExampleRepo {
  name: string;
  url: string;
  tech_stack: string[];
  description: string;
}

const initialSteps: TimelineStep[] = [
  { id: 'cloning',              label: 'Cloning Repository',                    status: 'pending' },
  { id: 'detecting',            label: 'Detecting Languages',                    status: 'pending' },
  { id: 'parsing',              label: 'Parsing Source Files',                   status: 'pending' },
  { id: 'generating_embeddings', label: 'Generating Embeddings',                  status: 'pending' },
  { id: 'building_symbols',     label: 'Building Symbol Index',                  status: 'pending' },
  { id: 'building_dependency',  label: 'Building Dependency Graph',              status: 'pending' },
  { id: 'building_call',        label: 'Building Call Graph',                    status: 'pending' },
  { id: 'building_api',         label: 'Computing API Surface',                  status: 'pending' },
  { id: 'computing_intel',      label: 'Computing Repository Intelligence',      status: 'pending' },
  { id: 'generating_report',    label: 'Generating Report',                      status: 'pending' },
];

/** Debounce before an in-progress keystroke is judged valid or invalid. */
const VALIDATION_DELAY_MS = 400;

export const RepoInput: React.FC = () => {
  const [url, setUrl] = useState('');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [examples, setExamples] = useState<ExampleRepo[]>([]);
  const [timelineSteps, setTimelineSteps] = useState<TimelineStep[]>(initialSteps);
  const [validation, setValidation] = useState<ValidationState>('empty');
  const [focused, setFocused] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const parsed = useMemo(() => parseGitHubUrl(url), [url]);

  useEffect(() => {
    fetch(apiUrl('/api/v1/repos/examples'))
      .then((res) => res.json())
      .then((data) => setExamples(data))
      .catch((err) => console.error(err));
  }, []);

  /**
   * Validation runs optimistically: a recognised repository resolves instantly
   * so pasting feels immediate, while an unrecognised value waits out the
   * debounce so it isn't flagged mid-typing.
   */
  useEffect(() => {
    if (!url.trim()) {
      setValidation('empty');
      return;
    }
    if (parsed) {
      setValidation('valid');
      return;
    }

    setValidation('checking');
    const timer = window.setTimeout(() => setValidation('invalid'), VALIDATION_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [url, parsed]);

  // Focus the field on "/" the way command palettes do, without hijacking typing.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== '/' || event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      const tag = target?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || target?.isContentEditable) return;
      event.preventDefault();
      inputRef.current?.focus();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  const handleAnalyze = async (repoUrl: string) => {
    if (!repoUrl.trim() || isAnalyzing) return;

    // Normalise to the canonical clone URL so trailing paths like
    // /tree/main/src never reach the backend.
    const target = parseGitHubUrl(repoUrl);
    const submitUrl = target ? `https://github.com/${target.slug}` : repoUrl;

    setIsAnalyzing(true);
    setErrorMessage(null);
    setTimelineSteps([
      { ...initialSteps[0], status: 'active' },
      ...initialSteps.slice(1),
    ]);

    try {
      const response = await fetch(apiUrl('/api/v1/analyze'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: submitUrl, branch: 'main' }),
      });

      if (!response.body) throw new Error('Stream not available');

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let finished = false;

      while (!finished) {
        const { value, done } = await reader.read();
        finished = done;
        if (!value) continue;

        const lines = decoder.decode(value).split('\n');
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const data = JSON.parse(line.slice(6));

            if (data.status === 'error') {
              const cleanMsg = (data.message || 'An error occurred during analysis.')
                .replace(/^[✗×x]\s*/i, '').trim();
              setErrorMessage(cleanMsg);
              setIsAnalyzing(false);
              reader.cancel().catch(() => {});
              return;
            }

            const activeStatus = data.status;

            // Advance steps in the timeline
            setTimelineSteps((prev) => {
              const currentIdx = prev.findIndex((s) => s.id === activeStatus);
              if (currentIdx !== -1) {
                return prev.map((s, idx) => {
                  if (idx < currentIdx) {
                    return { ...s, status: 'completed' as const };
                  } else if (idx === currentIdx) {
                    return { ...s, status: 'active' as const };
                  } else {
                    return { ...s, status: 'pending' as const };
                  }
                });
              } else if (activeStatus === 'cloned') {
                return prev.map((s) =>
                  s.id === 'cloning' ? { ...s, status: 'completed' as const } :
                  s.id === 'detecting' ? { ...s, status: 'active' as const } : s
                );
              } else if (activeStatus === 'detected') {
                return prev.map((s) =>
                  s.id === 'detecting' ? { ...s, status: 'completed' as const } :
                  s.id === 'parsing' ? { ...s, status: 'active' as const } : s
                );
              } else if (activeStatus === 'complete') {
                return prev.map((s) => ({ ...s, status: 'completed' as const }));
              }
              return prev;
            });

            if (data.status === 'done') {
              const repoPath = data.repo || data.repository
                || (data.owner && data.repo_name ? `${data.owner}/${data.repo_name}` : null);

              if (repoPath) {
                const [owner, repo] = repoPath.split('/');
                if (owner && repo) {
                  if (typeof window !== 'undefined') {
                    localStorage.setItem('activeRepo', repoPath);
                  }
                  window.location.href = `/analysis?owner=${owner}&repo=${repo}`;
                } else {
                  setErrorMessage('Invalid repo format received');
                  setIsAnalyzing(false);
                }
              } else {
                setErrorMessage('Missing repo in analysis result');
                setIsAnalyzing(false);
              }
            }
          } catch {/* ignore malformed SSE */}
        }
      }
    } catch (err) {
      console.error('Analysis stream interrupted', err);
      setIsAnalyzing(false);
    }
  };

  const canSubmit = validation === 'valid' && !isAnalyzing;

  // Ring colour tracks validation so the field itself reports state.
  const shellState =
    validation === 'invalid'
      ? 'border-danger/50 shadow-[0_0_0_4px_rgba(239,68,68,0.10)]'
      : validation === 'valid'
        ? 'border-success/50 shadow-[0_0_0_4px_rgba(16,185,129,0.10)]'
        : focused
          ? 'border-primary/60 shadow-[0_0_0_4px_var(--primary-ring)]'
          : 'border-border';

  return (
    <div className="space-y-8 max-w-3xl mx-auto w-full">
      {/* ── Command-palette style launcher ──────────────────────────────── */}
      <div className="card p-2 sm:p-2.5 shadow-float">
        <form onSubmit={(e) => { e.preventDefault(); if (canSubmit) handleAnalyze(url); }}>
          <div
            className={`flex items-center gap-2 rounded-xl border bg-canvas/80 backdrop-blur-sm
                        px-3 py-2 transition-all duration-200 ${shellState}`}
          >
            <span className="shrink-0 text-text-subtle" aria-hidden="true">
              <Search className="h-4 w-4" />
            </span>

            <label htmlFor="repo-url" className="sr-only">GitHub repository URL</label>
            <input
              id="repo-url"
              ref={inputRef}
              type="text"
              inputMode="url"
              autoComplete="off"
              spellCheck={false}
              disabled={isAnalyzing}
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onFocus={() => setFocused(true)}
              onBlur={() => setFocused(false)}
              placeholder="Paste a GitHub URL or owner/repo…"
              aria-invalid={validation === 'invalid'}
              aria-describedby="repo-url-status"
              className="flex-grow bg-transparent border-0 outline-none text-sm sm:text-base font-mono
                         text-text placeholder:text-text-subtle disabled:opacity-60 min-w-0"
            />

            {/* Live validation indicator */}
            <span className="shrink-0 flex items-center" aria-hidden="true">
              {validation === 'checking' && (
                <Loader2 className="h-4 w-4 text-text-subtle animate-spin" />
              )}
              {validation === 'valid' && (
                <CheckCircle2 className="h-4 w-4 text-success animate-pop-in" />
              )}
              {validation === 'invalid' && (
                <AlertCircle className="h-4 w-4 text-danger animate-pop-in" />
              )}
            </span>

            {/* Keyboard affordance — hidden once the field is in use */}
            {!url && !focused && (
              <kbd
                className="hidden sm:inline-flex shrink-0 items-center gap-1 rounded border border-border
                           bg-surface-2 px-1.5 py-0.5 text-[10px] font-mono text-text-subtle"
              >
                /
              </kbd>
            )}

            <button
              type="submit"
              disabled={!canSubmit}
              className="btn-primary shrink-0 px-4 py-2 text-sm disabled:opacity-40"
            >
              <span className="hidden sm:inline">Analyze</span>
              {isAnalyzing
                ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                : <ArrowRight className="h-4 w-4" aria-hidden="true" />}
            </button>
          </div>
        </form>

        {/* Status line — resolved target, or why the input was rejected */}
        <div
          id="repo-url-status"
          role="status"
          aria-live="polite"
          className="px-3 pt-2 pb-1 min-h-[1.75rem]"
        >
          {validation === 'valid' && parsed && (
            <div className="flex items-center gap-2 text-[11px] font-mono animate-pop-in">
              <span className="text-text-subtle">Target</span>
              <span className="px-1.5 py-0.5 rounded border border-success/30 bg-success/5 text-success">
                {parsed.owner}
              </span>
              <span className="text-text-subtle">/</span>
              <span className="px-1.5 py-0.5 rounded border border-success/30 bg-success/5 text-success">
                {parsed.repo}
              </span>
              <span className="hidden sm:inline-flex items-center gap-1 text-text-subtle ml-auto">
                <CornerDownLeft className="h-3 w-3" aria-hidden="true" /> to analyze
              </span>
            </div>
          )}
          {validation === 'invalid' && (
            <p className="text-[11px] font-sans text-danger/90 animate-pop-in">
              {describeInvalidUrl(url)}
            </p>
          )}
          {validation === 'empty' && !isAnalyzing && (
            <p className="text-[11px] font-sans text-text-subtle">
              Public repositories · shallow clone · nothing is written back to GitHub
            </p>
          )}
        </div>

        {isAnalyzing && (
          <div
            className="pt-4 mt-2 border-t border-border flex justify-center"
            role="status"
            aria-live="polite"
          >
            <Timeline steps={timelineSteps} />
          </div>
        )}

        {errorMessage && (
          <div
            role="alert"
            className="mt-3 mx-1 flex items-start gap-3 bg-danger/10 border border-danger/30 text-danger rounded-lg p-4 font-sans text-xs"
          >
            <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" aria-hidden="true" />
            <div className="space-y-1">
              <span className="font-bold uppercase tracking-wider text-[10px] block">Analysis Failed</span>
              <p className="leading-relaxed">{errorMessage}</p>
              {(errorMessage.includes('quota') || errorMessage.includes('429') || errorMessage.includes('RESOURCE_EXHAUSTED') || errorMessage.includes('rate limit')) && (
                <p className="text-danger/70 text-[10px] mt-1">
                  AI provider rate limit reached. Please wait a moment before retrying.
                </p>
              )}
            </div>
          </div>
        )}
      </div>

      {/* ── Examples ────────────────────────────────────────────────────── */}
      {!isAnalyzing && examples.length > 0 && (
        <div className="space-y-4 fade-up">
          <h2 className="text-xs uppercase tracking-widest font-semibold text-text-subtle font-mono">
            Try a sample repository
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {examples.map((repo) => (
              <button
                key={repo.name}
                type="button"
                onClick={() => { setUrl(repo.url); handleAnalyze(repo.url); }}
                className="card p-4 text-left transition-all hover:border-primary/40 hover:-translate-y-0.5
                           hover:shadow-raised focus-visible:outline-none focus-visible:shadow-ring space-y-3 group"
              >
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs text-text font-semibold group-hover:text-primary transition-colors truncate">
                    {repo.name}
                  </span>
                  <BookOpen className="h-3.5 w-3.5 text-text-muted shrink-0" aria-hidden="true" />
                </div>
                <p className="text-xs text-text-muted line-clamp-2 leading-relaxed font-sans">
                  {repo.description}
                </p>
                <div className="flex flex-wrap gap-1">
                  {repo.tech_stack.map((stack) => (
                    <span key={stack} className="text-[9px] font-mono bg-canvas border border-border px-1.5 py-0.5 rounded text-text-muted">
                      {stack}
                    </span>
                  ))}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default RepoInput;
