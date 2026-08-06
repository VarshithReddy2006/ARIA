import React, { useState, useCallback } from 'react';
import { apiUrl, extractErrorMessage } from '../../lib/api';
import { Button } from '../ui/Button';
import { Badge } from '../ui/Badge';
import { MetricCard } from '../ui/MetricCard';
import { EmptyState } from '../ui/EmptyState';
import { SkeletonCard, SkeletonGroup, Skeleton } from '../ui/Skeleton';
import {
  GitCommit, Flame, User, Calendar, AlertTriangle,
  TrendingUp, Clock, ChevronDown, ChevronUp, RefreshCw,
} from 'lucide-react';

// ── Types ─────────────────────────────────────────────────────────────────

interface HotspotFile {
  file_path: string;
  churn_score: number;
  centrality: number;
  hotspot_score: number;
  commit_count: number;
  primary_author: string;
  bus_factor_risk: boolean;
}

interface TimelineEntry {
  week: string;
  commit_count: number;
  files_changed: number;
  authors: string[];
}

interface AuthorOwnership {
  file_path: string;
  primary_author: string;
  ownership_pct: number;
  contributors: Record<string, number>;
}

interface ChurnSummary {
  repo: string;
  generated_at: string;
  since_days: number;
  total_commits: number;
  total_files: number;
  hotspots: HotspotFile[];
  author_ownership: AuthorOwnership[];
  timeline: TimelineEntry[];
  warning?: string;
}

interface Props {
  repoName: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────

function churnColor(score: number): string {
  if (score >= 80) return 'text-red-400';
  if (score >= 50) return 'text-orange-400';
  if (score >= 20) return 'text-yellow-400';
  return 'text-green-400';
}

function churnBg(score: number): string {
  if (score >= 80) return 'bg-red-500';
  if (score >= 50) return 'bg-orange-500';
  if (score >= 20) return 'bg-yellow-500';
  return 'bg-green-500';
}

function shortPath(fp: string): string {
  const parts = fp.replace('\\', '/').split('/');
  return parts.length > 3
    ? `…/${parts.slice(-2).join('/')}`
    : fp;
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  } catch {
    return iso.slice(0, 10);
  }
}

// ── Mini bar chart for timeline ────────────────────────────────────────────

function TimelineChart({ entries }: { entries: TimelineEntry[] }) {
  const maxCommits = Math.max(...entries.map((e) => e.commit_count), 1);
  const visible = entries.slice(-24); // last 24 weeks
  return (
    <div className="space-y-2">
      <div className="flex items-end gap-0.5 h-20 w-full" aria-label="Weekly commit activity chart">
        {visible.map((entry) => {
          const pct = (entry.commit_count / maxCommits) * 100;
          return (
            <div
              key={entry.week}
              title={`${entry.week}: ${entry.commit_count} commits, ${entry.files_changed} files`}
              className="flex-1 rounded-sm bg-primary/30 hover:bg-primary/60 transition-colors cursor-default"
              style={{ height: `${Math.max(pct, 4)}%` }}
              role="img"
              aria-label={`Week of ${entry.week}: ${entry.commit_count} commits`}
            />
          );
        })}
      </div>
      {visible.length > 0 && (
        <div className="flex justify-between text-[10px] text-text-muted font-mono">
          <span>{visible[0].week}</span>
          <span>{visible[visible.length - 1].week}</span>
        </div>
      )}
    </div>
  );
}

// ── Hotspot row ────────────────────────────────────────────────────────────

