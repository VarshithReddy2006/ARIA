/**
 * ImpactAnalysisGraph — predictive impact instrument.
 *
 * Answers one question: what will this change touch, and where does the risk
 * propagate? The graph is the product surface; the readout beside it explains
 * what the graph means, and the inspector explains the selected node.
 *
 *   SCENARIO → RISK → PROPAGATION → ARCHITECTURAL IMPACT
 *
 * Framing is computed from the measured canvas rather than left to `fitView`:
 * the layout is asked to balance its bounding box against the canvas aspect, and
 * the viewport is then set explicitly with a clamped zoom. Without that, a wide
 * short canvas had to zoom out to fit a roughly square graph, which is what made
 * the nodes render as specks with empty margins either side.
 *
 * Every figure comes from the `/api/v1/impact-analysis` payload unchanged. Node
 * degrees are counted from the edges of this view, as before.
 */

import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import ReactFlow, {
  MiniMap,
  Controls,
  Background,
  useNodesState,
  useEdgesState,
  useReactFlow,
  MarkerType,
  ReactFlowProvider,
} from 'reactflow';
import { PanControls } from './graph/PanControls';
import {
  layoutImpactGraph,
  fitZoomFor,
  DEFAULT_TARGET_ASPECT,
} from './graph/impactLayout';
import { X, AlertTriangle, ArrowRight, ExternalLink, MessageSquare, Layers } from 'lucide-react';
import { FilePath } from '../ui/FilePath';
import { LeaderRow } from './pr/instrument';
import 'reactflow/dist/style.css';

interface DependencyPath {
  path: string[];
}

interface ImpactAnalysisData {
  repo: string;
  issue_text: string;
  directly_affected_files: string[];
  indirectly_affected_files: string[];
  affected_components: string[];
  risk_level: string;
  estimated_file_count: number;
  dependency_paths: DependencyPath[];
  confidence: number;
}

interface GraphProps {
  repoName: string;
  impactData: ImpactAnalysisData;
  onReset: () => void;
}

type NodeCategory = 'direct' | 'indirect' | 'component' | 'regular';

interface SelectedNodeData {
  id: string;
  label: string;
  category: NodeCategory;
  inDegree: number;
  outDegree: number;
  riskContribution: 'High' | 'Medium' | 'Low';
}

interface HoverInfo {
  id: string;
  category: NodeCategory;
  degree: number;
}

/**
 * Node surfaces. Direct impact is the only bright surface, so the propagation
 * chain wins against the background topology; the rest are dark surfaces
 * separated by edge colour alone.
 */
const NODE_BASE =
  'rounded-[3px] px-2.5 py-1.5 text-center text-[11px] font-mono leading-tight ' +
  'break-words cursor-pointer transition-[color,border-color,opacity] duration-200';

const NODE_CLASS: Record<NodeCategory, string> = {
  direct: `${NODE_BASE} bg-[#1b0f12] border border-danger/70 text-white font-medium hover:border-danger`,
  indirect: `${NODE_BASE} bg-canvas border border-warn/55 text-warn hover:border-warn`,
  component: `${NODE_BASE} bg-canvas border border-primary/60 text-primary hover:border-primary`,
  regular: `${NODE_BASE} bg-canvas border border-white/[0.06] text-text-subtle hover:border-white/20 hover:text-text-muted`,
};

/** Label length drives width, within bounds that keep the grid gutters intact. */
const NODE_STYLE: React.CSSProperties = {
  width: 'auto',
  minWidth: 118,
  maxWidth: 216,
  overflowWrap: 'anywhere',
  display: '-webkit-box',
  WebkitLineClamp: 2,
  WebkitBoxOrient: 'vertical',
  overflow: 'hidden',
};

function riskToneClass(risk: string): string {
  const r = (risk || '').toLowerCase();
  if (r === 'high' || r === 'critical') return 'text-danger';
  if (r === 'medium' || r === 'moderate') return 'text-warn';
  if (r === 'low') return 'text-success';
  return 'text-text-muted';
}

function categoryTone(category: NodeCategory): string {
  if (category === 'direct') return 'text-danger';
  if (category === 'indirect') return 'text-warn';
  if (category === 'component') return 'text-primary';
  return 'text-text-muted';
}

/** Only relayout when the canvas shape has moved enough to matter. */
const ASPECT_EPSILON = 0.12;

