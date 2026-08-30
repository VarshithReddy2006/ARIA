/**
 * CallGraphAnalyzer — Developer-First Execution Investigation Workspace
 *
 * Core Principle:
 * FILE GRAPH = ARCHITECTURE (Spatial: System → Components → Modules → Files)
 * CALL GRAPH = BEHAVIOR (Temporal: Entry → Function → Branch → Side Effect → Return)
 *
 * Answers the three primary developer questions in the first 10 seconds:
 * 1. What happens when this software runs?
 * 2. Where can it break? (Failure Boundaries)
 * 3. What changes if I modify this? (Behavioral Change Simulation)
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
import { EmptyState } from '../ui/EmptyState';
import { SkeletonCard, SkeletonGroup } from '../ui/Skeleton';
import {
  Workflow, Zap, AlertTriangle, ArrowUpFromLine,
  ArrowDownToLine, RefreshCw, Search, X,
  Code2, GitBranch, Repeat2, Info, ZoomIn, ZoomOut, Maximize,
  Sparkles, ExternalLink, ArrowRight, ArrowLeft, Network,
  Layers, ShieldAlert, Crosshair, ArrowLeftRight, CheckCircle2,
  Flame, HelpCircle, Compass, ListTree, Copy, Check, ChevronDown, ChevronUp,
  Play, Split, Activity, Radio, GitCommit, ShieldCheck, AlertCircle, Database,
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
import {
  computeCallGraphSignals,
  extractExecutionFlows,
  extractBranchPoints,
  extractFailureBoundaries,
  simulateChangeImpact,
  buildAbstractedCallGraph,
  tracePathToNode,
  traceDetailedRoute,
  findRecursiveClusters,
  rankHotspots,
  generateCallGraphQuestions,
  deriveConfidenceLevel,
  deriveExecutionRole,
  generateWhyItMatters,
  shortLabel,
} from './graph/callGraphIntelligence';
import type {
  CgNode,
  CgEdge,
  ExecutionFlow,
  CallGraphSignals,
  CgInvestigationMode,
  ExecutionRole,
  BranchPoint,
  FailureBoundary,
  ChangeSimulationImpact,
  RecursiveCluster,
  HotspotNode,
  TraceRouteDetails,
} from './graph/callGraphIntelligence';

// ── Types ─────────────────────────────────────────────────────────────────

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
  onViewInCallGraph?: (filePath: string) => void;
}

// ── Execution Role Colors ─────────────────────────────────────────────────

const ROLE_ACCENT: Record<ExecutionRole, { color: string; border: string; bg: string }> = {
  ENTRY:       { color: '#10b981', border: 'border-emerald-500/80', bg: 'bg-emerald-950/60' },
  CALL:        { color: '#3b82f6', border: 'border-blue-500/60',    bg: 'bg-blue-950/40' },
  BRANCH:      { color: '#8b5cf6', border: 'border-purple-500/70',  bg: 'bg-purple-950/50' },
  RETURN:      { color: '#06b6d4', border: 'border-cyan-500/70',    bg: 'bg-cyan-950/40' },
  'SIDE EFFECT': { color: '#f43f5e', border: 'border-rose-500/80',  bg: 'bg-rose-950/60' },
  EXTERNAL:    { color: '#64748b', border: 'border-slate-500/60',   bg: 'bg-slate-900/60' },
  RECURSIVE:   { color: '#f59e0b', border: 'border-amber-500/80',   bg: 'bg-amber-950/70' },
  TERMINAL:    { color: '#71717a', border: 'border-zinc-700/80',    bg: 'bg-zinc-900/80' },
};

function shortId(id: string): string {
  const parts = id.split('::');
  return parts[parts.length - 1] || id;
}

// ── Custom React Flow Execution Node ──────────────────────────────────────

interface CustomNodeData {
  node: CgNode;
  isSelected: boolean;
  isDimmed: boolean;
  isCaller: boolean;
  isCallee: boolean;
  isOnPath?: boolean;
  role: ExecutionRole;
  stageDelayMs?: number;
}

const CustomCallNode: React.FC<{ data: CustomNodeData }> = ({ data }) => {
  const {
    node,
    isSelected,
    isDimmed,
    isCaller,
    isCallee,
    isOnPath,
    role,
    stageDelayMs = 0,
  } = data;

  const roleStyle = ROLE_ACCENT[role] || ROLE_ACCENT.CALL;

  let borderStyle = roleStyle.border;
  let glowStyle = '';

  if (isSelected) {
    borderStyle = 'border-indigo-400';
    glowStyle = 'ring-2 ring-indigo-500/70 shadow-lg shadow-indigo-500/30';
  } else if (isOnPath) {
    borderStyle = 'border-amber-400';
    glowStyle = 'ring-2 ring-amber-400/60 shadow-md shadow-amber-500/25';
  } else if (isCaller) {
    borderStyle = 'border-emerald-500';
    glowStyle = 'ring-1 ring-emerald-500/50 shadow-sm shadow-emerald-500/15';
  } else if (isCallee) {
    borderStyle = 'border-indigo-500';
    glowStyle = 'ring-1 ring-indigo-500/50 shadow-sm shadow-indigo-500/15';
  }

  return (
    <div
      style={{
        width: CG_NODE_W,
        height: CG_NODE_H,
        transitionDelay: `${stageDelayMs}ms`,
      }}
      className={`relative flex flex-col justify-center px-3 py-1.5 rounded-lg bg-zinc-950/95 border ${borderStyle} ${glowStyle} cursor-pointer select-none transition-all duration-200 ${
        isDimmed ? 'opacity-15 scale-95' : 'opacity-100 hover:border-zinc-400'
      }`}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!w-1.5 !h-1.5 !bg-zinc-500 !border-none !-top-1"
      />
      <Handle
        type="source"
        position={Position.Bottom}
        className="!w-1.5 !h-1.5 !bg-zinc-500 !border-none !-bottom-1"
      />

      <div className="flex items-center justify-between gap-1.5 min-w-0">
        <div className="flex items-center gap-1.5 min-w-0 flex-1">
          <span
            className="w-2 h-2 rounded-full shrink-0 shadow-sm"
            style={{ backgroundColor: roleStyle.color }}
            aria-hidden="true"
          />
          <span className="text-[11px] font-bold text-zinc-100 truncate font-mono" title={node.label}>
            {shortId(node.id)}
          </span>
        </div>

        <span
          className={`text-[8px] font-mono font-extrabold px-1.5 py-0.5 rounded shrink-0 border ${roleStyle.bg} text-zinc-200 border-zinc-700/80`}
        >
          {role}
        </span>
      </div>

      <div className="flex items-center justify-between text-[9px] text-zinc-500 font-mono mt-1 pt-1 border-t border-zinc-900">
        <span className="truncate max-w-[110px]" title={node.file_path || 'source'}>
          {node.file_path ? node.file_path.split('/').pop() : ''}
        </span>
        <span className="shrink-0 text-zinc-400 font-medium">
          <span className="text-emerald-400" title="Callers (Fan-in)">{node.fan_in}↓</span> / <span className="text-indigo-400" title="Callees (Fan-out)">{node.fan_out}↑</span>
        </span>
      </div>
    </div>
  );
};

const customNodeTypes = { customCallNode: CustomCallNode };

// ── Canvas Component ──────────────────────────────────────────────────────

interface CanvasProps {
  cgNodes: CgNode[];
  cgEdges: CgEdge[];
  selectedNodeId: string | null;
  activePathNodes: Set<string>;
  focusOnly: boolean;
  onNodeClick: (node: CgNode | null) => void;
  onToggleFocusOnly: () => void;
}

const CallGraphCanvas: React.FC<CanvasProps> = ({
  cgNodes,
  cgEdges,
  selectedNodeId,
  activePathNodes,
  focusOnly,
  onNodeClick,
  onToggleFocusOnly,
}) => {
  const [rfNodes, setRfNodes, onNodesChange] = useNodesState([]);
  const [rfEdges, setRfEdges, onEdgesChange] = useEdgesState([]);
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const { zoomIn, zoomOut, fitView, setCenter, getNodes } = useReactFlow();

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
    return new Set<string>([selectedNodeId, ...callerIds, ...calleeIds, ...Array.from(activePathNodes)]);
  }, [selectedNodeId, callerIds, calleeIds, activePathNodes]);

  const hoveredNode = useMemo(() => {
    if (!hoveredNodeId || hoveredNodeId === selectedNodeId) return null;
    return cgNodes.find((n) => n.id === hoveredNodeId) ?? null;
  }, [hoveredNodeId, selectedNodeId, cgNodes]);

  // Compute Layout & Map React Flow Elements
  useEffect(() => {
    const visibleNodes = focusOnly && selectedNodeId
      ? cgNodes.filter((n) => neighborIds.has(n.id))
      : cgNodes;

    const visibleNodeIds = new Set(visibleNodes.map((n) => n.id));
    const visibleEdges = cgEdges.filter(
      (e) => visibleNodeIds.has(e.source) && visibleNodeIds.has(e.target)
    );

    const positions = computeCallGraphLayout(visibleNodes, visibleEdges);

    const mappedNodes = visibleNodes.map((n) => {
      const isSelected = selectedNodeId === n.id;
      const isCaller = callerIds.has(n.id);
      const isCallee = calleeIds.has(n.id);
      const isOnPath = activePathNodes.has(n.id);
      const isDimmed = (selectedNodeId !== null || activePathNodes.size > 0) && !neighborIds.has(n.id);
      const role = n.execution_role || deriveExecutionRole(n);

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
          isOnPath,
          role,
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

    const mutualPairs = buildMutualPairSet(visibleEdges);

    const mappedEdges = visibleEdges.map((e, i) => {
      const isIncoming = Boolean(selectedNodeId) && e.target === selectedNodeId;
      const isOutgoing = Boolean(selectedNodeId) && e.source === selectedNodeId;
      const isPathEdge = activePathNodes.size > 1 && activePathNodes.has(e.source) && activePathNodes.has(e.target);

      const visual = resolveCallEdgeStyle({
        isSelfCall: e.source === e.target,
        isMutualRecursion: isMutual(mutualPairs, e.source, e.target),
        isOutgoing: isOutgoing || isPathEdge,
        isIncoming,
        isAmbiguous: Boolean(e.ambiguous),
        hasActive: selectedNodeId !== null || activePathNodes.size > 0,
      });

      const choreo = resolveFocusChoreography(
        edgeFocusRole({ isIncoming, isOutgoing, hasActive: selectedNodeId !== null }),
        'execution',
      );

      return {
        id: `e-${i}-${e.source}-${e.target}`,
        source: e.source,
        target: e.target,
        animated: false,
        style: {
          stroke: isPathEdge ? '#f59e0b' : isIncoming ? '#10b981' : isOutgoing ? '#6366f1' : visual.stroke,
          strokeWidth: isPathEdge ? 2.5 : visual.strokeWidth,
          opacity: isPathEdge ? 1 : visual.opacity,
          strokeDasharray: visual.dash,
          transition: edgeTransition(choreo),
        },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          width: 10,
          height: 10,
          color: isPathEdge ? '#f59e0b' : isIncoming ? '#10b981' : isOutgoing ? '#6366f1' : visual.stroke,
        },
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
  }, [
    cgNodes,
    cgEdges,
    selectedNodeId,
    neighborIds,
    callerIds,
    calleeIds,
    activePathNodes,
    focusOnly,
    setRfNodes,
    setRfEdges,
  ]);

  useEffect(() => {
    if (rfNodes.length > 0) {
      const timer = setTimeout(() => {
        fitView({ padding: 0.15, duration: 300, minZoom: 0.15, maxZoom: 1.5 });
      }, 100);
      return () => clearTimeout(timer);
    }
  }, [rfNodes.length, fitView]);

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
        <Background color="rgba(255, 255, 255, 0.03)" gap={24} size={1} />

        {/* Minimal Transparent Pan/Zoom Controls */}
        <div className="absolute bottom-4 left-4 z-10 flex items-center gap-1 p-1 bg-zinc-950/90 border border-zinc-800/80 rounded-lg shadow-2xl backdrop-blur-md select-none font-mono text-[10px]">
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

          {selectedNodeId && (
            <>
              <span className="w-px h-4 bg-zinc-800 mx-0.5" />
              <button
                type="button"
                onClick={onToggleFocusOnly}
                className={`px-2 py-1 rounded text-[10px] font-bold uppercase transition-colors ${
                  focusOnly
                    ? 'bg-indigo-600 text-white shadow-sm'
                    : 'text-zinc-400 hover:text-zinc-100 hover:bg-zinc-900'
                }`}
                title={focusOnly ? 'Show full graph' : 'Isolate focused neighborhood'}
              >
                {focusOnly ? 'Show Full Graph' : 'Focus Path'}
              </button>
            </>
          )}

          <span className="w-px h-4 bg-zinc-800 mx-0.5" />
          <button
            type="button"
            onClick={() => {
              onNodeClick(null);
              fitView({ duration: 300, padding: 0.15 });
            }}
            className="px-2 py-1 rounded hover:bg-zinc-900 text-zinc-400 hover:text-zinc-100 transition-colors uppercase font-bold"
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
            if (original.category === 'entry_point') return '#10b981';
            if (original.fan_in >= 5) return '#3b82f6';
            return '#3f3f46';
          }}
          maskColor="rgba(3, 3, 3, 0.88)"
          className="!bg-zinc-950/95 !border-zinc-800/80 !rounded-md overflow-hidden shadow-2xl"
          nodeStrokeWidth={0}
          nodeBorderRadius={2}
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
              className="h-2 w-2 rounded-full"
              style={{ backgroundColor: ROLE_ACCENT[hoveredNode.execution_role || 'CALL']?.color || '#3b82f6' }}
            />
            <span className="text-[10px] uppercase font-bold text-zinc-300">
              {hoveredNode.execution_role || 'CALL'}
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

