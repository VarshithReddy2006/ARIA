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
import dagre from 'dagre';
import 'reactflow/dist/style.css';
import { CATEGORY_COLORS } from './types';
import type { GraphNode, GraphEdge } from './types';
import { useGraphWorkspace } from './workspaceStore';

// ---------------------------------------------------------------------------
// Layout
// ---------------------------------------------------------------------------

const NODE_W = 200;
const NODE_H = 40;

function applyDagreLayout(
  rfNodes: Node[],
  rfEdges: Edge[],
  direction: 'TB' | 'LR' = 'TB',
): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: direction, ranksep: 60, nodesep: 40 });

  rfNodes.forEach((n) => g.setNode(n.id, { width: NODE_W, height: NODE_H }));
  rfEdges.forEach((e) => g.setEdge(e.source, e.target));
  dagre.layout(g);

  const laid = rfNodes.map((n) => {
    const pos = g.node(n.id);
    return {
      ...n,
      position: { x: pos.x - NODE_W / 2, y: pos.y - NODE_H / 2 },
    };
  });
  return { nodes: laid, edges: rfEdges };
}

function nodeClassName(
  category: string,
  highlighted: boolean,
  isFocus: boolean,
  isDimmed: boolean,
  heatmapMode: string,
  degree: number,
): string {
  const base =
    'rounded px-3 py-2 text-center text-xs font-mono truncate shadow cursor-pointer transition-all duration-200';
  const dim = isDimmed ? 'opacity-20 scale-95' : 'opacity-100';

  if (heatmapMode !== 'none') {
    if (heatmapMode === 'coupling' || heatmapMode === 'fan_out') {
      if (degree > 10) return `${base} ${dim} !bg-red-950/80 !border-2 !border-red-500 !text-red-300 font-bold`;
      if (degree > 5) return `${base} ${dim} !bg-amber-950/80 !border-2 !border-amber-500 !text-amber-300 font-bold`;
      return `${base} ${dim} !bg-zinc-900 !border !border-zinc-700 !text-zinc-400`;
    }
    if (heatmapMode === 'complexity' || heatmapMode === 'violations') {
      if (category === 'high_coupling') return `${base} ${dim} !bg-rose-950/90 !border-2 !border-rose-500 !text-rose-300 font-bold animate-pulse`;
      return `${base} ${dim} !bg-slate-900 !border !border-slate-800 !text-slate-400`;
    }
  }

  if (isFocus)
    return `${base} ${dim} !bg-white/20 !border-2 !border-white !text-white shadow-lg shadow-white/10 hover:!bg-white/30`;

  if (highlighted) {
    return `${base} ${dim} !bg-amber-950/60 !border-2 !border-amber-400 !text-amber-300 shadow-lg shadow-amber-500/10 hover:!bg-amber-900/40`;
  }

  switch (category) {
    case 'entry_point':
      return `${base} ${dim} !bg-emerald-950/60 !border-2 !border-emerald-500 !text-emerald-400 font-semibold shadow-emerald-500/5 hover:!bg-emerald-900/40`;
    case 'core_module':
      return `${base} ${dim} !bg-blue-950/60 !border-2 !border-blue-500 !text-blue-400 font-semibold shadow-blue-500/5 hover:!bg-blue-900/40`;
    case 'high_coupling':
      return `${base} ${dim} !bg-orange-950/60 !border !border-orange-500 !text-orange-400 hover:!bg-orange-900/40`;
    case 'directory':
      return `${base} ${dim} !bg-purple-950/60 !border !border-purple-500 !text-purple-400 font-semibold hover:!bg-purple-900/40`;
    case 'service':
      return `${base} ${dim} !bg-indigo-950/60 !border !border-indigo-500 !text-indigo-400 font-semibold hover:!bg-indigo-900/40`;
    case 'controller':
      return `${base} ${dim} !bg-pink-950/60 !border !border-pink-500 !text-pink-400 font-semibold hover:!bg-pink-900/40`;
    default:
      return `${base} ${dim} !bg-zinc-900 !border !border-zinc-700 !text-zinc-300 hover:!border-zinc-500`;
  }
}

export function toReactFlowNodes(apiNodes: GraphNode[], activeNodeId: string | null, neighborIds: Set<string>, heatmapMode: string): Node[] {
  return apiNodes.map((n) => {
    const isDimmed = activeNodeId !== null && !neighborIds.has(n.id);
    return {
      id: n.id,
      type: 'default',
      data: { label: n.label, raw: n },
      className: nodeClassName(n.category, n.highlighted, n.is_focus, isDimmed, heatmapMode, n.degree),
      position: { x: 0, y: 0 },
    };
  });
}

export function toReactFlowEdges(apiEdges: GraphEdge[], categoryMap: Map<string, string>, activeNodeId: string | null, pathNodes: string[]): Edge[] {
  const pathSet = new Set(pathNodes);
  return apiEdges.map((e) => {
    const isPathEdge = pathSet.size > 1 && pathSet.has(e.source) && pathSet.has(e.target);
    const isConnected = activeNodeId !== null && (e.source === activeNodeId || e.target === activeNodeId);
    const isDimmed = activeNodeId !== null && !isConnected && !isPathEdge;
    const isIncoming = activeNodeId !== null && e.target === activeNodeId;
    const isOutgoing = activeNodeId !== null && e.source === activeNodeId;

    let strokeColor = '#4b5563';
    if (isPathEdge) strokeColor = '#f43f5e'; // rose-500 for path trace
    else if (isIncoming) strokeColor = '#10b981';
    else if (isOutgoing) strokeColor = '#6366f1';
    else {
      const srcCategory = categoryMap.get(e.source) ?? 'regular';
      if (srcCategory === 'entry_point') strokeColor = '#10b981';
      else if (srcCategory === 'core_module') strokeColor = '#3b82f6';
      else if (srcCategory === 'high_coupling') strokeColor = '#f97316';
      else if (srcCategory === 'directory') strokeColor = '#a855f7';
    }

    return {
      id: `${e.source}→${e.target}`,
      source: e.source,
      target: e.target,
      animated: isPathEdge || isConnected || e.relationship === 'imports',
      style: {
        stroke: strokeColor,
        strokeWidth: isPathEdge ? 3.5 : isConnected ? 2.5 : 1.5,
        opacity: isDimmed ? 0.15 : 1.0,
      },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        width: 12,
        height: 12,
        color: strokeColor,
      },
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
      fitViewRef.current = () => instance.fitView({ padding: 0.15, duration: 300 });
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
      minZoom={0.05}
      maxZoom={2.5}
      nodesDraggable
      nodesConnectable={false}
      elementsSelectable
    >
      <Controls showInteractive={false} />
      <PanControls />
      <MiniMap
        nodeColor={(node) => {
          const raw: GraphNode | undefined = node.data?.raw;
          if (!raw) return '#27272a';
          if (raw.is_focus) return '#ffffff';
          if (raw.highlighted) return '#f59e0b';
          return CATEGORY_COLORS[raw.category] ?? '#71717a';
        }}
        maskColor="rgba(15, 23, 42, 0.75)"
        className="!bg-slate-950/95 !border-slate-800/80 !rounded-xl !shadow-float overflow-hidden"
        nodeStrokeWidth={0}
        nodeBorderRadius={5}
      />
      <Background color="#27272a" gap={16} />
    </ReactFlow>
  );
};
