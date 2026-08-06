/**
 * APISurfaceAnalyzer — API Surface Intelligence tab component.
 *
 * Integrates into AnalysisDashboard as a new "API Surface" tab.
 * Reuses the full existing design system (Card, Badge, MetricCard,
 * EmptyState, Skeleton) with no new UI primitives.
 *
 * Views:
 *   📋 Overview  — KPI strip + top public symbols table
 *   🌐 Public    — full public API table with search + kind filter
 *   🔒 Internal  — internal symbols table
 *   ⚠️  Issues    — deprecated + orphaned APIs + breaking changes
 *   🛣️  Routes    — HTTP route table
 */

import React, { useState, useCallback, useEffect, useRef } from 'react';
import { apiUrl, extractErrorMessage } from '../../lib/api';
import { Button } from '../ui/Button';
import { Badge } from '../ui/Badge';
import { MetricCard } from '../ui/MetricCard';
import { EmptyState } from '../ui/EmptyState';
import { SkeletonCard, SkeletonGroup, Skeleton } from '../ui/Skeleton';
import {
  Globe, Lock, AlertTriangle, Route, RefreshCw,
  Search, X, ChevronDown, ChevronUp, Zap,
  Shield, BookOpen, Info, CheckCircle2,
} from 'lucide-react';

// ── Types ─────────────────────────────────────────────────────────────────

interface ClassifiedSymbol {
  name: string;
  qualified: string;
  symbol_type: string;
  file_path: string;
  line_number: number;
  language: string;
  parent_class: string | null;
  visibility: string;
  api_kind: string;
  status: string;
  confidence: number;
  classification_reason: string;
  param_count: number;
  is_async: boolean;
  decorators: string[];
  fan_in: number;
  is_orphan: boolean;
}

interface APISurfaceStats {
  total_symbols: number;
  public_count: number;
  internal_count: number;
  private_count: number;
  unknown_count: number;
  deprecated_count: number;
  experimental_count: number;
  route_count: number;
  entry_point_count: number;
  orphan_public_count: number;
  by_language: Record<string, number>;
}

interface BreakingChange {
  kind: string;
  symbol_name: string;
  file_path: string;
  before_param_count: number | null;
  after_param_count: number | null;
  severity: string;
  description: string;
}

interface Props { repoName: string; }
type ViewId = 'overview' | 'public' | 'internal' | 'issues' | 'routes';

// ── Helpers ────────────────────────────────────────────────────────────────

function visibilityTone(v: string): 'success' | 'info' | 'warn' | 'primary' {
  if (v === 'public')   return 'success';
  if (v === 'internal') return 'info';
  if (v === 'private')  return 'warn';
  return 'primary';
}

function statusTone(s: string): 'danger' | 'warn' | 'success' | 'primary' {
  if (s === 'deprecated')   return 'danger';
  if (s === 'experimental') return 'warn';
  if (s === 'stable')       return 'success';
  return 'primary';
}

function kindLabel(k: string): string {
  const labels: Record<string, string> = {
    route: 'Route', exported: 'Export', cli_entry: 'CLI',
    main_entry: 'Entry', public_class: 'Class',
    public_function: 'Function', public_method: 'Method',
    interface: 'Interface', enum_type: 'Enum',
    internal_helper: 'Helper', unknown: '?',
  };
  return labels[k] ?? k;
}

function shortPath(fp: string, max = 40): string {
  if (fp.length <= max) return fp;
  const parts = fp.replace(/\\/g, '/').split('/');
  return parts.length > 2 ? `…/${parts.slice(-2).join('/')}` : fp;
}

function severityTone(s: string): 'danger' | 'warn' | 'success' {
  if (s === 'high')   return 'danger';
  if (s === 'medium') return 'warn';
  return 'success';
}

// ── Symbol row (expandable) ────────────────────────────────────────────────