const ImpactAnalysisGraphInner: React.FC<GraphProps> = ({ repoName, impactData, onReset }) => {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [selectedNode, setSelectedNode] = useState<SelectedNodeData | null>(null);
  const [hover, setHover] = useState<HoverInfo | null>(null);

  const canvasRef = useRef<HTMLDivElement>(null);
  const { setViewport } = useReactFlow();

  /** Canvas aspect, bucketed so a resize drag cannot thrash the layout. */
  const [targetAspect, setTargetAspect] = useState(DEFAULT_TARGET_ASPECT);

  useEffect(() => {
    const el = canvasRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return;

    const measure = () => {
      const { clientWidth: w, clientHeight: h } = el;
      if (w <= 0 || h <= 0) return;
      const next = w / h;
      setTargetAspect((prev) =>
        Math.abs(Math.log(next / prev)) > ASPECT_EPSILON ? next : prev,
      );
    };

    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Parse raw impact data into React Flow nodes and edges
  useEffect(() => {
    const directSet = new Set(impactData.directly_affected_files);
    const indirectSet = new Set(impactData.indirectly_affected_files);

    const uniqueNodes = new Set<string>();
    const tempEdges: { source: string; target: string; isDotted?: boolean }[] = [];

    // 1. Process propagation paths
    impactData.dependency_paths.forEach((p) => {
      const path = p.path;
      for (let i = 0; i < path.length; i++) {
        uniqueNodes.add(path[i]);
        if (i < path.length - 1) {
          tempEdges.push({
            source: path[i],
            target: path[i + 1]
          });
        }
      }
    });

    // 2. Add remaining isolated files
    impactData.directly_affected_files.forEach((f) => uniqueNodes.add(f));
    impactData.indirectly_affected_files.forEach((f) => uniqueNodes.add(f));

    // 3. Process component nodes
    impactData.affected_components.forEach((comp) => {
      const compId = `component-${comp}`;
      uniqueNodes.add(compId);

      // Heuristic connection: Link components to directly affected files that are related
      let connectedAny = false;
      const compLower = comp.toLowerCase();

      impactData.directly_affected_files.forEach((file) => {
        const fileLower = file.toLowerCase();
        // Simple matching logic
        const matches =
          (compLower.includes('api') && (fileLower.includes('api') || fileLower.includes('route'))) ||
          (compLower.includes('auth') && (fileLower.includes('auth') || fileLower.includes('sec'))) ||
          (compLower.includes('service') && fileLower.includes('service')) ||
          (compLower.includes('db') && (fileLower.includes('db') || fileLower.includes('model'))) ||
          fileLower.includes(compLower);

        if (matches) {
          tempEdges.push({
            source: compId,
            target: file,
            isDotted: true
          });
          connectedAny = true;
        }
      });

      // Fallback: connect component node to the first directly affected file if no matches found
      if (!connectedAny && impactData.directly_affected_files.length > 0) {
        tempEdges.push({
          source: compId,
          target: impactData.directly_affected_files[0],
          isDotted: true
        });
      }
    });

    const categoryOf = (id: string): NodeCategory => {
      if (id.startsWith('component-')) return 'component';
      if (directSet.has(id)) return 'direct';
      if (indirectSet.has(id)) return 'indirect';
      return 'regular';
    };

    // Build React Flow Node objects
    const flowNodes = Array.from(uniqueNodes).map((id) => {
      const isComponent = id.startsWith('component-');
      const cleanLabel = isComponent ? id.replace('component-', '') : id.split('/').pop() || id;
      const category = categoryOf(id);

      return {
        id,
        data: { label: cleanLabel, category, fullId: id },
        className: NODE_CLASS[category],
        style: NODE_STYLE,
        type: 'default'
      };
    });

    /*
      Edge weight follows the classification of what it points at, so an amber
      node is reached by an amber edge. Derived from the existing sets — no new
      classification is introduced.
    */
    const flowEdges = tempEdges.map((e, idx) => {
      const targetCategory = categoryOf(e.target);
      let stroke = '#ef4444';
      let width = 2;
      let opacity = 0.9;

      if (e.isDotted) {
        stroke = '#5e6ad2';
        width = 1.5;
        opacity = 0.68;
      } else if (targetCategory === 'indirect') {
        stroke = '#f59e0b';
        width = 1.75;
        opacity = 0.7;
      } else if (targetCategory === 'regular') {
        stroke = '#ffffff';
        width = 1;
        opacity = 0.16;
      }

      return {
        id: `edge-${idx}`,
        source: e.source,
        target: e.target,
        // No continuous animation: a permanently marching edge is noise.
        animated: false,
        style: e.isDotted
          ? { stroke, strokeWidth: width, opacity, strokeDasharray: '4,4' }
          : { stroke, strokeWidth: width, opacity },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          width: 11,
          height: 11,
          color: stroke,
        },
      };
    });

    /*
      Isolated files get a grid whose column count balances the *whole* bounding
      box against the canvas aspect — see `impactLayout.ts`. The propagation
      chains keep their left-to-right ranking.
    */
    const { nodes: layoutedNodes, edges: layoutedEdges, bounds } = layoutImpactGraph(
      flowNodes,
      flowEdges,
      { direction: 'LR', targetAspect },
    );

    setNodes(layoutedNodes as never);
    setEdges(layoutedEdges as never);
    setSelectedNode(null);
    setHover(null);

    // Explicit framing: clamped zoom, bounding box centred in the canvas.
    const el = canvasRef.current;
    if (el && bounds.width > 0 && bounds.height > 0) {
      const cw = el.clientWidth;
      const ch = el.clientHeight;
      const zoom = fitZoomFor(bounds, cw, ch);
      setViewport({
        x: (cw - bounds.width * zoom) / 2 - bounds.x * zoom,
        y: (ch - bounds.height * zoom) / 2 - bounds.y * zoom,
        zoom,
      });
    }
  }, [impactData, targetAspect, setNodes, setEdges, setViewport]);

  const degreeOf = useCallback(
    (id: string) => ({
      inDegree: edges.filter((e) => e.target === id).length,
      outDegree: edges.filter((e) => e.source === id).length,
    }),
    [edges],
  );

  /** Nodes adjacent to the selection, for the focus treatment. */
  const focusSet = useMemo(() => {
    if (!selectedNode) return null;
    const set = new Set<string>([selectedNode.id]);
    edges.forEach((e) => {
      if (e.source === selectedNode.id) set.add(e.target);
      if (e.target === selectedNode.id) set.add(e.source);
    });
    return set;
  }, [selectedNode, edges]);

  /**
   * Focus is applied at render time rather than written back into node state, so
   * clearing the selection cannot leave stale styling behind.
   */
  const displayNodes = useMemo(() => {
    if (!focusSet) return nodes;
    return nodes.map((n) => {
      const inFocus = focusSet.has(n.id);
      return {
        ...n,
        style: {
          ...(n.style as React.CSSProperties),
          opacity: inFocus ? 1 : 0.22,
        },
      };
    });
  }, [nodes, focusSet]);

  const displayEdges = useMemo(() => {
    if (!focusSet) return edges;
    return edges.map((e) => {
      const onPath = focusSet.has(e.source) && focusSet.has(e.target);
      const base = (e.style ?? {}) as React.CSSProperties;
      const baseOpacity = typeof base.opacity === 'number' ? base.opacity : 1;
      return {
        ...e,
        style: {
          ...base,
          opacity: onPath ? Math.min(1, baseOpacity + 0.25) : baseOpacity * 0.25,
        },
      };
    });
  }, [edges, focusSet]);

  // Handle node selection
  const onNodeClick = (_event: any, node: any) => {
    const id = node.id;
    const { inDegree, outDegree } = degreeOf(id);

    let riskContribution: 'High' | 'Medium' | 'Low' = 'Low';
    if (node.data.category === 'direct') {
      riskContribution = outDegree > 2 ? 'High' : 'Medium';
    } else if (node.data.category === 'indirect') {
      riskContribution = 'Medium';
    }

    setSelectedNode({
      id,
      label: node.data.label,
      category: node.data.category,
      inDegree,
      outDegree,
      riskContribution
    });
    setHover(null);
  };

  const onNodeMouseEnter = useCallback(
    (_event: React.MouseEvent, node: any) => {
      const { inDegree, outDegree } = degreeOf(node.id);
      setHover({
        id: node.id,
        category: node.data?.category ?? 'regular',
        degree: inDegree + outDegree,
      });
    },
    [degreeOf],
  );

  const onNodeMouseLeave = useCallback(() => setHover(null), []);

  const counts = useMemo(
    () => ({
      direct: impactData.directly_affected_files.length,
      indirect: impactData.indirectly_affected_files.length,
      chains: impactData.dependency_paths.length,
    }),
    [impactData],
  );

  const scenario = (impactData.issue_text || '').trim();

  return (
    <div className="min-w-0">
      {/* ── Scenario context strip ────────────────────────────────────────── */}
      {scenario && (
        <div className="flex items-baseline gap-3 pb-3 mb-7 hair-b min-w-0">
          <span className="mono-label shrink-0">SCENARIO</span>
          <span
            className="text-[12px] text-text-muted truncate min-w-0 flex-1"
            title={scenario}
          >
            &ldquo;{scenario}&rdquo;
          </span>
        </div>
      )}

      <div
        className="grid grid-cols-1 gap-y-8 items-start min-w-0
                   lg:grid-cols-[minmax(0,30fr)_minmax(0,70fr)] lg:gap-x-7"
      >
        {/* ── Risk intelligence ───────────────────────────────────────────── */}
        <div className="min-w-0">
          <div className="flex items-baseline justify-between gap-4 pb-2.5 hair-b">
            <h3 className="mono-label mono-label-accent">RISK INTELLIGENCE</h3>
            <button
              type="button"
              onClick={onReset}
              className="api-action link-arrow shrink-0"
            >
              RESET SCENARIO
              <ArrowRight className="h-2.5 w-2.5 arrow ml-1" aria-hidden="true" />
            </button>
          </div>

          {/* Risk state — a band, not a filled card */}
          <div className="mt-4 min-w-0">
            <div className="flex items-center gap-2.5">
              <AlertTriangle
                className={`h-3.5 w-3.5 shrink-0 ${riskToneClass(impactData.risk_level)}`}
                aria-hidden="true"
              />
              <span
                className={`font-mono text-[13px] uppercase tracking-[0.16em] ${riskToneClass(
                  impactData.risk_level,
                )}`}
              >
                {impactData.risk_level} RISK
              </span>
            </div>
            <p className="text-[12px] text-text-muted leading-relaxed mt-1.5 max-w-sm">
              Calculated risk of change propagation based on coupling and core components.
            </p>
          </div>

          {/* One continuous diagnostic readout */}
          <dl className="mt-4 min-w-0 border-t border-white/[0.055]">
            <LeaderRow label="ANALYSIS CONFIDENCE" first>
              <span className="font-mono text-[13px] text-text tabular-nums">
                {impactData.confidence}
                <span className="text-text-subtle">%</span>
              </span>
            </LeaderRow>
            <LeaderRow label="ESTIMATED IMPACT">
              <span className="font-mono text-[13px] text-text tabular-nums">
                {impactData.estimated_file_count}
                <span className="text-text-subtle"> files</span>
              </span>
            </LeaderRow>
          </dl>

          <div className="mt-4 min-w-0">
            <span className="mono-label block mb-1.5">AFFECTED COMPONENTS</span>
            {impactData.affected_components.length > 0 ? (
              <p className="font-mono text-[11.5px] text-primary leading-relaxed break-words">
                {impactData.affected_components.join('  ·  ')}
              </p>
            ) : (
              <p className="mono-detail" style={{ fontSize: 10 }}>
                NOT AVAILABLE
              </p>
            )}
          </div>

          <div className="mt-4 min-w-0">
            <span className="mono-label block mb-0.5">PROPAGATION</span>
            <dl className="min-w-0 border-t border-white/[0.055]">
              <LeaderRow label="DIRECT" first>
                <span className="font-mono text-[13px] text-danger tabular-nums">
                  {counts.direct}
                </span>
              </LeaderRow>
              <LeaderRow label="INDIRECT">
                <span className="font-mono text-[13px] text-warn tabular-nums">
                  {counts.indirect}
                </span>
              </LeaderRow>
              <LeaderRow label="CHAINS">
                <span className="font-mono text-[13px] text-primary tabular-nums">
                  {counts.chains}
                </span>
              </LeaderRow>
            </dl>
          </div>
        </div>

        {/* ── Impact propagation graph ────────────────────────────────────── */}
        <div className="min-w-0 lg:pl-7 lg:border-l lg:border-white/[0.055]">
          <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2 pb-2.5 hair-b">
            <h3 className="mono-label text-text">IMPACT PROPAGATION GRAPH</h3>
            <div className="flex items-center gap-x-4 gap-y-1 flex-wrap shrink-0">
              <LegendDot tone="bg-danger" label="DIRECT" />
              <LegendDot tone="bg-warn" label="INDIRECT" />
              <LegendDot tone="bg-primary" label="COMPONENT" />
              {/* Counts read brighter than the legend they sit beside. */}
              <span className="font-mono text-[10px] tracking-[0.14em] text-text-muted tabular-nums">
                {nodes.length} NODES · {edges.length} EDGES
              </span>
            </div>
          </div>

          <div
            ref={canvasRef}
            className="impact-canvas relative mt-3 min-w-0 border border-white/[0.055]
                       h-[clamp(28rem,calc(100vh-15rem),50rem)] overflow-hidden"
          >
            <ReactFlow
              nodes={displayNodes}
              edges={displayEdges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onNodeClick={onNodeClick}
              onNodeMouseEnter={onNodeMouseEnter}
              onNodeMouseLeave={onNodeMouseLeave}
              onPaneClick={() => {
                setHover(null);
                setSelectedNode(null);
              }}
              /* Framing is set explicitly from measured bounds, so `fitView` is
                 not used — it would override the computed viewport. */
              minZoom={0.15}
              maxZoom={2}
            >
              <Controls showInteractive={false} />
              <PanControls />
              <MiniMap
                // Never allowed to sit on top of the topology on a phone.
                className="!hidden sm:!block"
                pannable
                zoomable
                nodeStrokeWidth={2}
                nodeColor={(node) => {
                  const cat = node.data?.category;
                  if (cat === 'direct') return '#ef4444';
                  if (cat === 'indirect') return '#f59e0b';
                  if (cat === 'component') return '#5e6ad2';
                  return '#26262b';
                }}
                maskColor="rgba(2, 2, 4, 0.74)"
                style={{
                  backgroundColor: '#020204',
                  border: '1px solid rgba(255,255,255,0.07)',
                  width: 128,
                  height: 88,
                }}
              />
              <Background color="rgba(255,255,255,0.07)" gap={18} />
            </ReactFlow>

            {/* ── Hover micro-inspector ─────────────────────────────────── */}
            {hover && !selectedNode && (
              <div
                className="pointer-events-none absolute left-3 bottom-3 z-20 max-w-[18rem]
                           border border-white/10 bg-canvas/95 px-3 py-2"
                role="status"
              >
                <FilePath path={hover.id.replace(/^component-/, '')} tone="primary" size="sm" />
                <div className="flex items-baseline gap-x-4 gap-y-1 flex-wrap mt-1.5">
                  <span className="mono-detail" style={{ fontSize: 10 }}>
                    <span className={categoryTone(hover.category)}>
                      {hover.category.toUpperCase()}
                    </span>
                  </span>
                  <span className="mono-detail tabular-nums" style={{ fontSize: 10 }}>
                    DEGREE {hover.degree}
                  </span>
                </div>
              </div>
            )}

            {/*
              Inspector: a side drawer on desktop, a bottom sheet at <=640px so
              the topology stays visible behind it.
            */}
            {selectedNode && (
              <div
                className="absolute z-20 flex flex-col overflow-y-auto
                           border-white/10 bg-canvas/92 backdrop-blur-[2px]
                           inset-x-0 bottom-0 max-h-[62%] border-t
                           sm:inset-y-0 sm:left-auto sm:right-0 sm:max-h-none
                           sm:w-[19rem] sm:border-t-0 sm:border-l"
              >
                <div className="p-3.5 min-w-0">
                  <div className="flex items-start justify-between gap-3 pb-2.5 hair-b">
                    <span className="mono-label mono-label-accent">DEPENDENCY CHAIN</span>
                    <button
                      type="button"
                      onClick={() => setSelectedNode(null)}
                      className="shrink-0 text-text-muted hover:text-text transition-colors duration-200"
                      aria-label="Close node details"
                    >
                      <X className="h-3.5 w-3.5" aria-hidden="true" />
                    </button>
                  </div>

                  <div className="mt-3 min-w-0">
                    <span className="mono-label block mb-1" style={{ fontSize: 9 }}>
                      FILE / NODE
                    </span>
                    <FilePath
                      path={selectedNode.id.replace(/^component-/, '')}
                      tone="primary"
                      size="sm"
                    />
                  </div>

                  <dl className="mt-3 min-w-0 border-t border-white/[0.055]">
                    <LeaderRow label="IMPACT TYPE" first>
                      <span
                        className={`font-mono text-[11px] uppercase tracking-[0.14em] ${categoryTone(
                          selectedNode.category,
                        )}`}
                      >
                        {selectedNode.category}
                      </span>
                    </LeaderRow>
                    <LeaderRow label="DEPENDENTS">
                      <span className="font-mono text-[12px] text-text tabular-nums">
                        {selectedNode.inDegree}
                      </span>
                    </LeaderRow>
                    <LeaderRow label="DEPENDENCIES">
                      <span className="font-mono text-[12px] text-text tabular-nums">
                        {selectedNode.outDegree}
                      </span>
                    </LeaderRow>
                    <LeaderRow label="RISK CONTRIBUTION">
                      <span
                        className={`font-mono text-[11px] uppercase tracking-[0.14em] ${riskToneClass(
                          selectedNode.riskContribution,
                        )}`}
                      >
                        {selectedNode.riskContribution}
                      </span>
                    </LeaderRow>
                  </dl>

                  {/* Smart actions — not yet wired, and labelled as such. */}
                  <div className="mt-4 pt-3 border-t border-white/[0.055] min-w-0">
                    <div className="flex items-baseline justify-between gap-3 mb-2.5">
                      <span className="mono-label" style={{ fontSize: 9 }}>
                        SMART ACTIONS
                      </span>
                      <span className="mono-detail shrink-0" style={{ fontSize: 9 }}>
                        NOT AVAILABLE
                      </span>
                    </div>

                    <button
                      type="button"
                      disabled
                      className="w-full flex items-center justify-between gap-2 border border-white/[0.09]
                                 px-2.5 py-1.5 rounded-[2px] font-mono text-[10px] uppercase
                                 tracking-[0.14em] text-text-muted opacity-45 cursor-not-allowed"
                    >
                      <span className="flex items-center gap-2">
                        <Layers className="h-3 w-3 shrink-0" aria-hidden="true" />
                        View architecture
                      </span>
                      <ArrowRight className="h-2.5 w-2.5 shrink-0" aria-hidden="true" />
                    </button>

                    <ul className="mt-2 space-y-1.5 min-w-0">
                      {[
                        { icon: ExternalLink, label: 'Open file' },
                        { icon: MessageSquare, label: 'Ask about impact' },
                      ].map(({ icon: Icon, label }) => (
                        <li key={label}>
                          <button
                            type="button"
                            disabled
                            className="w-full flex items-center gap-2 font-mono text-[10px] uppercase
                                       tracking-[0.14em] text-text-subtle opacity-45 cursor-not-allowed"
                          >
                            <Icon className="h-3 w-3 shrink-0" aria-hidden="true" />
                            <span>{label}</span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* ── Status line ───────────────────────────────────────────────── */}
          <div className="flex flex-wrap items-baseline justify-between gap-x-5 gap-y-1 mt-2.5">
            <p className="mono-detail tabular-nums min-w-0" style={{ fontSize: 10, letterSpacing: '0.14em' }}>
              {selectedNode ? (
                <>
                  FOCUSED: <span className="text-text">{selectedNode.label}</span> · DEPENDENCY CHAIN
                </>
              ) : (
                <>SCENARIO TOPOLOGY · {nodes.length} NODES · {edges.length} EDGES</>
              )}
            </p>
            {!selectedNode && (
              <span className="mono-label shrink-0" style={{ fontSize: 9 }}>
                SELECT A NODE TO INSPECT ITS IMPACT CHAIN
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

const LegendDot: React.FC<{ tone: string; label: string }> = ({ tone, label }) => (
  <span className="flex items-center gap-1.5">
    <span className={`h-1.5 w-1.5 rounded-full ${tone}`} aria-hidden="true" />
    <span className="mono-label" style={{ fontSize: 9 }}>
      {label}
    </span>
  </span>
);

export const ImpactAnalysisGraph: React.FC<GraphProps> = (props) => {
  return (
    <ReactFlowProvider>
      <ImpactAnalysisGraphInner {...props} />
    </ReactFlowProvider>
  );
};

export default ImpactAnalysisGraph;
