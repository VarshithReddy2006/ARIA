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

// Impact-analysis contract types live in one place so this component and
// ImpactAnalysisWorkspace cannot drift apart. See frontend/src/lib/impactTypes.ts.
import type {
  ApiExposureInfo,
  CallerInfo,
  DependencyPath,
  EvidenceItem,
  ImpactAnalysisData,
  ImpactedFileDetail,
  TestImpactItem,
} from '../../lib/impactTypes';

export type {
  ApiExposureInfo,
  CallerInfo,
  DependencyPath,
  EvidenceItem,
  ImpactAnalysisData,
  ImpactedFileDetail,
  TestImpactItem,
};

interface GraphProps {
  repoName: string;
  impactData: ImpactAnalysisData;
  onReset: () => void;
  /**
   * `full`     — legacy layout: risk sidebar + propagation graph.
   * `graph-only` — canvas only; the surrounding workspace controls headers,
   *                metrics, and evidence. Used by ImpactAnalysisWorkspace.
   */
  variant?: 'full' | 'graph-only';
  /** Suppress the internal scenario line when the workspace already shows one. */
  hideScenarioStrip?: boolean;
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
  direct: `${NODE_BASE} bg-[rgba(242,119,129,0.09)] border border-[#F27781] text-[#F5F7FA] font-medium hover:border-[#FF8D96]`,
  indirect: `${NODE_BASE} bg-[rgba(240,180,41,0.10)] border border-[#F0B429] text-[#F0B429] hover:border-[#D89A24]`,
  component: `${NODE_BASE} bg-[rgba(165,140,255,0.09)] border border-[#A58CFF] text-[#A58CFF] hover:border-[#B9A6FF]`,
  regular: `${NODE_BASE} bg-[#090B0F] border border-[#202631] text-[#B8BEC9] hover:border-[#2A313C] hover:text-[#F5F7FA]`,
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

const ImpactAnalysisGraphInner: React.FC<GraphProps> = ({
  repoName: _repoName,
  impactData,
  onReset,
  variant = 'full',
  hideScenarioStrip = false,
}) => {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [selectedNode, setSelectedNode] = useState<SelectedNodeData | null>(null);
  const [hover, setHover] = useState<HoverInfo | null>(null);

  const canvasRef = useRef<HTMLDivElement>(null);
  const { setViewport } = useReactFlow();

  /** Canvas aspect, bucketed so a resize drag cannot thrash the layout. */
  const [targetAspect, setTargetAspect] = useState(DEFAULT_TARGET_ASPECT);
  const [evidenceFilter, setEvidenceFilter] = useState<'ALL' | 'FACT' | 'INFERENCE' | 'PREDICTION' | 'RECOMMENDATION'>('ALL');
  const [confidenceFilter, setConfidenceFilter] = useState<'ALL' | 'HIGH' | 'MEDIUM' | 'LOW'>('ALL');

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
      let stroke = '#F27781';
      let width = 2;
      let opacity = 0.9;

      if (e.isDotted) {
        stroke = '#7C83FF';
        width = 1.5;
        opacity = 0.68;
      } else if (targetCategory === 'indirect') {
        stroke = '#F0B429';
        width = 1.75;
        opacity = 0.7;
      } else if (targetCategory === 'regular') {
        stroke = '#202631';
        width = 1;
        opacity = 0.4;
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

  const isGraphOnly = variant === 'graph-only';

  return (
    <div className="min-w-0">
      {/* ── Scenario context strip ────────────────────────────────────────── */}
      {scenario && !hideScenarioStrip && !isGraphOnly && (
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
        className={
          isGraphOnly
            ? 'min-w-0'
            : 'grid grid-cols-1 gap-y-8 items-start min-w-0 lg:grid-cols-[minmax(0,30fr)_minmax(0,70fr)] lg:gap-x-7'
        }
      >
        {/* ── Risk intelligence ───────────────────────────────────────────── */}
        {!isGraphOnly && (
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
            {/* Blast radius rating badge */}
            <div className="mt-2 flex items-center gap-2">
              <span
                className={`px-2 py-0.5 rounded-[2px] font-mono text-[10px] uppercase tracking-wider font-semibold border ${
                  (impactData.blast_radius_category === 'XL' || counts.direct + counts.indirect > 15)
                    ? 'bg-danger/15 text-danger border-danger/40'
                    : (impactData.blast_radius_category === 'L' || counts.direct + counts.indirect > 8)
                    ? 'bg-warn/15 text-warn border-warn/40'
                    : (impactData.blast_radius_category === 'M' || counts.direct + counts.indirect > 3)
                    ? 'bg-amber-500/15 text-amber-400 border-amber-500/40'
                    : 'bg-emerald-500/15 text-emerald-400 border-emerald-500/40'
                }`}
              >
                BLAST RADIUS {impactData.blast_radius_category || (counts.direct + counts.indirect > 15 ? 'XL' : counts.direct + counts.indirect > 8 ? 'L' : counts.direct + counts.indirect > 3 ? 'M' : 'S')}
              </span>
            </div>
            <p className="text-[12px] text-text-muted leading-relaxed mt-1.5 max-w-sm">
              Deterministic impact radius based on call graph traversal and API exposure.
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
            <LeaderRow label="DIRECT CALLERS">
              <span className="font-mono text-[13px] text-text tabular-nums">
                {impactData.direct_callers?.length ?? 0}
              </span>
            </LeaderRow>
            <LeaderRow label="EXPOSED ROUTES">
              <span className="font-mono text-[13px] text-primary tabular-nums">
                {impactData.api_exposure?.public_routes?.length ?? 0}
              </span>
            </LeaderRow>
            <LeaderRow label="AFFECTED TESTS">
              <span className="font-mono text-[13px] text-warn tabular-nums">
                {impactData.affected_tests?.length ?? 0}
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

          {/* Implementation Sequence */}
          {impactData.implementation_order && impactData.implementation_order.length > 0 && (
            <div className="mt-4 pt-3 border-t border-white/[0.055] min-w-0">
              <span className="mono-label block mb-2 text-text">IMPLEMENTATION SEQUENCE</span>
              <ol className="space-y-1.5 font-mono text-[11px] text-text-muted leading-relaxed">
                {impactData.implementation_order.map((step, idx) => (
                  <li key={idx} className="flex items-start gap-2 bg-white/[0.02] border border-white/[0.04] p-1.5 rounded-[2px]">
                    <span className="text-primary font-semibold shrink-0">{idx + 1}.</span>
                    <span className="break-words">{step}</span>
                  </li>
                ))}
              </ol>
            </div>
          )}

          {/* Developer Safety Operating Breakdown */}
          <div className="mt-4 min-w-0 border-t border-white/[0.055] pt-3">
            <span className="mono-label block mb-2 text-text">DEVELOPER SAFETY READOUT</span>
            <dl className="min-w-0 border-t border-white/[0.055]">
              <LeaderRow label="VERIFIED IMPACT" first>
                <span className="font-mono text-[13px] text-danger font-semibold tabular-nums">
                  {impactData.verified_impact_count ?? (impactData.high_confidence_files?.length ?? 0)}
                </span>
              </LeaderRow>
              <LeaderRow label="LIKELY IMPACT">
                <span className="font-mono text-[13px] text-warn tabular-nums">
                  {impactData.likely_impact_count ?? (impactData.medium_confidence_files?.length ?? 0)}
                </span>
              </LeaderRow>
              <LeaderRow label="CANDIDATES">
                <span className="font-mono text-[13px] text-text-subtle tabular-nums">
                  {impactData.candidate_count ?? (impactData.low_confidence_files?.length ?? 0)}
                </span>
              </LeaderRow>
            </dl>
          </div>

          {/* Confidence-Aware Impact Details */}
          {impactData.impacted_file_details && impactData.impacted_file_details.length > 0 && (() => {
            const details = impactData.impacted_file_details;
            const filteredDetails = confidenceFilter === 'ALL'
              ? details
              : details.filter((d) => d.confidence_tier === confidenceFilter);

            return (
              <div className="mt-4 pt-3 border-t border-white/[0.055] min-w-0">
                <div className="flex items-center justify-between mb-2">
                  <span className="mono-label text-text">CONFIDENCE TIERS</span>
                  <span className="mono-detail text-[10px] tabular-nums">
                    {filteredDetails.length} / {details.length}
                  </span>
                </div>
                <div className="flex items-center gap-1 mb-2.5 overflow-x-auto pb-1 text-[9px] font-mono">
                  {(['ALL', 'HIGH', 'MEDIUM', 'LOW'] as const).map((tier) => (
                    <button
                      key={tier}
                      type="button"
                      onClick={() => setConfidenceFilter(tier)}
                      className={`px-1.5 py-0.5 rounded-[2px] transition-colors ${
                        confidenceFilter === tier
                          ? tier === 'HIGH'
                            ? 'bg-danger/20 text-danger border border-danger/50'
                            : tier === 'MEDIUM'
                            ? 'bg-warn/20 text-warn border border-warn/50'
                            : 'bg-white/10 text-text border border-white/30'
                          : 'text-text-muted hover:text-text border border-transparent'
                      }`}
                    >
                      {tier}
                    </button>
                  ))}
                </div>
                <div className="space-y-1.5 max-h-56 overflow-y-auto pr-1">
                  {filteredDetails.slice(0, 15).map((detail, idx) => (
                    <div
                      key={idx}
                      className="p-1.5 rounded-[2px] bg-white/[0.015] border border-white/[0.04] text-[10.5px] font-mono"
                    >
                      <div className="flex items-center justify-between gap-2 mb-1">
                        <span
                          className={`text-[9px] px-1 py-0.2 rounded font-semibold ${
                            detail.confidence_tier === 'HIGH'
                              ? 'bg-danger/20 text-danger'
                              : detail.confidence_tier === 'MEDIUM'
                              ? 'bg-warn/20 text-warn'
                              : 'bg-white/10 text-text-subtle'
                          }`}
                        >
                          {detail.confidence_tier}
                        </span>
                        <span className="text-[9px] text-text-subtle truncate max-w-[120px]">
                          {detail.evidence_strength}
                        </span>
                      </div>
                      <div className="text-text font-medium text-[11px] truncate mb-0.5">
                        {detail.file_path}
                      </div>
                      <p className="text-text-muted leading-tight break-words text-[10px]">
                        {detail.reason}
                      </p>
                      {detail.propagation_path && detail.propagation_path.length > 1 && (
                        <div className="mt-1 text-[9px] text-text-subtle flex items-center gap-1 overflow-x-auto">
                          <span>path:</span>
                          <span className="text-primary font-mono">{detail.propagation_path.join(' → ')}</span>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            );
          })()}

          {/* Ground-truth Evidence Audit */}
          {impactData.evidence_items && impactData.evidence_items.length > 0 && (() => {
            const evidenceItems = impactData.evidence_items;
            const filteredEvidence = evidenceFilter === 'ALL'
              ? evidenceItems
              : evidenceItems.filter((e) => e.kind === evidenceFilter);

            return (
              <div className="mt-4 pt-3 border-t border-white/[0.055] min-w-0">
                <div className="flex items-center justify-between mb-2">
                  <span className="mono-label text-text">EVIDENCE AUDIT</span>
                  <span className="mono-detail text-[10px] tabular-nums">
                    {filteredEvidence.length} / {evidenceItems.length}
                  </span>
                </div>
                <div className="flex items-center gap-1 mb-2.5 overflow-x-auto pb-1 text-[9px] font-mono">
                  {(['ALL', 'FACT', 'INFERENCE', 'PREDICTION', 'RECOMMENDATION'] as const).map((kind) => (
                    <button
                      key={kind}
                      type="button"
                      onClick={() => setEvidenceFilter(kind)}
                      className={`px-1.5 py-0.5 rounded-[2px] transition-colors ${
                        evidenceFilter === kind
                          ? 'bg-primary/20 text-primary border border-primary/50'
                          : 'text-text-muted hover:text-text border border-transparent'
                      }`}
                    >
                      {kind}
                    </button>
                  ))}
                </div>
                <div className="space-y-1.5 max-h-56 overflow-y-auto pr-1">
                  {filteredEvidence.slice(0, 15).map((ev, idx) => (
                    <div
                      key={idx}
                      className="p-1.5 rounded-[2px] bg-white/[0.015] border border-white/[0.04] text-[10.5px] font-mono"
                    >
                      <div className="flex items-center justify-between gap-2 mb-1">
                        <span
                          className={`text-[9px] px-1 py-0.2 rounded font-semibold ${
                            ev.kind === 'FACT'
                              ? 'bg-[rgba(53,214,163,0.09)] text-[#35D6A3] border border-[rgba(53,214,163,0.34)]'
                              : ev.kind === 'INFERENCE'
                              ? 'bg-[rgba(165,140,255,0.09)] text-[#A58CFF] border border-[rgba(165,140,255,0.30)]'
                              : ev.kind === 'PREDICTION'
                              ? 'bg-[rgba(240,180,41,0.10)] text-[#F0B429] border border-[rgba(240,180,41,0.38)]'
                              : 'bg-[rgba(124,131,255,0.10)] text-[#7C83FF] border border-[rgba(124,131,255,0.38)]'
                          }`}
                        >
                          {ev.kind}
                        </span>
                        {ev.source_reference && (
                          <span className="text-[9px] text-text-subtle truncate max-w-[120px]">
                            {ev.source_reference}
                          </span>
                        )}
                      </div>
                      <p className="text-text-muted leading-tight break-words">{ev.statement}</p>
                    </div>
                  ))}
                </div>
              </div>
            );
          })()}

          {/* Affected Tests Detail */}
          {impactData.affected_tests && impactData.affected_tests.length > 0 && (
            <div className="mt-4 pt-3 border-t border-white/[0.055] min-w-0">
              <div className="flex items-center justify-between mb-2">
                <span className="mono-label text-text">AFFECTED TESTS</span>
                <span className="mono-detail text-[10px] tabular-nums">
                  {impactData.affected_tests.length}
                </span>
              </div>
              <div className="space-y-1.5 max-h-52 overflow-y-auto pr-1">
                {impactData.affected_tests.slice(0, 15).map((test, idx) => (
                  <div
                    key={idx}
                    className="p-1.5 rounded-[2px] bg-white/[0.015] border border-white/[0.04] text-[10.5px] font-mono"
                  >
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <span
                        className={`text-[9px] px-1 py-0.2 rounded font-semibold ${
                          test.confidence_tier === 'HIGH' || test.impact_type === 'DIRECT TEST IMPACT'
                            ? 'bg-danger/20 text-danger'
                            : test.confidence_tier === 'MEDIUM' || test.impact_type === 'LIKELY TEST IMPACT'
                            ? 'bg-warn/20 text-warn'
                            : 'bg-white/10 text-text-subtle'
                        }`}
                      >
                        {test.confidence_tier || 'HIGH'}
                      </span>
                      <span className="text-[9px] text-text-subtle truncate max-w-[120px]">
                        {test.evidence_strength || test.impact_type}
                      </span>
                    </div>
                    <div className="text-text font-medium text-[11px] truncate mb-0.5">
                      {test.test_file}
                    </div>
                    <p className="text-text-muted leading-tight break-words text-[10px]">
                      {test.reason}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
        )}

        {/* ── Impact propagation graph ────────────────────────────────────── */}
        <div
          className={
            isGraphOnly
              ? 'min-w-0'
              : 'min-w-0 lg:pl-7 lg:border-l lg:border-white/[0.055]'
          }
        >
          <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2 pb-2.5 hair-b">
            <h3 className="mono-label text-text">IMPACT PROPAGATION GRAPH</h3>
            <div className="flex items-center gap-x-4 gap-y-1 flex-wrap shrink-0">
              <LegendDot tone="bg-danger" label="DIRECT" />
              <LegendDot tone="bg-warn" label="DOWNSTREAM" />
              <LegendDot tone="bg-primary" label="COMPONENT" />
              {/* Counts read brighter than the legend they sit beside. */}
              <span className="font-mono text-[10px] tracking-[0.14em] text-text-muted tabular-nums">
                {nodes.length} NODES · {edges.length} EDGES
              </span>
            </div>
          </div>

          <div
            ref={canvasRef}
            className={`impact-canvas relative mt-3 min-w-0 border border-white/[0.055] overflow-hidden ${
              nodes.length <= 3 ? 'h-[22rem]' : 'h-[clamp(26rem,calc(100vh-18rem),44rem)]'
            }`}
            style={{ backgroundColor: '#020304' }}
          >
            {nodes.length === 0 ? (
              <div className="absolute inset-0 flex items-center justify-center p-6 text-center font-mono">
                <div className="max-w-md space-y-2">
                  <span className="mono-label block text-text">NO PROPAGATION GRAPH AVAILABLE</span>
                  <p className="text-[12px] text-text-muted leading-relaxed">
                    Static dependency and call graph analysis detected no propagation edges or import relationships for the identified modification targets.
                  </p>
                </div>
              </div>
            ) : (
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
                    if (cat === 'direct') return '#F27781';
                    if (cat === 'indirect') return '#F0B429';
                    if (cat === 'component') return '#7C83FF';
                    return '#090B0F';
                  }}
                  maskColor="rgba(5, 6, 8, 0.74)"
                  style={{
                    backgroundColor: '#050608',
                    border: '1px solid #202631',
                    width: 128,
                    height: 88,
                  }}
                />
                <Background color="rgba(255,255,255,0.07)" gap={18} />
              </ReactFlow>
            )}

            {/* ── Hover micro-inspector ─────────────────────────────────── */}
            {hover && !selectedNode && (
              <div
                className="pointer-events-none absolute left-3 bottom-3 z-20 max-w-[18rem]
                           border border-white/10 bg-[#090B0E]/95 px-3 py-2 rounded-md"
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
                           border-white/10 bg-[#090B0E] backdrop-blur-[12px]
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

                  {/* Smart actions — wired to ARIA navigation and chat */}
                  <div className="mt-4 pt-3 border-t border-white/[0.055] min-w-0">
                    <div className="flex items-baseline justify-between gap-3 mb-2.5">
                      <span className="mono-label" style={{ fontSize: 9 }}>
                        INVESTIGATION ACTIONS
                      </span>
                      <span className="mono-detail shrink-0 text-emerald-400" style={{ fontSize: 9 }}>
                        READY
                      </span>
                    </div>

                    <button
                      type="button"
                      onClick={() => {
                        const target = selectedNode.id.replace(/^component-/, '');
                        window.dispatchEvent(
                          new CustomEvent('aria-open-graph', {
                            detail: { file: target, path: target, source: 'impact_analysis' },
                          })
                        );
                        window.dispatchEvent(
                          new CustomEvent('aria-navigate-tab', {
                            detail: { tab: 'graph', file: target },
                          })
                        );
                      }}
                      className="w-full flex items-center justify-between gap-2 border border-white/[0.07] bg-[#0C0E12]
                                 px-2.5 py-1.5 rounded-md font-mono text-[10px] uppercase
                                 tracking-[0.14em] text-[#F4F4F5] hover:border-[#7C83FF]/50 hover:text-[#7C83FF] transition-colors cursor-pointer"
                    >
                      <span className="flex items-center gap-2">
                        <Layers className="h-3 w-3 shrink-0" aria-hidden="true" />
                        View in File Graph
                      </span>
                      <ArrowRight className="h-2.5 w-2.5 shrink-0" aria-hidden="true" />
                    </button>

                    <ul className="mt-2 space-y-1.5 min-w-0">
                      <li>
                        <button
                          type="button"
                          onClick={() => {
                            const target = selectedNode.id.replace(/^component-/, '');
                            window.dispatchEvent(
                              new CustomEvent('aria-navigate-tab', {
                                detail: { tab: 'call_graph', file: target },
                              })
                            );
                          }}
                          className="w-full flex items-center gap-2 font-mono text-[10px] uppercase
                                     tracking-[0.14em] text-text-muted hover:text-text transition-colors cursor-pointer"
                        >
                          <ExternalLink className="h-3 w-3 shrink-0" aria-hidden="true" />
                          <span>Inspect in Call Graph</span>
                        </button>
                      </li>
                      <li>
                        <button
                          type="button"
                          onClick={() => {
                            const target = selectedNode.id.replace(/^component-/, '');
                            const prompt = `What is the architectural and functional blast radius of modifying ${target} in ${impactData.repo}?`;
                            window.dispatchEvent(
                              new CustomEvent('aria-open-chat', {
                                detail: { prompt, source: 'impact_analysis' },
                              })
                            );
                            window.dispatchEvent(
                              new CustomEvent('aria-navigate-tab', {
                                detail: { tab: 'chat' },
                              })
                            );
                          }}
                          className="w-full flex items-center gap-2 font-mono text-[10px] uppercase
                                     tracking-[0.14em] text-text-muted hover:text-text transition-colors cursor-pointer"
                        >
                          <MessageSquare className="h-3 w-3 shrink-0 text-primary" aria-hidden="true" />
                          <span>Ask about impact in Chat</span>
                        </button>
                      </li>
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
