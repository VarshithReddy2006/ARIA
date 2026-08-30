import React, { useEffect, useState } from 'react';
import { FileDown, Github, RefreshCw, Search } from 'lucide-react';
import { apiUrl } from '../../lib/api';
import { relativeTimeFrom, type ComplexityResult } from '../../lib/repoMetrics';

export interface RepoHealth {
  score: number;
  grade: string;
  analyzedAt: string | null;
}

/** A component ranked by how many relationships touch it. Derived, not fetched. */
export interface CentralityHub {
  name: string;
  /** Inbound relationship count. */
  inbound: number;
  /** Total degree, used for the bar length. */
  degree: number;
}

export interface RepoHeroProps {
  owner: string;
  repoSlug: string;
  summary?: string;
  primaryLanguage?: string | null;
  readingMinutes?: number;
  complexity?: ComplexityResult;
  /** Epoch ms of the last local index. */
  indexedAt: number | null;
  /** Top components by degree, computed from the real architecture graph. */
  hubs?: CentralityHub[];
  onRefresh: () => void;
  onExportReport: () => void;
  onOpenCommandPalette: () => void;
}

/**
 * Reads the cached health score from the lightweight `summary` endpoint so the
 * header never triggers an expensive report rebuild. Failure is non-fatal — the
 * read-out reports that it is unavailable rather than inventing a value.
 */
export function useRepoHealth(owner: string, repoSlug: string) {
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

/** Health colour follows the score: green healthy, amber degraded, red poor. */
export function healthTone(score: number | null) {
  if (score === null) return { text: 'text-text-muted', bar: 'bg-white/20', border: 'border-l-white/[0.09]' };
  if (score >= 80) return { text: 'text-success', bar: 'bg-success', border: 'border-l-success/50' };
  if (score >= 60) return { text: 'text-warn', bar: 'bg-warn', border: 'border-l-warn/50' };
  return { text: 'text-danger', bar: 'bg-danger', border: 'border-l-danger/50' };
}

/**
 * Compact Repository Header.
 * Displays repository breadcrumb identity, indexing telemetry, and primary actions.
 */
export const RepoHero: React.FC<RepoHeroProps> = ({
  owner,
  repoSlug,
  indexedAt,
  onRefresh,
  onExportReport,
  onOpenCommandPalette,
}) => {
  const indexedAgo = relativeTimeFrom(indexedAt);

  return (
    <section aria-labelledby="repo-header-title" className="w-full pb-4 border-b border-white/[0.055]">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        {/* ── Left: Compact Repository Identity ── */}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap min-w-0">
            <h1
              id="repo-header-title"
              className="font-sans font-bold tracking-tight text-text text-xl sm:text-2xl md:text-3xl flex items-baseline gap-1.5 min-w-0 truncate"
              title={`${owner}/${repoSlug}`}
            >
              <span className="text-text-muted font-normal truncate max-w-[200px] sm:max-w-xs md:max-w-sm">
                {owner}
              </span>
              <span className="text-text-subtle select-none font-normal">/</span>
              <span className="text-text font-bold truncate max-w-[260px] sm:max-w-md md:max-w-xl">
                {repoSlug}
              </span>
            </h1>
          </div>

          <div className="flex items-center gap-2.5 mt-1.5 text-[11px] font-mono text-text-muted flex-wrap">
            <span className="flex items-center gap-1.5 text-success font-semibold">
              <span className="h-1.5 w-1.5 rounded-full bg-success shrink-0" aria-hidden="true" />
              INDEXED
            </span>
            <span className="text-text-subtle select-none">·</span>
            <span className="text-text-muted">main</span>
            <span className="text-text-subtle select-none">·</span>
            <span className="text-text-muted capitalize">
              {indexedAgo ? `${indexedAgo}` : 'just now'}
            </span>
          </div>
        </div>

        {/* ── Right: Repository Actions ── */}
        <div className="flex flex-wrap items-center gap-2.5 sm:gap-3 shrink-0">
          <button
            type="button"
            onClick={onOpenCommandPalette}
            className="action-chip text-xs px-3 py-1.5 inline-flex items-center gap-2 font-sans font-medium"
            aria-label="Search repository commands and files"
            aria-keyshortcuts="Control+K Meta+K"
          >
            <Search className="h-3.5 w-3.5 text-text-subtle" aria-hidden="true" />
            <span className="mono-label" style={{ fontSize: 10 }}>SEARCH</span>
            <kbd className="hidden sm:inline-flex items-center border border-white/[0.09] px-1 font-mono text-[9px] text-text-subtle">
              ⌘K
            </kbd>
          </button>

          <a
            href={`https://github.com/${owner}/${repoSlug}`}
            target="_blank"
            rel="noopener noreferrer"
            className="action-chip text-xs px-3 py-1.5 inline-flex items-center gap-1.5 font-sans font-medium"
            aria-label="View repository on GitHub"
          >
            <Github className="h-3.5 w-3.5 text-text-subtle" aria-hidden="true" />
            <span className="mono-label" style={{ fontSize: 10 }}>GITHUB</span>
          </a>

          <button
            type="button"
            onClick={onRefresh}
            className="action-chip text-xs px-3 py-1.5 inline-flex items-center gap-1.5 font-sans font-medium"
            aria-label="Refresh repository analysis"
          >
            <RefreshCw className="h-3.5 w-3.5 text-text-subtle" aria-hidden="true" />
            <span className="mono-label" style={{ fontSize: 10 }}>REFRESH</span>
          </button>

          <button
            type="button"
            onClick={onExportReport}
            className="btn-primary text-xs px-3.5 py-1.5 inline-flex items-center gap-1.5 font-sans font-semibold"
            aria-label="Export or view repository health report"
          >
            <FileDown className="h-3.5 w-3.5" aria-hidden="true" />
            <span>EXPORT REPORT</span>
          </button>
        </div>
      </div>
    </section>
  );
};

export default RepoHero;