// ── Node detail panel (Execution Command Center Inspector) ─────────────────

interface NodePanelProps {
  node: CgNode;
  repoName: string;
  signals: CallGraphSignals;
  allNodes: CgNode[];
  allEdges: CgEdge[];
  onClose: () => void;
  onSelectNode: (node: CgNode) => void;
  onSimulateChange: (node: CgNode) => void;
  onTraceUpstream: (id: string) => void;
  onTraceDownstream: (id: string) => void;
  onBlastRadius: (id: string) => void;
}

const NodePanel: React.FC<NodePanelProps> = ({
  node,
  repoName,
  signals,
  allNodes,
  allEdges,
  onClose,
  onSelectNode,
  onSimulateChange,
  onTraceUpstream,
  onTraceDownstream,
  onBlastRadius,
}) => {
  const [panelTab, setPanelTab] = useState<'execution' | 'callers' | 'callees' | 'technical'>('execution');
  const [copied, setCopied] = useState(false);

  const nodeMap = useMemo(() => new Map<string, CgNode>(allNodes.map((n) => [n.id, n])), [allNodes]);

  const directCallers = useMemo(() => {
    return allEdges
      .filter((e) => e.target === node.id)
      .map((e) => nodeMap.get(e.source))
      .filter(Boolean) as CgNode[];
  }, [allEdges, node.id, nodeMap]);

  const directCallees = useMemo(() => {
    return allEdges
      .filter((e) => e.source === node.id)
      .map((e) => nodeMap.get(e.target))
      .filter(Boolean) as CgNode[];
  }, [allEdges, node.id, nodeMap]);

  const dynamicQuestions = useMemo(() => {
    return generateCallGraphQuestions(node, signals);
  }, [node, signals]);

  const whyItMatters = useMemo(() => {
    return generateWhyItMatters(node, signals);
  }, [node, signals]);

  const confidenceBadge = useMemo(() => {
    return deriveConfidenceLevel(node);
  }, [node]);

  const role = useMemo(() => {
    return node.execution_role || deriveExecutionRole(node);
  }, [node]);

  const couplingBand = useMemo(() => {
    if (node.degree > 15 || node.fan_in > 5) {
      return { text: 'HIGH COUPLING', tone: 'warn' as const };
    }
    if (node.degree > 6) {
      return { text: 'MODERATE COUPLING', tone: 'neutral' as const };
    }
    return { text: 'LOW COUPLING', tone: 'neutral' as const };
  }, [node]);

  const handleCopySymbol = useCallback(() => {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(node.id);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }
  }, [node.id]);

  const handleOpenInChat = useCallback((promptText: string) => {
    if (typeof window !== 'undefined') {
      window.dispatchEvent(
        new CustomEvent('aria-open-chat', {
          detail: {
            prompt: promptText,
            repository: repoName,
            file: node.file_path,
            symbol: node.id,
            mode: 'call_graph',
            role,
            callersCount: node.fan_in,
            calleesCount: node.fan_out,
            confidence: confidenceBadge,
          },
        })
      );
    }
  }, [repoName, node, role, confidenceBadge]);

  return (
    <aside
      className="w-84 sm:w-96 shrink-0 border-l border-zinc-800/80 bg-zinc-950/95 flex flex-col overflow-hidden font-mono z-20 shadow-2xl animate-in fade-in slide-in-from-right-2 duration-200"
      aria-label="Execution Symbol Details"
    >
      {/* Title */}
      <div className="flex items-start justify-between px-4 pt-4 pb-3 border-b border-zinc-800 bg-zinc-950 shrink-0 select-none">
        <div className="space-y-1 min-w-0 pr-2">
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-[9px] font-bold text-indigo-400 uppercase tracking-wider flex items-center gap-1">
              <Workflow className="h-3 w-3 text-indigo-400" aria-hidden="true" /> Function Inspector
            </span>
            <span className="text-[8px] font-bold text-emerald-400 bg-emerald-950/60 border border-emerald-800/60 px-1.5 py-0.2 rounded uppercase">
              [{confidenceBadge}]
            </span>
          </div>
          <div className="flex items-center gap-2">
            <h3 className="text-xs font-semibold text-zinc-100 truncate block font-mono" title={node.label}>
              {shortId(node.id)}
            </h3>
            <button
              onClick={handleCopySymbol}
              className="text-zinc-500 hover:text-zinc-200 p-0.5 rounded"
              title="Copy symbol identifier"
            >
              {copied ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
            </button>
          </div>
          <span className="text-[9px] text-zinc-500 truncate block" title={node.file_path || 'source'}>
            {node.file_path || 'Source file unknown'}
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
        <button
          onClick={() => setPanelTab('execution')}
          className={`flex-1 py-2 px-1 text-center border-b-2 transition-all whitespace-nowrap ${
            panelTab === 'execution'
              ? 'border-indigo-400 text-indigo-300 bg-indigo-500/10 font-extrabold'
              : 'border-transparent text-zinc-400 hover:text-zinc-200'
          }`}
        >
          Execution
        </button>
        <button
          onClick={() => setPanelTab('callers')}
          className={`flex-1 py-2 px-1 text-center border-b-2 transition-all whitespace-nowrap ${
            panelTab === 'callers'
              ? 'border-indigo-400 text-indigo-300 bg-indigo-500/10 font-extrabold'
              : 'border-transparent text-zinc-400 hover:text-zinc-200'
          }`}
        >
          Called By ({node.fan_in})
        </button>
        <button
          onClick={() => setPanelTab('callees')}
          className={`flex-1 py-2 px-1 text-center border-b-2 transition-all whitespace-nowrap ${
            panelTab === 'callees'
              ? 'border-indigo-400 text-indigo-300 bg-indigo-500/10 font-extrabold'
              : 'border-transparent text-zinc-400 hover:text-zinc-200'
          }`}
        >
          Calls ({node.fan_out})
        </button>
        <button
          onClick={() => setPanelTab('technical')}
          className={`flex-1 py-2 px-1 text-center border-b-2 transition-all whitespace-nowrap ${
            panelTab === 'technical'
              ? 'border-indigo-400 text-indigo-300 bg-indigo-500/10 font-extrabold'
              : 'border-transparent text-zinc-400 hover:text-zinc-200'
          }`}
        >
          Details
        </button>
      </div>

      {/* Tab Panels */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 text-xs">
        {panelTab === 'execution' && (
          <>
            {/* Coupling Band Verdict */}
            <div className="flex items-center justify-between p-2.5 bg-zinc-900/80 border border-zinc-800 rounded-lg text-xs">
              <div className="space-y-0.5">
                <span className="text-[9px] font-bold text-zinc-400 uppercase tracking-wider block">Coupling Verdict</span>
                <span className="text-[9px] text-zinc-500 block">Derived from fan-in and degree metrics</span>
              </div>
              <span className={`text-[9px] font-bold px-2 py-0.5 rounded border uppercase ${
                couplingBand.tone === 'warn'
                  ? 'text-amber-400 bg-amber-950/40 border-amber-500/40'
                  : 'text-zinc-300 bg-zinc-800 border-zinc-700'
              }`}>
                {couplingBand.text}
              </span>
            </div>

            {/* Role & Behavioral Reach */}
            <div className="p-2.5 bg-zinc-900/80 border border-zinc-800 rounded-lg flex items-center justify-between">
              <div className="space-y-0.5">
                <span className="text-[9px] font-bold text-zinc-400 uppercase tracking-wider block">Execution Role</span>
                <span className="text-[10px] text-zinc-200 font-semibold">{role}</span>
              </div>
              <span className={`text-[9px] font-bold px-2 py-0.5 rounded border uppercase ${ROLE_ACCENT[role]?.bg || 'bg-zinc-800'} text-zinc-200 border-zinc-700`}>
                {role}
              </span>
            </div>

            {/* Execution Metrics Grid */}
            <div className="grid grid-cols-3 gap-2 select-none">
              <div className="p-2 bg-zinc-900/80 border border-zinc-800 rounded-lg text-center">
                <p className="text-zinc-400 text-[8px] uppercase tracking-wider font-bold">Inbound</p>
                <p className="text-base font-bold text-emerald-400 mt-0.5">{node.fan_in}</p>
                <p className="text-[7px] text-zinc-500">callers</p>
              </div>
              <div className="p-2 bg-zinc-900/80 border border-zinc-800 rounded-lg text-center">
                <p className="text-zinc-400 text-[8px] uppercase tracking-wider font-bold">Outbound</p>
                <p className="text-base font-bold text-indigo-400 mt-0.5">{node.fan_out}</p>
                <p className="text-[7px] text-zinc-500">callees</p>
              </div>
              <div className="p-2 bg-zinc-900/80 border border-zinc-800 rounded-lg text-center">
                <p className="text-zinc-400 text-[8px] uppercase tracking-wider font-bold">Centrality</p>
                <p className="text-base font-bold text-amber-400 mt-0.5">{(node.centrality * 100).toFixed(0)}%</p>
                <p className="text-[7px] text-zinc-500">route influence</p>
              </div>
            </div>

            {/* Why This Matters Narrative */}
            <div className="p-3 bg-zinc-900/60 border border-zinc-800/80 rounded-lg space-y-1">
              <span className="text-[9px] font-bold text-zinc-400 uppercase tracking-wider block">
                Why This Symbol Matters
              </span>
              <p className="text-[11px] text-zinc-300 leading-relaxed font-sans">
                {whyItMatters}
              </p>
            </div>

            {/* Dynamic Next Investigation */}
            <div className="space-y-1.5 pt-2 border-t border-zinc-800/60">
              <span className="text-[9px] text-indigo-400 uppercase font-bold tracking-wider block flex items-center gap-1">
                <Sparkles className="h-3 w-3" /> Next Investigation
              </span>
              <div className="space-y-1">
                {dynamicQuestions.map((q, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleOpenInChat(q)}
                    className="w-full text-left p-2 bg-zinc-900/90 hover:bg-zinc-800 border border-zinc-800/80 hover:border-indigo-500/40 rounded text-[10px] text-zinc-300 hover:text-zinc-100 transition-all font-sans leading-snug flex items-start gap-1.5"
                  >
                    <ArrowRight className="h-3 w-3 text-indigo-400 shrink-0 mt-0.5" />
                    <span>{q}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Execution Actions */}
            <div className="space-y-1.5 pt-2 border-t border-zinc-800/60">
              <span className="text-[9px] text-zinc-400 uppercase font-bold tracking-wider block mb-1">
                Execution Actions
              </span>
              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={() => onTraceUpstream(node.id)}
                  className="flex items-center justify-center gap-1.5 bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/30 text-emerald-300 font-bold px-2 py-1.5 rounded text-[10px] transition-all"
                  title="Trace upstream execution ancestry"
                >
                  <ArrowLeft className="h-3 w-3" /> Trace Upstream
                </button>
                <button
                  onClick={() => onTraceDownstream(node.id)}
                  className="flex items-center justify-center gap-1.5 bg-indigo-500/10 hover:bg-indigo-500/20 border border-indigo-500/30 text-indigo-300 font-bold px-2 py-1.5 rounded text-[10px] transition-all"
                  title="Trace downstream execution targets"
                >
                  <ArrowRight className="h-3 w-3" /> Trace Downstream
                </button>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={() => onSimulateChange(node)}
                  className="flex items-center justify-center gap-1.5 bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/30 text-amber-300 font-bold px-2 py-1.5 rounded text-[10px] transition-all"
                  title="Simulate behavioral change impact"
                >
                  <Zap className="h-3 w-3" /> Simulate Change
                </button>
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
                  className="flex items-center justify-center gap-1.5 bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 text-zinc-300 font-bold px-2 py-1.5 rounded text-[10px] transition-all"
                >
                  <ExternalLink className="h-3 w-3 text-indigo-400" /> File Graph
                </button>
              </div>

              <button
                onClick={() =>
                  handleOpenInChat(
                    `Explain execution behavior of ${node.id} in file ${node.file_path}, its callers, callees, and failure blast radius.`
                  )
                }
                className="w-full flex items-center justify-center gap-1.5 bg-indigo-500/10 hover:bg-indigo-500/20 border border-indigo-500/30 text-indigo-300 font-bold px-2 py-1.5 rounded text-[10px] transition-all"
              >
                <Sparkles className="h-3 w-3 text-indigo-400" /> Ask ARIA
              </button>
            </div>
          </>
        )}

        {panelTab === 'callers' && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <p className="text-zinc-400 text-[10px]">Functions that call <strong>{shortId(node.id)}</strong>:</p>
              <button
                onClick={() => onTraceUpstream(node.id)}
                className="text-[9px] text-emerald-400 hover:underline font-bold"
              >
                Trace Upstream
              </button>
            </div>
            {directCallers.length === 0 ? (
              <p className="text-zinc-500 text-[10px] italic p-2 bg-zinc-900/40 rounded">
                No direct callers found (this is a root entry or uncalled function).
              </p>
            ) : (
              <div className="space-y-1.5 max-h-72 overflow-y-auto">
                {directCallers.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => onSelectNode(c)}
                    className="w-full text-left p-2 bg-zinc-900/80 hover:bg-zinc-800 border border-zinc-800 rounded flex items-center justify-between gap-2 transition-all"
                  >
                    <div className="min-w-0">
                      <div className="font-semibold text-zinc-200 truncate text-[11px]">
                        {shortId(c.id)}
                      </div>
                      <div className="text-[8px] text-zinc-500 truncate">
                        {c.file_path}
                      </div>
                    </div>
                    <span className="text-[9px] font-bold text-emerald-400 shrink-0">
                      {c.fan_in} callers
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {panelTab === 'callees' && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <p className="text-zinc-400 text-[10px]">Functions called by <strong>{shortId(node.id)}</strong>:</p>
              <button
                onClick={() => onTraceDownstream(node.id)}
                className="text-[9px] text-indigo-400 hover:underline font-bold"
              >
                Trace Downstream
              </button>
            </div>
            {directCallees.length === 0 ? (
              <p className="text-zinc-500 text-[10px] italic p-2 bg-zinc-900/40 rounded">
                No outgoing calls found (this is a terminal leaf function).
              </p>
            ) : (
              <div className="space-y-1.5 max-h-72 overflow-y-auto">
                {directCallees.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => onSelectNode(c)}
                    className="w-full text-left p-2 bg-zinc-900/80 hover:bg-zinc-800 border border-zinc-800 rounded flex items-center justify-between gap-2 transition-all"
                  >
                    <div className="min-w-0">
                      <div className="font-semibold text-zinc-200 truncate text-[11px]">
                        {shortId(c.id)}
                      </div>
                      <div className="text-[8px] text-zinc-500 truncate">
                        {c.file_path}
                      </div>
                    </div>
                    <span className="text-[9px] font-bold text-indigo-400 shrink-0">
                      {c.fan_out} callees
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {panelTab === 'technical' && (
          <div className="space-y-2">
            <div className="flex justify-between py-1 border-b border-zinc-800/80">
              <span className="text-zinc-500">Symbol Type</span>
              <span className="text-zinc-200 font-semibold">{node.symbol_type || 'function'}</span>
            </div>
            <div className="flex justify-between py-1 border-b border-zinc-800/80">
              <span className="text-zinc-500">Language</span>
              <span className="text-zinc-200 font-semibold">{node.language || 'Python'}</span>
            </div>
            <div className="flex justify-between py-1 border-b border-zinc-800/80">
              <span className="text-zinc-500">Recursive</span>
              <span className={node.is_recursive ? 'text-amber-400 font-bold' : 'text-zinc-400'}>
                {node.is_recursive ? 'Yes (Cyclic)' : 'No'}
              </span>
            </div>
            <div className="flex justify-between py-1 border-b border-zinc-800/80">
              <span className="text-zinc-500">Total Degree</span>
              <span className="text-zinc-200">{node.degree}</span>
            </div>
            <div className="flex justify-between py-1 border-b border-zinc-800/80">
              <span className="text-zinc-500">Route Centrality</span>
              <span className="text-zinc-200">{(node.centrality * 100).toFixed(1)}%</span>
            </div>
            <div className="flex justify-between py-1 border-b border-zinc-800/80">
              <span className="text-zinc-500">Line</span>
              <span className="text-zinc-200">{node.line ?? '—'}</span>
            </div>
          </div>
        )}
      </div>
    </aside>
  );
};

// ── Behavioral Change Simulation Panel ─────────────────────────────────────

interface ChangeSimulationPanelProps {
  sim: ChangeSimulationImpact;
  repoName: string;
  onClose: () => void;
  onTraceAffectedFlows: () => void;
}

const ChangeSimulationPanel: React.FC<ChangeSimulationPanelProps> = ({
  sim,
  repoName,
  onClose,
  onTraceAffectedFlows,
}) => {
  const riskColor =
    sim.riskRating === 'Critical'
      ? 'text-red-400 border-red-500/40 bg-red-950/30'
      : sim.riskRating === 'High'
        ? 'text-orange-400 border-orange-500/40 bg-orange-950/30'
        : sim.riskRating === 'Medium'
          ? 'text-amber-400 border-amber-500/40 bg-amber-950/30'
          : 'text-emerald-400 border-emerald-500/40 bg-emerald-950/30';

  return (
    <div className="p-4 bg-zinc-950 border border-amber-500/40 rounded-xl space-y-3 font-mono shadow-2xl animate-in fade-in duration-200">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Zap className="h-4 w-4 text-amber-400" />
          <h4 className="text-xs font-bold text-zinc-100 uppercase tracking-wider">
            Behavioral Change Simulation: <span className="text-amber-300">{shortId(sim.targetId)}</span>
          </h4>
          <span className={`text-[9px] font-bold px-2 py-0.5 rounded border uppercase ${riskColor}`}>
            {sim.riskRating} Risk
          </span>
          <span className="text-[8px] text-zinc-500 font-bold px-1.5 py-0.5 rounded border border-zinc-800 bg-zinc-900 uppercase">
            Static Graph Impact
          </span>
        </div>
        <button onClick={onClose} className="text-zinc-500 hover:text-zinc-200">
          <X className="h-4 w-4" />
        </button>
      </div>

      <p className="text-[11px] text-zinc-300 font-sans leading-relaxed">
        {sim.narrativeImpact}
      </p>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center text-xs">
        <div className="p-2 bg-zinc-900/90 border border-zinc-800 rounded-lg">
          <span className="text-zinc-500 text-[9px] block">Affected Entry Paths</span>
          <span className="text-base font-bold text-emerald-400">{sim.affectedEntryPaths.length}</span>
        </div>
        <div className="p-2 bg-zinc-900/90 border border-zinc-800 rounded-lg">
          <span className="text-zinc-500 text-[9px] block">Downstream Cascade</span>
          <span className="text-base font-bold text-indigo-400">{sim.downstreamCount}</span>
        </div>
        <div className="p-2 bg-zinc-900/90 border border-zinc-800 rounded-lg">
          <span className="text-zinc-500 text-[9px] block">Upstream Callers</span>
          <span className="text-base font-bold text-zinc-200">{sim.upstreamCount}</span>
        </div>
        <div className="p-2 bg-zinc-900/90 border border-zinc-800 rounded-lg">
          <span className="text-zinc-500 text-[9px] block">Affected Files</span>
          <span className="text-base font-bold text-amber-400">{sim.affectedFileCount}</span>
        </div>
      </div>

      <div className="flex items-center justify-between gap-2 pt-2 border-t border-zinc-800/80 flex-wrap">
        <div className="text-[10px] text-zinc-400">
          {sim.affectedTests.length > 0
            ? `${sim.affectedTests.length} test suite(s) exercise this execution subtree.`
            : 'No automated tests detected in downstream subtree.'}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={onTraceAffectedFlows}
            className="px-3 py-1 bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/30 text-amber-300 rounded text-[10px] font-bold uppercase transition-all"
          >
            Trace Affected Flows
          </button>
          <button
            onClick={() => {
              if (typeof window !== 'undefined') {
                window.dispatchEvent(
                  new CustomEvent('aria-open-chat', {
                    detail: {
                      prompt: `Simulate change impact for function ${sim.targetId}. What execution behavior breaks across its ${sim.downstreamCount} downstream functions and ${sim.affectedEntryPaths.length} entry flows?`,
                      repository: repoName,
                      file: sim.targetNode.file_path,
                      symbol: sim.targetId,
                      mode: 'call_graph',
                    },
                  })
                );
              }
            }}
            className="px-3 py-1 bg-indigo-600 hover:bg-indigo-500 text-white rounded text-[10px] font-bold uppercase transition-all flex items-center gap-1"
          >
            <Sparkles className="h-3 w-3" /> Ask ARIA
          </button>
        </div>
      </div>
    </div>
  );
};

// ── Stats Dashboard Panel ───────────────────────────────────────────────────

interface StatsPanelProps {
  stats: CgStats;
  signals?: CallGraphSignals;
}

const StatsPanel: React.FC<StatsPanelProps> = ({ stats, signals }) => {
  return (
    <div className="space-y-4 font-mono">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="p-3 bg-zinc-950 border border-zinc-800 rounded-xl">
          <span className="text-[9px] font-bold text-zinc-500 uppercase tracking-wider block">Functions</span>
          <span className="text-xl font-bold text-zinc-100 mt-1 block">{stats.node_count.toLocaleString()}</span>
        </div>
        <div className="p-3 bg-zinc-950 border border-zinc-800 rounded-xl">
          <span className="text-[9px] font-bold text-zinc-500 uppercase tracking-wider block">Call Edges</span>
          <span className="text-xl font-bold text-zinc-100 mt-1 block">{stats.edge_count.toLocaleString()}</span>
        </div>
        <div className="p-3 bg-zinc-950 border border-zinc-800 rounded-xl">
          <span className="text-[9px] font-bold text-zinc-500 uppercase tracking-wider block">Entry Functions</span>
          <span className="text-xl font-bold text-emerald-400 mt-1 block">{stats.entry_functions.toLocaleString()}</span>
        </div>
        <div className="p-3 bg-zinc-950 border border-zinc-800 rounded-xl">
          <span className="text-[9px] font-bold text-zinc-500 uppercase tracking-wider block">Recursive Symbols</span>
          <span className="text-xl font-bold text-amber-400 mt-1 block">{stats.recursive_functions.toLocaleString()}</span>
        </div>
      </div>

      {signals && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="p-3 bg-zinc-950 border border-zinc-800 rounded-xl">
            <span className="text-[9px] font-bold text-zinc-500 uppercase tracking-wider block">Avg Fan-In / Out</span>
            <span className="text-lg font-bold text-zinc-100 mt-1 block">
              {signals.avgFanIn} / {signals.avgFanOut}
            </span>
          </div>
          <div className="p-3 bg-zinc-950 border border-zinc-800 rounded-xl">
            <span className="text-[9px] font-bold text-zinc-500 uppercase tracking-wider block">Max Fan-In</span>
            <span className="text-lg font-bold text-emerald-400 mt-1 block">{signals.maxFanIn} callers</span>
          </div>
          <div className="p-3 bg-zinc-950 border border-zinc-800 rounded-xl">
            <span className="text-[9px] font-bold text-zinc-500 uppercase tracking-wider block">Recursive Cycles</span>
            <span className="text-lg font-bold text-amber-400 mt-1 block">{signals.recursiveClustersCount}</span>
          </div>
          <div className="p-3 bg-zinc-950 border border-zinc-800 rounded-xl">
            <span className="text-[9px] font-bold text-zinc-500 uppercase tracking-wider block">Disconnected</span>
            <span className="text-lg font-bold text-zinc-400 mt-1 block">{signals.disconnectedCount} symbols</span>
          </div>
        </div>
      )}

      {/* Top Fan-In and Fan-Out lists */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="p-4 bg-zinc-950 border border-zinc-800 rounded-xl space-y-2">
          <h4 className="text-xs font-bold text-emerald-400 uppercase tracking-wider flex items-center gap-1.5">
            <ArrowDownToLine className="h-4 w-4" /> Top Fan-In Symbols (Most Called)
          </h4>
          <div className="space-y-1.5 max-h-60 overflow-y-auto">
            {stats.top_fan_in.slice(0, 8).map((item) => (
              <div key={item.node_id} className="flex justify-between items-center text-xs p-2 bg-zinc-900/60 rounded">
                <span className="truncate max-w-[200px] text-zinc-300 font-mono" title={item.node_id}>
                  {shortId(item.node_id)}
                </span>
                <span className="text-emerald-400 font-bold">{item.fan_in} callers</span>
              </div>
            ))}
          </div>
        </div>

        <div className="p-4 bg-zinc-950 border border-zinc-800 rounded-xl space-y-2">
          <h4 className="text-xs font-bold text-indigo-400 uppercase tracking-wider flex items-center gap-1.5">
            <ArrowUpFromLine className="h-4 w-4" /> Top Fan-Out Symbols (Most Outgoing)
          </h4>
          <div className="space-y-1.5 max-h-60 overflow-y-auto">
            {stats.top_fan_out.slice(0, 8).map((item) => (
              <div key={item.node_id} className="flex justify-between items-center text-xs p-2 bg-zinc-900/60 rounded">
                <span className="truncate max-w-[200px] text-zinc-300 font-mono" title={item.node_id}>
                  {shortId(item.node_id)}
                </span>
                <span className="text-indigo-400 font-bold">{item.fan_out} callees</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

// ── Main Component ─────────────────────────────────────────────────────────

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

  // Investigation Mode state (Default: execution_flows)
  const [mode, setMode] = useState<CgInvestigationMode>('execution_flows');
  const [activeFlow, setActiveFlow] = useState<ExecutionFlow | null>(null);
  const [activePathNodes, setActivePathNodes] = useState<Set<string>>(new Set());
  const [activeTraceRoute, setActiveTraceRoute] = useState<TraceRouteDetails | null>(null);
  const [activeSimulation, setActiveSimulation] = useState<ChangeSimulationImpact | null>(null);
  const [focusOnly, setFocusOnly] = useState(false);
  const [showStory, setShowStory] = useState(true);

  // UI state
  const [activeView, setActiveView] = useState<'graph' | 'stats'>('graph');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedNode, setSelectedNode] = useState<CgNode | null>(null);
  const [blastRadius, setBlastRadius] = useState<BlastRadius | null>(null);
  const [brLoading, setBrLoading] = useState(false);

  // Filters & controls
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

      // Default mode is always Execution Flows for behavioral focus
      if (!q && data.nodes) {
        setMode('execution_flows');
      }
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

  // Filter nodes & edges on client side
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

  // Derived Signals & Telemetry
  const signals = useMemo(() => {
    return computeCallGraphSignals(filteredNodes, filteredEdges);
  }, [filteredNodes, filteredEdges]);

  // Ranked Flows (Top 3–5)
  const rankedFlows = useMemo(() => {
    return extractExecutionFlows(filteredNodes, filteredEdges, 5);
  }, [filteredNodes, filteredEdges]);

  // Failure Boundaries
  const failureBoundariesList = useMemo(() => {
    return signals.failureBoundaries || extractFailureBoundaries(filteredNodes, filteredEdges, rankedFlows);
  }, [signals.failureBoundaries, filteredNodes, filteredEdges, rankedFlows]);

  // Hot Paths Ranking
  const rankedHotspotsList = useMemo(() => {
    return rankHotspots(filteredNodes, filteredEdges, 'top10');
  }, [filteredNodes, filteredEdges]);

  // Branch Points
  const branchPointsList = useMemo(() => {
    return extractBranchPoints(filteredNodes, filteredEdges);
  }, [filteredNodes, filteredEdges]);

  // Recursive Clusters
  const recursiveClustersList = useMemo(() => {
    return findRecursiveClusters(filteredNodes, filteredEdges);
  }, [filteredNodes, filteredEdges]);

  // Mode-based Graph Builder
  const abstractedResult = useMemo(() => {
    let baseNodes = filteredNodes;
    let baseEdges = filteredEdges;

    if (mode === 'hot_paths' || mode === 'hotspots') {
      const hotspotNodeIds = new Set(rankedHotspotsList.map((h) => h.node.id));
      baseNodes = filteredNodes.filter((n) => hotspotNodeIds.has(n.id));
    } else if (mode === 'branches') {
      const branchIds = new Set(branchPointsList.map((b) => b.nodeId));
      branchPointsList.forEach((b) => {
        b.divergentBranches.forEach((d) => branchIds.add(d.targetId));
      });
      baseNodes = filteredNodes.filter((n) => branchIds.has(n.id));
    } else if (mode === 'recursion') {
      baseNodes = filteredNodes.filter((n) => n.is_recursive);
    } else if (mode === 'failure_boundaries') {
      const boundaryIds = new Set(failureBoundariesList.map((b) => b.nodeId));
      baseNodes = filteredNodes.filter((n) => boundaryIds.has(n.id));
    }

    const level = mode === 'symbol_detail' ? 'symbols' : 'flows';
    return buildAbstractedCallGraph(baseNodes, baseEdges, level, selectedNode?.id || null, activeFlow);
  }, [filteredNodes, filteredEdges, mode, rankedHotspotsList, branchPointsList, failureBoundariesList, selectedNode?.id, activeFlow]);

  // Trace Upstream Handler
  const handleTraceUpstream = useCallback((nodeId: string) => {
    const path = tracePathToNode(nodeId, filteredNodes, filteredEdges, 'upstream');
    setActivePathNodes(new Set(path));
    const details = traceDetailedRoute(path, filteredNodes, filteredEdges, nodeId);
    setActiveTraceRoute(details);
    setMode('trace');
  }, [filteredNodes, filteredEdges]);

  // Trace Downstream Handler
  const handleTraceDownstream = useCallback((nodeId: string) => {
    const path = tracePathToNode(nodeId, filteredNodes, filteredEdges, 'downstream');
    setActivePathNodes(new Set(path));
    const details = traceDetailedRoute(path, filteredNodes, filteredEdges, nodeId);
    setActiveTraceRoute(details);
    setMode('trace');
  }, [filteredNodes, filteredEdges]);

  // Change Simulation Handler
  const handleSimulateChange = useCallback((node: CgNode) => {
    const sim = simulateChangeImpact(node.id, filteredNodes, filteredEdges);
    setActiveSimulation(sim);
  }, [filteredNodes, filteredEdges]);

  // Keyboard shortcut '/'
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === '/' && !['INPUT', 'TEXTAREA'].includes((e.target as HTMLElement)?.tagName)) {
        e.preventDefault();
        const searchInput = document.querySelector('input[aria-label="Search call graph"]') as HTMLInputElement;
        if (searchInput) {
          searchInput.focus();
          searchInput.select();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Auto-load on mount
  useEffect(() => {
    setSelectedNode(null);
    setBlastRadius(null);
    setActiveFlow(null);
    setActivePathNodes(new Set());
    setActiveTraceRoute(null);
    setActiveSimulation(null);
    setFocusOnly(false);
    setSearchQuery('');
    setGraphData(null);
    setStats(null);
    loadGraph('');
    loadStats();
  }, [repoName, loadGraph, loadStats]);

  // Build handler
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

  const handleSearch = useCallback((val: string) => {
    setSearchQuery(val);
    if (searchDebounce.current) clearTimeout(searchDebounce.current);
    searchDebounce.current = setTimeout(() => {
      loadGraph(val);
    }, 300);
  }, [loadGraph]);

  const searchSuggestions = useMemo(() => {
    if (!searchQuery.trim() || !filteredNodes.length) return [];
    const q = searchQuery.toLowerCase();
    return filteredNodes
      .filter(
        (n) =>
          n.id.toLowerCase().includes(q) ||
          n.label.toLowerCase().includes(q) ||
          (n.file_path && n.file_path.toLowerCase().includes(q))
      )
      .slice(0, 5);
  }, [searchQuery, filteredNodes]);

  return (
    <div className="space-y-3 font-mono">
      {/* Editorial Technical Header with Engineering Signals */}
      <div className="px-4 py-2.5 border border-zinc-800/60 bg-zinc-950/95 rounded-lg flex items-center justify-between gap-4 z-10 flex-wrap shadow-2xl">
        <div className="space-y-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-bold text-indigo-400 tracking-wider uppercase">FUNCTION CALL GRAPH</span>
            <span className="text-zinc-600 text-[10px]">/</span>
            <span className="text-[10px] font-bold text-zinc-300 tracking-wider uppercase">INTER-FUNCTION TOPOLOGY</span>
            <span className="text-zinc-600 text-[10px]">/</span>
            <span className="text-[10px] text-zinc-400 uppercase tracking-wider">REPOSITORY EXECUTION</span>
          </div>
          <div className="flex items-center gap-2 text-[10px] text-zinc-400 flex-wrap">
            <span className="text-zinc-200 font-bold">{filteredNodes.length.toLocaleString()}</span> FUNCTIONS
            <span className="text-zinc-600">·</span>
            <span className="text-zinc-200 font-bold">{filteredEdges.length.toLocaleString()}</span> CALL EDGES
            <span className="text-zinc-600">·</span>
            <span className="text-emerald-400 font-bold">{signals.entryPointCount}</span> ENTRY POINTS
            {signals.recursiveSymbolsCount > 0 && (
              <>
                <span className="text-zinc-600">·</span>
                <span className="text-amber-400 font-bold">{signals.recursiveSymbolsCount}</span> RECURSIVE
              </>
            )}
            {signals.highFanInCount > 0 && (
              <>
                <span className="text-zinc-600">·</span>
                <span className="text-indigo-400 font-bold">{signals.highFanInCount}</span> HIGH FAN-IN
              </>
            )}
            {signals.disconnectedCount > 0 && (
              <>
                <span className="text-zinc-600">·</span>
                <span className="text-zinc-500">{signals.disconnectedCount} DISCONNECTED</span>
              </>
            )}
          </div>
        </div>

        {/* Header Actions */}
        <div className="flex items-center gap-3 shrink-0">
          <div className="flex items-center bg-zinc-900 border border-zinc-800 rounded p-0.5 text-[9px]">
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

          <button
            onClick={() => {
              setSelectedNode(null);
              setBlastRadius(null);
              setActiveFlow(null);
              setActivePathNodes(new Set());
              setActiveTraceRoute(null);
              setActiveSimulation(null);
              setFocusOnly(false);
              setMode('execution_flows');
              setSearchQuery('');
              loadGraph('');
            }}
            className="flex items-center gap-1 px-2.5 py-1 rounded border border-zinc-800 bg-zinc-900 hover:bg-zinc-800 text-zinc-400 hover:text-zinc-100 text-xs transition-colors"
            title="Reset active query and selection"
          >
            <RefreshCw className="h-3 w-3" /> Reset
          </button>

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

      {/* Hero Initial Experience: "WHAT HAPPENS WHEN THIS SOFTWARE RUNS?" */}
      {signals.executionStory && (
        <div className="p-4 bg-zinc-950/95 border border-indigo-500/30 rounded-xl space-y-3 font-mono shadow-2xl">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div className="flex items-center gap-2">
              <Play className="h-4 w-4 text-emerald-400 fill-emerald-500/20" />
              <div>
                <h3 className="font-extrabold text-xs text-zinc-100 uppercase tracking-wider">
                  WHAT HAPPENS WHEN THIS SOFTWARE RUNS?
                </h3>
                <p className="text-[10px] text-zinc-400">
                  {signals.executionStory.summaryText}
                </p>
              </div>
            </div>

            <button
              onClick={() => setShowStory((prev) => !prev)}
              className="text-zinc-500 hover:text-zinc-200 text-[10px] flex items-center gap-1"
            >
              {showStory ? 'Collapse Narrative' : 'Expand Narrative'}
              {showStory ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
            </button>
          </div>

          {/* Primary Flow Flowchart Ribbon */}
          {signals.executionStory.whatHappensFirst.length > 0 && (
            <div className="p-2.5 bg-zinc-900/80 border border-zinc-800 rounded-lg overflow-x-auto">
              <div className="flex items-center gap-2 min-w-max">
                {signals.executionStory.whatHappensFirst.map((step, idx) => (
                  <React.Fragment key={idx}>
                    <div className="px-2.5 py-1 bg-zinc-950 border border-zinc-800 rounded text-[10px] text-zinc-200 font-semibold flex items-center gap-1.5 shadow-sm">
                      <span className={`text-[8px] font-bold px-1 rounded ${idx === 0 ? 'text-emerald-400 bg-emerald-950' : idx === signals.executionStory!.whatHappensFirst.length - 1 ? 'text-rose-400 bg-rose-950' : 'text-blue-400 bg-blue-950'}`}>
                        {idx === 0 ? 'ENTRY' : idx === signals.executionStory!.whatHappensFirst.length - 1 ? 'RETURN' : 'ACTION'}
                      </span>
                      <span>{step.split(':')[1]?.trim() || step}</span>
                    </div>
                    {idx < signals.executionStory!.whatHappensFirst.length - 1 && (
                      <ArrowRight className="h-3.5 w-3.5 text-zinc-600 shrink-0" />
                    )}
                  </React.Fragment>
                ))}
              </div>
            </div>
          )}

          {/* Narrative Grounded Statements */}
          {showStory && signals.executionStory.narrativeParagraphs.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2 pt-1 border-t border-zinc-800/60 text-[11px] font-sans text-zinc-300 leading-relaxed">
              {signals.executionStory.narrativeParagraphs.map((p, idx) => (
                <div key={idx} className="p-2 bg-zinc-900/40 border border-zinc-800/60 rounded flex items-start gap-2">
                  <span className="text-indigo-400 font-bold shrink-0 mt-0.5">•</span>
                  <span>{p}</span>
                </div>
              ))}
            </div>
          )}

          {/* Three Immediate Developer Investigation Actions */}
          <div className="pt-2 border-t border-zinc-800/80 flex items-center gap-2 flex-wrap">
            <span className="text-[9px] font-bold text-zinc-500 uppercase tracking-wider mr-1">
              INVESTIGATE:
            </span>

            <button
              onClick={() => {
                setMode('execution_flows');
                if (rankedFlows.length > 0) {
                  setActiveFlow(rankedFlows[0]);
                  setActivePathNodes(new Set(rankedFlows[0].path));
                }
              }}
              className={`px-3 py-1.5 rounded text-[10px] font-bold uppercase transition-all flex items-center gap-1.5 ${
                mode === 'execution_flows'
                  ? 'bg-indigo-600 text-white shadow-md'
                  : 'bg-zinc-900 border border-zinc-800 text-zinc-300 hover:text-zinc-100 hover:border-indigo-500/50'
              }`}
            >
              <Play className="h-3 w-3 text-emerald-400" /> 1. What happens?
            </button>

            <button
              onClick={() => {
                setMode('failure_boundaries');
              }}
              className={`px-3 py-1.5 rounded text-[10px] font-bold uppercase transition-all flex items-center gap-1.5 ${
                mode === 'failure_boundaries'
                  ? 'bg-rose-600 text-white shadow-md'
                  : 'bg-zinc-900 border border-zinc-800 text-zinc-300 hover:text-zinc-100 hover:border-rose-500/50'
              }`}
            >
              <AlertTriangle className="h-3 w-3 text-rose-400" /> 2. Where can it break?
            </button>

            <button
              onClick={() => {
                if (signals.primaryEntryPoint) {
                  handleSimulateChange(signals.primaryEntryPoint);
                } else if (filteredNodes.length > 0) {
                  handleSimulateChange(filteredNodes[0]);
                }
              }}
              className="px-3 py-1.5 rounded text-[10px] font-bold uppercase transition-all flex items-center gap-1.5 bg-zinc-900 border border-zinc-800 text-zinc-300 hover:text-zinc-100 hover:border-amber-500/50"
            >
              <Zap className="h-3 w-3 text-amber-400" /> 3. What changes if I modify this?
            </button>
          </div>
        </div>
      )}

      {/* Building Notification */}
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

      {/* Loading & Error States */}
      {graphLoading && !building && (
        <div className="h-[600px] border border-zinc-800 rounded-xl bg-zinc-950 flex flex-col items-center justify-center gap-2 text-xs text-zinc-400">
          <RefreshCw className="h-5 w-5 animate-spin text-indigo-400" />
          <span>MAPPING EXECUTION TOPOLOGY…</span>
        </div>
      )}

      {!graphLoading && graphError && (
        <div className="h-[600px] border border-zinc-800 rounded-xl bg-zinc-950 flex items-center justify-center p-6">
          <EmptyState
            tone="danger"
            icon={<AlertTriangle className="h-6 w-6 text-red-400" />}
            title="TOPOLOGY UNAVAILABLE"
            description={graphError}
            action={<Button variant="ghost" onClick={() => loadGraph('')}>Retry</Button>}
          />
        </div>
      )}

      {!graphLoading && !graphError && !graphData && !building && (
        <div className="h-[600px] border border-zinc-800 rounded-xl bg-zinc-950 flex items-center justify-center p-6">
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
          {activeView === 'stats' && stats && <StatsPanel stats={stats} signals={signals} />}

          {activeView === 'graph' && (
            <div className="space-y-2">
              {/* Execution-First Modes Controller & Search */}
              <div className="px-3 py-2 bg-zinc-950/95 border border-zinc-800/80 rounded-lg flex items-center justify-between gap-3 flex-wrap select-none text-xs shadow-md">
                {/* Modes */}
                <div className="flex items-center bg-zinc-900 border border-zinc-800 rounded p-0.5 text-[9px] overflow-x-auto">
                  <button
                    onClick={() => {
                      setMode('execution_flows');
                      setActiveTraceRoute(null);
                    }}
                    className={`px-2.5 py-1 rounded transition-all font-bold whitespace-nowrap ${
                      mode === 'execution_flows' ? 'bg-indigo-600 text-white shadow-sm' : 'text-zinc-400 hover:text-zinc-200'
                    }`}
                    title="Ranked end-to-end execution chains"
                  >
                    EXECUTION FLOWS
                  </button>
                  <button
                    onClick={() => setMode('trace')}
                    className={`px-2.5 py-1 rounded transition-all font-bold whitespace-nowrap ${
                      mode === 'trace' ? 'bg-indigo-600 text-white shadow-sm' : 'text-zinc-400 hover:text-zinc-200'
                    }`}
                    title="Investigate upstream callers and downstream callees"
                  >
                    TRACE
                  </button>
                  <button
                    onClick={() => setMode('failure_boundaries')}
                    className={`px-2.5 py-1 rounded transition-all font-bold whitespace-nowrap ${
                      mode === 'failure_boundaries' ? 'bg-rose-600 text-white shadow-sm' : 'text-zinc-400 hover:text-zinc-200'
                    }`}
                    title="Failure boundaries & risky execution gates"
                  >
                    WHERE IT CAN BREAK
                  </button>
                  <button
                    onClick={() => setMode('branches')}
                    className={`px-2.5 py-1 rounded transition-all font-bold whitespace-nowrap ${
                      mode === 'branches' ? 'bg-indigo-600 text-white shadow-sm' : 'text-zinc-400 hover:text-zinc-200'
                    }`}
                    title="Divergent conditional execution paths"
                  >
                    BRANCHES
                  </button>
                  <button
                    onClick={() => setMode('hot_paths')}
                    className={`px-2.5 py-1 rounded transition-all font-bold whitespace-nowrap ${
                      mode === 'hot_paths' ? 'bg-indigo-600 text-white shadow-sm' : 'text-zinc-400 hover:text-zinc-200'
                    }`}
                    title="High route-participation symbols"
                  >
                    HOT PATHS
                  </button>
                  <button
                    onClick={() => setMode('recursion')}
                    className={`px-2.5 py-1 rounded transition-all font-bold whitespace-nowrap ${
                      mode === 'recursion' ? 'bg-amber-500/20 text-amber-300 border border-amber-500' : 'text-zinc-400 hover:text-zinc-200'
                    }`}
                    title="Recursive call cycles"
                  >
                    RECURSION
                  </button>
                  <button
                    onClick={() => setMode('symbol_detail')}
                    className={`px-2.5 py-1 rounded transition-all font-bold whitespace-nowrap ${
                      mode === 'symbol_detail' ? 'bg-indigo-600 text-white shadow-sm' : 'text-zinc-400 hover:text-zinc-200'
                    }`}
                    title="Advanced full low-level topology"
                  >
                    SYMBOL DETAIL
                  </button>
                </div>

                {/* Search Bar */}
                <div className="relative flex-grow max-w-xs ml-auto">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-zinc-500 pointer-events-none" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => handleSearch(e.target.value)}
                    placeholder="Search functions, methods, symbols…"
                    className="w-full bg-zinc-900/90 border border-zinc-800 rounded pl-8 pr-8 py-1 text-xs font-mono focus:outline-none focus:border-indigo-500 text-zinc-100 placeholder:text-zinc-500/70"
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
                    <kbd className="absolute right-2 top-1/2 -translate-y-1/2 text-[9px] font-mono text-zinc-500 bg-zinc-950 border border-zinc-800 px-1 py-0.5 rounded pointer-events-none">
                      /
                    </kbd>
                  )}

                  {/* Search Suggestions Dropdown */}
                  {searchSuggestions.length > 0 && searchQuery && (
                    <div className="absolute top-full mt-1 left-0 right-0 z-30 bg-zinc-950 border border-zinc-800 rounded-lg shadow-2xl overflow-hidden font-mono">
                      {searchSuggestions.map((s) => (
                        <button
                          key={s.id}
                          onClick={() => {
                            setSelectedNode(s);
                            handleTraceUpstream(s.id);
                            setSearchQuery('');
                          }}
                          className="w-full text-left px-3 py-1.5 hover:bg-zinc-900 border-b border-zinc-900 flex items-center justify-between text-xs transition-colors"
                        >
                          <div className="min-w-0">
                            <span className="text-zinc-200 font-semibold truncate block">{shortId(s.id)}</span>
                            <span className="text-[8px] text-zinc-500 truncate block">{s.file_path}</span>
                          </div>
                          <span className="text-[9px] text-zinc-400 shrink-0">
                            {s.fan_in}↓ / {s.fan_out}↑
                          </span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Execution Flows Mode: Ranked End-to-End Chains */}
              {mode === 'execution_flows' && rankedFlows.length > 0 && (
                <div className="p-3 bg-zinc-950/90 border border-zinc-800/80 rounded-lg space-y-2 shadow-sm font-mono">
                  <div className="flex items-center justify-between text-[10px]">
                    <span className="font-bold text-indigo-400 uppercase tracking-wider flex items-center gap-1">
                      <Workflow className="h-3 w-3" /> Ranked Execution Flows (Top {rankedFlows.length})
                    </span>
                    <span className="text-zinc-500">Click any flow to trace step-by-step execution</span>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2.5">
                    {rankedFlows.map((flow, idx) => (
                      <div
                        key={flow.id}
                        className={`p-3 rounded-lg border text-left flex flex-col justify-between space-y-2 transition-all ${
                          activeFlow?.id === flow.id
                            ? 'bg-indigo-950/50 border-indigo-500 ring-1 ring-indigo-500/40 shadow-lg'
                            : 'bg-zinc-900/70 border-zinc-800/80 hover:border-zinc-700 text-zinc-300'
                        }`}
                      >
                        <div>
                          <div className="flex items-center justify-between text-[9px] text-zinc-400 mb-1">
                            <span className="font-bold text-indigo-300">FLOW #{idx + 1}</span>
                            <span>{flow.length} steps · {flow.crossModuleCount} modules</span>
                          </div>

                          {/* Step breakdown */}
                          <div className="p-2 bg-zinc-950/80 border border-zinc-800/80 rounded my-1.5 space-y-1 text-[10px]">
                            {flow.steps?.map((step, sIdx) => (
                              <div key={sIdx} className="flex items-center gap-1.5 text-zinc-200 truncate">
                                <span className={`text-[8px] font-bold px-1 rounded ${step.isEntry ? 'text-emerald-400 bg-emerald-950/80' : step.isTerminal ? 'text-zinc-400 bg-zinc-800' : 'text-blue-400 bg-blue-950/80'}`}>
                                  {step.role}
                                </span>
                                <span className="font-semibold truncate">{step.label}()</span>
                                <span className="text-[8px] text-zinc-500 truncate ml-auto">{step.filePath.split('/').pop()}</span>
                              </div>
                            ))}
                          </div>

                          <div className="text-[9px] text-zinc-400 leading-tight font-sans">
                            {flow.rankingReason}
                          </div>
                        </div>

                        <div className="flex items-center gap-2 pt-1 border-t border-zinc-800/80">
                          <button
                            onClick={() => {
                              setActiveFlow(flow);
                              setActivePathNodes(new Set(flow.path));
                              const first = filteredNodes.find((n) => n.id === flow.path[0]);
                              if (first) setSelectedNode(first);
                            }}
                            className="flex-1 py-1 bg-indigo-600 hover:bg-indigo-500 text-white rounded text-[9px] font-bold uppercase transition-all"
                          >
                            Trace Flow
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Failure Boundaries Section ("WHERE CAN IT BREAK?") */}
              {mode === 'failure_boundaries' && (
                <div className="p-3 bg-zinc-950 border border-rose-500/40 rounded-lg space-y-3 font-mono">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <AlertTriangle className="h-4 w-4 text-rose-400" />
                      <h3 className="text-xs font-bold text-zinc-100 uppercase tracking-wider">
                        WHERE CAN IT BREAK? (Failure Boundaries & Critical Gates)
                      </h3>
                    </div>
                    <span className="text-[9px] text-zinc-400">{failureBoundariesList.length} boundaries detected</span>
                  </div>

                  {failureBoundariesList.length === 0 ? (
                    <div className="p-3 bg-zinc-900/60 border border-zinc-800 rounded text-zinc-400 text-xs">
                      No high-risk database or recursive failure boundaries identified in static graph.
                    </div>
                  ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      {failureBoundariesList.slice(0, 6).map((fb) => (
                        <div
                          key={fb.id}
                          className="p-3 bg-zinc-900/80 border border-rose-500/30 rounded-lg space-y-2 text-xs"
                        >
                          <div className="flex items-center justify-between">
                            <span className="text-[11px] font-bold text-rose-300">{fb.symbolName}</span>
                            <span className={`text-[8px] px-1.5 py-0.5 rounded font-bold uppercase border ${fb.riskRating === 'Critical' ? 'bg-red-950/80 text-red-300 border-red-800' : 'bg-amber-950/80 text-amber-300 border-amber-800'}`}>
                              {fb.boundaryType} · {fb.riskRating}
                            </span>
                          </div>

                          <p className="text-[10px] text-zinc-300 font-sans leading-relaxed">
                            {fb.whyItIsRisky}
                          </p>

                          <div className="flex items-center justify-between pt-1 border-t border-zinc-800 text-[9px] text-zinc-500">
                            <span>Reachable from {fb.inboundEntryPathsCount} entry path(s)</span>
                            <div className="flex items-center gap-2">
                              <button
                                onClick={() => handleTraceUpstream(fb.nodeId)}
                                className="text-rose-400 hover:text-rose-300 font-bold uppercase"
                              >
                                Trace Ancestry
                              </button>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Trace Mode: WHERE DID EXECUTION COME FROM? vs WHAT HAPPENS NEXT? */}
              {mode === 'trace' && activeTraceRoute && (
                <div className="p-3 bg-zinc-950 border border-indigo-500/40 rounded-lg space-y-3 font-mono">
                  <div className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2">
                      <Compass className="h-4 w-4 text-indigo-400" />
                      <span className="font-bold text-zinc-100 uppercase">
                        Execution Trace: {shortId(activeTraceRoute.path[activeTraceRoute.path.length - 1] || '')}
                      </span>
                      <span className="text-[9px] text-zinc-400">
                        ({activeTraceRoute.pathLength} steps · {activeTraceRoute.moduleCrossings} module crossings)
                      </span>
                    </div>
                    <button
                      onClick={() => { setActiveTraceRoute(null); setMode('execution_flows'); setActivePathNodes(new Set()); }}
                      className="text-zinc-500 hover:text-zinc-200 text-[10px]"
                    >
                      Clear Trace
                    </button>
                  </div>

                  {/* Split Path Breakdown */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div className="p-2.5 bg-zinc-900/80 border border-emerald-500/30 rounded-lg space-y-1.5">
                      <span className="text-[9px] font-bold text-emerald-400 uppercase tracking-wider block">
                        WHERE DID EXECUTION COME FROM? (Upstream Ancestry)
                      </span>
                      <div className="space-y-1">
                        {activeTraceRoute.upstreamPath.map((id, idx) => (
                          <div key={id} className="flex items-center gap-2 text-[10px] text-zinc-200 p-1 bg-zinc-950/60 rounded">
                            <span className="text-emerald-400 font-bold text-[9px]">#{idx + 1}</span>
                            <span className="font-semibold truncate">{shortId(id)}()</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="p-2.5 bg-zinc-900/80 border border-indigo-500/30 rounded-lg space-y-1.5">
                      <span className="text-[9px] font-bold text-indigo-400 uppercase tracking-wider block">
                        WHAT HAPPENS NEXT? (Downstream Propagation)
                      </span>
                      <div className="space-y-1">
                        {activeTraceRoute.downstreamPath.map((id, idx) => (
                          <div key={id} className="flex items-center gap-2 text-[10px] text-zinc-200 p-1 bg-zinc-950/60 rounded">
                            <span className="text-indigo-400 font-bold text-[9px]">#{idx + 1}</span>
                            <span className="font-semibold truncate">{shortId(id)}()</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Branch Mode: Divergent Execution Paths */}
              {mode === 'branches' && (
                <div className="p-3 bg-zinc-950 border border-purple-500/40 rounded-lg space-y-3 font-mono">
                  <div className="flex items-center gap-2">
                    <Split className="h-4 w-4 text-purple-400" />
                    <h3 className="text-xs font-bold text-zinc-100 uppercase tracking-wider">
                      Branch Points & Divergent Execution Routes ({branchPointsList.length} detected)
                    </h3>
                  </div>

                  {branchPointsList.length === 0 ? (
                    <div className="p-3 bg-zinc-900/60 border border-zinc-800 rounded text-zinc-400 text-xs">
                      ARIA cannot establish the branch behavior from the indexed call graph.
                    </div>
                  ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      {branchPointsList.slice(0, 6).map((bp) => (
                        <div
                          key={bp.nodeId}
                          className="p-3 bg-zinc-900/80 border border-purple-500/30 rounded-lg space-y-2 text-xs"
                        >
                          <div className="flex items-center justify-between">
                            <span className="text-[11px] font-bold text-purple-300">{shortId(bp.nodeId)}()</span>
                            <span className="text-[8px] bg-purple-950/80 text-purple-300 border border-purple-800 px-1.5 py-0.5 rounded font-bold uppercase">
                              {bp.branchCount} Divergent Branches
                            </span>
                          </div>
                          <p className="text-[9px] text-zinc-400 font-sans">{bp.reason}</p>

                          <div className="space-y-1 pt-1 border-t border-zinc-800">
                            {bp.divergentBranches.map((br) => (
                              <div key={br.targetId} className="p-1.5 bg-zinc-950/60 rounded flex items-center justify-between text-[10px]">
                                <span className="text-zinc-200 truncate">→ {shortId(br.targetId)}()</span>
                                <span className="text-[8px] text-zinc-500">{br.downstreamCount} downstream</span>
                              </div>
                            ))}
                          </div>

                          <div className="flex items-center gap-2 pt-1 border-t border-zinc-800">
                            <button
                              onClick={() => {
                                setSelectedNode(bp.node);
                                handleTraceUpstream(bp.nodeId);
                              }}
                              className="flex-1 py-1 bg-purple-600 hover:bg-purple-500 text-white rounded text-[9px] font-bold uppercase"
                            >
                              Trace Branch Point
                            </button>
                            <button
                              onClick={() => handleSimulateChange(bp.node)}
                              className="flex-1 py-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 rounded text-[9px] font-bold uppercase"
                            >
                              Simulate Change
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Hot Paths Mode: High Route-Participation Symbols */}
              {mode === 'hot_paths' && (
                <div className="p-3 bg-zinc-950 border border-zinc-800 rounded-lg space-y-3 font-mono">
                  <div className="flex items-center gap-2">
                    <Flame className="h-4 w-4 text-orange-400" />
                    <h3 className="text-xs font-bold text-zinc-100 uppercase tracking-wider">
                      Hot Execution Paths & High Route Participation
                    </h3>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2.5">
                    {rankedHotspotsList.map((h) => (
                      <div
                        key={h.node.id}
                        className="p-3 bg-zinc-900/80 border border-zinc-800 hover:border-zinc-700 rounded-lg space-y-2 text-xs transition-all"
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-[9px] font-bold text-amber-400">#{h.rank} HOT PATH</span>
                          <span className="text-[8px] text-zinc-500 truncate max-w-[140px]">{h.node.file_path}</span>
                        </div>
                        <div className="font-bold text-zinc-100 truncate text-[11px]">{shortId(h.node.id)}()</div>
                        <div className="text-[9px] text-zinc-400 font-sans">{h.riskReason}</div>
                        <div className="flex items-center gap-1.5 pt-1 border-t border-zinc-800/80">
                          <button
                            onClick={() => setSelectedNode(h.node)}
                            className="flex-1 py-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 rounded text-[9px] font-bold uppercase"
                          >
                            Center
                          </button>
                          <button
                            onClick={() => handleTraceUpstream(h.node.id)}
                            className="flex-1 py-1 bg-indigo-500/10 hover:bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 rounded text-[9px] font-bold uppercase"
                          >
                            Trace
                          </button>
                          <button
                            onClick={() => handleSimulateChange(h.node)}
                            className="flex-1 py-1 bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/30 rounded text-[9px] font-bold uppercase"
                          >
                            Simulate
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Recursion Mode: Dedicated Recursive Cycles Diagnostics */}
              {mode === 'recursion' && (
                <div className="p-3 bg-zinc-950 border border-amber-500/40 rounded-lg space-y-3 font-mono">
                  <div className="flex items-center gap-2">
                    <Repeat2 className="h-4 w-4 text-amber-400" />
                    <h3 className="text-xs font-bold text-zinc-100 uppercase tracking-wider">
                      Recursion Diagnostics & Call Cycles ({recursiveClustersList.length} detected)
                    </h3>
                  </div>

                  {recursiveClustersList.length === 0 ? (
                    <p className="text-xs text-zinc-400 italic">No recursive cycles detected in analyzed call graph.</p>
                  ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      {recursiveClustersList.map((cl) => (
                        <div
                          key={cl.id}
                          className="p-3 bg-zinc-900/80 border border-amber-500/30 rounded-lg space-y-2 text-xs"
                        >
                          <div className="flex items-center justify-between">
                            <span className="text-[11px] font-bold text-amber-300">{cl.name}</span>
                            <span className="text-[8px] bg-amber-950/80 text-amber-400 border border-amber-800 px-1.5 py-0.5 rounded font-bold uppercase">
                              {cl.isSelfLoop ? 'Self Loop' : `${cl.cycleLength}-Cycle`}
                            </span>
                          </div>

                          <div className="p-2 bg-zinc-950 rounded space-y-1 font-mono text-[10px]">
                            {cl.isSelfLoop ? (
                              <div className="text-amber-300">{shortId(cl.symbols[0])}() ↺ {shortId(cl.symbols[0])}()</div>
                            ) : (
                              <div className="text-amber-300">{shortId(cl.symbols[0])}() ↕ {shortId(cl.symbols[1] || cl.symbols[0])}()</div>
                            )}
                          </div>

                          <div className="flex items-center justify-between pt-1 border-t border-zinc-800 text-[9px] text-zinc-500">
                            <span>Files: {cl.files.join(', ') || 'source'}</span>
                            <button
                              onClick={() => {
                                const first = filteredNodes.find((n) => cl.symbols.includes(n.id));
                                if (first) {
                                  setSelectedNode(first);
                                  setActivePathNodes(new Set(cl.symbols));
                                }
                              }}
                              className="text-amber-400 hover:text-amber-300 font-bold uppercase"
                            >
                              Trace Cycle
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Change Simulation Panel */}
              {activeSimulation && (
                <ChangeSimulationPanel
                  sim={activeSimulation}
                  repoName={repoName}
                  onClose={() => setActiveSimulation(null)}
                  onTraceAffectedFlows={() => {
                    const allIds = [activeSimulation.targetId, ...activeSimulation.downstreamCascade];
                    setActivePathNodes(new Set(allIds));
                  }}
                />
              )}

              {/* Canvas + Inspector */}
              <div className="flex border border-zinc-800/60 rounded-lg overflow-hidden bg-[#030303] h-[680px] relative shadow-2xl">
                <div className="flex-1 min-w-0 h-full">
                  <ReactFlowProvider>
                    <CallGraphCanvas
                      cgNodes={abstractedResult.nodes}
                      cgEdges={abstractedResult.edges}
                      selectedNodeId={selectedNode?.id ?? null}
                      activePathNodes={activePathNodes}
                      focusOnly={focusOnly}
                      onNodeClick={(node) => {
                        setSelectedNode(node);
                        setBlastRadius(null);
                        setActiveSimulation(null);
                      }}
                      onToggleFocusOnly={() => setFocusOnly((prev) => !prev)}
                    />
                  </ReactFlowProvider>
                </div>

                {/* Execution Inspector */}
                {selectedNode && (
                  <NodePanel
                    node={selectedNode}
                    repoName={repoName}
                    signals={signals}
                    allNodes={filteredNodes}
                    allEdges={filteredEdges}
                    onClose={() => {
                      setSelectedNode(null);
                      setBlastRadius(null);
                      setActiveSimulation(null);
                      setActivePathNodes(new Set());
                      setActiveTraceRoute(null);
                      setFocusOnly(false);
                    }}
                    onSelectNode={(n) => setSelectedNode(n)}
                    onSimulateChange={handleSimulateChange}
                    onTraceUpstream={handleTraceUpstream}
                    onTraceDownstream={handleTraceDownstream}
                    onBlastRadius={loadBlastRadius}
                  />
                )}
              </div>

              {/* Blast radius panel */}
              {brLoading && (
                <SkeletonGroup label="Computing blast radius">
                  <SkeletonCard />
                </SkeletonGroup>
              )}
              {blastRadius && !brLoading && (
                <div className="p-4 bg-zinc-950 border border-zinc-800 rounded-xl space-y-3 font-mono">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Zap className="h-4 w-4 text-rose-400" />
                      <h4 className="text-xs font-bold text-zinc-100 uppercase tracking-wider">
                        Blast Radius: {shortId(blastRadius.function_id)}
                      </h4>
                      <span className="text-[9px] font-bold px-2 py-0.5 rounded border uppercase text-rose-400 border-rose-500/40 bg-rose-950/20">
                        {blastRadius.risk_level} Risk
                      </span>
                    </div>
                    <button onClick={() => setBlastRadius(null)} className="text-zinc-500 hover:text-zinc-200">
                      <X className="h-4 w-4" />
                    </button>
                  </div>

                  <div className="grid grid-cols-3 gap-3 text-center text-xs">
                    <div className="p-2 bg-zinc-900 rounded-lg">
                      <span className="text-zinc-500 text-[9px] block">Affected Functions</span>
                      <span className="text-base font-bold text-zinc-100">{blastRadius.affected_functions.length}</span>
                    </div>
                    <div className="p-2 bg-zinc-900 rounded-lg">
                      <span className="text-zinc-500 text-[9px] block">Affected Files</span>
                      <span className="text-base font-bold text-zinc-100">{blastRadius.affected_files.length}</span>
                    </div>
                    <div className="p-2 bg-zinc-900 rounded-lg">
                      <span className="text-zinc-500 text-[9px] block">Propagation Depth</span>
                      <span className="text-base font-bold text-zinc-100">{blastRadius.depth}</span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default CallGraphAnalyzer;
