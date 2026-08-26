/**
 * CallGraphAnalyzer — Function Call Graph architectural intelligence instrument.
 *
 * Provides function-to-function dependency analysis, blast radius estimation,
 * caller/callee tracing, recursion detection, and function-level telemetry.
 */

import React, { useState, useCallback, useEffect, useRef, useMemo } from 'react';
import ReactFlow, {
  Background,
  MiniMap,
  useNodesState,
  useEdgesState,
  ReactFlowProvider,
  Position,
  MarkerType,
  Handle,
  useReactFlow,
} from 'reactflow';
import 'reactflow/dist/style.css';

import { apiUrl, extractErrorMessage } from '../../lib/api';
import { Button } from '../ui/Button';
import { Badge } from '../ui/Badge';
import { MetricCard } from '../ui/MetricCard';
import { EmptyState } from '../ui/EmptyState';
import { SkeletonCard, SkeletonGroup, Skeleton } from '../ui/Skeleton';
import {
  Workflow, Zap, AlertTriangle, ArrowUpFromLine,
  ArrowDownToLine, RefreshCw, Search, X,
  Code2, GitBranch, Repeat2, Info, ZoomIn, ZoomOut, Maximize,
  Sparkles, ExternalLink, ArrowRight, ArrowLeft,
} from 'lucide-react';
import { computeCallGraphLayout, CG_NODE_W, CG_NODE_H } from './graph/callGraphLayout';
import {
  buildMutualPairSet,
  edgeFocusRole,
  edgeTransition,
  isMutual,
  resolveCallEdgeStyle,
  resolveFocusChoreography,
} from './graph/edgeSemantics';

// ── Types ─────────────────────────────────────────────────────────────────

interface CgNode {
  id: string;
  label: string;
  category: string;
  degree: number;
  centrality: number;
  language: string;
  highlighted: boolean;
  is_focus: boolean;
  qualified: string;
  file_path: string;
  fan_in: number;
  fan_out: number;
  is_recursive: boolean;
  parent_class?: string;
  symbol_type: string;
}

interface CgEdge {
  source: string;
  target: string;
  relationship: string;
  ambiguous: boolean;
}

interface GraphResponse {
  nodes: CgNode[];
  edges: CgEdge[];
  node_count: number;
  edge_count: number;
  error?: string;
}

interface CgStats {
  node_count: number;
  edge_count: number;
  entry_functions: number;
  recursive_functions: number;
  mutual_recursion_groups: number;
  top_fan_in: { node_id: string; fan_in: number }[];
  top_fan_out: { node_id: string; fan_out: number }[];
  generated_at: string | null;
}

interface BlastRadius {
  function_id: string;
  affected_functions: string[];
  affected_files: string[];
  depth: number;
  risk_level: string;
  recursive_cycles: string[][];
}

interface Props {
  repoName: string;
}

// ── Constants ──────────────────────────────────────────────────────────────

const CAT_COLOR: Record<string, string> = {
  entry_point:  '#818cf8',  // indigo  — entry roots
  core_module:  '#34d399',  // emerald — high fan-in hubs
  high_coupling:'#f59e0b',  // amber   — recursive
  focus:        '#ffffff',  // white   — selected node
  regular:      '#71717a',  // zinc
};

const LANG_COLOR: Record<string, string> = {
  python:     '#3572A5',
  typescript: '#3178C6',
  javascript: '#f1e05a',
  go:         '#00ADD8',
  rust:       '#dea584',
  cpp:        '#f34b7d',
  java:       '#b07219',
};

function shortId(id: string): string {
  const parts = id.split('::');
  return parts.length > 1 ? parts[1] : id;
}

function riskTone(level: string): 'danger' | 'warn' | 'success' {
  if (level === 'high') return 'danger';
  if (level === 'medium') return 'warn';
  return 'success';
}

// ── Custom React Flow Node Card Component ─────────────────────────────────

interface CustomNodeData {
  node: CgNode;
  isSelected: boolean;
  isDimmed: boolean;
  isCaller: boolean;
  isCallee: boolean;
  colorBy: 'category' | 'language';
  /** Where this node sits in the execution ordering, in milliseconds. */
  stageDelayMs?: number;
  onNodeClick: (node: CgNode) => void;
}

const CustomCallNode: React.FC<{ data: CustomNodeData }> = ({ data }) => {
  const { node, isSelected, isDimmed, isCaller, isCallee, colorBy, stageDelayMs = 0 } = data;
  const isRecursive = node.is_recursive;

  let baseBorder = 'border-zinc-800 bg-zinc-900/90 text-zinc-300 hover:border-zinc-700';

  if (colorBy === 'language') {
    const lang = node.language.toLowerCase();
    const hex = LANG_COLOR[lang] || '#71717a';
    baseBorder = `border-[${hex}] bg-zinc-900/90 text-zinc-200`;
  } else {
    if (isRecursive) {
      baseBorder = 'border-amber-500/70 bg-zinc-900/95 text-amber-200 hover:border-amber-400';
    } else if (node.category === 'entry_point' || node.fan_in === 0) {
      baseBorder = 'border-indigo-500/60 bg-zinc-900/95 text-indigo-300 font-medium hover:border-indigo-400';
    } else if (node.category === 'core_module' || node.fan_in >= 3) {
      baseBorder = 'border-emerald-500/60 bg-zinc-900/95 text-emerald-300 font-medium hover:border-emerald-400';
    }
  }

  if (isCaller) {
    baseBorder = 'border-emerald-400/80 bg-zinc-900/95 text-emerald-200 z-10 shadow-sm hover:border-emerald-300';
  } else if (isCallee) {
    baseBorder = 'border-indigo-400/80 bg-zinc-900/95 text-indigo-200 z-10 shadow-sm hover:border-indigo-300';
  }

  if (isSelected) {
    baseBorder = 'border-indigo-400 bg-zinc-900 text-white ring-1 ring-indigo-500/50 shadow-[0_0_20px_rgba(99,102,241,0.15)] font-bold scale-[1.02] z-20';
  }

  const fileName = node.file_path.split('/').pop() || node.file_path;
  const inlineBorder = colorBy === 'language' && !isSelected
    ? { borderColor: LANG_COLOR[node.language.toLowerCase()] || '#71717a' }
    : {};

  return (
    <div
      style={{
        ...(isSelected ? {} : inlineBorder),
        // Execution ordering: what runs before this lights first, what it calls
        // follows. A delay only — the node was already transitioning.
        transitionDelay: `${stageDelayMs}ms`,
      }}
      className={`px-3 py-2.5 min-w-[210px] max-w-[240px] rounded-lg flex flex-col gap-1.5 transition-all duration-200 border select-none font-mono text-left shadow-lg ${baseBorder} ${
        /* Recedes by opacity only — shrinking unrelated nodes changed their
           geometry on every selection and read as breakage, not as focus. */
        isDimmed ? 'opacity-[0.16]' : 'opacity-100'
      }${isSelected ? ' gnode-identified' : ''}`}
    >
      <Handle type="target" position={Position.Left} className="!bg-zinc-600 !border-zinc-500 !w-2 !h-2" />

      {/*
        Position in the execution chain relative to the selection. Caller and
        callee were previously distinguished by border colour alone; the arrow and
        word state it outright, which is what makes "what runs before and after
        this function" readable at a glance.
      */}
      {(isCaller || isCallee) && !isSelected && (
        <span
          className={`self-start flex items-center gap-1 text-[8px] font-bold uppercase tracking-[0.14em] ${
            isCaller ? 'text-emerald-300' : 'text-indigo-300'
          }`}
        >
          <span aria-hidden="true">{isCaller ? '↓' : '↑'}</span>
          {isCaller ? 'calls this' : 'called by this'}
        </span>
      )}

      {/* Function name + Fan-in badge */}
      <div className="flex items-center justify-between gap-2 min-w-0">
        <div className="flex items-center gap-1.5 min-w-0">
          {isRecursive ? (
            <Repeat2 className="h-3.5 w-3.5 text-amber-400 shrink-0" />
          ) : (
            <Code2 className="h-3.5 w-3.5 text-indigo-400 shrink-0" />
          )}
          <span className="text-xs font-bold text-zinc-100 truncate" title={node.label}>
            {shortId(node.id)}
          </span>
        </div>
        <div className="flex items-center gap-1 text-[9px] font-mono text-zinc-400 shrink-0">
          {node.fan_in > 0 && <span title="Incoming callers">↙{node.fan_in}</span>}
          {node.fan_out > 0 && <span title="Outgoing callees">↗{node.fan_out}</span>}
        </div>
      </div>

      {/* File & category pills */}
      <div className="space-y-1">
        <span className="text-[9px] text-zinc-400 truncate block" title={node.file_path}>
          {fileName}
        </span>
        <div className="flex flex-wrap items-center gap-1 text-[8px] uppercase">
          {node.language && (
            <span className="bg-zinc-950 border border-zinc-800 px-1 py-0.5 rounded text-zinc-400">
              {node.language}
            </span>
          )}
          {node.symbol_type && (
            <span className="bg-zinc-950 border border-zinc-800 px-1 py-0.5 rounded text-zinc-400">
              {node.symbol_type}
            </span>
          )}
          {isRecursive && (
            <span className="bg-amber-500/10 border border-amber-500/30 px-1 py-0.5 rounded text-amber-400 font-bold">
              cyclic
            </span>
          )}
        </div>
      </div>

      <Handle type="source" position={Position.Right} className="!bg-zinc-600 !border-zinc-500 !w-2 !h-2" />
    </div>
  );
};

