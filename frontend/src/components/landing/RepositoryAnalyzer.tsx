import React, { useEffect, useRef, useState } from 'react';
import { AlertCircle, ArrowRight, CheckCircle2, Loader2 } from 'lucide-react';
import { AnalysisProgress } from './AnalysisProgress';
import { SampleCodebases } from './SampleCodebases';
import { useRepoAnalysis } from '../../lib/useRepoAnalysis';
import { describeInvalidUrl } from '../../lib/repoUrl';
import { FALLBACK_SAMPLES } from './data';

/* ─────────────────────────────────────────────────────────────────────────────
 * RepositoryAnalyzer — chapters 10 and 11.
 *
 * The single moment of conversion, placed only after the story has been told.
 * One large command-line style field: a prompt glyph, a monospace target, a
 * keyboard affordance, and one action. All streaming, validation and navigation
 * behaviour lives in useRepoAnalysis so this file stays presentational.
 * ────────────────────────────────────────────────────────────────────────── */

export const RepositoryAnalyzer: React.FC = () => {
  const {
    url,
    setUrl,
    parsed,
    validation,
    isAnalyzing,
    errorMessage,
    analysisSteps,
    examples,
    canSubmit,
    jobProgress,
    jobStartedAt,
    jobElapsedSeconds,
    analyze,
  } = useRepoAnalysis();

  const [focused, setFocused] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // "/" focuses the field the way a command palette would, without hijacking typing.
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

  const samples = examples.length > 0 ? examples : FALLBACK_SAMPLES;

  // The field itself reports state through its border and glow.
  const frame =
    validation === 'invalid'
      ? 'border-danger/45'
      : focused
        ? 'border-primary/55'
        : validation === 'valid'
          ? 'border-primary/35'
          : 'border-white/[0.09] hover:border-white/[0.16]';

  /*
    Submit handoff, derived entirely from state the client genuinely holds:

      resolving — the analyze request is in flight and the backend has not yet
                  reported a completed stage
      analyzing — at least one pipeline stage has actually completed

    No timers, no synthetic progress. If the backend is slow the surface stays on
    RESOLVING for as long as that is the truth, rather than advancing on a clock.
  */
  const completedSteps = analysisSteps.filter((s) => s.status === 'completed').length;
  const handoff: 'idle' | 'resolving' | 'analyzing' = !isAnalyzing
    ? 'idle'
    : completedSteps === 0
      ? 'resolving'
      : 'analyzing';

  return (
    <div className="space-y-14 sm:space-y-16">
      {/* ── The command field ─────────────────────────────────────────────── */}
      <div>
        <form
          id="repo-analyzer-form"
          name="repo_analyzer_form"
          onSubmit={(e) => {
            e.preventDefault();
            if (canSubmit) analyze(url);
          }}
        >
          <div className="flex items-baseline justify-between gap-4 mb-3">
            <span className="mono-label mono-label-accent">SYSTEM COMMAND</span>
            <span className="mono-label hidden sm:block">PUBLIC GITHUB REPOSITORY</span>
          </div>

          {/*
            The same corner marks the topology figure carries, so the input reads
            as part of the instrument rather than as a form at the end of a page.
          */}
          <div
            data-pointer="command"
            className={`command-surface data-brackets ${focused ? 'is-focused' : ''}
                        flex items-center gap-4 sm:gap-5 border bg-canvas/70 backdrop-blur-sm
                        px-4 sm:px-7 py-5 sm:py-7 ${frame}`}
          >
            <span
              className="shrink-0 font-mono text-base sm:text-xl text-primary select-none leading-none"
              aria-hidden="true"
            >
              $
            </span>

            <label htmlFor="repo-url" className="sr-only">
              GitHub repository URL
            </label>
            <input
              id="repo-url"
              name="repo_url"
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
              placeholder="github.com/owner/repository"
              aria-invalid={validation === 'invalid'}
              aria-describedby="repo-url-status"
              style={{ caretColor: 'var(--primary)' }}
              className="flex-1 min-w-0 bg-transparent border-0 outline-none font-mono
                         text-[15px] sm:text-xl text-text placeholder:text-text-subtle/70
                         disabled:opacity-60"
            />

            {/* Live validation glyph */}
            <span className="shrink-0 flex items-center" aria-hidden="true">
              {validation === 'checking' && (
                <Loader2 className="h-4 w-4 text-text-subtle animate-spin" />
              )}
              {validation === 'valid' && (
                <CheckCircle2 className="h-4 w-4 text-primary animate-pop-in" />
              )}
              {validation === 'invalid' && (
                <AlertCircle className="h-4 w-4 text-danger animate-pop-in" />
              )}
            </span>

            {/* Keyboard affordance, retired once the field is in use */}
            {!url && !focused && !isAnalyzing && (
              <kbd
                className="hidden sm:inline-flex shrink-0 items-center justify-center h-6 w-6
                           border border-white/[0.09] font-mono text-[11px] text-text-subtle select-none"
              >
                /
              </kbd>
            )}

            <button
              id="analyze-submit-btn"
              type="submit"
              disabled={!canSubmit}
              className="link-arrow lumen-button shrink-0 inline-flex items-center gap-2 sm:gap-2.5 px-4 sm:px-6 py-2.5 sm:py-3
                         font-mono text-[11px] sm:text-xs font-bold uppercase tracking-[0.18em]
                         border focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary
                         enabled:border-primary/60 enabled:bg-primary/12 enabled:text-primary
                         enabled:hover:bg-primary enabled:hover:text-white enabled:hover:border-primary
                         disabled:border-white/[0.07] disabled:text-text-subtle disabled:cursor-not-allowed"
            >
              <span className="hidden sm:inline">{isAnalyzing ? 'Analyzing' : 'Analyze'}</span>
              <span className="sm:hidden">{isAnalyzing ? '···' : 'Run'}</span>
              {isAnalyzing ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
              ) : (
                <ArrowRight className="h-3.5 w-3.5 arrow" aria-hidden="true" />
              )}
            </button>
          </div>
        </form>

        {/* Status line — resolved target, or why the value was rejected */}
        <div
          id="repo-url-status"
          role="status"
          aria-live="polite"
          className="mt-5 min-h-[1.5rem] flex flex-wrap items-center gap-x-4 gap-y-2"
        >
          {validation === 'valid' && parsed && (
            <span className="font-mono text-[11px] text-text animate-pop-in">
              <span className="text-text-subtle mr-2 tracking-[0.2em]">
                {isAnalyzing ? 'INDEXING' : 'TARGET'}
              </span>
              <span>{parsed.owner} / {parsed.repo}</span>
              {!isAnalyzing && (
                <span className="text-text-subtle ml-3 hidden sm:inline">· ↵ to execute</span>
              )}
            </span>
          )}

          {/*
            The handoff. Between pressing Analyze and the page changing, the
            surface says what is actually happening — and only what is actually
            happening. Both labels are reflections of real state.
          */}
          {handoff !== 'idle' && (
            <span
              className={`command-phase is-shown mono-label mono-label-accent`}
              style={{ letterSpacing: '0.2em' }}
            >
              {handoff === 'resolving' ? 'RESOLVING REPOSITORY' : 'ANALYZING STRUCTURE'}
            </span>
          )}

          {validation === 'invalid' && (
            <span className="font-mono text-[11px] text-danger/90 animate-pop-in">
              {describeInvalidUrl(url)}
            </span>
          )}

          {(validation === 'empty' || validation === 'checking') && !isAnalyzing && (
            <div className="w-full flex items-center justify-between gap-4">
              <span className="mono-detail" style={{ fontSize: 10, letterSpacing: '0.16em' }}>
                DETERMINISTIC AST PARSER · GRAPH INTELLIGENCE · ZERO WRITEBACK
              </span>
              <span className="mono-detail hidden sm:inline" style={{ fontSize: 10 }}>
                Press / to focus
              </span>
            </div>
          )}
        </div>

        {/* Live pipeline while indexing */}
        {isAnalyzing && (
          <div className="mt-10" role="status">
            <AnalysisProgress
              steps={analysisSteps}
              progress={jobProgress}
              jobStartedAt={jobStartedAt}
              jobElapsedSeconds={jobElapsedSeconds}
            />
          </div>
        )}

        {errorMessage && (
          <div
            role="alert"
            className="mt-7 flex items-start gap-3.5 border border-danger/25 bg-danger/[0.04] p-5"
          >
            <AlertCircle className="h-4 w-4 shrink-0 mt-0.5 text-danger" aria-hidden="true" />
            <div className="space-y-1.5">
              <span className="mono-label block" style={{ color: 'var(--danger)' }}>
                ANALYSIS FAILED
              </span>
              <p className="text-[13px] text-text-muted leading-relaxed">{errorMessage}</p>
              {/(quota|429|RESOURCE_EXHAUSTED|rate limit)/i.test(errorMessage) && (
                <p className="mono-detail" style={{ fontSize: 10 }}>
                  AI provider rate limit reached — wait a moment before retrying.
                </p>
              )}
            </div>
          </div>
        )}
      </div>

      {/* ── Sample codebases ──────────────────────────────────────────────── */}
      {!isAnalyzing && (
        <SampleCodebases
          repos={samples}
          disabled={isAnalyzing}
          onSelect={(sampleUrl) => {
            setUrl(sampleUrl);
            analyze(sampleUrl);
          }}
        />
      )}
    </div>
  );
};

export default RepositoryAnalyzer;
