import React, { useEffect, useState } from 'react';
import {
  CheckCircle2, Code2, Clock, Gauge, Github, RefreshCw, FileDown,
  Layers, HeartPulse, Search,
} from 'lucide-react';
import { apiUrl } from '../../lib/api';
import { Badge } from '../ui/Badge';
import { Skeleton } from '../ui/Skeleton';
import {
  formatDuration, relativeTimeFrom, scoreTone,
  type ComplexityResult,
} from '../../lib/repoMetrics';

interface RepoHealth {
  score: number;
  grade: string;
  analyzedAt: string | null;
}

interface RepoHeroProps {
  owner: string;
  repoSlug: string;
  /** Architecture summary — truncated into the hero subtitle */
  summary: string;
  primaryLanguage: string | null;
  readingMinutes: number;
  complexity: ComplexityResult;
  /** Epoch ms of the last local index, used for the "indexed X ago" line */
  indexedAt: number | null;
  onRefresh: () => void;
  onExportReport: () => void;
  onOpenCommandPalette: () => void;
}

const toneText = {
  success: 'text-success',
  warn: 'text-warn',
  danger: 'text-danger',
  info: 'text-info',
} as const;

const toneBorder = {
  success: 'border-success/30 bg-success/5',
  warn: 'border-warn/30 bg-warn/5',
  danger: 'border-danger/30 bg-danger/5',
  info: 'border-info/30 bg-info/5',
} as const;

/**
 * Reads the cached health score. Uses the lightweight `summary` endpoint so the
 * hero never triggers an expensive report rebuild — the Health Report tab owns
 * that. Failure is non-fatal: the stat is simply omitted.
 */
function useRepoHealth(owner: string, repoSlug: string) {
  const [health, setHealth] = useState<RepoHealth | null>(null);
  const [state, setState] = useState<'loading' | 'ready' | 'unavailable'>('loading');

  useEffect(() => {
    if (!owner || !repoSlug) {
      setState('unavailable');
      return;
    }

    const controller = new AbortController();
    setState('loading');
    setHealth(null);

    fetch(apiUrl(`/api/v1/report/${owner}/${repoSlug}/summary`), { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error('unavailable');
        return res.json();
      })
      .then((data) => {
        const score = Number(data?.score);
        if (!Number.isFinite(score)) throw new Error('malformed');
        setHealth({
          score: Math.round(score),
          grade: String(data?.grade ?? '—'),
          analyzedAt: data?.analyzed_at ?? null,
        });
        setState('ready');
      })
      .catch((err) => {
        if (err?.name === 'AbortError') return;
        setState('unavailable');
      });

    return () => controller.abort();
  }, [owner, repoSlug]);

  return { health, state };
}

interface StatProps {
  icon: React.ReactNode;
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  tone?: keyof typeof toneText;
}

const Stat: React.FC<StatProps> = ({ icon, label, value, hint, tone }) => (
  <div className="flex items-start gap-3 min-w-0">
    <div
      className={`h-8 w-8 shrink-0 rounded-lg border flex items-center justify-center ${
        tone ? `${toneBorder[tone]} ${toneText[tone]}` : 'border-border bg-surface-2 text-text-muted'
      }`}
      aria-hidden="true"
    >
      {icon}
    </div>
    <div className="min-w-0">
      <div className="text-[10px] font-mono font-semibold uppercase tracking-wider text-text-subtle">
        {label}
      </div>
      <div className={`text-sm font-semibold mt-0.5 truncate ${tone ? toneText[tone] : 'text-text'}`}>
        {value}
      </div>
      {hint && <div className="text-[10px] text-text-muted font-sans truncate">{hint}</div>}
    </div>
  </div>
);