const SymbolRow: React.FC<{ sym: ClassifiedSymbol }> = ({ sym }) => {
  const [open, setOpen] = useState(false);
  return (
    <div className="border border-border rounded-lg overflow-hidden text-xs">
      <button
        type="button"
        onClick={() => setOpen(p => !p)}
        className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-surface/40
                   transition-colors text-left focus-visible:outline-none focus-visible:shadow-ring"
        aria-expanded={open}
      >
        <span className="font-mono text-text font-medium truncate flex-1 min-w-0">
          {sym.is_async && <span className="text-blue-400 mr-1">async</span>}
          {sym.qualified}
        </span>
        <Badge tone={visibilityTone(sym.visibility)} className="shrink-0">
          {sym.visibility}
        </Badge>
        <Badge tone="primary" className="shrink-0">{kindLabel(sym.api_kind)}</Badge>
        {sym.status !== 'stable' && sym.status !== 'unknown' && (
          <Badge tone={statusTone(sym.status)} className="shrink-0">{sym.status}</Badge>
        )}
        {sym.is_orphan && (
          <Badge tone="warn" className="shrink-0">orphan</Badge>
        )}
        {open
          ? <ChevronUp className="h-3.5 w-3.5 text-text-muted shrink-0" />
          : <ChevronDown className="h-3.5 w-3.5 text-text-muted shrink-0" />}
      </button>

      {open && (
        <div className="px-4 pb-4 pt-1 border-t border-border bg-canvas/40 space-y-3 fade-up">
          <p className="font-mono text-text-muted break-all">{sym.file_path}:{sym.line_number}</p>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div>
              <p className="text-text-muted text-[10px] uppercase tracking-wide">Language</p>
              <p className="font-mono text-text">{sym.language}</p>
            </div>
            <div>
              <p className="text-text-muted text-[10px] uppercase tracking-wide">Type</p>
              <p className="font-mono text-text">{sym.symbol_type}</p>
            </div>
            <div>
              <p className="text-text-muted text-[10px] uppercase tracking-wide">Params</p>
              <p className="font-mono text-text">{sym.param_count}</p>
            </div>
            <div>
              <p className="text-text-muted text-[10px] uppercase tracking-wide">Fan-in</p>
              <p className="font-mono text-text">{sym.fan_in}</p>
            </div>
          </div>

          <div className="space-y-1">
            <p className="text-text-muted text-[10px] uppercase tracking-wide">Classification</p>
            <p className="text-text-muted leading-relaxed">{sym.classification_reason}</p>
          </div>

          {sym.decorators.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {sym.decorators.map((d, i) => (
                <span key={i} className="font-mono text-[10px] bg-canvas border border-border/60 px-2 py-0.5 rounded text-primary">
                  {d}
                </span>
              ))}
            </div>
          )}

          <p className="text-[10px] text-text-muted">
            Confidence: {Math.round(sym.confidence * 100)}%
          </p>
        </div>
      )}
    </div>
  );
};

// ── Breaking change row ────────────────────────────────────────────────────

const BreakingRow: React.FC<{ bc: BreakingChange }> = ({ bc }) => (
  <div className="border border-border rounded-lg px-4 py-3 space-y-2 text-xs">
    <div className="flex items-center gap-2 flex-wrap">
      <Badge tone={severityTone(bc.severity)}>{bc.severity.toUpperCase()}</Badge>
      <span className="font-mono text-text font-medium">{bc.symbol_name}</span>
      <Badge tone="primary">{bc.kind.replace(/_/g, ' ')}</Badge>
    </div>
    <p className="text-text-muted font-sans leading-relaxed">{bc.description}</p>
    {bc.before_param_count !== null && (
      <p className="font-mono text-[10px] text-text-muted">
        params: {bc.before_param_count} → {bc.after_param_count ?? '?'}
      </p>
    )}
  </div>
);

// ── Symbol table with search ───────────────────────────────────────────────

