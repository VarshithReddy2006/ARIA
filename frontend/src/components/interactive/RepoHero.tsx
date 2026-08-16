import React, { useEffect, useState } from 'react';
import { FileDown, Github, RefreshCw, Search } from 'lucide-react';
import { apiUrl } from '../../lib/api';
import { AnimatedNumber } from '../ui/AnimatedNumber';
import { Meter } from '../ui/Meter';
import { Reveal } from '../ui/Reveal';
import { FilePath } from '../ui/FilePath';
import { formatDuration, relativeTimeFrom, type ComplexityResult } from '../../lib/repoMetrics';

interface RepoHealth {
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

interface RepoHeroProps {
  owner: string;
  repoSlug: string;
  summary: string;
  primaryLanguage: string | null;
  readingMinutes: number;
  complexity: ComplexityResult;
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

/** Health colour follows the score: green healthy, amber degraded, red poor. */
function healthTone(score: number | null) {
  if (score === null) return { text: 'text-text-muted', bar: 'bg-white/20', border: 'border-l-white/[0.09]' };
  if (score >= 80) return { text: 'text-success', bar: 'bg-success', border: 'border-l-success/50' };
  if (score >= 60) return { text: 'text-warn', bar: 'bg-warn', border: 'border-l-warn/50' };
  return { text: 'text-danger', bar: 'bg-danger', border: 'border-l-danger/50' };
}

export const RepoHero: React.FC<RepoHeroProps> = ({
  owner,
  repoSlug,
  primaryLanguage,
  readingMinutes,
  complexity,
  indexedAt,
  hubs = [],
  onRefresh,
  onExportReport,
  onOpenCommandPalette,
}) => {
  const { health, state: healthState } = useRepoHealth(owner, repoSlug);
  const indexedAgo = relativeTimeFrom(indexedAt);
  const tone = healthTone(health ? health.score : null);

  const leadHub = hubs[0];
  const maxDegree = hubs.reduce((max, h) => Math.max(max, h.degree), 0) || 1;

  return (
    <section aria-labelledby="repo-hero-title">
      {/* ── Header ───────────────────────────────────────────────────────── */}
      <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-6">
        <div className="min-w-0">
          <div className="flex items-center gap-2.5 mb-4">
            <span className="mono-label mono-label-accent">REPOSITORY / ANALYSIS</span>
            <span className="h-1 w-1 rounded-full bg-success shrink-0" aria-hidden="true" />
            <span className="mono-label" style={{ color: 'var(--success)' }}>
              INDEXED
            </span>
          </div>

          {/* Editorial, but deliberately smaller than the landing hero */}
          <h1 id="repo-hero-title" className="font-mono font-bold tracking-tight min-w-0">
            <span
              className="block text-text-muted leading-none break-all"
              style={{ fontSize: 'clamp(1.05rem, 2vw, 1.5rem)' }}
            >
              {owner} <span className="text-text-subtle">/</span>
            </span>
            <span
              className="block text-text leading-[0.95] break-all"
              style={{ fontSize: 'clamp(1.75rem, 4.2vw, 3.25rem)', letterSpacing: '-0.03em' }}
            >
              {repoSlug}
            </span>
          </h1>
        </div>

        {/* Actions — quiet, except the primary export */}
        <div className="flex flex-wrap items-center gap-x-5 gap-y-3 shrink-0">
          <button
            type="button"
            onClick={onOpenCommandPalette}
            className="group flex items-center gap-2 mono-label hover:text-text transition-colors
                       focus-visible:outline-none"
            aria-keyshortcuts="Control+K Meta+K"
          >
            <Search className="h-3.5 w-3.5" aria-hidden="true" />
            <span>SEARCH</span>
            <kbd className="hidden sm:inline-flex items-center border border-white/[0.09] px-1
                            font-mono text-[10px] text-text-subtle">
              ⌘K
            </kbd>
          </button>

          <a
            href={`https://github.com/${owner}/${repoSlug}`}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 mono-label hover:text-text transition-colors
                       focus-visible:outline-none"
          >
            <Github className="h-3.5 w-3.5" aria-hidden="true" />
            <span>GITHUB</span>
          </a>

          <button
            type="button"
            onClick={onRefresh}
            className="flex items-center gap-2 mono-label hover:text-text transition-colors
                       focus-visible:outline-none"
          >
            <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
            <span>REFRESH</span>
          </button>

          <button
            type="button"
            onClick={onExportReport}
            className="link-arrow flex items-center gap-2 border border-primary/50 bg-primary/10 px-4 py-2
                       font-mono text-[11px] uppercase tracking-[0.16em] text-primary
                       hover:bg-primary hover:text-white hover:border-primary
                       transition-colors duration-300 focus-visible:outline-none"
          >
            <FileDown className="h-3.5 w-3.5 arrow" aria-hidden="true" />
            <span>Export Report</span>
          </button>
        </div>
      </div>

      {/* ── Signal rail ──────────────────────────────────────────────────── */}
      <Reveal delay={80} className="mt-9 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-y-7">
        {/* Architecture health — the page's primary signal */}
        <div className={`readout readout--lead metric-enter-1 border-l-2 ${tone.border} col-span-2 md:col-span-1`}>
          <div className="mono-label mono-label-accent mb-2.5">ARCHITECTURE HEALTH</div>
          <div className="flex items-baseline gap-2.5 flex-wrap">
            <span className={`readout-value readout-value--lead ${tone.text}`}>
              {health ? (
                <AnimatedNumber value={health.score} suffix="%" duration={1100} />
              ) : healthState === 'loading' ? (
                '··'
              ) : (
                '—'
              )}
            </span>
            {health && (
              <span
                className={`font-mono text-[11px] uppercase tracking-[0.16em] ${tone.text}`}
              >
                Grade {health.grade}
              </span>
            )}
          </div>

          {/* One thin risk line, no gauge — grows once in view */}
          <Meter
            value={health ? health.score / 100 : 0}
            barClassName={tone.bar}
            className="mt-3.5 max-w-[9rem]"
            delay={120}
          />

          <div className="mono-detail mt-2.5" style={{ fontSize: 10 }}>
            {healthState === 'loading'
              ? 'Evaluating topology…'
              : healthState === 'unavailable'
                ? 'Report not yet generated'
                : 'Deterministic score'}
          </div>
        </div>

        <div className="readout metric-enter-2">
          <div className="mono-label mb-2.5">PRIMARY STACK</div>
          <div className="readout-value truncate">{primaryLanguage ?? '—'}</div>
          <div className="mono-detail mt-2.5" style={{ fontSize: 10 }}>
            Tree-sitter parsed
          </div>
        </div>

        <div className="readout metric-enter-3">
          <div className="mono-label mb-2.5">READING TIME</div>
          <div className="readout-value">{formatDuration(readingMinutes)}</div>
          <div className="mono-detail mt-2.5" style={{ fontSize: 10 }}>
            Topological sequence
          </div>
        </div>

        <div className="readout metric-enter-4">
          <div className="mono-label mb-2.5">COMPLEXITY</div>
          <div className="readout-value uppercase truncate">{complexity.label}</div>
          <div className="mono-detail mt-2.5" style={{ fontSize: 10 }}>
            Density {complexity.score}/100
          </div>
        </div>

        <div className="readout metric-enter-5">
          <div className="mono-label mb-2.5">LAST INDEXED</div>
          <div className="readout-value text-text-muted truncate">{indexedAgo ?? 'just now'}</div>
          <div className="mono-detail mt-2.5" style={{ fontSize: 10 }}>
            Cached locally
          </div>
        </div>
      </Reveal>

      {/* ── Architectural gravity ────────────────────────────────────────── */}
      {hubs.length > 0 && (
        <Reveal className="mt-8 pt-7 hair-t grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-12">
          <div className="lg:col-span-4 min-w-0">
            <div className="mono-label mono-label-accent mb-3">MOST CONNECTED MODULE</div>
            <FilePath path={leadHub.name} tone="primary" size="lg" />

            <p className="mono-detail mt-2.5">
              {leadHub.inbound} inbound {leadHub.inbound === 1 ? 'relationship' : 'relationships'} ·{' '}
              {leadHub.degree} total degree
            </p>
            <p className="text-[13px] text-text-muted leading-relaxed mt-4 max-w-sm">
              This is where the repository's architectural gravity sits. Changes here travel
              furthest.
            </p>
          </div>

          {/* Degree distribution — the lead bar is dominant */}
          <div className="lg:col-span-8 min-w-0 relative">
            {/* Faint graph hint behind the bars */}
            <svg
              className="pointer-events-none absolute inset-0 h-full w-full opacity-[0.5]"
              viewBox="0 0 400 120"
              preserveAspectRatio="none"
              aria-hidden="true"
            >
              <g stroke="rgba(94,106,210,0.16)" strokeWidth="0.5" fill="none">
                <path d="M0 96 L120 30 L260 74 L400 18" />
                <path d="M0 40 L150 100 L300 44 L400 88" />
              </g>
            </svg>

            <div className="flex items-baseline justify-between gap-4 mb-4 relative">
              <span className="mono-label">TOPOLOGICAL CENTRALITY</span>
              <span className="mono-label shrink-0">BY DEGREE</span>
            </div>

            <ul className="relative space-y-3.5">
              {hubs.map((hub, i) => (
                <li
                  key={hub.name}
                  tabIndex={0}
                  className="hub-row group/hub min-w-0 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary/50 rounded-sm p-0.5"
                >
                  <div className="flex items-baseline justify-between gap-4">
                    <span className="hub-name min-w-0 truncate">
                      <FilePath
                        path={hub.name}
                        tone={i === 0 ? 'primary' : 'secondary'}
                        size="sm"
                      />
                    </span>
                    <span className="mono-detail shrink-0 tabular-nums" style={{ fontSize: 10 }}>
                      {hub.inbound} in · {hub.degree} deg
                    </span>
                  </div>
                  {/* Bars draw in sequence, heaviest first */}
                  <Meter
                    value={hub.degree / maxDegree}
                    barClassName={i === 0 ? 'bg-primary' : 'bg-primary/35'}
                    className={`mt-2 ${i === 0 ? 'h-[3px]' : ''}`}
                    delay={i * 110}
                  />
                </li>
              ))}
            </ul>
          </div>
        </Reveal>
      )}
    </section>
  );
};

export default RepoHero;
