import React, { useCallback, useEffect, useRef, useMemo } from 'react';
import ReactFlow, {
  MiniMap,
  Controls,
  Background,
  useNodesState,
  useEdgesState,
  MarkerType,
  type Node,
  type Edge,
} from 'reactflow';
import { PanControls } from './PanControls';
import 'reactflow/dist/style.css';
import { CATEGORY_COLORS } from './types';
import type { GraphNode, GraphEdge } from './types';
import { useGraphWorkspace } from './workspaceStore';
import { applyDagreLayout, NODE_W, NODE_H } from './dagreLayout';
import {
  buildMutualPairSet,
  edgeFocusRole,
  edgeTransition,
  isMutual,
  resolveDependencyEdgeStyle,
  resolveFocusChoreography,
} from './edgeSemantics';
export { applyDagreLayout, NODE_W, NODE_H };

function nodeClassName(
  category: string,
  highlighted: boolean,
  isFocus: boolean,
  isDimmed: boolean,
  isNeighbor: boolean,
  heatmapMode: string,
  degree: number,
): string {
  const base =
    'rounded px-3 py-2 text-center text-xs font-mono truncate cursor-pointer transition-all duration-200 border';
  /*
    Background topology recedes by opacity alone. It used to also shrink, which
    changed node geometry on every selection and made the unrelated graph look
    broken rather than subdued. It stays visible — 0.16 is legible against the
    near-black canvas — because the surrounding shape is still information.
  */
  const dim = isDimmed ? 'opacity-[0.16]' : 'opacity-100';

  if (heatmapMode !== 'none') {
    if (heatmapMode === 'coupling' || heatmapMode === 'fan_out') {
      if (degree > 10) return `${base} ${dim} !bg-red-950/80 !border-red-500 !text-red-300 font-bold`;
      if (degree > 5) return `${base} ${dim} !bg-amber-950/80 !border-amber-500 !text-amber-300 font-bold`;
      return `${base} ${dim} !bg-zinc-900 !border-zinc-800 !text-zinc-400`;
    }
    if (heatmapMode === 'complexity' || heatmapMode === 'violations') {
      // Colour alone carries the severity — a permanently pulsing node reads as
      // live activity rather than as a static classification.
      if (category === 'high_coupling') return `${base} ${dim} !bg-rose-950/90 !border-rose-500 !text-rose-300 font-bold`;
      return `${base} ${dim} !bg-zinc-900 !border-zinc-800 !text-zinc-400`;
    }
  }

  if (isFocus) {
    return `${base} ${dim} !bg-zinc-900 !border-indigo-400 !text-white ring-1 ring-indigo-500/50 shadow-[0_0_20px_rgba(99,102,241,0.15)] font-bold scale-[1.03] z-20`;
  }

  if (isNeighbor) {
    return `${base} ${dim} !bg-zinc-900/95 !border-zinc-500 !text-zinc-200 shadow-sm z-10 hover:!border-zinc-300`;
  }

  if (highlighted) {
    return `${base} ${dim} !bg-amber-950/50 !border-amber-400 !text-amber-200 shadow-lg shadow-amber-500/10 hover:!bg-amber-900/40`;
  }

  switch (category) {
    case 'entry_point':
      return `${base} ${dim} !bg-zinc-900/90 !border-emerald-500/60 !text-emerald-300 font-medium hover:!border-emerald-400`;
    case 'core_module':
      return `${base} ${dim} !bg-zinc-900/90 !border-blue-500/60 !text-blue-300 font-medium hover:!border-blue-400`;
    case 'high_coupling':
      return `${base} ${dim} !bg-zinc-900/90 !border-amber-500/60 !text-amber-300 hover:!border-amber-400`;
    case 'directory':
      return `${base} ${dim} !bg-zinc-900/90 !border-purple-500/60 !text-purple-300 font-medium hover:!border-purple-400`;
    case 'service':
      return `${base} ${dim} !bg-zinc-900/90 !border-indigo-500/60 !text-indigo-300 font-medium hover:!border-indigo-400`;
    case 'controller':
      return `${base} ${dim} !bg-zinc-900/90 !border-pink-500/60 !text-pink-300 font-medium hover:!border-pink-400`;
    case 'test':
      return `${base} ${dim} !bg-zinc-900/90 !border-cyan-500/50 !text-cyan-300 hover:!border-cyan-400`;
    default:
      return `${base} ${dim} !bg-zinc-900/80 !border-zinc-800 !text-zinc-300 hover:!border-zinc-600`;
  }
}