function HotspotRow({ h, rank }: { h: HotspotFile; rank: number }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((p) => !p)}
        className="w-full flex items-center gap-3 px-4 py-3 hover:bg-surface/50
                   transition-colors text-left focus-visible:outline-none focus-visible:shadow-ring"
        aria-expanded={open}
      >
        {/* rank badge */}
        <span className="text-[11px] font-mono text-text-muted w-5 shrink-0">
          #{rank}
        </span>

        {/* churn bar */}
        <div className="w-20 shrink-0">
          <div className="h-1.5 rounded-full bg-border overflow-hidden">
            <div
              className={`h-full rounded-full ${churnBg(h.churn_score)}`}
              style={{ width: `${h.churn_score}%` }}
            />
          </div>
        </div>

        {/* file path */}
        <span className="flex-1 text-xs font-mono text-text truncate min-w-0">
          {shortPath(h.file_path)}
        </span>

        {/* commit count */}
        <span className="text-xs font-mono text-text-muted shrink-0 hidden sm:block">
          {h.commit_count} commits
        </span>

        {/* bus factor warning */}
        {h.bus_factor_risk && (
          <AlertTriangle
            className="h-3.5 w-3.5 text-orange-400 shrink-0"
            aria-label="Bus factor risk"
          />
        )}

        {/* score */}
        <span className={`text-xs font-bold font-mono shrink-0 ${churnColor(h.churn_score)}`}>
          {h.churn_score.toFixed(0)}
        </span>

        {open
          ? <ChevronUp className="h-3.5 w-3.5 text-text-muted shrink-0" />
          : <ChevronDown className="h-3.5 w-3.5 text-text-muted shrink-0" />}
      </button>

      {open && (
        <div className="px-4 pb-4 pt-1 border-t border-border bg-canvas/40 space-y-2 fade-up">
          <p className="text-[10px] font-mono text-text-muted break-all">{h.file_path}</p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
            <div>
              <span className="text-text-muted">Churn Score</span>
              <p className={`font-bold font-mono ${churnColor(h.churn_score)}`}>
                {h.churn_score.toFixed(1)} / 100
              </p>
            </div>
            <div>
              <span className="text-text-muted">Graph Centrality</span>
              <p className="font-mono text-text">{(h.centrality * 100).toFixed(1)} %</p>
            </div>
            <div>
              <span className="text-text-muted">Hotspot Score</span>
              <p className="font-mono text-text">{h.hotspot_score.toFixed(2)}</p>
            </div>
            <div>
              <span className="text-text-muted">Primary Author</span>
              <p className="font-mono text-text truncate">{h.primary_author || '—'}</p>
            </div>
          </div>
          {h.bus_factor_risk && (
            <p className="text-[11px] text-orange-400 flex items-center gap-1.5">
              <AlertTriangle className="h-3 w-3" />
              Bus factor risk — one author owns &gt;80 % of commits on this file.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────

export const GitHistoryAnalyzer: React.FC<Props> = ({ repoName }) => {
  const [summary, setSummary] = useState<ChurnSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [sinceDays, setSinceDays] = useState(365);
  const [activeView, setActiveView] = useState<'hotspots' | 'timeline' | 'authors'>('hotspots');

  const [owner, repo] = repoName.split('/');

  // Try loading cached summary on first mount or sinceDays change
  React.useEffect(() => {
    setSummary(null);
    setError(null);
    fetch(apiUrl(`/api/v1/churn/${owner}/${repo}?since_days=${sinceDays}`))
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (d) setSummary(d); })
      .catch(() => { /* no cached data — show empty state */ });
  }, [repoName, sinceDays, owner, repo]);

  const runAnalysis = useCallback(async () => {
    setLoading(true);
    setError(null);
    setProgress('Starting…');
    setSummary(null);

    try {
      const res = await fetch(apiUrl('/api/v1/churn/analyze'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ repo: repoName, since_days: sinceDays }),
      });

      if (!res.body) throw new Error('No response body from server.');

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop() ?? '';

        for (const part of parts) {
          const line = part.replace(/^data: /, '').trim();
          if (!line) continue;
          try {
            const event = JSON.parse(line);
            if (event.status === 'error') {
              setError(event.message);
              setLoading(false);
              return;
            }
            if (event.status === 'done') { setLoading(false); return; }
            if (event.status === 'result' && event.data) {
              setSummary(event.data as ChurnSummary);
            } else if (event.message) {
              setProgress(event.message);
            }
          } catch { /* non-JSON line — skip */ }
        }
      }
    } catch (err: any) {
      setError(extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [repoName, sinceDays]);

  // ── Render ──────────────────────────────────────────────────────────────

  return (
    <div className="space-y-5 fade-up">
      {/* Header + controls */}
      <div className="card p-5 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <h2 className="panel-title">
              <GitCommit className="h-4 w-4 text-primary" aria-hidden="true" />
              Git History &amp; Churn Analysis
            </h2>
            <p className="text-xs text-text-muted font-sans mt-1">
              Identify hotspot files, author ownership risk, and commit activity trends.
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <label htmlFor="since-days" className="text-xs text-text-muted font-sans sr-only">
              History window
            </label>
            <select
              id="since-days"
              value={sinceDays}
              onChange={(e) => setSinceDays(Number(e.target.value))}
              className="input text-xs py-1.5 pr-6"
              disabled={loading}
            >
              <option value={90}>Last 90 days</option>
              <option value={180}>Last 180 days</option>
              <option value={365}>Last 1 year</option>
              <option value={730}>Last 2 years</option>
            </select>
            <Button
              onClick={runAnalysis}
              disabled={loading}
              className="shrink-0"
            >
              {loading ? (
                <><RefreshCw className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> Analyzing…</>
              ) : summary ? (
                <><RefreshCw className="h-3.5 w-3.5" aria-hidden="true" /> Re-analyze</>
              ) : (
                'Analyze History'
              )}
            </Button>
          </div>
        </div>

        {/* Progress bar */}
        {loading && (
          <div className="space-y-2" role="status" aria-live="polite">
            <div className="h-1 rounded-full bg-border overflow-hidden">
              <div className="h-full bg-primary rounded-full animate-pulse w-2/3" />
            </div>
            <p className="text-xs text-text-muted font-mono">{progress}</p>
          </div>
        )}

        {/* Error */}
        {error && (
          <div role="alert" className="text-xs text-danger bg-danger/10 border border-danger/30 p-3 rounded-lg font-sans">
            {error}
          </div>
        )}

        {/* Warning (shallow clone etc.) */}
        {summary?.warning && (
          <div role="status" className="text-xs text-orange-400 bg-orange-500/10 border border-orange-500/20 p-3 rounded-lg flex items-start gap-2">
            <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5" aria-hidden="true" />
            <span>{summary.warning}</span>
          </div>
        )}
      </div>

      {/* Loading skeleton */}
      {loading && !summary && (
        <SkeletonGroup label="Loading churn analysis">
          <div className="space-y-3">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {[0, 1, 2, 3].map((i) => <SkeletonCard key={i} />)}
            </div>
            <SkeletonCard />
            <SkeletonCard />
          </div>
        </SkeletonGroup>
      )}

      {/* Empty state */}
      {!loading && !summary && !error && (
        <EmptyState
          icon={<GitCommit className="h-6 w-6" aria-hidden="true" />}
          title="No churn data yet"
          description="Click 'Analyze History' to mine the git log and identify hotspot files."
        />
      )}

      {/* Results */}
      {summary && !loading && (
        <div className="space-y-5 fade-up">
          {/* KPI strip */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <MetricCard
              tone="primary"
              icon={<GitCommit className="h-4 w-4" />}
              label="Commits Mined"
              value={summary.total_commits.toLocaleString()}
              hint={`last ${summary.since_days} days`}
            />
            <MetricCard
              tone="warn"
              icon={<Flame className="h-4 w-4" />}
              label="Files Tracked"
              value={summary.total_files.toLocaleString()}
              hint="in history window"
            />
            <MetricCard
              tone="danger"
              icon={<TrendingUp className="h-4 w-4" />}
              label="Hotspots"
              value={summary.hotspots.length}
              hint="high-churn + central"
            />
            <MetricCard
              tone="info"
              icon={<User className="h-4 w-4" />}
              label="Bus Factor Files"
              value={summary.hotspots.filter((h) => h.bus_factor_risk).length}
              hint="single-owner risk"
            />
          </div>

          {/* View switcher */}
          <div className="card p-1 flex gap-1" role="tablist" aria-label="Churn views">
            {(['hotspots', 'timeline', 'authors'] as const).map((v) => (
              <button
                key={v}
                role="tab"
                aria-selected={activeView === v}
                onClick={() => setActiveView(v)}
                className={`flex-1 text-xs font-medium px-3 py-2 rounded-md transition-colors capitalize
                  focus-visible:outline-none focus-visible:shadow-ring
                  ${activeView === v
                    ? 'bg-primary text-white'
                    : 'text-text-muted hover:text-text hover:bg-surface'}`}
              >
                {v === 'hotspots' ? '🔥 Hotspots'
                  : v === 'timeline' ? '📅 Timeline'
                  : '👤 Authors'}
              </button>
            ))}
          </div>

          {/* Hotspots view */}
          {activeView === 'hotspots' && (
            <div className="card p-5 space-y-3" role="tabpanel">
              <div className="flex items-center justify-between">
                <h3 className="panel-title">
                  <Flame className="h-4 w-4 text-primary" /> Top Hotspot Files
                </h3>
                <span className="text-[10px] text-text-muted font-mono">
                  churn × (1 + centrality)
                </span>
              </div>
              {summary.hotspots.length === 0 ? (
                <EmptyState compact icon={<Flame className="h-5 w-5" aria-hidden="true" />} title="No hotspots detected" description="All files have low churn." />
              ) : (
                <div className="space-y-2">
                  {summary.hotspots.map((h, i) => (
                    <HotspotRow key={h.file_path} h={h} rank={i + 1} />
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Timeline view */}
          {activeView === 'timeline' && (
            <div className="card p-5 space-y-4" role="tabpanel">
              <h3 className="panel-title">
                <Calendar className="h-4 w-4 text-primary" /> Weekly Commit Activity
              </h3>
              {summary.timeline.length === 0 ? (
                <EmptyState compact icon={<Calendar className="h-5 w-5" aria-hidden="true" />} title="No timeline data" description="No weekly commit data found." />
              ) : (
                <>
                  <TimelineChart entries={summary.timeline} />
                  <div className="max-h-72 overflow-y-auto space-y-1 border-t border-border pt-3">
                    {[...summary.timeline].reverse().slice(0, 20).map((entry) => (
                      <div
                        key={entry.week}
                        className="flex items-center gap-3 text-xs font-mono py-1 border-b border-border/40 last:border-0"
                      >
                        <span className="text-text-muted w-24 shrink-0">{entry.week}</span>
                        <Badge tone={entry.commit_count > 10 ? 'danger' : entry.commit_count > 3 ? 'warn' : 'primary'}>
                          {entry.commit_count} commits
                        </Badge>
                        <span className="text-text-muted">{entry.files_changed} files</span>
                        <span className="text-text-muted hidden sm:block">
                          {entry.authors.length} author{entry.authors.length !== 1 ? 's' : ''}
                        </span>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          )}

          {/* Authors view */}
          {activeView === 'authors' && (
            <div className="card p-5 space-y-3" role="tabpanel">
              <h3 className="panel-title">
                <User className="h-4 w-4 text-primary" /> Author Ownership
              </h3>
              {summary.author_ownership.length === 0 ? (
                <EmptyState compact icon={<User className="h-5 w-5" aria-hidden="true" />} title="No ownership data" description="Author data unavailable." />
              ) : (
                <div className="max-h-96 overflow-y-auto space-y-2">
                  {summary.author_ownership.slice(0, 30).map((ao) => (
                    <div key={ao.file_path} className="border border-border rounded-lg px-4 py-3 space-y-2">
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-xs font-mono text-text truncate">{shortPath(ao.file_path)}</p>
                        {ao.ownership_pct > 80 && (
                          <Badge tone="warn">
                            <AlertTriangle className="h-3 w-3" /> bus risk
                          </Badge>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        <div className="flex-1 h-1.5 rounded-full bg-border overflow-hidden">
                          <div
                            className={`h-full rounded-full ${ao.ownership_pct > 80 ? 'bg-orange-500' : 'bg-primary'}`}
                            style={{ width: `${ao.ownership_pct}%` }}
                          />
                        </div>
                        <span className="text-[11px] font-mono text-text-muted shrink-0 w-12 text-right">
                          {ao.ownership_pct.toFixed(0)} %
                        </span>
                      </div>
                      <p className="text-[11px] text-text-muted font-mono">{ao.primary_author}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Generated at footer */}
          <p className="text-[10px] text-text-muted font-mono text-right flex items-center justify-end gap-1.5">
            <Clock className="h-3 w-3" />
            Generated {formatDate(summary.generated_at)}
          </p>
        </div>
      )}
    </div>
  );
};

export default GitHistoryAnalyzer;