export const RepoHero: React.FC<RepoHeroProps> = ({
  owner,
  repoSlug,
  summary,
  primaryLanguage,
  readingMinutes,
  complexity,
  indexedAt,
  onRefresh,
  onExportReport,
  onOpenCommandPalette,
}) => {
  const { health, state: healthState } = useRepoHealth(owner, repoSlug);
  const indexedAgo = relativeTimeFrom(indexedAt);
  const trimmedSummary =
    summary && summary.length > 220 ? `${summary.slice(0, 220).trimEnd()}…` : summary;

  return (
    <section
      className="relative overflow-hidden card p-6 sm:p-8 fade-up"
      aria-labelledby="repo-hero-title"
    >
      {/* Ambient brand wash — decorative only */}
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10">
        <div
          className="absolute -top-32 -right-24 h-72 w-72 rounded-full blur-3xl opacity-25"
          style={{ background: 'radial-gradient(circle, rgba(94,106,210,0.55) 0%, transparent 70%)' }}
        />
      </div>

      <div className="flex flex-col gap-6">
        {/* Title row */}
        <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-5">
          <div className="min-w-0">
            <div className="flex items-center gap-2.5 mb-2">
              <span className="text-[10px] font-mono uppercase tracking-widest text-primary font-bold">
                Repository Intelligence
              </span>
              <Badge tone="success" icon={<CheckCircle2 className="h-3 w-3" />}>
                Indexed
              </Badge>
            </div>

            <h1
              id="repo-hero-title"
              className="text-2xl sm:text-3xl lg:text-4xl font-semibold tracking-tight flex items-center gap-3 min-w-0"
            >
              <Layers className="h-7 w-7 text-primary shrink-0" aria-hidden="true" />
              <span className="font-mono break-all">
                <span className="text-text-muted">{owner}</span>
                <span className="text-text-subtle">/</span>
                <span className="text-text">{repoSlug}</span>
              </span>
            </h1>

            {trimmedSummary && (
              <p className="text-sm text-text-muted mt-3 max-w-2xl leading-relaxed font-sans">
                {trimmedSummary}
              </p>
            )}
          </div>

          {/* Primary actions */}
          <div className="flex flex-wrap items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={onOpenCommandPalette}
              className="btn-ghost text-xs"
              aria-keyshortcuts="Control+K Meta+K"
            >
              <Search className="h-3.5 w-3.5" aria-hidden="true" />
              <span>Search</span>
              <kbd className="ml-1 hidden sm:inline-flex items-center rounded border border-border
                              bg-surface-2 px-1 text-[10px] font-mono text-text-subtle">
                ⌘K
              </kbd>
            </button>
            <a
              href={`https://github.com/${owner}/${repoSlug}`}
              target="_blank"
              rel="noopener noreferrer"
              className="btn-ghost text-xs"
            >
              <Github className="h-3.5 w-3.5" aria-hidden="true" />
              GitHub
            </a>
            <button type="button" className="btn-ghost text-xs" onClick={onRefresh}>
              <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
              Refresh
            </button>
            <button type="button" className="btn-primary text-xs px-3 py-1.5" onClick={onExportReport}>
              <FileDown className="h-3.5 w-3.5" aria-hidden="true" />
              Export Report
            </button>
          </div>
        </div>

        {/* Stat rail */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5 pt-5 border-t border-border">
          {/* Health score — real backend value */}
          {healthState === 'loading' ? (
            <div className="flex items-start gap-3">
              <Skeleton size="h-8 w-8" rounded="lg" />
              <div className="space-y-1.5 flex-grow">
                <Skeleton size="h-2.5 w-20" rounded="sm" />
                <Skeleton size="h-3.5 w-16" rounded="sm" />
              </div>
            </div>
          ) : health ? (
            <Stat
              icon={<HeartPulse className="h-4 w-4" />}
              label="Health Score"
              value={`${health.score}/100`}
              hint={`Grade ${health.grade}`}
              tone={scoreTone(health.score)}
            />
          ) : (
            <Stat
              icon={<HeartPulse className="h-4 w-4" />}
              label="Health Score"
              value="Not yet scored"
              hint="Open Health Report to generate"
            />
          )}

          <Stat
            icon={<Code2 className="h-4 w-4" />}
            label="Primary Language"
            value={primaryLanguage ?? 'Unknown'}
            hint={primaryLanguage ? 'Highest-confidence detection' : 'No language detected'}
          />

          <Stat
            icon={<Clock className="h-4 w-4" />}
            label="Est. Reading Time"
            value={formatDuration(readingMinutes)}
            hint="Full onboarding path"
          />

          <Stat
            icon={<Gauge className="h-4 w-4" />}
            label="Complexity"
            value={complexity.label}
            hint={`Density index ${complexity.score}/100`}
            tone={complexity.tone}
          />
        </div>

        {indexedAgo && (
          <p className="text-[10px] font-mono text-text-subtle">
            Indexed {indexedAgo}
          </p>
        )}
      </div>
    </section>
  );
};

export default RepoHero;