export function toReactFlowNodes(apiNodes: GraphNode[], activeNodeId: string | null, neighborIds: Set<string>, heatmapMode: string): Node[] {
  return apiNodes.map((n) => {
    const isFocus = n.id === activeNodeId;
    const isNeighbor = activeNodeId !== null && !isFocus && neighborIds.has(n.id);
    const isDimmed = activeNodeId !== null && !isFocus && !isNeighbor;

    /*
      Architecture is a topology, so related nodes resolve together and the
      unrelated graph recedes just behind them. The focus itself never waits.
      Only a delay is applied — the node already transitions.
    */
    const choreo = resolveFocusChoreography(
      activeNodeId === null ? 'idle' : isFocus ? 'focus' : isNeighbor ? 'incoming' : 'unrelated',
      'architecture',
    );

    return {
      id: n.id,
      type: 'default',
      data: { label: n.label, raw: n },
      className: `${nodeClassName(n.category, n.highlighted, isFocus, isDimmed, isNeighbor, heatmapMode, n.degree)}${
        // A single luminance peak on the node ARIA just identified. The class is
        // keyed to the focus, so it is re-applied — and re-runs once — per
        // selection, and never appears on any other node.
        isFocus ? ' gnode-identified' : ''
      }`,
      style: { transitionDelay: `${choreo.delayMs}ms` },
      position: { x: 0, y: 0 },
    };
  });
}

export function toReactFlowEdges(apiEdges: GraphEdge[], categoryMap: Map<string, string>, activeNodeId: string | null, pathNodes: string[]): Edge[] {
  const pathSet = new Set(pathNodes);
  // Cycles are derived from the edge list already on screen — one O(E) pass.
  const mutualPairs = buildMutualPairSet(apiEdges);

  return apiEdges.map((e) => {
    const isPathEdge = pathSet.size > 1 && pathSet.has(e.source) && pathSet.has(e.target);
    const isIncoming = activeNodeId !== null && e.target === activeNodeId;
    const isOutgoing = activeNodeId !== null && e.source === activeNodeId;

    // Resting colour follows the source's architectural category.
    let idleTone: string | undefined;
    if (!activeNodeId) {
      const srcCategory = categoryMap.get(e.source) ?? 'regular';
      if (srcCategory === 'entry_point') idleTone = '#059669';
      else if (srcCategory === 'core_module') idleTone = '#2563eb';
      else if (srcCategory === 'high_coupling') idleTone = '#d97706';
    }

    const visual = resolveDependencyEdgeStyle({
      isPath: isPathEdge,
      isOutgoing,
      isIncoming,
      isCyclic: isMutual(mutualPairs, e.source, e.target),
      hasActive: activeNodeId !== null,
      idleTone,
    });

    const choreo = resolveFocusChoreography(
      edgeFocusRole({ isIncoming, isOutgoing, hasActive: activeNodeId !== null }),
      'architecture',
    );

    return {
      id: `${e.source}→${e.target}`,
      source: e.source,
      target: e.target,
      /*
        Never animated. React Flow's `animated` paints its own marching dashes,
        which would overwrite the dash patterns that carry the relationship
        meaning — and a permanently moving edge reads as live traffic rather than
        a static dependency.
      */
      animated: false,
      style: {
        stroke: visual.stroke,
        strokeWidth: visual.strokeWidth,
        opacity: visual.opacity,
        strokeDasharray: visual.dash,
        /*
          The relationship changes state in one short transition rather than
          snapping. Bounded and one-shot: it finishes and stops, so the topology
          never carries continuous motion.
        */
        transition: edgeTransition(choreo),
      },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        width: 10,
        height: 10,
        color: visual.stroke,
      },
      // A cycle gets a head at both ends, so direction is not colour-only.
      ...(visual.bothEnds
        ? {
            markerStart: {
              type: MarkerType.ArrowClosed,
              width: 10,
              height: 10,
              color: visual.stroke,
            },
          }
        : {}),
    };
  });
}

interface GraphCanvasProps {
  apiNodes: GraphNode[];
  apiEdges: GraphEdge[];
  onNodeSelect: (node: GraphNode | null) => void;
  fitViewRef: React.MutableRefObject<(() => void) | null>;
}

