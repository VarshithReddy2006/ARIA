import React, {
  useState,
  useEffect,
  useRef,
  useCallback,
  useMemo,
} from 'react';
import { Info, RefreshCw, GitBranch, Network, Layers, RotateCw } from 'lucide-react';
import { ReactFlowProvider, useReactFlow } from 'reactflow';

import { apiUrl, extractErrorMessage } from '../../../lib/api';
import { GraphCanvas } from './GraphCanvas';
import { GraphToolbar } from './GraphToolbar';
import { SearchBar } from './SearchBar';
import { NodeDetailsPanel } from './NodeDetailsPanel';
import { GraphFilterBar } from './GraphFilterBar';
import { GraphBreadcrumbNav } from './GraphBreadcrumbNav';
import { ArchitectureDiagramModal } from './ArchitectureDiagramModal';
import { GraphWorkspaceProvider } from './workspaceStore';
import { computeGraphStats } from './graphStats';
import { CATEGORY_COLORS, CATEGORY_LABELS } from './types';
import type { GraphNode, GraphEdge, GraphMode, GraphResponse } from './types';
import { EmptyState } from '../../ui/EmptyState';
import { Button } from '../../ui/Button';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Build the fetch URL for each graph mode. */
function buildUrl(
  owner: string,
  repo: string,
  mode: GraphMode,
  focusNode: string | null,
  searchQuery: string,
  traceDir: 'forward' | 'backward' | 'both',
): string {
  const base = `/api/v1/graph/${owner}/${repo}`;
  switch (mode) {
    case 'neighbors':
      return apiUrl(`${base}/neighbors/${focusNode}`);
    case 'trace_fwd':
      return apiUrl(`${base}/trace/${focusNode}?direction=forward&depth=6`);
    case 'trace_bwd':
      return apiUrl(`${base}/trace/${focusNode}?direction=backward&depth=6`);
    case 'search':
      return apiUrl(`${base}/search?q=${encodeURIComponent(searchQuery)}`);
    case 'full':
    default:
      return searchQuery.trim()
        ? apiUrl(`${base}/full?q=${encodeURIComponent(searchQuery)}`)
        : apiUrl(`${base}/full`);
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface InteractiveDependencyGraphProps {
  repoName: string;
  /**
   * Externally requested focus target (e.g. "View in graph" from the reading
   * path). The `token` lets the same path be re-requested; bumping it re-runs
   * the focus even when the path is unchanged.
   */
  focusRequest?: { path: string; token: number } | null;
}

/**
 * PH2-001 Interactive Dependency Graph orchestrator.
 *
 * Owns all state: mode, focusNode, searchQuery, selectedNode, graph data.
 * Delegates rendering to four sub-components:
 *   GraphToolbar    — mode buttons, fit/reset, status
 *   SearchBar       — debounced search input
 *   GraphCanvas     — React Flow canvas + Dagre layout
 *   NodeDetailsPanel — right-side drawer
 */
const InteractiveDependencyGraphInner: React.FC<
  InteractiveDependencyGraphProps
> = ({ repoName, focusRequest }) => {
  const { zoomIn, zoomOut, setViewport, getViewport, setCenter, fitView, getNodes } = useReactFlow();
  // ── Repo split ──────────────────────────────────────────────────────────
  const [owner, repo] = useMemo(() => {
    const parts = repoName.split('/');
    return [parts[0] ?? '', parts[1] ?? ''];
  }, [repoName]);

  // ── Graph data state ────────────────────────────────────────────────────
  const [apiNodes, setApiNodes] = useState<GraphNode[]>([]);
  const [apiEdges, setApiEdges] = useState<GraphEdge[]>([]);
  const [matchCount, setMatchCount] = useState<number | null>(null);

  // ── Interaction state ───────────────────────────────────────────────────
  const [mode, setMode] = useState<GraphMode>('full');
  const [focusNode, setFocusNode] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  // used internally to differentiate trace directions when both toolbar
  // buttons share the same mode key
  const [traceDir, setTraceDir] = useState<'forward' | 'backward' | 'both'>(
    'both',
  );

  // ── Request state ───────────────────────────────────────────────────────
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ── Refs ─────────────────────────────────────────────────────────────────
  const fitViewRef = useRef<(() => void) | null>(null);
  /** AbortController for in-flight requests — cancels stale fetches. */
  const abortRef = useRef<AbortController | null>(null);
  /** Debounce timer for search input. */
  const searchDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Core fetch ───────────────────────────────────────────────────────────
  const fetchGraph = useCallback(
    async (
      fetchMode: GraphMode,
      focusId: string | null,
      query: string,
      dir: 'forward' | 'backward' | 'both',
    ) => {
      if (!owner || !repo) return;

      // Cancel any in-flight request
      abortRef.current?.abort();
      abortRef.current = new AbortController();

      setLoading(true);
      setError(null);
      setMatchCount(null);

      const url = buildUrl(owner, repo, fetchMode, focusId, query, dir);

      try {
        const res = await fetch(url, { signal: abortRef.current.signal });

        if (!res.ok) {
          let detail = `HTTP ${res.status}`;
          try {
            const body = await res.json();
            detail = extractErrorMessage(body);
          } catch {
            /* ignore */
          }
          setError(detail);
          setApiNodes([]);
          setApiEdges([]);
          return;
        }

        const data: GraphResponse = await res.json();

        if (data.error) {
          setError(data.error);
          setApiNodes([]);
          setApiEdges([]);
          return;
        }

        setApiNodes(data.nodes ?? []);
        setApiEdges(data.edges ?? []);
        if (data.matched_count !== undefined) {
          setMatchCount(data.matched_count);
        }

        // Auto-fit after data loads
        setTimeout(() => fitView({ padding: 0.15, duration: 300 }), 80);
      } catch (err: any) {
        if (err.name === 'AbortError') return; // stale request cancelled
        setError(extractErrorMessage(err));
        setApiNodes([]);
        setApiEdges([]);
      } finally {
        setLoading(false);
      }
    },
    [owner, repo],
  );

  // ── Initial load ─────────────────────────────────────────────────────────
  useEffect(() => {
    setFocusNode(null);
    setSelectedNode(null);
    setSearchQuery('');
    setMatchCount(null);
    setMode('full');
    fetchGraph('full', null, '', 'both');
    return () => abortRef.current?.abort();
  }, [fetchGraph]);

  // ── External focus request ───────────────────────────────────────────────
  // Declared after the initial load so it wins on mount; fetchGraph aborts the
  // in-flight full-graph request.
  useEffect(() => {
    const path = focusRequest?.path;
    if (!path) return;
    setSearchQuery('');
    setMatchCount(null);
    setSelectedNode(null);
    setFocusNode(path);
    setMode('neighbors');
    setTraceDir('both');
    fetchGraph('neighbors', path, '', 'both');
  }, [focusRequest?.path, focusRequest?.token, fetchGraph]);

  // ── Search debounce ──────────────────────────────────────────────────────
  const handleSearchChange = useCallback(
    (value: string) => {
      setSearchQuery(value);
      if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current);
      searchDebounceRef.current = setTimeout(() => {
        if (value.trim()) {
          setMode('search');
          setFocusNode(null);
          setSelectedNode(null);
          fetchGraph('search', null, value, 'both');
        } else {
          setMode('full');
          fetchGraph('full', null, '', 'both');
        }
      }, 300);
    },
    [fetchGraph],
  );

  const handleSearchClear = useCallback(() => {
    setSearchQuery('');
    setMatchCount(null);
    setMode('full');
    fetchGraph('full', null, '', 'both');
  }, [fetchGraph]);

  // ── Toolbar actions ──────────────────────────────────────────────────────
  const handleExpand = useCallback(() => {
    if (!focusNode) return;
    setMode('neighbors');
    setTraceDir('both');
    fetchGraph('neighbors', focusNode, '', 'both');
  }, [focusNode, fetchGraph]);

  const handleTraceForward = useCallback(
    (nodeId?: string) => {
      const id = nodeId ?? focusNode;
      if (!id) return;
      setFocusNode(id);
      setMode('trace_fwd');
      setTraceDir('forward');
      fetchGraph('trace_fwd', id, '', 'forward');
    },
    [focusNode, fetchGraph],
  );

  const handleTraceBackward = useCallback(
    (nodeId?: string) => {
      const id = nodeId ?? focusNode;
      if (!id) return;
      setFocusNode(id);
      setMode('trace_bwd');
      setTraceDir('backward');
      fetchGraph('trace_bwd', id, '', 'backward');
    },
    [focusNode, fetchGraph],
  );

  const handleTraceBoth = useCallback(
    (nodeId?: string) => {
      const id = nodeId ?? focusNode;
      if (!id) return;
      setFocusNode(id);
      // Reuse trace_fwd mode key — backend gets direction=both
      setMode('trace_fwd');
      setTraceDir('both');
      fetchGraph('trace_fwd', id, '', 'both');
    },
    [focusNode, fetchGraph],
  );

  const handlePanUp = useCallback(() => {
    const { x, y, zoom } = getViewport();
    setViewport({ x, y: y + 150, zoom }, { duration: 200 });
  }, [getViewport, setViewport]);

  const handlePanDown = useCallback(() => {
    const { x, y, zoom } = getViewport();
    setViewport({ x, y: y - 150, zoom }, { duration: 200 });
  }, [getViewport, setViewport]);

  const handlePanLeft = useCallback(() => {
    const { x, y, zoom } = getViewport();
    setViewport({ x: x + 150, y, zoom }, { duration: 200 });
  }, [getViewport, setViewport]);

  const handlePanRight = useCallback(() => {
    const { x, y, zoom } = getViewport();
    setViewport({ x: x - 150, y, zoom }, { duration: 200 });
  }, [getViewport, setViewport]);

  const handleZoomIn = useCallback(() => {
    zoomIn({ duration: 200 });
  }, [zoomIn]);

  const handleZoomOut = useCallback(() => {
    zoomOut({ duration: 200 });
  }, [zoomOut]);

  const handleCenterGraph = useCallback(() => {
    const nodes = getNodes();
    if (nodes.length > 0) {
      let minX = Infinity;
      let maxX = -Infinity;
      let minY = Infinity;
      let maxY = -Infinity;
      nodes.forEach((node) => {
        const x = node.position.x;
        const y = node.position.y;
        const w = node.width ?? 200;
        const h = node.height ?? 40;
        if (x < minX) minX = x;
        if (x + w > maxX) maxX = x + w;
        if (y < minY) minY = y;
        if (y + h > maxY) maxY = y + h;
      });
      const centerX = minX + (maxX - minX) / 2;
      const centerY = minY + (maxY - minY) / 2;
      const { zoom } = getViewport();
      setCenter(centerX, centerY, { zoom, duration: 200 });
    }
  }, [getNodes, getViewport, setCenter]);

  const handleReset = useCallback(() => {
    setMode('full');
    setFocusNode(null);
    setSelectedNode(null);
    setSearchQuery('');
    setMatchCount(null);
    fetchGraph('full', null, '', 'both');
    setTimeout(() => {
      fitView({ padding: 0.15, duration: 200 });
    }, 100);
  }, [fetchGraph, fitView]);

  const handleFitView = useCallback(() => {
    fitView({ padding: 0.15, duration: 200 });
  }, [fitView]);

  // ── Node selection ────────────────────────────────────────────────────────
  const handleNodeSelect = useCallback((node: GraphNode | null) => {
    setSelectedNode(node);
    if (node) setFocusNode(node.id);
  }, []);

  // Compute lightweight stats client-side over current view
  const stats = useMemo(() => computeGraphStats(apiNodes, apiEdges), [apiNodes, apiEdges]);

  // Diagram Modal state
  const [diagramModalNodeId, setDiagramModalNodeId] = useState<string | null>(null);

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="card overflow-hidden flex flex-col h-[700px] relative">
      {/* Statistics + search header */}
      <div className="px-3 py-2.5 border-b border-border bg-surface-2 flex items-center gap-3 z-10 flex-wrap">
        <SearchBar
          value={searchQuery}
          matchCount={matchCount}
          onChange={handleSearchChange}
          onClear={handleSearchClear}
        />

        {/* Stat pills */}
        <div className="flex items-center gap-1.5 font-mono text-[10px]">
          <StatPill icon={<Network className="h-3 w-3" />} label="Nodes" value={apiNodes.length} />
          <StatPill icon={<GitBranch className="h-3 w-3" />} label="Edges" value={apiEdges.length} />
          <StatPill icon={<Layers className="h-3 w-3" />} label="Components" value={stats.components} />
          <StatPill
            icon={<RotateCw className="h-3 w-3" />}
            label="Cycles"
            value={stats.cycleClusters}
            tone={stats.cycleClusters > 0 ? 'danger' : 'neutral'}
          />
        </div>

        {/* Legend */}
        <div className="ml-auto text-[10px] font-mono text-text-muted hidden lg:flex items-center gap-3">
          {(['entry_point', 'core_module', 'high_coupling'] as const).map((k) => (
            <span key={k} className="flex items-center gap-1.5">
              <span
                className="h-2 w-2 rounded-full"
                style={{ backgroundColor: CATEGORY_COLORS[k] }}
                aria-hidden="true"
              />
              {CATEGORY_LABELS[k]}
            </span>
          ))}
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-amber-400" aria-hidden="true" /> Match
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-white" aria-hidden="true" /> Focus
          </span>
        </div>
      </div>

      {/* Filter Bar & Breadcrumb Navigation */}
      <GraphFilterBar />
      <GraphBreadcrumbNav />

      {/* ── Toolbar ─────────────────────────────────────────────────── */}
      <GraphToolbar
        mode={mode}
        traceDir={traceDir}
        focusNode={focusNode}
        loading={loading}
        nodeCount={apiNodes.length}
        edgeCount={apiEdges.length}
        onFitView={handleFitView}
        onReset={handleReset}
        onTraceForward={() => handleTraceForward()}
        onTraceBackward={() => handleTraceBackward()}
        onTraceBoth={() => handleTraceBoth()}
        onNeighbors={handleExpand}
        onPanUp={handlePanUp}
        onPanDown={handlePanDown}
        onPanLeft={handlePanLeft}
        onPanRight={handlePanRight}
        onZoomIn={handleZoomIn}
        onZoomOut={handleZoomOut}
        onCenterGraph={handleCenterGraph}
      />

      {/* ── Main canvas area ─────────────────────────────────────────── */}
      <div className="flex-grow relative flex overflow-hidden">
        {/* Loading overlay */}
        {loading && (
          <div
            role="status"
            aria-live="polite"
            className="absolute inset-0 bg-canvas/70 backdrop-blur-sm flex flex-col items-center justify-center gap-2 z-30 font-mono text-xs text-text-muted"
          >
            <RefreshCw className="h-5 w-5 animate-spin text-primary" aria-hidden="true" />
            <span>Loading graph…</span>
          </div>
        )}

        {/* Error overlay */}
        {!loading && error && (
          <div className="absolute inset-0 bg-canvas/80 backdrop-blur-sm flex items-center justify-center z-30 p-6">
            <EmptyState
              tone="danger"
              icon={<Info className="h-6 w-6" aria-hidden="true" />}
              title="Graph failed to load"
              description={error}
              action={<Button variant="ghost" onClick={handleReset}>Retry</Button>}
            />
          </div>
        )}

        {/* Empty state */}
        {!loading && !error && apiNodes.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center z-30 p-6">
            <EmptyState
              icon={<Network className="h-6 w-6" aria-hidden="true" />}
              title={searchQuery ? 'No nodes matched your search' : 'Graph is empty'}
              description={
                searchQuery
                  ? 'Try a different keyword or clear the search to see the full graph.'
                  : 'Run a repository analysis to populate the dependency graph.'
              }
              action={searchQuery ? <Button variant="ghost" onClick={handleSearchClear}>Clear search</Button> : undefined}
            />
          </div>
        )}

        {/* React Flow canvas */}
        <div className="flex-grow h-full bg-canvas/10">
          <GraphCanvas
            apiNodes={apiNodes}
            apiEdges={apiEdges}
            onNodeSelect={handleNodeSelect}
            fitViewRef={fitViewRef}
          />
        </div>

        {/* Node details panel */}
        {selectedNode && (
          <NodeDetailsPanel
            node={selectedNode}
            repoName={repoName}
            onClose={() => setSelectedNode(null)}
            onExpand={(id) => {
              setFocusNode(id);
              setMode('neighbors');
              fetchGraph('neighbors', id, '', 'both');
            }}
            onTraceForward={handleTraceForward}
            onTraceBackward={handleTraceBackward}
            onTraceBoth={handleTraceBoth}
            onOpenDiagramModal={(id) => setDiagramModalNodeId(id)}
            onSelectNode={(id) => {
              const match = apiNodes.find((n) => n.id === id) || { id, label: id.split('/').pop() || id, category: 'regular', degree: 1, centrality: 0.1, language: 'typescript', highlighted: false, is_focus: true };
              setSelectedNode(match);
              setFocusNode(id);
            }}
          />
        )}

        {/* Diagram exporter modal */}
        {diagramModalNodeId && (
          <ArchitectureDiagramModal
            repoName={repoName}
            nodeId={diagramModalNodeId}
            onClose={() => setDiagramModalNodeId(null)}
          />
        )}
      </div>
    </div>
  );
};

export const InteractiveDependencyGraph: React.FC<
  InteractiveDependencyGraphProps
> = (props) => {
  return (
    <GraphWorkspaceProvider>
      <ReactFlowProvider>
        <InteractiveDependencyGraphInner {...props} />
      </ReactFlowProvider>
    </GraphWorkspaceProvider>
  );
};

interface StatPillProps {
  icon: React.ReactNode;
  label: string;
  value: number | string;
  tone?: 'neutral' | 'danger';
}
const StatPill: React.FC<StatPillProps> = ({ icon, label, value, tone = 'neutral' }) => (
  <span
    className={[
      'flex items-center gap-1 px-2 py-0.5 rounded border',
      tone === 'danger'
        ? 'border-danger/30 bg-danger/10 text-danger'
        : 'border-border bg-canvas text-text',
    ].join(' ')}
    title={`${label}: ${value}`}
  >
    <span className="text-text-muted" aria-hidden="true">{icon}</span>
    <span className="text-text-muted">{label}</span>
    <span className="font-bold">{value}</span>
  </span>
);

export default InteractiveDependencyGraph;