const customNodeTypes = {
  customCallNode: CustomCallNode,
};

// ── React Flow canvas wrapper ──────────────────────────────────────────────

interface CanvasProps {
  cgNodes: CgNode[];
  cgEdges: CgEdge[];
  selectedNodeId: string | null;
  colorBy: 'category' | 'language';
  onNodeClick: (node: CgNode | null) => void;
}

const CallGraphCanvas: React.FC<CanvasProps> = ({ cgNodes, cgEdges, selectedNodeId, colorBy, onNodeClick }) => {
  const [rfNodes, setRfNodes, onNodesChange] = useNodesState([]);
  const [rfEdges, setRfEdges, onEdgesChange] = useEdgesState([]);
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const { zoomIn, zoomOut, fitView, setCenter, getNodes } = useReactFlow();

  // Find direct callers (incoming) and callees (outgoing)
  const callerIds = useMemo(() => {
    if (!selectedNodeId) return new Set<string>();
    const set = new Set<string>();
    cgEdges.forEach((e) => {
      if (e.target === selectedNodeId) set.add(e.source);
    });
    return set;
  }, [selectedNodeId, cgEdges]);

  const calleeIds = useMemo(() => {
    if (!selectedNodeId) return new Set<string>();
    const set = new Set<string>();
    cgEdges.forEach((e) => {
      if (e.source === selectedNodeId) set.add(e.target);
    });
    return set;
  }, [selectedNodeId, cgEdges]);

  const neighborIds = useMemo(() => {
    if (!selectedNodeId) return new Set<string>();
    const set = new Set<string>([selectedNodeId, ...callerIds, ...calleeIds]);
    return set;
  }, [selectedNodeId, callerIds, calleeIds]);

  // Hovered node object for micro-inspector tooltip
  const hoveredNode = useMemo(() => {
    if (!hoveredNodeId || hoveredNodeId === selectedNodeId) return null;
    return cgNodes.find((n) => n.id === hoveredNodeId) ?? null;
  }, [hoveredNodeId, selectedNodeId, cgNodes]);

  // Compute balanced aspect-ratio layout on data changes
  useEffect(() => {
    const positions = computeCallGraphLayout(cgNodes, cgEdges);

    const mappedNodes = cgNodes.map((n) => {
      const isSelected = selectedNodeId === n.id;
      const isCaller = callerIds.has(n.id);
      const isCallee = calleeIds.has(n.id);
      const isDimmed = selectedNodeId !== null && !neighborIds.has(n.id);

      return {
        id: n.id,
        type: 'customCallNode',
        position: positions[n.id] || { x: 0, y: 0 },
        width: CG_NODE_W,
        height: CG_NODE_H,
        data: {
          node: n,
          isSelected,
          isDimmed,
          isCaller,
          isCallee,
          colorBy,
          /*
            Position in the execution ordering, so the node's own transition
            waits its turn: callers, then the function, then callees.
          */
          stageDelayMs: resolveFocusChoreography(
            selectedNodeId === null
              ? 'idle'
              : isSelected
                ? 'focus'
                : isCaller
                  ? 'incoming'
                  : isCallee
                    ? 'outgoing'
                    : 'unrelated',
            'execution',
          ).delayMs,
        },
      };
    });

    // Mutual recursion is derived from the edge list already on screen.
    const mutualPairs = buildMutualPairSet(cgEdges);

    const mappedEdges = cgEdges.map((e, i) => {
      const isIncoming = Boolean(selectedNodeId) && e.target === selectedNodeId;
      const isOutgoing = Boolean(selectedNodeId) && e.source === selectedNodeId;

      const visual = resolveCallEdgeStyle({
        isSelfCall: e.source === e.target,
        isMutualRecursion: isMutual(mutualPairs, e.source, e.target),
        isOutgoing,
        isIncoming,
        isAmbiguous: Boolean(e.ambiguous),
        hasActive: selectedNodeId !== null,
      });

      /*
        Execution order, expressed as timing. Callers illuminate immediately,
        callees follow, unrelated chains retreat last — so selecting a function
        reads as tracing execution through it rather than as a highlight snapping
        on. The shared choreography keeps this identical to the node staging
        below and distinct from the File Graph's simultaneous resolve.
      */
      const choreo = resolveFocusChoreography(
        edgeFocusRole({ isIncoming, isOutgoing, hasActive: selectedNodeId !== null }),
        'execution',
      );

      return {
        id: `e-${i}`,
        source: e.source,
        target: e.target,
        /*
          Never animated: React Flow's `animated` paints marching dashes that
          would overwrite the dash patterns carrying recursion and ambiguity, and
          a moving edge implies runtime traffic the analyser never measured.
        */
        animated: false,
        style: {
          stroke: visual.stroke,
          strokeWidth: visual.strokeWidth,
          opacity: visual.opacity,
          strokeDasharray: visual.dash,
          transition: edgeTransition(choreo),
        },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          width: 10,
          height: 10,
          color: visual.stroke,
        },
        // Mutual recursion gets a head at both ends.
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

    setRfNodes(mappedNodes as any);
    setRfEdges(mappedEdges as any);
  }, [cgNodes, cgEdges, selectedNodeId, neighborIds, callerIds, calleeIds, colorBy, setRfNodes, setRfEdges]);

  // Center on load
  useEffect(() => {
    if (rfNodes.length > 0) {
      const timer = setTimeout(() => {
        fitView({ padding: 0.15, duration: 300, minZoom: 0.15, maxZoom: 1.5 });
      }, 100);
      return () => clearTimeout(timer);
    }
  }, [rfNodes.length, fitView]);

  // Smooth center on selected node
  useEffect(() => {
    if (selectedNodeId) {
      const nodes = getNodes();
      const target = nodes.find((n) => n.id === selectedNodeId);
      if (target && target.position) {
        setCenter(target.position.x + CG_NODE_W / 2, target.position.y + CG_NODE_H / 2, {
          zoom: 1.15,
          duration: 350,
        });
      }
    }
  }, [selectedNodeId, getNodes, setCenter]);

  const handleNodeClick = useCallback((_: any, node: any) => {
    const original = cgNodes.find((n) => n.id === node.id);
    if (original) onNodeClick(original);
  }, [cgNodes, onNodeClick]);

  const handleNodeMouseEnter = useCallback((_: any, node: any) => {
    setHoveredNodeId(node.id);
  }, []);

  const handleNodeMouseLeave = useCallback(() => {
    setHoveredNodeId(null);
  }, []);

  const handlePaneClick = useCallback(() => {
    onNodeClick(null);
    setHoveredNodeId(null);
  }, [onNodeClick]);

  return (
    <div className="relative w-full h-full bg-[#030303]">
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        nodeTypes={customNodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        onNodeMouseEnter={handleNodeMouseEnter}
        onNodeMouseLeave={handleNodeMouseLeave}
        onPaneClick={handlePaneClick}
        onInit={(instance) => instance.fitView({ padding: 0.15, duration: 300, minZoom: 0.15, maxZoom: 1.5 })}
        fitView
        fitViewOptions={{ padding: 0.15, minZoom: 0.15, maxZoom: 1.5 }}
        minZoom={0.05}
        maxZoom={2.5}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#1e1e24" gap={18} size={1} />

        {/* Minimal Transparent Pan/Zoom Controls */}
        <div className="absolute bottom-4 left-4 z-10 flex items-center gap-1 p-1 bg-zinc-950/80 border border-zinc-800/80 rounded-md shadow-lg backdrop-blur-sm select-none font-mono text-[10px]">
          <button
            type="button"
            onClick={() => zoomIn({ duration: 200 })}
            className="w-7 h-7 flex items-center justify-center rounded hover:bg-zinc-900 text-zinc-400 hover:text-zinc-100 transition-colors focus:outline-none"
            title="Zoom In"
          >
            <ZoomIn className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={() => zoomOut({ duration: 200 })}
            className="w-7 h-7 flex items-center justify-center rounded hover:bg-zinc-900 text-zinc-400 hover:text-zinc-100 transition-colors focus:outline-none"
            title="Zoom Out"
          >
            <ZoomOut className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={() => fitView({ duration: 300, padding: 0.15 })}
            className="w-7 h-7 flex items-center justify-center rounded hover:bg-zinc-900 text-zinc-400 hover:text-zinc-100 transition-colors focus:outline-none"
            title="Fit View"
          >
            <Maximize className="h-3.5 w-3.5" />
          </button>
          <span className="w-px h-4 bg-zinc-800 mx-0.5" />
          <button
            type="button"
            onClick={() => {
              onNodeClick(null);
              fitView({ duration: 300, padding: 0.15 });
            }}
            className="px-2 py-1 rounded hover:bg-zinc-900 text-zinc-400 hover:text-zinc-100 transition-colors focus:outline-none uppercase font-bold"
            title="Reset active selection and frame overview"
          >
            Reset
          </button>
        </div>

        <MiniMap
          nodeColor={(n: any) => {
            const original = n.data?.node as CgNode;
            if (!original) return '#27272a';
            if (original.is_recursive) return '#f59e0b';
            if (original.category === 'entry_point') return '#818cf8';
            if (original.category === 'core_module') return '#34d399';
            return '#3f3f46';
          }}
          maskColor="rgba(3, 3, 3, 0.85)"
          className="!bg-zinc-950/95 !border-zinc-800/80 !rounded-lg overflow-hidden"
          nodeStrokeWidth={0}
          nodeBorderRadius={3}
        />
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
              style={{ backgroundColor: CAT_COLOR[hoveredNode.category] ?? '#a1a1aa' }}
            />
            <span className="text-[10px] uppercase font-bold text-zinc-400">
              {hoveredNode.category.replace('_', ' ')}
            </span>
            {hoveredNode.language && (
              <span className="text-[9px] text-zinc-500 ml-auto">{hoveredNode.language}</span>
            )}
          </div>
          <div className="font-semibold text-zinc-100 truncate text-[11px]">{shortId(hoveredNode.id)}</div>
          <div className="text-[9px] text-zinc-400 truncate mb-2">{hoveredNode.file_path}</div>
          <div className="flex items-center justify-between text-[10px] text-zinc-400 border-t border-zinc-800/80 pt-1.5">
            <span>Callers: <strong className="text-zinc-200">{hoveredNode.fan_in}</strong></span>
            <span>Callees: <strong className="text-zinc-200">{hoveredNode.fan_out}</strong></span>
            {hoveredNode.is_recursive && (
              <span className="text-amber-400 font-bold">CYCLIC</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

// ── Node detail panel (Function Inspector v2) ──────────────────────────

interface NodePanelProps {
  node: CgNode;
  repoName: string;
  onClose: () => void;
  onBlastRadius: (id: string) => void;
  onNeighbors: (id: string) => void;
  onTrace: (id: string, dir: 'forward' | 'backward') => void;
}

const NodePanel: React.FC<NodePanelProps> = ({
  node, repoName, onClose, onBlastRadius, onNeighbors, onTrace,
}) => {
  const [panelTab, setPanelTab] = useState<'overview' | 'metadata' | 'callers' | 'callees'>('overview');

  const panelTabs = [
    { id: 'overview', label: 'Overview' },
    { id: 'metadata', label: 'Metadata' },
    { id: 'callers',  label: 'Callers' },
    { id: 'callees',  label: 'Callees' },
  ] as const;

  /**
   * Coupling band, derived from the node's own fan-in and degree.
   *
   * This replaces a former HIGH/MEDIUM/LOW *RISK* verdict. The backend supplies
   * no risk score, so that badge asserted a severity the payload never measured —
   * and it folded `is_recursive` into the verdict even though recursion already
   * has its own badge beside it and is not a coupling measure.
   *
   * The band is labelled as derived so it cannot be mistaken for backend
   * telemetry, and it stays amber at worst: heavy coupling is a property worth
   * noticing, not a failure.
   */
  const couplingBand = useMemo(() => {
    if (node.degree > 15 || node.fan_in > 5) {
      return { text: 'HIGH COUPLING', tone: 'warn' as const };
    }
    if (node.degree > 6) {
      return { text: 'MODERATE COUPLING', tone: 'neutral' as const };
    }
    return { text: 'LOW COUPLING', tone: 'neutral' as const };
  }, [node]);

  return (
    <aside
      className="w-80 shrink-0 border-l border-zinc-800 bg-zinc-950/95 flex flex-col overflow-hidden font-mono z-20 shadow-2xl animate-in fade-in slide-in-from-right-2 duration-200"
      aria-label="Function details"
    >
      {/* Title */}
      <div className="flex items-start justify-between px-4 pt-4 pb-3 border-b border-zinc-800 bg-zinc-950 shrink-0 select-none">
        <div className="space-y-0.5 min-w-0 pr-2">
          <span className="text-[9px] font-bold text-indigo-400 uppercase tracking-wider block flex items-center gap-1">
            {/* Workflow, not a sparkle: this inspector reports execution flow. */}
            <Workflow className="h-3 w-3 text-indigo-400" aria-hidden="true" /> Function Inspector
          </span>
          <h3 className="text-xs font-semibold text-zinc-100 truncate block" title={node.label}>
            {shortId(node.id)}
          </h3>
          <span className="text-[9px] text-zinc-500 truncate block" title={node.file_path}>
            {node.file_path}
          </span>
        </div>
        <button
          onClick={onClose}
          className="text-zinc-400 hover:text-zinc-100 rounded p-1"
          aria-label="Close panel"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-zinc-800 bg-zinc-950 select-none text-[9px] font-bold uppercase overflow-x-auto">
        {panelTabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setPanelTab(t.id)}
            className={`flex-1 py-2 px-1 text-center border-b-2 transition-all ${
              panelTab === t.id
                ? 'border-indigo-400 text-indigo-300 bg-indigo-500/10 font-extrabold'
                : 'border-transparent text-zinc-400 hover:text-zinc-200'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab Panels */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 text-xs">
        {panelTab === 'overview' && (
          <>
            {/* Fan-in / Fan-out cards */}
            <div className="grid grid-cols-2 gap-2 select-none">
              <div className="p-3 bg-zinc-900/80 border border-zinc-800 rounded-lg text-center">
                <p className="text-zinc-400 text-[9px] uppercase tracking-wider font-bold">Incoming Callers</p>
                <p className="text-xl font-bold text-emerald-400 mt-0.5">{node.fan_in}</p>
                <p className="text-[9px] text-zinc-500 mt-0.5">fan-in refs</p>
              </div>
              <div className="p-3 bg-zinc-900/80 border border-zinc-800 rounded-lg text-center">
                <p className="text-zinc-400 text-[9px] uppercase tracking-wider font-bold">Outgoing Callees</p>
                <p className="text-xl font-bold text-indigo-400 mt-0.5">{node.fan_out}</p>
                <p className="text-[9px] text-zinc-500 mt-0.5">fan-out calls</p>
              </div>
            </div>

            {/* Smart Actions */}
            <div className="space-y-1.5 pt-2 border-t border-zinc-800/60">
              <span className="text-[9px] text-zinc-400 uppercase font-bold tracking-wider block mb-1">
                Smart Actions
              </span>
              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={() => {
                    if (typeof window !== 'undefined') {
                      window.dispatchEvent(
                        new CustomEvent('aria-open-chat', {
                          detail: { prompt: `Explain the function ${node.id} in file ${node.file_path}, its callers, and its callees.` },
                        })
                      );
                    }
                  }}
                  className="flex items-center justify-center gap-1.5 bg-indigo-500/10 hover:bg-indigo-500/20 border border-indigo-500/30 text-indigo-300 font-bold px-2 py-2 rounded text-[10px] transition-all"
                  title="Ask ARIA Chat to explain this function"
                >
                  <Sparkles className="h-3 w-3" /> Ask ARIA
                </button>

                <button
                  onClick={() => onBlastRadius(node.id)}
                  className="flex items-center justify-center gap-1.5 bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 text-rose-400 font-bold px-2 py-2 rounded text-[10px] transition-all"
                  title="Evaluate blast radius and risk"
                >
                  <Zap className="h-3 w-3" /> Blast Radius
                </button>
              </div>

              <button
                onClick={() => {
                  if (typeof window !== 'undefined' && node.file_path) {
                    window.dispatchEvent(
                      new CustomEvent('aria-open-graph', {
                        detail: { path: node.file_path },
                      })
                    );
                  }
                }}
                className="w-full flex items-center justify-center gap-2 bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 text-zinc-200 font-bold px-3 py-1.5 rounded text-[10px] transition-all"
              >
                <ExternalLink className="h-3 w-3 text-indigo-400" /> View in File Graph
              </button>
            </div>

            {/* Call Graph Traversal */}
            <div className="space-y-1.5 pt-2 border-t border-zinc-800/60">
              <span className="text-[9px] text-zinc-400 uppercase font-bold tracking-wider block mb-1">
                Call Traversal
              </span>
              <div className="space-y-1">
                <button
                  onClick={() => onNeighbors(node.id)}
                  className="w-full flex items-center gap-2 bg-zinc-900 border border-zinc-800 hover:border-indigo-500/50 px-3 py-1.5 rounded text-[10px] text-zinc-200"
                >
                  <GitBranch className="h-3.5 w-3.5 text-indigo-400" /> Show Nearest Neighbors
                </button>
                <button
                  onClick={() => onTrace(node.id, 'forward')}
                  className="w-full flex items-center gap-2 bg-zinc-900 border border-zinc-800 hover:border-emerald-500/50 px-3 py-1.5 rounded text-[10px] text-zinc-200"
                >
                  <ArrowRight className="h-3.5 w-3.5 text-emerald-400" /> Trace Downstream Callees →
                </button>
                <button
                  onClick={() => onTrace(node.id, 'backward')}
                  className="w-full flex items-center gap-2 bg-zinc-900 border border-zinc-800 hover:border-orange-500/50 px-3 py-1.5 rounded text-[10px] text-zinc-200"
                >
                  <ArrowLeft className="h-3.5 w-3.5 text-orange-400" /> ← Trace Upstream Callers
                </button>
              </div>
            </div>
          </>
        )}

        {panelTab === 'metadata' && (
          <div className="space-y-3">
            <div className="p-3 bg-zinc-900/80 border border-zinc-800 rounded-lg space-y-1">
              <span className="text-[9px] font-bold text-zinc-400 block uppercase tracking-wider select-none">
                Declared File Path
              </span>
              <p className="text-zinc-300 break-all text-[11px] leading-relaxed select-all">
                {node.file_path}
              </p>
            </div>

            <div className="space-y-1.5 select-none">
              <span className="text-[9px] font-bold text-zinc-400 block uppercase tracking-wider">
                Properties
              </span>
              <div className="flex flex-wrap gap-1.5">
                <span className="text-[9px] font-bold uppercase px-2 py-0.5 rounded border border-indigo-500/40 bg-indigo-500/10 text-indigo-300">
                  {node.symbol_type}
                </span>
                <span className="text-[9px] font-bold uppercase px-2 py-0.5 rounded border border-blue-500/40 bg-blue-500/10 text-blue-300">
                  {node.language}
                </span>
                {/* Derived from fan-in / degree, not reported by the backend. */}
                <span
                  title={`Derived from fan-in ${node.fan_in} and degree ${node.degree}`}
                  className={`text-[9px] font-bold uppercase px-2 py-0.5 rounded border ${
                    couplingBand.tone === 'warn'
                      ? 'border-amber-500/40 bg-amber-500/10 text-amber-400'
                      : 'border-zinc-700 bg-zinc-900 text-zinc-400'
                  }`}
                >
                  {couplingBand.text}
                </span>
                <span className="text-[9px] font-bold uppercase px-2 py-0.5 rounded border border-zinc-800 bg-zinc-900/60 text-zinc-500">
                  derived
                </span>
                {node.is_recursive && (
                  <span className="text-[9px] font-bold uppercase px-2 py-0.5 rounded border border-amber-500/40 bg-amber-500/10 text-amber-300">
                    cyclic recursion
                  </span>
                )}
              </div>
            </div>

            {node.parent_class && (
              <div className="space-y-1 text-[10px]">
                <span className="text-zinc-400 uppercase text-[9px] block">Parent Class</span>
                <span className="text-zinc-200 font-semibold break-all">{node.parent_class}</span>
              </div>
            )}

            <div className="border-t border-zinc-800/80 pt-3 space-y-2 text-[10px] select-none text-zinc-400">
              <div className="flex justify-between">
                <span>Centrality Rank:</span>
                <span className="text-zinc-200 font-semibold">{node.centrality.toFixed(4)}</span>
              </div>
              <div className="flex justify-between">
                <span>Degree Connections:</span>
                <span className="text-zinc-200 font-semibold">{node.degree}</span>
              </div>
            </div>
          </div>
        )}

        {panelTab === 'callers' && (
          <div className="space-y-3 select-none">
            <p className="text-zinc-400 text-[11px] leading-relaxed">
              Trace callers recursively to map upstream modules and structural dependencies invoking this function symbol.
            </p>
            <button
              onClick={() => onTrace(node.id, 'backward')}
              className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-orange-500/10 hover:bg-orange-500/20 border border-orange-500/30 text-orange-400 font-bold transition-all text-[10px]"
            >
              <ArrowLeft className="h-3.5 w-3.5" /> Trace Upstream Callers
            </button>
          </div>
        )}

        {panelTab === 'callees' && (
          <div className="space-y-3 select-none">
            <p className="text-zinc-400 text-[11px] leading-relaxed">
              Trace callees recursively to map downstream modules and execution flow branches triggered by this function symbol.
            </p>
            <button
              onClick={() => onTrace(node.id, 'forward')}
              className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/30 text-emerald-400 font-bold transition-all text-[10px]"
            >
              <ArrowRight className="h-3.5 w-3.5" /> Trace Downstream Callees →
            </button>
          </div>
        )}
      </div>
    </aside>
  );
};

// ── Blast radius panel ─────────────────────────────────────────────────────

const BlastRadiusPanel: React.FC<{
  br: BlastRadius;
  onClose: () => void;
}> = ({ br, onClose }) => (
  <div className="p-4 bg-zinc-950 border border-zinc-800 rounded-xl space-y-3 font-mono shadow-2xl animate-in fade-in duration-200">
    <div className="flex items-center justify-between border-b border-zinc-800 pb-2.5 select-none">
      <h3 className="text-xs font-bold text-zinc-100 flex items-center gap-2">
        <Zap className="h-4 w-4 text-rose-400" />
        <span>Blast Radius Risk Assessment</span>
      </h3>
      <button
        onClick={onClose}
        aria-label="Close blast radius"
        className="text-zinc-400 hover:text-zinc-100 rounded p-1"
      >
        <X className="h-4 w-4" />
      </button>
    </div>

    <div className="grid grid-cols-3 gap-3 select-none text-center">
      <div className="p-2.5 bg-zinc-900 border border-zinc-800 rounded-lg">
        <p className="text-[9px] text-zinc-400 uppercase tracking-wider font-bold">Callers Affected</p>
        <p className="text-xl font-bold text-zinc-100 mt-0.5">{br.affected_functions.length}</p>
      </div>
      <div className="p-2.5 bg-zinc-900 border border-zinc-800 rounded-lg">
        <p className="text-[9px] text-zinc-400 uppercase tracking-wider font-bold">Files Affected</p>
        <p className="text-xl font-bold text-zinc-100 mt-0.5">{br.affected_files.length}</p>
      </div>
      <div className="p-2.5 bg-zinc-900 border border-zinc-800 rounded-lg">
        <p className="text-[9px] text-zinc-400 uppercase tracking-wider font-bold">Max Call Depth</p>
        <p className="text-xl font-bold text-indigo-400 mt-0.5">{br.depth}</p>
      </div>
    </div>

    <div className="flex items-center gap-2 select-none text-xs">
      <span className="text-zinc-400">Risk Factor:</span>
      <Badge tone={riskTone(br.risk_level)}>{br.risk_level.toUpperCase()}</Badge>
    </div>

    {br.recursive_cycles.length > 0 && (
      <div className="space-y-1.5 select-none">
        <p className="text-[10px] font-bold text-amber-400 flex items-center gap-1.5 uppercase tracking-wider">
          <Repeat2 className="h-4 w-4" /> {br.recursive_cycles.length} recursion cycle{br.recursive_cycles.length > 1 ? 's' : ''} detected
        </p>
        <div className="space-y-1">
          {br.recursive_cycles.slice(0, 3).map((cycle, i) => (
            <div key={i} className="text-[10px] text-zinc-300 bg-zinc-900 border border-zinc-800 rounded p-2">
              {cycle.map(shortId).join(' ↔ ')}
            </div>
          ))}
        </div>
      </div>
    )}
  </div>
);

// ── Stats panel ────────────────────────────────────────────────────────────

const StatsPanel: React.FC<{ stats: CgStats }> = ({ stats }) => (
  <div className="space-y-4 font-mono animate-in fade-in duration-200">
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
      <MetricCard tone="primary" icon={<Workflow className="h-4 w-4" />}
        label="Functions" value={stats.node_count.toLocaleString()} hint="tracked symbols" />
      <MetricCard tone="info" icon={<GitBranch className="h-4 w-4" />}
        label="Call Edges" value={stats.edge_count.toLocaleString()} hint="call relationships" />
      <MetricCard tone="success" icon={<ArrowUpFromLine className="h-4 w-4" />}
        label="Entry Points" value={stats.entry_functions} hint="no callers" />
      <MetricCard tone="warn" icon={<Repeat2 className="h-4 w-4" />}
        label="Recursive" value={stats.recursive_functions} hint="self-calling" />
      <MetricCard tone="danger" icon={<AlertTriangle className="h-4 w-4" />}
        label="Mutual Cycles" value={stats.mutual_recursion_groups} hint="SCCs > 1" />
    </div>

    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      <div className="p-4 bg-zinc-950 border border-zinc-800 rounded-xl space-y-3">
        <h3 className="text-xs font-bold text-zinc-100 flex items-center gap-1.5">
          <ArrowUpFromLine className="h-4 w-4 text-emerald-400" /> Top Fan-in (Most Referenced Functions)
        </h3>
        <div className="space-y-1.5">
          {stats.top_fan_in.slice(0, 8).map((item, i) => (
            <div key={item.node_id} className="flex items-center gap-3 text-xs py-1 border-b border-zinc-800/50 last:border-0">
              <span className="text-zinc-500 w-4 shrink-0 font-bold">#{i + 1}</span>
              <span className="flex-1 text-zinc-200 truncate" title={item.node_id}>{shortId(item.node_id)}</span>
              <Badge tone="success">{item.fan_in} calls</Badge>
            </div>
          ))}
        </div>
      </div>
      <div className="p-4 bg-zinc-950 border border-zinc-800 rounded-xl space-y-3">
        <h3 className="text-xs font-bold text-zinc-100 flex items-center gap-1.5">
          <ArrowDownToLine className="h-4 w-4 text-indigo-400" /> Top Fan-out (Most Outgoing Calls)
        </h3>
        <div className="space-y-1.5">
          {stats.top_fan_out.slice(0, 8).map((item, i) => (
            <div key={item.node_id} className="flex items-center gap-3 text-xs py-1 border-b border-zinc-800/50 last:border-0">
              <span className="text-zinc-500 w-4 shrink-0 font-bold">#{i + 1}</span>
              <span className="flex-1 text-zinc-200 truncate" title={item.node_id}>{shortId(item.node_id)}</span>
              <Badge tone="primary">{(item as any).fan_out} calls</Badge>
            </div>
          ))}
        </div>
      </div>
    </div>
  </div>
);

// ── Main component ─────────────────────────────────────────────────────────

export const CallGraphAnalyzer: React.FC<Props> = ({ repoName }) => {
  const [owner, repoSlug] = repoName.split('/');

  // Build state
  const [building, setBuilding] = useState(false);
  const [buildProgress, setBuildProgress] = useState('');
  const [buildError, setBuildError] = useState<string | null>(null);

  // Graph data
  const [graphData, setGraphData] = useState<GraphResponse | null>(null);
  const [graphLoading, setGraphLoading] = useState(false);
  const [graphError, setGraphError] = useState<string | null>(null);

  // Stats
  const [stats, setStats] = useState<CgStats | null>(null);

  // UI state
  const [activeView, setActiveView] = useState<'graph' | 'stats'>('graph');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedNode, setSelectedNode] = useState<CgNode | null>(null);
  const [blastRadius, setBlastRadius] = useState<BlastRadius | null>(null);
  const [brLoading, setBrLoading] = useState(false);

  // Filters & controls
  const [colorBy, setColorBy] = useState<'category' | 'language'>('category');
  const [hideExternal, setHideExternal] = useState(false);
  const [hideCycles, setHideCycles] = useState(false);

  const searchDebounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Data fetchers ────────────────────────────────────────────────────────

  const loadGraph = useCallback(async (q: string) => {
    setGraphLoading(true);
    setGraphError(null);
    try {
      const url = apiUrl(
        `/api/v1/call-graph/${owner}/${repoSlug}${q ? `?q=${encodeURIComponent(q)}` : ''}`
      );
      const res = await fetch(url);
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        if (res.status === 404) { setGraphData(null); return; }
        throw new Error(extractErrorMessage(body));
      }
      const data: GraphResponse = await res.json();
      setGraphData(data);
    } catch (err: any) {
      setGraphError(extractErrorMessage(err));
    } finally {
      setGraphLoading(false);
    }
  }, [owner, repoSlug]);

  const loadStats = useCallback(async () => {
    try {
      const res = await fetch(apiUrl(`/api/v1/call-graph/${owner}/${repoSlug}/stats`));
      if (res.ok) setStats(await res.json());
    } catch { /* optional */ }
  }, [owner, repoSlug]);

  const loadNeighbors = useCallback(async (functionId: string) => {
    setGraphLoading(true);
    setGraphError(null);
    try {
      const res = await fetch(
        apiUrl(`/api/v1/call-graph/${owner}/${repoSlug}/neighbors/${encodeURIComponent(functionId)}`)
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: GraphResponse = await res.json();
      setGraphData(data);
    } catch (err: any) {
      setGraphError(extractErrorMessage(err));
    } finally {
      setGraphLoading(false);
    }
  }, [owner, repoSlug]);

  const loadTrace = useCallback(async (functionId: string, dir: 'forward' | 'backward') => {
    setGraphLoading(true);
    setGraphError(null);
    try {
      const res = await fetch(
        apiUrl(`/api/v1/call-graph/${owner}/${repoSlug}/trace/${encodeURIComponent(functionId)}?direction=${dir}&depth=6`)
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: GraphResponse = await res.json();
      setGraphData(data);
    } catch (err: any) {
      setGraphError(extractErrorMessage(err));
    } finally {
      setGraphLoading(false);
    }
  }, [owner, repoSlug]);

  const loadBlastRadius = useCallback(async (functionId: string) => {
    setBrLoading(true);
    setBlastRadius(null);
    try {
      const res = await fetch(
        apiUrl(`/api/v1/call-graph/${owner}/${repoSlug}/blast-radius/${encodeURIComponent(functionId)}`)
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setBlastRadius(await res.json());
    } catch (err: any) {
      setGraphError(extractErrorMessage(err));
    } finally {
      setBrLoading(false);
    }
  }, [owner, repoSlug]);

  // Filter nodes & edges on client side before passing to canvas
  const filteredNodes = useMemo(() => {
    if (!graphData || !graphData.nodes) return [];
    return graphData.nodes.filter(n => {
      if (hideCycles && n.is_recursive) return false;
      if (hideExternal && (n.symbol_type === 'external' || !n.file_path)) return false;
      return true;
    });
  }, [graphData, hideCycles, hideExternal]);

  const filteredEdges = useMemo(() => {
    if (!graphData || !graphData.edges) return [];
    const validNodeIds = new Set(filteredNodes.map(n => n.id));
    return graphData.edges.filter(e => {
      return validNodeIds.has(e.source) && validNodeIds.has(e.target);
    });
  }, [graphData, filteredNodes]);

  // Telemetry metrics
  const entryCount = useMemo(() => {
    return filteredNodes.filter((n) => n.category === 'entry_point' || n.fan_in === 0).length;
  }, [filteredNodes]);

  const recursiveCount = useMemo(() => {
    return filteredNodes.filter((n) => n.is_recursive).length;
  }, [filteredNodes]);

  // ── Auto-load on mount ───────────────────────────────────────────────────
  useEffect(() => {
    setSelectedNode(null);
    setBlastRadius(null);
    setSearchQuery('');
    setGraphData(null);
    setStats(null);
    loadGraph('');
    loadStats();
  }, [repoName, loadGraph, loadStats]);

  // ── Build handler (SSE stream) ───────────────────────────────────────────

  const handleBuild = useCallback(async () => {
    setBuilding(true);
    setBuildError(null);
    setBuildProgress('Starting…');
    setGraphData(null);
    setStats(null);

    try {
      const res = await fetch(apiUrl('/api/v1/call-graph/build'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ repo: repoName }),
      });

      if (!res.body) throw new Error('No response body.');

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const ev = JSON.parse(line.slice(6));
            if (ev.status === 'indexing' || ev.status === 'resolving') {
              setBuildProgress(`${ev.file_count ?? 0} files scanned…`);
            } else if (ev.status === 'complete') {
              setBuilding(false);
              loadGraph('');
              loadStats();
              return;
            } else if (ev.status === 'error') {
              throw new Error(ev.message || 'Build failed.');
            }
          } catch (e: any) {
            if (e.message && e.message !== 'Unexpected end of JSON input') {
              throw e;
            }
          }
        }
      }
    } catch (err: any) {
      setBuildError(extractErrorMessage(err));
    } finally {
      setBuilding(false);
    }
  }, [repoName, loadGraph, loadStats]);

  // ── Search handler ───────────────────────────────────────────────────────

  const handleSearch = useCallback((val: string) => {
    setSearchQuery(val);
    if (searchDebounce.current) clearTimeout(searchDebounce.current);
    searchDebounce.current = setTimeout(() => {
      loadGraph(val);
    }, 300);
  }, [loadGraph]);

  return (
    <div className="space-y-4 font-mono">
      {/* Editorial Technical Header */}
      <div className="px-4 py-3 border border-border/80 bg-zinc-950/90 rounded-xl flex items-center justify-between gap-4 z-10 flex-wrap">
        <div className="space-y-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-bold text-indigo-400 tracking-wider uppercase">FUNCTION CALL GRAPH</span>
            <span className="text-zinc-600 text-[10px]">/</span>
            <span className="text-[10px] text-zinc-400 uppercase tracking-wider">INTER-FUNCTION TOPOLOGY</span>
          </div>
          <div className="flex items-center gap-2 text-[10px] text-zinc-400 flex-wrap">
            <span className="text-zinc-200 font-bold">{filteredNodes.length.toLocaleString()}</span> FUNCTIONS
            <span className="text-zinc-600">·</span>
            <span className="text-zinc-200 font-bold">{filteredEdges.length.toLocaleString()}</span> CALL EDGES
            <span className="text-zinc-600">·</span>
            <span className="text-zinc-200 font-bold">{entryCount}</span> ENTRY POINTS
            {recursiveCount > 0 && (
              <>
                <span className="text-zinc-600">·</span>
                <span className="text-amber-400 font-bold">{recursiveCount}</span> RECURSIVE
              </>
            )}
            <span className="text-zinc-600">·</span>
            <span>DIRECTED</span>
          </div>
        </div>

        {/* Controls: Mode toggle + Actions */}
        <div className="flex items-center gap-3 shrink-0">
          {/* Graph / Stats Mode Switch */}
          <div className="flex items-center bg-zinc-900 border border-zinc-800 rounded-lg p-0.5 text-[10px]">
            <button
              onClick={() => setActiveView('graph')}
              className={`px-3 py-1 rounded font-bold transition-all ${
                activeView === 'graph'
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-zinc-400 hover:text-zinc-200'
              }`}
            >
              GRAPH
            </button>
            <button
              onClick={() => setActiveView('stats')}
              className={`px-3 py-1 rounded font-bold transition-all ${
                activeView === 'stats'
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-zinc-400 hover:text-zinc-200'
              }`}
            >
              STATS
            </button>
          </div>

          {/* Reset button */}
          <button
            onClick={() => {
              setSelectedNode(null);
              setBlastRadius(null);
              setSearchQuery('');
              loadGraph('');
            }}
            className="flex items-center gap-1 px-2.5 py-1 rounded border border-zinc-800 bg-zinc-900 hover:bg-zinc-800 text-zinc-400 hover:text-zinc-100 text-xs transition-colors"
            title="Reset active query and selection"
          >
            <RefreshCw className="h-3 w-3" /> Reset
          </button>

          {/* Rebuild button */}
          <button
            onClick={handleBuild}
            disabled={building}
            className="flex items-center gap-1.5 px-3 py-1 rounded bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs font-bold transition-colors shadow-sm"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${building ? 'animate-spin' : ''}`} />
            {building ? buildProgress || 'Building…' : 'Rebuild'}
          </button>
        </div>
      </div>

      {/*
        Build progress notification banner. The spinner carries the activity —
        pulsing the whole banner as well was two signals for one state.
      */}
      {building && (
        <div className="p-3 bg-indigo-500/10 border border-indigo-500/30 rounded-xl flex items-center gap-3 text-xs text-indigo-300">
          <RefreshCw className="h-4 w-4 animate-spin text-indigo-400" />
          <span>Analyzing AST and constructing function call graph: {buildProgress}</span>
        </div>
      )}

      {buildError && (
        <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-xl flex items-center justify-between text-xs text-red-300">
          <span>Error generating call graph: {buildError}</span>
          <Button variant="ghost" onClick={handleBuild}>Retry</Button>
        </div>
      )}

      {/* Loading state */}
      {graphLoading && !building && (
        <div className="h-[600px] border border-border/80 rounded-xl bg-zinc-950 flex flex-col items-center justify-center gap-2 text-xs text-zinc-400">
          <RefreshCw className="h-5 w-5 animate-spin text-indigo-400" />
          <span>MAPPING FUNCTION CALL TOPOLOGY…</span>
        </div>
      )}

      {/* Error state */}
      {!graphLoading && graphError && (
        <div className="h-[600px] border border-border/80 rounded-xl bg-zinc-950 flex items-center justify-center p-6">
          <EmptyState
            tone="danger"
            icon={<AlertTriangle className="h-6 w-6 text-red-400" />}
            title="TOPOLOGY UNAVAILABLE"
            description={graphError}
            action={<Button variant="ghost" onClick={() => loadGraph('')}>Retry</Button>}
          />
        </div>
      )}

      {/* Empty / Not Built State */}
      {!graphLoading && !graphError && !graphData && !building && (
        <div className="h-[600px] border border-border/80 rounded-xl bg-zinc-950 flex items-center justify-center p-6">
          <EmptyState
            icon={<Workflow className="h-6 w-6 text-indigo-400" />}
            title="Call Graph Not Built"
            description="Generate a complete function-level call hierarchy for this repository."
            action={<Button onClick={handleBuild}>Build Call Graph</Button>}
          />
        </div>
      )}

      {/* Main Content Area */}
      {!graphLoading && !graphError && graphData && (
        <div className="space-y-3">
          {/* Stats View */}
          {activeView === 'stats' && stats && <StatsPanel stats={stats} />}
          {activeView === 'stats' && !stats && (
            <EmptyState compact icon={<Info className="h-5 w-5" />}
              title="NOT AVAILABLE" description="Build the call graph to compute execution statistics." />
          )}

          {/* Graph View */}
          {activeView === 'graph' && (
            <div className="space-y-3">
              {graphData.nodes.length === 0 ? (
                <div className="h-[600px] border border-border/80 rounded-xl bg-zinc-950 flex items-center justify-center p-6 font-mono">
                  <EmptyState
                    icon={<Workflow className="h-6 w-6 text-zinc-500" />}
                    title="NO CALLABLE SYMBOLS DETECTED"
                    description="No callable symbols were detected in this repository."
                  />
                </div>
              ) : (
                <>
                  {/* Command Search & Analysis Filters */}
                  <div className="px-3 py-2 bg-zinc-950 border border-zinc-800 rounded-xl flex items-center justify-between gap-4 flex-wrap select-none text-xs">
                {/* Search functions */}
                <div className="relative flex-grow max-w-sm">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-zinc-500 pointer-events-none" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => handleSearch(e.target.value)}
                    placeholder="Search functions, methods, symbols…"
                    className="w-full bg-zinc-900/90 border border-zinc-800 rounded-md pl-8 pr-12 py-1 text-xs font-mono focus:outline-none focus:border-indigo-500 text-zinc-100 placeholder:text-zinc-500/70"
                    aria-label="Search call graph"
                  />
                  {searchQuery ? (
                    <button
                      onClick={() => { setSearchQuery(''); loadGraph(''); }}
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-100"
                      aria-label="Clear search"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  ) : (
                    <kbd className="absolute right-2 top-1/2 -translate-y-1/2 text-[9px] font-mono text-zinc-500 bg-zinc-950 border border-zinc-800 px-1.5 py-0.5 rounded pointer-events-none">
                      /
                    </kbd>
                  )}
                </div>

                {/* Filters */}
                <div className="flex items-center gap-4 text-[10px] text-zinc-400 ml-auto">
                  {/* Color selector */}
                  <div className="flex items-center gap-1.5">
                    <span>Color Nodes:</span>
                    <select
                      value={colorBy}
                      onChange={(e) => setColorBy(e.target.value as 'category' | 'language')}
                      className="bg-zinc-900 border border-zinc-800 rounded px-2 py-1 text-zinc-200 focus:outline-none focus:border-indigo-500"
                    >
                      <option value="category">Category (Layer)</option>
                      <option value="language">Language</option>
                    </select>
                  </div>

                  {/* Hide External */}
                  <label className="flex items-center gap-1.5 cursor-pointer hover:text-zinc-200 transition-colors">
                    <input
                      type="checkbox"
                      checked={hideExternal}
                      onChange={(e) => setHideExternal(e.target.checked)}
                      className="rounded border-zinc-800 bg-zinc-900 text-indigo-500 focus:ring-0"
                    />
                    <span>Hide External</span>
                  </label>

                  {/* Hide Recursive */}
                  <label className="flex items-center gap-1.5 cursor-pointer hover:text-zinc-200 transition-colors">
                    <input
                      type="checkbox"
                      checked={hideCycles}
                      onChange={(e) => setHideCycles(e.target.checked)}
                      className="rounded border-zinc-800 bg-zinc-900 text-indigo-500 focus:ring-0"
                    />
                    <span>Hide Recursions</span>
                  </label>
                </div>
              </div>

              {/* Minimal Legend */}
              <div className="flex flex-wrap items-center gap-3.5 text-[9px] font-mono text-zinc-400 select-none uppercase">
                {colorBy === 'category' ? (
                  [
                    { color: CAT_COLOR.entry_point, label: 'Entry point' },
                    { color: CAT_COLOR.core_module,  label: 'High fan-in' },
                    { color: CAT_COLOR.high_coupling,label: 'Recursive' },
                    { color: CAT_COLOR.regular,      label: 'Regular' },
                  ].map(({ color, label }) => (
                    <span key={label} className="flex items-center gap-1">
                      <span className="h-1.5 w-1.5 rounded-full shrink-0"
                            style={{ backgroundColor: color }} aria-hidden="true" />
                      {label}
                    </span>
                  ))
                ) : (
                  Object.entries(LANG_COLOR).map(([lang, color]) => (
                    <span key={lang} className="flex items-center gap-1">
                      <span className="h-1.5 w-1.5 rounded-full shrink-0"
                            style={{ backgroundColor: color }} aria-hidden="true" />
                      <span className="capitalize">{lang}</span>
                    </span>
                  ))
                )}
                <span className="flex items-center gap-1">
                  <span className="h-0.5 w-3 border-t border-dashed border-amber-400" aria-hidden="true" />
                  Ambiguous call
                </span>
              </div>

              {/* Canvas + Side Panel Drawer */}
              <div className="flex border border-border/80 rounded-xl overflow-hidden bg-[#030303] h-[680px] relative">
                <div className="flex-1 min-w-0 h-full">
                  <ReactFlowProvider>
                    <CallGraphCanvas
                      cgNodes={filteredNodes}
                      cgEdges={filteredEdges}
                      selectedNodeId={selectedNode?.id ?? null}
                      colorBy={colorBy}
                      onNodeClick={(node) => {
                        setSelectedNode(node);
                        setBlastRadius(null);
                      }}
                    />
                  </ReactFlowProvider>
                </div>

                {/* Function Details Inspector Drawer */}
                {selectedNode && (
                  <NodePanel
                    node={selectedNode}
                    repoName={repoName}
                    onClose={() => { setSelectedNode(null); setBlastRadius(null); }}
                    onBlastRadius={loadBlastRadius}
                    onNeighbors={loadNeighbors}
                    onTrace={loadTrace}
                  />
                )}
              </div>

              {/* Blast radius panel — shown below graph when active */}
              {brLoading && (
                <SkeletonGroup label="Computing blast radius">
                  <SkeletonCard />
                </SkeletonGroup>
              )}
              {blastRadius && !brLoading && (
                <BlastRadiusPanel
                  br={blastRadius}
                  onClose={() => setBlastRadius(null)}
                />
              )}
                </>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default CallGraphAnalyzer;