export const GraphCanvas: React.FC<GraphCanvasProps> = ({
  apiNodes,
  apiEdges,
  onNodeSelect,
  fitViewRef,
}) => {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const rfRef = useRef<any>(null);

  const { selectedNodeId, hoveredNodeId, hoverNode, activeFilters, focusMode, heatmapMode, dependencyPath } = useGraphWorkspace();
  const activeNodeId = hoveredNodeId || selectedNodeId;
  const pathNodes = dependencyPath?.path_nodes || [];

  // Filter nodes based on active filter bar chips
  const filteredNodes = useMemo(() => {
    if (activeFilters.length === 0) return apiNodes;
    return apiNodes.filter((n) => activeFilters.includes(n.category));
  }, [apiNodes, activeFilters]);

  // Compute neighbor node IDs for hover/selection highlight
  const neighborIds = useMemo(() => {
    if (!activeNodeId) return new Set<string>();
    const set = new Set<string>([activeNodeId]);
    apiEdges.forEach((e) => {
      if (e.source === activeNodeId) set.add(e.target);
      if (e.target === activeNodeId) set.add(e.source);
    });
    return set;
  }, [activeNodeId, apiEdges]);

  // Hovered node object for micro-inspector tooltip
  const hoveredNode = useMemo(() => {
    if (!hoveredNodeId || hoveredNodeId === selectedNodeId) return null;
    return apiNodes.find((n) => n.id === hoveredNodeId) ?? null;
  }, [hoveredNodeId, selectedNodeId, apiNodes]);

  // Focus mode filtering
  const visibleNodes = useMemo(() => {
    if (!focusMode || !selectedNodeId) return filteredNodes;
    return filteredNodes.filter((n) => neighborIds.has(n.id));
  }, [filteredNodes, focusMode, selectedNodeId, neighborIds]);

  useEffect(() => {
    const rfNodes = toReactFlowNodes(visibleNodes, activeNodeId, neighborIds, heatmapMode);
    const categoryMap = new Map<string, string>();
    visibleNodes.forEach((n) => categoryMap.set(n.id, n.category));
    const rfEdges = toReactFlowEdges(apiEdges, categoryMap, activeNodeId, pathNodes);

    const { nodes: laid, edges: laidEdges } = applyDagreLayout(rfNodes, rfEdges, 'TB');
    setNodes(laid);
    setEdges(laidEdges);
  }, [visibleNodes, apiEdges, activeNodeId, neighborIds, setNodes, setEdges]);

  const onInit = useCallback(
    (instance: any) => {
      rfRef.current = instance;
      fitViewRef.current = () => instance.fitView({ padding: 0.15, duration: 300, minZoom: 0.15, maxZoom: 1.5 });
    },
    [fitViewRef],
  );

  const handleNodeClick = useCallback(
    (_evt: React.MouseEvent, node: Node) => {
      onNodeSelect(node.data?.raw ?? null);
    },
    [onNodeSelect],
  );

  const handleNodeMouseEnter = useCallback(
    (_evt: React.MouseEvent, node: Node) => {
      hoverNode(node.id);
    },
    [hoverNode],
  );

  const handleNodeMouseLeave = useCallback(() => {
    hoverNode(null);
  }, [hoverNode]);

  const handlePaneClick = useCallback(() => {
    onNodeSelect(null);
    hoverNode(null);
  }, [onNodeSelect, hoverNode]);

  return (
    <div className="relative w-full h-full bg-[#030303]">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        onNodeMouseEnter={handleNodeMouseEnter}
        onNodeMouseLeave={handleNodeMouseLeave}
        onPaneClick={handlePaneClick}
        onInit={onInit}
        fitView
        fitViewOptions={{ padding: 0.15, minZoom: 0.15, maxZoom: 1.5 }}
        minZoom={0.05}
        maxZoom={2.5}
        nodesDraggable
        nodesConnectable={false}
        elementsSelectable
      >
        <Controls showInteractive={false} className="!bg-zinc-950/80 !border-zinc-800/80 !rounded-lg backdrop-blur-sm" />
        <PanControls />
        <MiniMap
          nodeColor={(node) => {
            const raw: GraphNode | undefined = node.data?.raw;
            if (!raw) return '#27272a';
            if (raw.is_focus) return '#818cf8';
            if (raw.highlighted) return '#f59e0b';
            return CATEGORY_COLORS[raw.category] ?? '#71717a';
          }}
          maskColor="rgba(3, 3, 3, 0.85)"
          className="!bg-zinc-950/95 !border-zinc-800/80 !rounded-lg overflow-hidden"
          nodeStrokeWidth={0}
          nodeBorderRadius={3}
        />
        <Background color="#1e1e24" gap={18} size={1} />
      </ReactFlow>

      {/* Hover Micro-Inspector Tooltip */}
      {hoveredNode && (
        <div
          role="tooltip"
          className="absolute bottom-4 right-4 z-20 bg-zinc-950/95 border border-zinc-800 text-xs font-mono p-3 rounded-lg shadow-2xl max-w-xs backdrop-blur-sm pointer-events-none animate-in fade-in duration-150"
        >
          <div className="flex items-center gap-1.5 mb-1">
            <span
              className="h-1.5 w-1.5 rounded-full"
              style={{ backgroundColor: CATEGORY_COLORS[hoveredNode.category] ?? '#a1a1aa' }}
            />
            <span className="text-[10px] uppercase font-bold text-zinc-400">
              {hoveredNode.category.replace('_', ' ')}
            </span>
            {hoveredNode.language && (
              <span className="text-[9px] text-zinc-500 ml-auto">{hoveredNode.language}</span>
            )}
          </div>
          <div className="font-semibold text-zinc-100 truncate text-[11px]">{hoveredNode.label}</div>
          <div className="text-[9px] text-zinc-400 truncate mb-2">{hoveredNode.id}</div>
          <div className="flex items-center justify-between text-[10px] text-zinc-400 border-t border-zinc-800/80 pt-1.5">
            <span>Degree: <strong className="text-zinc-200">{hoveredNode.degree}</strong></span>
            <span>Centrality: <strong className="text-zinc-200">{(hoveredNode.centrality * 100).toFixed(1)}%</strong></span>
          </div>
        </div>
      )}
    </div>
  );
};
