import React, {
  useState,
  useEffect,
  useRef,
  useCallback,
  useMemo,
} from 'react';
import { Info, RefreshCw, GitBranch, Network, Layers, RotateCw, X } from 'lucide-react';
import { ReactFlowProvider, useReactFlow } from 'reactflow';

import { apiUrl, extractErrorMessage } from '../../../lib/api';
import { normalizeGraphPath, resolveGraphNode } from '../../../lib/graphPathUtils';
import { GraphCanvas } from './GraphCanvas';
import { GraphToolbar } from './GraphToolbar';
import { SearchBar } from './SearchBar';
import { NodeDetailsPanel } from './NodeDetailsPanel';
import { GraphFilterBar } from './GraphFilterBar';
import { GraphBreadcrumbNav } from './GraphBreadcrumbNav';
import { ArchitectureDiagramModal } from './ArchitectureDiagramModal';
import { GraphWorkspaceProvider, useGraphWorkspace } from './workspaceStore';
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
  const { selectNode } = useGraphWorkspace();

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
  const [nonGraphFileTarget, setNonGraphFileTarget] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [traceDir, setTraceDir] = useState<'forward' | 'backward' | 'both'>('both');

  // ── Request state ───────────────────────────────────────────────────────
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ── Refs ─────────────────────────────────────────────────────────────────
  const fitViewRef = useRef<(() => void) | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const searchDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  /** Holds a pending target file to resolve as soon as graph nodes become available. */
  const pendingTargetRef = useRef<string | null>(focusRequest?.path ?? null);

  // ── Centering and Selection Helpers ─────────────────────────────────────
  const centerOnNode = useCallback(
    (nodeId: string) => {
      let attempts = 0;
      const tryCenter = () => {
        attempts++;
        const nodes = getNodes();
        const target = nodes.find((n) => n.id === nodeId);
        if (target && target.position) {
          const x = target.position.x + (target.width ?? 200) / 2;
          const y = target.position.y + (target.height ?? 40) / 2;
          setCenter(x, y, { zoom: 1.15, duration: 400 });
        } else if (attempts < 10) {
          setTimeout(tryCenter, 60);
        } else {
          fitView({ padding: 0.15, duration: 300, minZoom: 0.15, maxZoom: 1.5 });
        }
      };
      setTimeout(tryCenter, 50);
    },
    [getNodes, setCenter, fitView],
  );

  const applyTargetSelection = useCallback(
    (targetPath: string, nodes: GraphNode[]) => {
      if (!targetPath || !nodes || nodes.length === 0) return;
      const decodedTarget = decodeURIComponent(targetPath);
      const match = resolveGraphNode(decodedTarget, nodes, repoName);
      if (match) {
        setNonGraphFileTarget(null);
        setSelectedNode(match);
        setFocusNode(match.id);
        selectNode(match.id);
        centerOnNode(match.id);
        pendingTargetRef.current = null;

        // Keep URL in sync with durable file parameter without reload
        if (typeof window !== 'undefined') {
          const url = new URL(window.location.href);
          url.searchParams.set('tab', 'graph');
          url.searchParams.set('file', match.id);
          url.searchParams.delete('focus');
          window.history.replaceState({}, '', url.toString());
          window.dispatchEvent(new CustomEvent('aria-workspace-file-select', { detail: { path: match.id } }));
        }
      } else {
        // Node not in graph (e.g. documentation or non-indexed file)
        // Keep the graph fully rendered, set non-graph notice, and fit viewport
        setNonGraphFileTarget(decodedTarget);
        pendingTargetRef.current = null;
        setTimeout(() => fitView({ padding: 0.15, duration: 300, minZoom: 0.15, maxZoom: 1.5 }), 100);
      }
    },
    [repoName, selectNode, centerOnNode, fitView],
  );

  // ── Core fetch ───────────────────────────────────────────────────────────
  const fetchGraph = useCallback(
    async (
      fetchMode: GraphMode,
      focusId: string | null,
      query: string,
      dir: 'forward' | 'backward' | 'both',
      isOptionalEnrichment = false,
    ) => {
      if (!owner || !repo) return;

      if (!isOptionalEnrichment) {
        abortRef.current?.abort();
        abortRef.current = new AbortController();
        setLoading(true);
        setError(null);
        setMatchCount(null);
      }

      const url = buildUrl(owner, repo, fetchMode, focusId, query, dir);

      try {
        const res = await fetch(url, { signal: isOptionalEnrichment ? undefined : abortRef.current?.signal });

        if (!res.ok) {
          let detail = `HTTP ${res.status}`;
          try {
            const body = await res.json();
            detail = extractErrorMessage(body);
          } catch {
            /* ignore */
          }
          if (isOptionalEnrichment) {
            // CRITICAL: Optional enrichment failure must NOT clear existing nodes!
            return;
          }
          setError(detail);
          setApiNodes([]);
          setApiEdges([]);
          return;
        }

        const data: GraphResponse = await res.json();

        if (data.error) {
          if (isOptionalEnrichment) return;
          setError(data.error);
          setApiNodes([]);
          setApiEdges([]);
          return;
        }

        const receivedNodes = data.nodes ?? [];
        const receivedEdges = data.edges ?? [];

        setApiNodes(receivedNodes);
        setApiEdges(receivedEdges);
        if (data.matched_count !== undefined) {
          setMatchCount(data.matched_count);
        }

        // Asynchronously resolve pending focus target against loaded nodes
        if (pendingTargetRef.current) {
          applyTargetSelection(pendingTargetRef.current, receivedNodes);
        } else {
          setTimeout(() => fitView({ padding: 0.15, duration: 300, minZoom: 0.15, maxZoom: 1.5 }), 80);
        }
      } catch (err: any) {
        if (err.name === 'AbortError') return;
        if (isOptionalEnrichment) return;
        setError(extractErrorMessage(err));
        setApiNodes([]);
        setApiEdges([]);
      } finally {
        if (!isOptionalEnrichment) {
          setLoading(false);
        }
      }
    },
    [owner, repo, applyTargetSelection, fitView],
  );

  const lastHandledTokenRef = useRef<number | null>(focusRequest?.token ?? null);

  // ── Initial load: always fetch full repository graph first ────────────────
  useEffect(() => {
    if (focusRequest?.path) {
      pendingTargetRef.current = focusRequest.path;
      lastHandledTokenRef.current = focusRequest.token;
    }
    setMode('full');
    fetchGraph('full', null, '', 'both');
    return () => abortRef.current?.abort();
  }, [repoName]);

  // ── External focus request handling ───────────────────────────────────────
  useEffect(() => {
    if (!focusRequest?.path || focusRequest.token === lastHandledTokenRef.current) return;
    lastHandledTokenRef.current = focusRequest.token;
    pendingTargetRef.current = focusRequest.path;

    if (apiNodes.length > 0) {
      applyTargetSelection(focusRequest.path, apiNodes);
    }
  }, [focusRequest?.token, focusRequest?.path, apiNodes, applyTargetSelection]);

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
      fitView({ padding: 0.15, duration: 200, minZoom: 0.15, maxZoom: 1.5 });
    }, 100);
  }, [fetchGraph, fitView]);

  const handleFitView = useCallback(() => {
    fitView({ padding: 0.15, duration: 200, minZoom: 0.15, maxZoom: 1.5 });
  }, [fitView]);

  // ── Node selection ────────────────────────────────────────────────────────
  const handleNodeSelect = useCallback(
    (node: GraphNode | null) => {
      setNonGraphFileTarget(null);
      setSelectedNode(node);
      if (node) {
        setFocusNode(node.id);
        selectNode(node.id);
        if (typeof window !== 'undefined') {
          const url = new URL(window.location.href);
          url.searchParams.set('tab', 'graph');
          url.searchParams.set('file', node.id);
          url.searchParams.delete('focus');
          window.history.replaceState({}, '', url.toString());
          window.dispatchEvent(new CustomEvent('aria-workspace-file-select', { detail: { path: node.id } }));
        }
      } else {
        setFocusNode(null);
        selectNode(null);
        if (typeof window !== 'undefined') {
          const url = new URL(window.location.href);
          url.searchParams.delete('file');
          url.searchParams.delete('focus');
          window.history.replaceState({}, '', url.toString());
          window.dispatchEvent(new CustomEvent('aria-workspace-file-select', { detail: { path: null } }));
        }
      }
    },
    [selectNode],
  );

  // Compute lightweight stats client-side over current view
  const stats = useMemo(() => computeGraphStats(apiNodes, apiEdges), [apiNodes, apiEdges]);

  // Diagram Modal state
  const [diagramModalNodeId, setDiagramModalNodeId] = useState<string | null>(null);

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="card overflow-hidden flex flex-col h-[700px] relative border border-border/70 bg-[#030303]">
      {/* Editorial Technical Header */}
      <div className="px-4 py-2.5 border-b border-border/80 bg-zinc-950/90 flex items-center justify-between gap-4 z-10 flex-wrap font-mono">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-bold text-indigo-400 tracking-wider uppercase">FILE GRAPH</span>
            <span className="text-zinc-600 text-[10px]">/</span>
            <span className="text-[10px] text-zinc-400 uppercase tracking-wider">REPOSITORY TOPOLOGY</span>
          </div>
          <div className="hidden sm:flex items-center gap-1.5 text-[10px] text-zinc-400">
            <span className="text-zinc-200 font-bold">{apiNodes.length.toLocaleString()}</span> NODES
            <span className="text-zinc-600">·</span>
            <span className="text-zinc-200 font-bold">{apiEdges.length.toLocaleString()}</span> EDGES
            {stats.components > 0 && (
              <>
                <span className="text-zinc-600">·</span>
                <span className="text-zinc-200 font-bold">{stats.components}</span> COMPONENTS
              </>
            )}
            <span className="text-zinc-600">·</span>
            <span className="text-zinc-400">DIRECTED</span>
          </div>
        </div>

        <div className="flex items-center gap-3 ml-auto">
          <SearchBar
            value={searchQuery}
            matchCount={matchCount}
            onChange={handleSearchChange}
            onClear={handleSearchClear}
          />

          {/* Compact Legend */}
          <div className="hidden xl:flex items-center gap-3 text-[9px] text-zinc-400 uppercase font-mono">
            <span className="flex items-center gap-1">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" /> Entry
            </span>
            <span className="flex items-center gap-1">
              <span className="h-1.5 w-1.5 rounded-full bg-blue-400" /> Module
            </span>
            <span className="flex items-center gap-1">
              <span className="h-1.5 w-1.5 rounded-full bg-amber-400" /> Coupled
            </span>
            <span className="flex items-center gap-1">
              <span className="h-1.5 w-1.5 rounded-full bg-indigo-400" /> Focus
            </span>
          </div>
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
            className="absolute inset-0 bg-canvas/80 backdrop-blur-sm flex flex-col items-center justify-center gap-2 z-30 font-mono text-xs text-text-muted"
          >
            <RefreshCw className="h-5 w-5 animate-spin text-indigo-400" aria-hidden="true" />
            <span className="tracking-wide">BUILDING REPOSITORY TOPOLOGY…</span>
          </div>
        )}

        {/* Error overlay */}
        {!loading && error && (
          <div className="absolute inset-0 bg-canvas/85 backdrop-blur-sm flex items-center justify-center z-30 p-6 font-mono">
            <EmptyState
              tone="danger"
              icon={<Info className="h-6 w-6 text-red-400" aria-hidden="true" />}
              title="TOPOLOGY UNAVAILABLE"
              description={error || 'Unable to load repository dependency graph.'}
              action={<Button variant="ghost" onClick={handleReset}>Retry</Button>}
            />
          </div>
        )}

        {/* Empty state */}
        {!loading && !error && apiNodes.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center z-30 p-6 font-mono">
            <EmptyState
              icon={<Network className="h-6 w-6 text-zinc-500" aria-hidden="true" />}
              title={searchQuery ? 'NO MATCHING NODES' : 'GRAPH IS EMPTY'}
              description={
                searchQuery
                  ? 'Try a different keyword or clear search to reveal the full topology.'
                  : 'Run repository analysis to index module relationships.'
              }
              action={searchQuery ? <Button variant="ghost" onClick={handleSearchClear}>Clear search</Button> : undefined}
            />
          </div>
        )}

        {/* React Flow canvas */}
        <div className="flex-grow h-full bg-[#030303]">
          <GraphCanvas
            apiNodes={apiNodes}
            apiEdges={apiEdges}
            onNodeSelect={handleNodeSelect}
            fitViewRef={fitViewRef}
          />
        </div>

        {/* Compact instruction hint when no node is selected */}
        {!selectedNode && !nonGraphFileTarget && apiNodes.length > 0 && (
          <div className="absolute top-3 right-3 hidden lg:flex items-center gap-2 px-3 py-1.5 bg-zinc-950/85 border border-zinc-800/80 rounded-md text-[10px] font-mono text-zinc-400 shadow-sm backdrop-blur-sm pointer-events-none select-none">
            <span className="h-1.5 w-1.5 rounded-full bg-indigo-500/80" />
            <span>Select any node to open Architecture Inspector</span>
          </div>
        )}

        {/* Non-graph file drawer notice */}
        {nonGraphFileTarget && !selectedNode && (
          <div
            role="dialog"
            aria-label={`Notice: ${nonGraphFileTarget} not in graph`}
            className="fixed inset-x-0 bottom-0 max-h-[80vh] md:absolute md:right-0 md:top-0 md:bottom-0 md:max-h-none md:w-[380px] bg-zinc-950 border-t md:border-t-0 md:border-l border-zinc-800 flex flex-col z-20 shadow-2xl font-mono animate-in fade-in slide-in-from-right-2 duration-200"
          >
            <div className="flex items-start justify-between px-4 pt-4 pb-3 border-b border-zinc-800/80 shrink-0">
              <div>
                <span className="text-[9px] font-bold text-amber-400 uppercase tracking-wider block">
                  Topology Notice
                </span>
                <h3 className="text-xs font-semibold text-zinc-100 truncate block mt-0.5" title={nonGraphFileTarget}>
                  {nonGraphFileTarget.split('/').pop() || nonGraphFileTarget}
                </h3>
                <span className="text-[9px] text-zinc-500 truncate block">{nonGraphFileTarget}</span>
              </div>
              <button
                type="button"
                onClick={() => setNonGraphFileTarget(null)}
                className="text-zinc-400 hover:text-zinc-100 p-1 rounded"
                title="Dismiss notice"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="p-4 space-y-3 text-xs text-zinc-300">
              <div className="p-3 bg-amber-950/20 border border-amber-500/30 rounded-lg space-y-1.5">
                <span className="text-[10px] font-bold text-amber-400 uppercase tracking-wider block">
                  File Not Represented in Topology
                </span>
                <p className="text-[11px] text-zinc-300 leading-relaxed">
                  This file exists in the repository but does not import or export code modules in the structural AST dependency graph (e.g. documentation, static assets, or configs).
                </p>
              </div>
              <p className="text-[10px] text-zinc-400 leading-relaxed">
                The full repository dependency graph remains rendered and interactive. Click any graph node to inspect its architectural properties.
              </p>
            </div>
          </div>
        )}

        {/* Node details panel */}
        {selectedNode && (
          <NodeDetailsPanel
            node={selectedNode}
            repoName={repoName}
            onClose={() => handleNodeSelect(null)}
            onExpand={(id) => {
              setFocusNode(id);
              setMode('neighbors');
              fetchGraph('neighbors', id, '', 'both', true);
            }}
            onTraceForward={handleTraceForward}
            onTraceBackward={handleTraceBackward}
            onTraceBoth={handleTraceBoth}
            onOpenDiagramModal={(id) => setDiagramModalNodeId(id)}
            onSelectNode={(id) => {
              const match = resolveGraphNode(id, apiNodes, repoName) || {
                id,
                label: id.split('/').pop() || id,
                category: 'regular',
                degree: 1,
                centrality: 0.1,
                language: 'typescript',
                highlighted: false,
                is_focus: true,
              };
              handleNodeSelect(match);
              centerOnNode(match.id);
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
// Interactive dependency graph entry point
