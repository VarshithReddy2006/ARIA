/**
 * APISurfaceAnalyzer — API Surface Intelligence tab.
 *
 * Answers "what does this repository expose, who can use it, and what needs
 * attention?" rather than listing symbols. The hierarchy is:
 *
 *   editorial header → diagnostic strip → exposure signal → mode rail
 *   → searchable inventory → structured symbol evidence
 *
 * Every figure shown is passed through unmodified from the api-surface
 * endpoints. Derived sentences restate real counts; nothing is scored,
 * estimated or invented here.
 *
 * Views: Overview · Public · Internal · Issues · Routes
 */

import React, { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import { apiUrl, extractErrorMessage } from '../../lib/api';
import { Button } from '../ui/Button';
import { EmptyState } from '../ui/EmptyState';
import { SkeletonCard, SkeletonGroup } from '../ui/Skeleton';
import { FilePath } from '../ui/FilePath';
import { Meter } from '../ui/Meter';
import {
  Globe, Lock, AlertTriangle, Route, RefreshCw,
  Search, X, ChevronDown, Zap, Info, CheckCircle2, LayoutList, ArrowRight,
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

interface Props { repoName: string; }
type ViewId = 'overview' | 'public' | 'internal' | 'issues' | 'routes';

// ── Helpers ────────────────────────────────────────────────────────────────

/** Semantic colour per §22: emerald public, indigo internal, red deprecated,
 *  amber orphan. Internal is never red. */
const TAG_TONE: Record<string, string> = {
  public: 'text-success',
  internal: 'text-info',
  private: 'text-text-muted',
  deprecated: 'text-danger',
  experimental: 'text-warn',
  orphan: 'text-warn',
  route: 'text-primary',
};

function visibilityClass(v: string): string {
  return TAG_TONE[v] ?? 'text-text-muted';
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

/**
 * Reads an HTTP method and route path out of a decorator string such as
 * `@app.get("/items/{item_id}")`. Presentation only: when nothing matches the
 * row falls back to the symbol, so no route metadata is ever guessed.
 */
function parseRoute(decorators: string[]): { method: string; path: string } | null {
  for (const raw of decorators) {
    const m = /\.(get|post|put|patch|delete|head|options|route)\s*\(\s*['"`]([^'"`]+)['"`]/i.exec(raw);
    if (m) return { method: m[1].toUpperCase(), path: m[2] };
  }
  return null;
}

const METHOD_TONE: Record<string, string> = {
  GET: 'text-success',
  POST: 'text-primary',
  PUT: 'text-warn',
  PATCH: 'text-warn',
  DELETE: 'text-danger',
};

/** A compact uppercase mono tag. No pill, no fill. */
const Tag: React.FC<{ children: React.ReactNode; className?: string }> = ({ children, className = '' }) => (
  <span className={`font-mono text-[10px] uppercase tracking-[0.16em] shrink-0 ${className}`}>
    {children}
  </span>
);

// ── Symbol row (expandable evidence record) ────────────────────────────────

const SymbolRow: React.FC<{ sym: ClassifiedSymbol; showRoute?: boolean }> = ({
  sym,
  showRoute = false,
}) => {
  const [open, setOpen] = useState(false);
  const route = showRoute ? parseRoute(sym.decorators) : null;

  /**
   * Deep links reuse the dashboard's existing window events — the same contract
   * the graph and chat surfaces already listen for. No navigation logic here.
   */
  const openInGraph = () => {
    window.dispatchEvent(
      new CustomEvent('aria-open-graph', { detail: { path: sym.file_path } })
    );
  };
  const askAria = () => {
    window.dispatchEvent(
      new CustomEvent('aria-open-chat', {
        detail: {
          prompt: `Explain the API symbol \`${sym.qualified}\` in \`${sym.file_path}\`. What is its contract, who calls it, and is it safe to change?`,
        },
      })
    );
  };

  return (
    <div className="api-row hair-t last:border-b last:border-white/[0.055]">
      <button
        type="button"
        onClick={() => setOpen((p) => !p)}
        className="w-full flex items-start gap-4 py-3 px-1 text-left min-w-0
                   focus-visible:outline-none focus-visible:shadow-ring"
        aria-expanded={open}
      >
        <div className="min-w-0 flex-1">
          {/* Route rows lead with method + endpoint; others lead with the symbol */}
          {route ? (
            <span className="flex items-baseline gap-3 min-w-0">
              <Tag className={METHOD_TONE[route.method] ?? 'text-primary'}>{route.method}</Tag>
              <span className="font-mono text-[13px] text-text font-semibold truncate">
                {route.path}
              </span>
            </span>
          ) : (
            <span className="font-mono text-[13px] text-text font-semibold break-words">
              {sym.is_async && <span className="text-info font-normal mr-1.5">async</span>}
              {sym.qualified}
            </span>
          )}

          <span className="block mt-1 min-w-0">
            <FilePath
              path={sym.file_path}
              tone="secondary"
              size="sm"
              trailing={`:${sym.line_number}`}
            />
          </span>

          {route && (
            <span className="mono-detail block mt-1 truncate" style={{ fontSize: 10 }}>
              {sym.is_async ? 'async ' : ''}{sym.name}
            </span>
          )}
        </div>

        {/* Classification — compact, technical, no containers */}
        <span className="hidden sm:flex items-center gap-3 shrink-0 pt-0.5">
          <Tag className="text-text-subtle">{kindLabel(sym.api_kind)}</Tag>
          <Tag className={visibilityClass(sym.visibility)}>{sym.visibility}</Tag>
          {sym.status !== 'stable' && sym.status !== 'unknown' && (
            <Tag className={TAG_TONE[sym.status] ?? 'text-text-muted'}>{sym.status}</Tag>
          )}
          {sym.is_orphan && <Tag className="text-warn">orphan</Tag>}
        </span>

        <ChevronDown
          className={`h-3.5 w-3.5 shrink-0 mt-1 text-text-subtle transition-transform duration-200 ${
            open ? 'rotate-180' : ''
          }`}
          aria-hidden="true"
        />
      </button>

      {/* Mobile keeps the tags, on their own line */}
      <div className="sm:hidden flex flex-wrap items-center gap-x-3 gap-y-1 px-1 pb-2.5 -mt-1">
        <Tag className="text-text-subtle">{kindLabel(sym.api_kind)}</Tag>
        <Tag className={visibilityClass(sym.visibility)}>{sym.visibility}</Tag>
        {sym.status !== 'stable' && sym.status !== 'unknown' && (
          <Tag className={TAG_TONE[sym.status] ?? 'text-text-muted'}>{sym.status}</Tag>
        )}
        {sym.is_orphan && <Tag className="text-warn">orphan</Tag>}
      </div>

      {open && (
        <div className="api-evidence px-1 pb-5 pt-1 space-y-4">
          <div>
            <span className="mono-label block mb-2">SOURCE</span>
            <FilePath
              path={sym.file_path}
              tone="primary"
              size="sm"
              trailing={`:${sym.line_number}`}
            />
          </div>

          <dl className="grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-4 pt-4 hair-t">
            <div className="min-w-0">
              <dt className="mono-label mb-1.5">LANGUAGE</dt>
              <dd className="font-mono text-[12px] text-text truncate">{sym.language}</dd>
            </div>
            <div className="min-w-0">
              <dt className="mono-label mb-1.5">TYPE</dt>
              <dd className="font-mono text-[12px] text-text truncate">{sym.symbol_type}</dd>
            </div>
            <div className="min-w-0">
              <dt className="mono-label mb-1.5">PARAMETERS</dt>
              <dd className="font-mono text-[12px] text-text tabular-nums">{sym.param_count}</dd>
            </div>
            <div className="min-w-0">
              <dt className="mono-label mb-1.5">FAN-IN</dt>
              <dd className="font-mono text-[12px] text-text tabular-nums">{sym.fan_in}</dd>
            </div>
          </dl>

          <div className="pt-4 hair-t">
            <span className="mono-label block mb-2">CLASSIFICATION</span>
            <p className="text-[12px] text-text-muted leading-relaxed max-w-[70ch]">
              {sym.classification_reason}
            </p>
          </div>

          <div className="pt-4 hair-t">
            <span className="mono-label block mb-2">CONFIDENCE</span>
            <div className="flex items-center gap-3">
              <span className="font-mono text-[13px] text-text tabular-nums">
                {Math.round(sym.confidence * 100)}%
              </span>
              <Meter
                value={sym.confidence}
                barClassName="bg-primary"
                className="max-w-[8rem] flex-1"
              />
            </div>
          </div>

          {sym.decorators.length > 0 && (
            <div className="pt-4 hair-t min-w-0">
              <span className="mono-label block mb-2">DECORATORS</span>
              <ul className="min-w-0">
                {sym.decorators.map((d, i) => (
                  <li
                    key={i}
                    className="font-mono text-[11px] text-primary/90 py-0.5"
                    style={{ overflowWrap: 'anywhere' }}
                  >
                    {d}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Actions reuse existing dashboard navigation events */}
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2 pt-4 hair-t">
            <button type="button" onClick={openInGraph} className="api-action link-arrow">
              View in Graph
              <ArrowRight className="h-3 w-3 arrow" aria-hidden="true" />
            </button>
            <button type="button" onClick={askAria} className="api-action link-arrow">
              Ask ARIA
              <ArrowRight className="h-3 w-3 arrow" aria-hidden="true" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

// ── Inventory: header + search + rows ──────────────────────────────────────

const SymbolInventory: React.FC<{
  title: string;
  total: number;
  unit?: string;
  symbols: ClassifiedSymbol[];
  placeholder?: string;
  emptyTitle?: string;
  emptyDesc?: string;
  showRoute?: boolean;
  /** Binds the "/" shortcut used across ARIA. One inventory per view. */
  shortcut?: boolean;
  accentClass?: string;
  note?: string;
}> = ({
  title,
  total,
  unit = 'SYMBOLS',
  symbols,
  placeholder = 'Search symbols…',
  emptyTitle = 'No symbols',
  emptyDesc = '',
  showRoute = false,
  shortcut = false,
  accentClass = 'text-text',
  note,
}) => {
  const [query, setQuery] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!shortcut) return;
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
  }, [shortcut]);

  const needle = query.trim().toLowerCase();
  const filtered = useMemo(
    () =>
      needle
        ? symbols.filter(
            (s) =>
              s.name.toLowerCase().includes(needle) ||
              s.qualified.toLowerCase().includes(needle) ||
              s.file_path.toLowerCase().includes(needle)
          )
        : symbols,
    [symbols, needle]
  );

  const shown = filtered.slice(0, 100);

  return (
    <section className="min-w-0" aria-label={title}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2 pb-3 hair-b">
        <h3 className={`font-mono text-[13px] uppercase tracking-[0.16em] ${accentClass}`}>
          {title}
        </h3>
        <span className="mono-detail tabular-nums shrink-0" style={{ fontSize: 10 }}>
          {total.toLocaleString()} {unit}
        </span>
      </div>

      {note && (
        <p className="text-[12px] text-text-muted leading-relaxed mt-3 max-w-[70ch]">{note}</p>
      )}

      {/* Search — ARIA's command surface treatment */}
      <div className="relative mt-4">
        <Search
          className="absolute left-0 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-text-subtle pointer-events-none"
          aria-hidden="true"
        />
        <input
          ref={inputRef}
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={placeholder}
          aria-label={placeholder}
          className="api-search w-full bg-transparent border-0 border-b border-white/[0.07]
                     pl-6 pr-16 py-2.5 font-mono text-[12px] text-text
                     placeholder:text-text-subtle focus:outline-none focus:border-primary/60
                     transition-colors duration-200"
        />
        {query ? (
          <button
            type="button"
            onClick={() => setQuery('')}
            className="absolute right-0 top-1/2 -translate-y-1/2 text-text-subtle hover:text-text
                       transition-colors focus-visible:outline-none"
            aria-label="Clear search"
          >
            <X className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        ) : (
          shortcut && (
            <kbd
              className="absolute right-0 top-1/2 -translate-y-1/2 hidden sm:inline-flex
                         items-center justify-center h-5 w-5 border border-white/[0.09]
                         font-mono text-[10px] text-text-subtle select-none"
            >
              /
            </kbd>
          )
        )}
      </div>

      {/* Result summary — stable height so searching never shifts the list */}
      <p
        className="mono-detail mt-3 mb-1 tabular-nums"
        style={{ fontSize: 10 }}
        role="status"
        aria-live="polite"
      >
        {filtered.length === 0
          ? 'NO MATCHING SYMBOLS'
          : `SHOWING ${shown.length.toLocaleString()} OF ${filtered.length.toLocaleString()}${
              needle ? ` · FILTERED FROM ${symbols.length.toLocaleString()}` : ''
            }`}
      </p>

      {filtered.length === 0 ? (
        <div className="py-6">
          {needle ? (
            <p className="text-[12px] text-text-muted">
              No symbols match “{query}”. Try a shorter fragment or clear the search.
            </p>
          ) : (
            <EmptyState
              compact
              icon={<Info className="h-5 w-5" aria-hidden="true" />}
              title={emptyTitle}
              description={emptyDesc}
            />
          )}
        </div>
      ) : (
        <div className="min-w-0">
          {shown.map((s) => (
            <SymbolRow key={`${s.file_path}::${s.qualified}`} sym={s} showRoute={showRoute} />
          ))}
          {filtered.length > shown.length && (
            <p className="mono-detail py-4" style={{ fontSize: 10 }}>
              REFINE THE SEARCH TO REACH THE REMAINING{' '}
              {(filtered.length - shown.length).toLocaleString()}
            </p>
          )}
        </div>
      )}
    </section>
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

  // ── Auto-load on mount ───────────────────────────────────────────────
  useEffect(() => { loadAll(); }, [loadAll]);

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

  const notBuilt = !loading && !stats && !loadError;
  const hasData  = !!stats;

  /**
   * A factual restatement of the numbers already on screen — no percentages
   * beyond a direct ratio of two reported counts, and no health score.
   */
  const exposureNote = useMemo(() => {
    if (!stats) return null;
    if (stats.total_symbols === 0) {
      return 'No public or internal code symbols were detected in this repository. API surface analysis applies to repositories with supported source code files.';
    }
    const { public_count, orphan_public_count, deprecated_count, route_count } = stats;
    const parts: string[] = [];

    if (public_count > 0 && orphan_public_count > 0) {
      const share = Math.round((orphan_public_count / public_count) * 100);
      parts.push(
        `${orphan_public_count.toLocaleString()} of ${public_count.toLocaleString()} public symbols (${share}%) have no caller in the call graph`
      );
    }
    if (deprecated_count > 0) {
      parts.push(`${deprecated_count.toLocaleString()} are marked deprecated`);
    }
    if (route_count > 0) {
      parts.push(`${route_count.toLocaleString()} are reachable as HTTP endpoints`);
    }
    if (parts.length === 0) return null;
    return `${parts.join(' · ')}.`;
  }, [stats]);

  const languages = useMemo(() => {
    if (!stats) return [];
    const entries = Object.entries(stats.by_language).sort((a, b) => b[1] - a[1]);
    const max = entries.reduce((m, [, c]) => Math.max(m, c), 0) || 1;
    return entries.map(([lang, count]) => ({ lang, count, ratio: count / max }));
  }, [stats]);

  const MODES: [ViewId, string, React.ComponentType<{ className?: string }>][] = [
    ['overview', 'OVERVIEW', LayoutList],
    ['public',   'PUBLIC',   Globe],
    ['internal', 'INTERNAL', Lock],
    ['issues',   'ISSUES',   AlertTriangle],
    ['routes',   'ROUTES',   Route],
  ];

  return (
    <div className="space-y-8 fade-up min-w-0">
      {/* ── Editorial header ────────────────────────────────────────────── */}
      <header className="min-w-0">
        <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-5">
          <div className="min-w-0 max-w-2xl">
            <span className="mono-label mono-label-accent block mb-3">
              API SURFACE / PUBLIC CONTRACT
            </span>
            <h2 className="display-3 text-text">Everything the codebase exposes.</h2>
            <p className="text-[13px] text-text-muted leading-relaxed mt-3.5 max-w-xl">
              Map public symbols, routes, deprecations, and orphaned interfaces before they become
              hidden maintenance costs.
            </p>
          </div>

          {/* Controls: rebuild primary, refresh secondary */}
          <div className="flex items-center gap-5 shrink-0">
            {hasData && (
              <button
                type="button"
                onClick={loadAll}
                className="flex items-center gap-2 mono-label hover:text-text transition-colors
                           focus-visible:outline-none"
              >
                <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
                REFRESH
              </button>
            )}
            <button
              type="button"
              onClick={handleBuild}
              disabled={building}
              className="action-chip disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {building ? (
                <>
                  <RefreshCw className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                  Analyzing
                </>
              ) : hasData ? (
                <>
                  <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
                  Rebuild
                </>
              ) : (
                <>
                  Analyze API Surface
                  <ArrowRight className="h-3 w-3" aria-hidden="true" />
                </>
              )}
            </button>
          </div>
        </div>

        {building && (
          <div className="mt-6 space-y-2" role="status" aria-live="polite">
            <div className="h-px w-full bg-white/[0.07] overflow-hidden">
              <div className="h-full w-1/3 bg-primary animate-pulse" />
            </div>
            <p className="mono-detail" style={{ fontSize: 10 }}>{buildProgress}</p>
          </div>
        )}
        {buildError && (
          <div
            role="alert"
            className="mt-5 flex items-start gap-3 border border-danger/25 bg-danger/[0.04] p-4"
          >
            <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5 text-danger" aria-hidden="true" />
            <p className="text-[12px] text-text-muted leading-relaxed">{buildError}</p>
          </div>
        )}
      </header>

      {/* ── Loading ──────────────────────────────────────────────────────── */}
      {loading && !hasData && (
        <SkeletonGroup label="Loading API surface">
          <div className="space-y-3">
            <SkeletonCard />
            <SkeletonCard />
          </div>
        </SkeletonGroup>
      )}

      {/* ── Not built ────────────────────────────────────────────────────── */}
      {notBuilt && !building && (
        <EmptyState
          icon={<Globe className="h-6 w-6" aria-hidden="true" />}
          title="API surface not analyzed yet"
          description="Run the analyzer to classify public APIs, detect routes, and find deprecated symbols."
          action={<Button onClick={handleBuild}>Analyze API Surface</Button>}
        />
      )}

      {/* ── Error ────────────────────────────────────────────────────────── */}
      {loadError && !loading && (
        <div
          role="alert"
          className="flex items-start gap-3 border border-danger/25 bg-danger/[0.04] p-4"
        >
          <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5 text-danger" aria-hidden="true" />
          <p className="text-[12px] text-text-muted leading-relaxed">{loadError}</p>
        </div>
      )}

      {/* ── Surface ──────────────────────────────────────────────────────── */}
      {hasData && !loading && (
        <div className="space-y-8 min-w-0">
          {/* Diagnostic strip */}
          <dl className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 border-t border-white/[0.055]">
            {[
              { k: 'PUBLIC APIs', v: stats.public_count, hint: 'exported symbols', tone: 'text-success' },
              { k: 'INTERNAL', v: stats.internal_count, hint: 'package-private', tone: 'text-info' },
              { k: 'DEPRECATED', v: stats.deprecated_count, hint: 'marked deprecated', tone: 'text-danger' },
              { k: 'ORPHANED', v: stats.orphan_public_count, hint: 'public, never called', tone: 'text-warn' },
              { k: 'ROUTES', v: stats.route_count, hint: 'HTTP endpoints', tone: 'text-primary' },
            ].map((m, i) => (
              <div
                key={m.k}
                className={`min-w-0 px-4 sm:px-5 py-5 border-b border-white/[0.055]
                            border-l border-white/[0.055]
                            [&:nth-child(2n+1)]:border-l-0
                            md:[&:nth-child(2n+1)]:border-l md:[&:nth-child(3n+1)]:border-l-0
                            lg:[&:nth-child(3n+1)]:border-l lg:[&:nth-child(5n+1)]:border-l-0`}
                style={{ ['--reveal-delay' as string]: `${i * 60}ms` }}
              >
                <dt className="mono-label mb-2.5">{m.k}</dt>
                <dd>
                  <span className={`readout-value block ${m.tone}`}>
                    {m.v.toLocaleString()}
                  </span>
                  <span className="mono-detail block mt-2 truncate" style={{ fontSize: 10 }}>
                    {m.hint}
                  </span>
                </dd>
              </div>
            ))}
          </dl>

          {/* Exposure signal — a restatement of the counts above */}
          {exposureNote && (
            <div className="min-w-0">
              <span className="mono-label block mb-3">PUBLIC EXPOSURE</span>
              <p className="text-[13px] sm:text-sm text-text-muted leading-relaxed max-w-[76ch]">
                {exposureNote}
              </p>
            </div>
          )}

          {/* Mode rail */}
          <div
            className="inner-scroll-x relative flex items-stretch gap-6 border-y border-white/[0.055]"
            role="tablist"
            aria-label="API surface views"
          >
            {MODES.map(([v, label, Icon]) => {
              const isActive = activeView === v;
              return (
                <button
                  key={v}
                  role="tab"
                  type="button"
                  aria-selected={isActive}
                  onClick={() => setActiveView(v)}
                  className={`group relative shrink-0 flex items-center gap-2 py-3
                              font-mono text-[11px] uppercase tracking-[0.14em] whitespace-nowrap
                              transition-colors duration-200 focus-visible:outline-none ${
                                isActive ? 'text-text' : 'text-text-subtle hover:text-text-muted'
                              }`}
                >
                  <Icon
                    className={`h-3.5 w-3.5 shrink-0 ${
                      isActive ? 'text-primary' : 'text-text-subtle group-hover:text-text-muted'
                    }`}
                    aria-hidden="true"
                  />
                  {label}
                  <span
                    aria-hidden="true"
                    className="absolute -bottom-px left-0 right-0 h-px origin-left bg-primary"
                    style={{
                      transform: `scaleX(${isActive ? 1 : 0})`,
                      transition: 'transform 240ms cubic-bezier(0.16,1,0.3,1)',
                    }}
                  />
                </button>
              );
            })}
          </div>

          {/* ── Overview ───────────────────────────────────────────────── */}
          {activeView === 'overview' && (
            <div className="space-y-9 panel-enter min-w-0">
              {languages.length > 0 && (
                <section aria-label="Symbols by language" className="min-w-0">
                  <div className="flex items-baseline justify-between gap-4 pb-3 hair-b">
                    <span className="mono-label">LANGUAGES</span>
                    <span className="mono-detail tabular-nums shrink-0" style={{ fontSize: 10 }}>
                      {languages.length}
                    </span>
                  </div>
                  <ul className="mt-1 min-w-0">
                    {languages.map(({ lang, count, ratio }, i) => (
                      <li key={lang} className="flex items-center gap-4 py-2.5 hair-t min-w-0">
                        <span className="font-mono text-[12px] text-text uppercase tracking-[0.1em] w-28 shrink-0 truncate">
                          {lang}
                        </span>
                        <Meter
                          value={ratio}
                          barClassName="bg-primary/60"
                          className="flex-1"
                          delay={i * 70}
                        />
                        <span className="font-mono text-[12px] text-text-muted tabular-nums w-16 text-right shrink-0">
                          {count.toLocaleString()}
                        </span>
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              <SymbolInventory
                title="TOP PUBLIC APIs"
                total={stats.public_count}
                unit="EXPORTED SYMBOLS"
                symbols={publicSyms.slice(0, 10)}
                placeholder="Search public APIs…"
                emptyTitle="No public symbols found"
                accentClass="text-success"
              />
            </div>
          )}

          {/* ── Public ─────────────────────────────────────────────────── */}
          {activeView === 'public' && (
            <div className="panel-enter min-w-0">
              <SymbolInventory
                title="PUBLIC API"
                total={stats.public_count}
                unit="EXPORTED SYMBOLS"
                symbols={publicSyms}
                placeholder="Search public symbols…"
                emptyTitle="No public symbols"
                emptyDesc="All symbols are internal or private."
                shortcut
                accentClass="text-success"
              />
            </div>
          )}

          {/* ── Internal ───────────────────────────────────────────────── */}
          {activeView === 'internal' && (
            <div className="panel-enter min-w-0">
              <SymbolInventory
                title="INTERNAL SURFACE"
                total={stats.internal_count}
                unit="PACKAGE-PRIVATE SYMBOLS"
                symbols={internalSyms}
                placeholder="Search internal symbols…"
                emptyTitle="No internal symbols"
                shortcut
                accentClass="text-info"
                note="Not part of the published contract — these symbols are reachable within the package but are not intended for external consumers."
              />
            </div>
          )}

          {/* ── Issues ─────────────────────────────────────────────────── */}
          {activeView === 'issues' && (
            <div className="space-y-10 panel-enter min-w-0">
              <SymbolInventory
                title="DEPRECATED"
                total={deprecatedSyms.length}
                unit="SYMBOLS"
                symbols={deprecatedSyms}
                placeholder="Search deprecated symbols…"
                emptyTitle="No deprecated APIs"
                emptyDesc="All public APIs are stable."
                shortcut
                accentClass="text-danger"
              />

              <SymbolInventory
                title="ORPHANED"
                total={orphanSyms.length}
                unit="PUBLIC SYMBOLS"
                symbols={orphanSyms.slice(0, 50)}
                placeholder="Search orphaned symbols…"
                emptyTitle="No orphaned APIs detected"
                emptyDesc="All public APIs have at least one internal caller, or the call graph is not built."
                accentClass="text-warn"
                note="Public symbols with no callers in the call graph. They may be unused, or called only from outside the repository."
              />
            </div>
          )}

          {/* ── Routes ─────────────────────────────────────────────────── */}
          {activeView === 'routes' && (
            <div className="panel-enter min-w-0">
              {routeSyms.length === 0 ? (
                <div>
                  <div className="flex items-baseline justify-between gap-4 pb-3 hair-b">
                    <h3 className="font-mono text-[13px] uppercase tracking-[0.16em] text-primary">
                      HTTP ROUTES
                    </h3>
                    <span className="mono-detail tabular-nums" style={{ fontSize: 10 }}>
                      {stats.route_count.toLocaleString()} ENDPOINTS
                    </span>
                  </div>
                  <p className="text-[12px] text-text-muted leading-relaxed mt-4 max-w-[70ch]">
                    No HTTP routes detected. Routes are inferred from FastAPI, Flask and Express
                    decorators and patterns.
                  </p>
                </div>
              ) : (
                <SymbolInventory
                  title="HTTP ROUTES"
                  total={stats.route_count}
                  unit="ENDPOINTS"
                  symbols={routeSyms}
                  placeholder="Search routes…"
                  showRoute
                  shortcut
                  accentClass="text-primary"
                />
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default APISurfaceAnalyzer;