const SymbolTable: React.FC<{
  symbols: ClassifiedSymbol[];
  placeholder?: string;
  emptyTitle?: string;
  emptyDesc?: string;
}> = ({ symbols, placeholder = 'Search symbols…', emptyTitle = 'No symbols', emptyDesc = '' }) => {
  const [query, setQuery] = useState('');
  const filtered = query
    ? symbols.filter(s =>
        s.name.toLowerCase().includes(query.toLowerCase()) ||
        s.file_path.toLowerCase().includes(query.toLowerCase())
      )
    : symbols;

  return (
    <div className="space-y-3">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-text-muted pointer-events-none" />
        <input
          type="search"
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder={placeholder}
          className="input pl-9 pr-9 text-xs w-full"
          aria-label={placeholder}
        />
        {query && (
          <button onClick={() => setQuery('')}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text"
            aria-label="Clear">
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {filtered.length === 0 ? (
        <EmptyState compact
          icon={<Info className="h-5 w-5" aria-hidden="true" />}
          title={query ? `No symbols matching "${query}"` : emptyTitle}
          description={emptyDesc}
        />
      ) : (
        <div className="space-y-2">
          {filtered.slice(0, 100).map(s => <SymbolRow key={`${s.file_path}::${s.qualified}`} sym={s} />)}
          {filtered.length > 100 && (
            <p className="text-[10px] text-text-muted font-mono text-center py-2">
              Showing 100 of {filtered.length} — refine your search to see more
            </p>
          )}
        </div>
      )}
    </div>
  );
};

// ── Main component ─────────────────────────────────────────────────────────

export const APISurfaceAnalyzer: React.FC<Props> = ({ repoName }) => {
  const [owner, repoSlug] = repoName.split('/');

  // Build
  const [building, setBuilding]       = useState(false);
  const [buildProgress, setBuildProgress] = useState('');
  const [buildError, setBuildError]   = useState<string | null>(null);

  // Data
  const [stats, setStats]             = useState<APISurfaceStats | null>(null);
  const [publicSyms, setPublicSyms]   = useState<ClassifiedSymbol[]>([]);
  const [internalSyms, setInternalSyms] = useState<ClassifiedSymbol[]>([]);
  const [deprecatedSyms, setDeprecatedSyms] = useState<ClassifiedSymbol[]>([]);
  const [orphanSyms, setOrphanSyms]   = useState<ClassifiedSymbol[]>([]);
  const [routeSyms, setRouteSyms]     = useState<ClassifiedSymbol[]>([]);

  const [loading, setLoading]         = useState(false);
  const [loadError, setLoadError]     = useState<string | null>(null);

  const [activeView, setActiveView]   = useState<ViewId>('overview');

  // ── Auto-load on mount ───────────────────────────────────────────────
  useEffect(() => { loadAll(); }, [repoName]);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    setStats(null);
    setPublicSyms([]);
    setInternalSyms([]);
    setDeprecatedSyms([]);
    setOrphanSyms([]);
    setRouteSyms([]);
    try {
      const [statsRes, pubRes, intRes, depRes, breakRes, routeRes] = await Promise.all([
        fetch(apiUrl(`/api/v1/api-surface/${owner}/${repoSlug}/stats`)),
        fetch(apiUrl(`/api/v1/api-surface/${owner}/${repoSlug}/public`)),
        fetch(apiUrl(`/api/v1/api-surface/${owner}/${repoSlug}/internal`)),
        fetch(apiUrl(`/api/v1/api-surface/${owner}/${repoSlug}/deprecated`)),
        fetch(apiUrl(`/api/v1/api-surface/${owner}/${repoSlug}/breaking`)),
        fetch(apiUrl(`/api/v1/api-surface/${owner}/${repoSlug}/public?kind=route&limit=200`)),
      ]);

      if (statsRes.status === 404) { setLoading(false); return; } // not built yet
      if (!statsRes.ok) throw new Error(`HTTP ${statsRes.status}`);

      const [statsData, pubData, intData, depData, breakData, routeData] = await Promise.all([
        statsRes.json(), pubRes.json(), intRes.json(),
        depRes.json(), breakRes.json(), routeRes.json(),
      ]);

      setStats(statsData);
      setPublicSyms(pubData.symbols ?? []);
      setInternalSyms(intData.symbols ?? []);
      setDeprecatedSyms(depData.symbols ?? []);
      setOrphanSyms(breakData.orphans ?? []);
      setRouteSyms(routeData.symbols ?? []);
    } catch (err: any) {
      setLoadError(extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [owner, repoSlug]);

  // ── Build handler ────────────────────────────────────────────────────
  const handleBuild = useCallback(async () => {
    setBuilding(true);
    setBuildError(null);
    setBuildProgress('Starting…');
    setStats(null);

    try {
      const res = await fetch(apiUrl('/api/v1/api-surface/build'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ repo: repoName }),
      });

      if (!res.body) throw new Error('No response body.');
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
            const ev = JSON.parse(line);
            if (ev.status === 'error') { setBuildError(ev.message); setBuilding(false); return; }
            if (ev.status === 'done')  { setBuilding(false); loadAll(); return; }
            if (ev.message)             setBuildProgress(ev.message);
          } catch { /* non-JSON */ }
        }
      }
    } catch (err: any) {
      setBuildError(extractErrorMessage(err));
    } finally {
      setBuilding(false);
    }
  }, [repoName, loadAll]);

  // ── Render ───────────────────────────────────────────────────────────
  const notBuilt = !loading && !stats && !loadError;
  const hasData  = !!stats;

  return (
    <div className="space-y-5 fade-up">
      {/* ── Header ──────────────────────────────────────────────────── */}
      <div className="card p-5 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <h2 className="panel-title">
              <Globe className="h-4 w-4 text-primary" aria-hidden="true" />
              API Surface Intelligence
            </h2>
            <p className="text-xs text-text-muted font-sans mt-1">
              Discover and classify the public API surface. Detect deprecated, orphaned, and breaking APIs.
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {hasData && (
              <button onClick={loadAll} aria-label="Refresh" className="btn-ghost text-xs">
                <RefreshCw className="h-3.5 w-3.5" /> Refresh
              </button>
            )}
            <Button onClick={handleBuild} disabled={building}>
              {building
                ? <><RefreshCw className="h-3.5 w-3.5 animate-spin" /> Analyzing…</>
                : hasData ? <><RefreshCw className="h-3.5 w-3.5" /> Rebuild</> : 'Analyze API Surface'}
            </Button>
          </div>
        </div>

        {building && (
          <div className="space-y-1.5" role="status" aria-live="polite">
            <div className="h-1 rounded-full bg-border overflow-hidden">
              <div className="h-full bg-primary rounded-full animate-pulse w-2/3" />
            </div>
            <p className="text-xs font-mono text-text-muted">{buildProgress}</p>
          </div>
        )}
        {buildError && (
          <div role="alert" className="text-xs text-danger bg-danger/10 border border-danger/30 p-3 rounded-lg font-sans">
            {buildError}
          </div>
        )}
      </div>

      {/* ── Loading ──────────────────────────────────────────────────── */}
      {loading && !hasData && (
        <SkeletonGroup label="Loading API surface">
          <div className="space-y-3">
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              {[0,1,2,3,4].map(i => <SkeletonCard key={i} />)}
            </div>
            <SkeletonCard /><SkeletonCard />
          </div>
        </SkeletonGroup>
      )}

      {/* ── Not built ────────────────────────────────────────────────── */}
      {notBuilt && !building && (
        <EmptyState
          icon={<Globe className="h-6 w-6" aria-hidden="true" />}
          title="API surface not analyzed yet"
          description="Click 'Analyze API Surface' to classify public APIs, detect routes, and find deprecated symbols."
          action={<Button onClick={handleBuild}>Analyze API Surface</Button>}
        />
      )}

      {/* ── Error ────────────────────────────────────────────────────── */}
      {loadError && !loading && (
        <div role="alert" className="text-xs text-danger bg-danger/10 border border-danger/30 p-3 rounded-lg font-sans">
          {loadError}
        </div>
      )}

      {/* ── Main content ─────────────────────────────────────────────── */}
      {hasData && !loading && (
        <div className="space-y-4 fade-up">
          {/* View switcher */}
          <div className="card p-1 flex flex-wrap gap-1" role="tablist" aria-label="API surface views">
            {([
              ['overview', '📋 Overview'],
              ['public',   '🌐 Public'],
              ['internal', '🔒 Internal'],
              ['issues',   '⚠️ Issues'],
              ['routes',   '🛣️ Routes'],
            ] as [ViewId, string][]).map(([v, label]) => (
              <button key={v} role="tab" aria-selected={activeView === v}
                onClick={() => setActiveView(v)}
                className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors
                  focus-visible:outline-none focus-visible:shadow-ring
                  ${activeView === v ? 'bg-primary text-white' : 'text-text-muted hover:text-text hover:bg-surface'}`}>
                {label}
              </button>
            ))}
          </div>

          {/* ── Overview ──────────────────────────────────────────── */}
          {activeView === 'overview' && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
                <MetricCard tone="success" icon={<Globe className="h-4 w-4" />}
                  label="Public APIs" value={stats.public_count} hint="exported symbols" />
                <MetricCard tone="info" icon={<Lock className="h-4 w-4" />}
                  label="Internal" value={stats.internal_count} hint="package-private" />
                <MetricCard tone="danger" icon={<AlertTriangle className="h-4 w-4" />}
                  label="Deprecated" value={stats.deprecated_count} hint="marked deprecated" />
                <MetricCard tone="warn" icon={<Zap className="h-4 w-4" />}
                  label="Orphaned" value={stats.orphan_public_count} hint="public, never called" />
                <MetricCard tone="primary" icon={<Route className="h-4 w-4" />}
                  label="Routes" value={stats.route_count} hint="HTTP endpoints" />
              </div>

              {/* Language breakdown */}
              {Object.keys(stats.by_language).length > 0 && (
                <div className="card p-4 space-y-3">
                  <h3 className="panel-title"><BookOpen className="h-3.5 w-3.5 text-primary" /> By Language</h3>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(stats.by_language).map(([lang, count]) => (
                      <div key={lang} className="flex items-center gap-2 bg-canvas border border-border rounded-md px-3 py-1.5 text-xs">
                        <span className="font-mono text-text">{lang}</span>
                        <Badge tone="primary">{count}</Badge>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Top public APIs preview */}
              <div className="card p-4 space-y-3">
                <h3 className="panel-title"><CheckCircle2 className="h-3.5 w-3.5 text-primary" /> Top Public APIs</h3>
                <SymbolTable
                  symbols={publicSyms.slice(0, 10)}
                  placeholder="Search public APIs…"
                  emptyTitle="No public symbols found"
                />
              </div>
            </div>
          )}

          {/* ── Public ───────────────────────────────────────────── */}
          {activeView === 'public' && (
            <div className="card p-5 space-y-4">
              <h3 className="panel-title">
                <Globe className="h-4 w-4 text-primary" /> Public API ({stats.public_count})
              </h3>
              <SymbolTable symbols={publicSyms} placeholder="Search public symbols…"
                emptyTitle="No public symbols" emptyDesc="All symbols are internal or private." />
            </div>
          )}

          {/* ── Internal ─────────────────────────────────────────── */}
          {activeView === 'internal' && (
            <div className="card p-5 space-y-4">
              <h3 className="panel-title">
                <Lock className="h-4 w-4 text-primary" /> Internal Symbols ({stats.internal_count})
              </h3>
              <SymbolTable symbols={internalSyms} placeholder="Search internal symbols…"
                emptyTitle="No internal symbols" />
            </div>
          )}

          {/* ── Issues ───────────────────────────────────────────── */}
          {activeView === 'issues' && (
            <div className="space-y-4">
              {/* Deprecated */}
              <div className="card p-5 space-y-3">
                <h3 className="panel-title">
                  <AlertTriangle className="h-4 w-4 text-danger" /> Deprecated APIs ({deprecatedSyms.length})
                </h3>
                {deprecatedSyms.length === 0 ? (
                  <EmptyState compact icon={<CheckCircle2 className="h-5 w-5" aria-hidden="true" />}
                    title="No deprecated APIs" description="All public APIs are stable." />
                ) : (
                  <div className="space-y-2">
                    {deprecatedSyms.map(s => <SymbolRow key={`${s.file_path}::${s.qualified}`} sym={s} />)}
                  </div>
                )}
              </div>

              {/* Orphaned */}
              <div className="card p-5 space-y-3">
                <h3 className="panel-title">
                  <Zap className="h-4 w-4 text-warn" /> Orphaned Public APIs ({orphanSyms.length})
                </h3>
                <p className="text-xs text-text-muted font-sans">
                  Public symbols with no callers in the call graph. May be unused or only called externally.
                </p>
                {orphanSyms.length === 0 ? (
                  <EmptyState compact icon={<CheckCircle2 className="h-5 w-5" aria-hidden="true" />}
                    title="No orphaned APIs detected"
                    description="All public APIs have at least one internal caller, or call graph is not built." />
                ) : (
                  <div className="space-y-2">
                    {orphanSyms.slice(0, 50).map(s => <SymbolRow key={`${s.file_path}::${s.qualified}`} sym={s} />)}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ── Routes ───────────────────────────────────────────── */}
          {activeView === 'routes' && (
            <div className="card p-5 space-y-4">
              <h3 className="panel-title">
                <Route className="h-4 w-4 text-primary" /> HTTP Routes ({stats.route_count})
              </h3>
              {routeSyms.length === 0 ? (
                <EmptyState compact icon={<Info className="h-5 w-5" aria-hidden="true" />}
                  title="No HTTP routes detected"
                  description="Routes are detected from FastAPI, Flask, Express decorators and patterns." />
              ) : (
                <SymbolTable symbols={routeSyms} placeholder="Search routes…" />
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default APISurfaceAnalyzer;
