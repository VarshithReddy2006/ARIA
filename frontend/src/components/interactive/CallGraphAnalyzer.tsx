/**
 * CallGraphAnalyzer — Function Call Graph tab component.
 *
 * Integrates into the existing AnalysisDashboard tab panel.
 * Reuses React Flow (already a dependency), existing UI components,
 * and the established graph data schema (nodes/edges with id, label,
 * category, etc.) so the existing GraphCanvas renders it unchanged
 * when hooked in through InteractiveDependencyGraph's graphType toggle.
 *
 * This component provides its own self-contained view because the call
 * graph has richer node metadata (fan_in, fan_out, file_path, qualified)
 * than the file graph and warrants dedicated panels.
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
import { Tabs, type TabItem } from './Tabs';
import {
  Workflow, Zap, AlertTriangle, ArrowUpFromLine,
  ArrowDownToLine, RefreshCw, Search, X,
  Code2, GitBranch, Repeat2, Info, ZoomIn, ZoomOut, Maximize,
} from 'lucide-react';

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
  entry_point:  '#6366f1',  // indigo  — call-graph roots
  core_module:  '#22c55e',  // green   — high fan-in (hottest functions)
  high_coupling:'#f59e0b',  // amber   — recursive
  focus:        '#ffffff',  // white   — selected node
  regular:      '#64748b',  // slate
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

// ── Hierarchical layout engine ───────────────────────────────────────────

const computeHierarchicalLayout = (nodes: CgNode[], edges: CgEdge[]) => {
  const adj: Record<string, string[]> = {};
  const inDegree: Record<string, number> = {};
  
  nodes.forEach(n => {
    adj[n.id] = [];
    inDegree[n.id] = 0;
  });

  edges.forEach(e => {
    if (adj[e.source]) adj[e.source].push(e.target);
    if (inDegree[e.target] !== undefined) inDegree[e.target]++;
  });

  const layers: Record<string, number> = {};
  const queue: string[] = [];

  // Identify roots
  nodes.forEach(n => {
    if (inDegree[n.id] === 0) {
      layers[n.id] = 0;
      queue.push(n.id);
    }
  });

  if (queue.length === 0 && nodes.length > 0) {
    layers[nodes[0].id] = 0;
    queue.push(nodes[0].id);
  }

  let maxLayer = 0;
  while (queue.length > 0) {
    const curr = queue.shift()!;
    const currLayer = layers[curr] || 0;
    
    const neighbors = adj[curr] || [];
    neighbors.forEach(nxt => {
      if (layers[nxt] === undefined) {
        layers[nxt] = currLayer + 1;
        maxLayer = Math.max(maxLayer, currLayer + 1);
        queue.push(nxt);
      } else {
        layers[nxt] = Math.max(layers[nxt], currLayer + 1);
        maxLayer = Math.max(maxLayer, layers[nxt]);
      }
    });
  }

  nodes.forEach(n => {
    if (layers[n.id] === undefined) {
      layers[n.id] = maxLayer + 1;
    }
  });

  const layerGroups: Record<number, string[]> = {};
  nodes.forEach(n => {
    const l = layers[n.id];
    if (!layerGroups[l]) layerGroups[l] = [];
    layerGroups[l].push(n.id);
  });

  const isLargeGraph = nodes.length > 40;
  const horizSpacing = isLargeGraph ? 260 : 340;
  const vertSpacing = isLargeGraph ? 110 : 155;

  const positions: Record<string, { x: number; y: number }> = {};
  Object.keys(layerGroups).forEach(layerStr => {
    const layer = parseInt(layerStr);
    const nodeIds = layerGroups[layer];
    const columnHeight = (nodeIds.length - 1) * vertSpacing;
    const yStart = -columnHeight / 2;

    nodeIds.forEach((id, idx) => {
      positions[id] = {
        x: layer * horizSpacing,
        y: yStart + (idx * vertSpacing),
      };
    });
  });

  return positions;
};

// ── Custom React Flow Node Card Component ─────────────────────────────────

interface CustomNodeData {
  node: CgNode;
  isSelected: boolean;
  isDimmed: boolean;
  colorBy: 'category' | 'language';
  onNodeClick: (node: CgNode) => void;
}

const CustomCallNode: React.FC<{ data: CustomNodeData }> = ({ data }) => {
  const { node, isSelected, isDimmed, colorBy } = data;
  const isRecursive = node.is_recursive;

  let accentColor = 'border-slate-800 bg-slate-900/90 text-text hover:border-slate-700';
  
  if (colorBy === 'language') {
    const lang = node.language.toLowerCase();
    const hex = LANG_COLOR[lang] || '#64748b';
    accentColor = `border-[${hex}] bg-slate-900/90 text-text`;
    // inline dynamic style to bypass tailwind compiler constraints for arbitrary bracket hex borders
  } else {
    if (isRecursive) {
      accentColor = 'border-amber-500 bg-amber-950/20 text-text ring-1 ring-amber-500/10 hover:border-amber-400';
    } else if (node.category === 'entry_point') {
      accentColor = 'border-indigo-500 bg-indigo-950/20 text-text ring-1 ring-indigo-500/10 hover:border-indigo-400';
    } else if (node.category === 'core_module') {
      accentColor = 'border-emerald-500 bg-emerald-950/20 text-text ring-1 ring-emerald-500/10 hover:border-emerald-400';
    }
  }

  if (isSelected) {
    accentColor = 'border-primary bg-slate-900 ring-2 ring-primary/30 scale-[1.02]';
  }

  const fileName = node.file_path.split('/').pop() || node.file_path;
  const inlineBorder = colorBy === 'language' ? { borderColor: LANG_COLOR[node.language.toLowerCase()] || '#64748b' } : {};

  return (
    <div
      style={isSelected ? {} : inlineBorder}
      className={`card p-3 min-w-[190px] max-w-[240px] flex flex-col gap-2 transition-all duration-200 border-2 select-none font-sans text-left shadow-float ${accentColor} ${
        isDimmed ? 'opacity-40 scale-[0.98]' : 'opacity-100'
      }`}
    >
      <Handle type="target" position={Position.Left} className="!bg-slate-700 !border-slate-600 !w-2 !h-2" />
      
      {/* Function name */}
      <div className="flex items-center justify-between gap-2.5 min-w-0">
        <div className="flex items-center gap-1.5 min-w-0">
          <Code2 className="h-3.5 w-3.5 text-primary shrink-0" />
          <span className="font-mono text-xs font-bold text-text truncate" title={node.label}>
            {shortId(node.id)}
          </span>
        </div>
        {node.fan_in > 0 && (
          <span className="text-[9px] font-bold font-mono text-text-muted bg-canvas border border-border px-1 rounded-md shrink-0">
            ↙{node.fan_in}
          </span>
        )}
      </div>

      {/* File & tags */}
      <div className="space-y-1.5">
        <span className="text-[9px] font-mono text-text-subtle truncate block" title={node.file_path}>
          {fileName}
        </span>
        <div className="flex flex-wrap gap-1 select-none">
          <span className="text-[8px] font-mono font-bold bg-canvas border border-border px-1 rounded uppercase text-text-muted">
            {node.language}
          </span>
          <span className="text-[8px] font-mono font-bold bg-canvas border border-border px-1 rounded uppercase text-text-muted">
            {node.symbol_type}
          </span>
          {isRecursive && (
            <span className="text-[8px] font-mono font-bold bg-amber-500/10 border border-amber-500/20 px-1 rounded uppercase text-amber-500">
              cyclic
            </span>
          )}
        </div>
      </div>

      <Handle type="source" position={Position.Right} className="!bg-slate-700 !border-slate-600 !w-2 !h-2" />
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
  const { zoomIn, zoomOut, fitView } = useReactFlow();

  // Find neighbor nodes of the currently selected node
  const neighborIds = useMemo(() => {
    if (!selectedNodeId) return new Set<string>();
    const set = new Set<string>([selectedNodeId]);
    cgEdges.forEach(e => {
      if (e.source === selectedNodeId) set.add(e.target);
      if (e.target === selectedNodeId) set.add(e.source);
    });
    return set;
  }, [selectedNodeId, cgEdges]);

  // Compute hierarchical layered layouts on data/selection changes
  useEffect(() => {
    const positions = computeHierarchicalLayout(cgNodes, cgEdges);
    
    const mappedNodes = cgNodes.map((n) => {
      const isSelected = selectedNodeId === n.id;
      const isDimmed = selectedNodeId !== null && !neighborIds.has(n.id);
      return {
        id: n.id,
        type: 'customCallNode',
        position: positions[n.id] || { x: 0, y: 0 },
        data: {
          node: n,
          isSelected,
          isDimmed,
          colorBy,
        },
      };
    });

    const mappedEdges = cgEdges.map((e, i) => {
      const isSelected = selectedNodeId && (e.source === selectedNodeId || e.target === selectedNodeId);
      const isDimmed = selectedNodeId && !isSelected;
      return {
        id: `e-${i}`,
        source: e.source,
        target: e.target,
        label: e.ambiguous ? '?' : undefined,
        animated: isSelected || !selectedNodeId,
        style: {
          stroke: isSelected ? '#6366f1' : e.ambiguous ? '#f59e0b' : '#334155',
          strokeWidth: isSelected ? 3.0 : 1.8,
          opacity: isDimmed ? 0.25 : 1.0,
        },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: isSelected ? '#6366f1' : e.ambiguous ? '#f59e0b' : '#334155',
        },
      };
    });

    setRfNodes(mappedNodes as any);
    setRfEdges(mappedEdges as any);
  }, [cgNodes, cgEdges, selectedNodeId, neighborIds, colorBy, setRfNodes, setRfEdges]);

  // Automatically fit and center on data changes
  useEffect(() => {
    if (rfNodes.length > 0) {
      const timer = setTimeout(() => {
        fitView({ padding: 0.25, duration: 400 });
      }, 60);
      return () => clearTimeout(timer);
    }
  }, [rfNodes.length, fitView]);

  const handleNodeClick = useCallback((_: any, node: any) => {
    const original = cgNodes.find((n) => n.id === node.id);
    if (original) onNodeClick(original);
  }, [cgNodes, onNodeClick]);

  return (
    <div className="relative w-full h-full">
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        nodeTypes={customNodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        fitView
        fitViewOptions={{ padding: 0.25 }}
        minZoom={0.08}
        maxZoom={3.5}
        proOptions={{ hideAttribution: true }}
        className="bg-canvas/5"
      >
        <Background color="#1e293b" gap={28} />
        
        {/* Floating Custom Control Toolbar */}
        <div className="absolute bottom-4 left-4 z-10 flex items-center gap-1.5 p-1.5 bg-surface/95 border border-border rounded-xl shadow-float select-none fade-up">
          <button
            type="button"
            onClick={() => zoomIn({ duration: 250 })}
            className="p-2 rounded-lg hover:bg-canvas hover:text-text transition-colors text-text-muted focus-visible:outline-none"
            title="Zoom In"
          >
            <ZoomIn className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => zoomOut({ duration: 250 })}
            className="p-2 rounded-lg hover:bg-canvas hover:text-text transition-colors text-text-muted focus-visible:outline-none"
            title="Zoom Out"
          >
            <ZoomOut className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => fitView({ duration: 600, padding: 0.25 })}
            className="p-2 rounded-lg hover:bg-canvas hover:text-text transition-colors text-text-muted focus-visible:outline-none"
            title="Fit view"
          >
            <Maximize className="h-4 w-4" />
          </button>
          <span className="w-px h-4 bg-border/80 mx-1"></span>
          <button
            type="button"
            onClick={() => {
              onNodeClick(null);
              fitView({ duration: 600, padding: 0.25 });
            }}
            className="rounded-lg hover:bg-canvas hover:text-text transition-colors text-text-muted focus-visible:outline-none text-[9px] font-mono px-2 py-1 font-bold uppercase tracking-wider border border-border/80"
            title="Clear active node selection"
          >
            Reset
          </button>
          <button
            type="button"
            onClick={() => fitView({ duration: 800, padding: 0.15 })}
            className="rounded-lg hover:bg-canvas hover:text-text transition-colors text-text-muted focus-visible:outline-none text-[9px] font-mono px-2 py-1 font-bold uppercase tracking-wider border border-border/80"
            title="Trigger dynamic layout scaling"
          >
            Auto Layout
          </button>
        </div>

        <MiniMap
          nodeColor={(n: any) => {
            const original = n.data?.node as CgNode;
            if (!original) return '#64748b';
            if (original.is_recursive) return '#f59e0b';
            if (original.category === 'entry_point') return '#6366f1';
            if (original.category === 'core_module') return '#22c55e';
            return '#334155';
          }}
          maskColor="rgba(15, 23, 42, 0.75)"
          className="!bg-slate-950/95 !border-slate-800/80 !rounded-xl !shadow-float overflow-hidden"
          nodeStrokeWidth={0}
          nodeBorderRadius={5}
        />
      </ReactFlow>
    </div>
  );
};

// ── Node detail panel (Inspector Tabbed Layout) ──────────────────────────

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

  // Determine dynamic risk level
  const riskLevel = useMemo(() => {
    if (node.is_recursive || node.degree > 15) return { text: 'HIGH RISK', tone: 'danger' as const };
    if (node.fan_in > 5 || node.degree > 6) return { text: 'MEDIUM RISK', tone: 'warn' as const };
    return { text: 'LOW RISK', tone: 'success' as const };
  }, [node]);

  return (
    <aside
      className="w-80 shrink-0 border-l border-border bg-surface flex flex-col overflow-hidden"
      aria-label="Function details"
    >
      {/* Title */}
      <div className="flex items-center justify-between px-4.5 py-3.5 border-b border-border bg-card/10 select-none">
        <div className="flex items-center gap-1.5 min-w-0">
          <Code2 className="h-4 w-4 text-primary shrink-0 animate-pulse" />
          <span className="text-xs font-bold text-text font-mono truncate" title={node.label}>
            {shortId(node.id)}
          </span>
        </div>
        <button
          onClick={onClose}
          className="text-text-muted hover:text-text focus-visible:outline-none focus-visible:shadow-ring rounded p-1"
          aria-label="Close panel"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-border bg-card/5 select-none text-[10px] font-mono">
        {panelTabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setPanelTab(t.id)}
            className={`flex-1 py-2 text-center border-b-2 font-bold transition-all ${
              panelTab === t.id
                ? 'border-primary text-text bg-primary/5'
                : 'border-transparent text-text-muted hover:text-text hover:bg-canvas/40'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab Panels */}
      <div className="flex-1 overflow-y-auto p-5 space-y-5 text-xs font-sans">
        {panelTab === 'overview' && (
          <>
            {/* Fan-in / Fan-out cards */}
            <div className="grid grid-cols-2 gap-3 select-none">
              <div className="card p-3.5 text-center border-border/80 hover:border-primary/20 transition-all duration-200 group">
                <p className="text-text-subtle text-[9px] uppercase tracking-widest font-mono font-semibold">Incoming Fan-In</p>
                <p className="text-2xl font-black font-mono text-primary mt-1 group-hover:scale-105 transition-transform duration-200">{node.fan_in}</p>
                <p className="text-[9px] text-text-muted font-sans mt-0.5">call references</p>
              </div>
              <div className="card p-3.5 text-center border-border/80 hover:border-primary/20 transition-all duration-200 group">
                <p className="text-text-subtle text-[9px] uppercase tracking-widest font-mono font-semibold">Outgoing Fan-Out</p>
                <p className="text-2xl font-black font-mono text-primary mt-1 group-hover:scale-105 transition-transform duration-200">{node.fan_out}</p>
                <p className="text-[9px] text-text-muted font-sans mt-0.5">invokes callees</p>
              </div>
            </div>

            {/* Actions Grid */}
            <div className="space-y-2 select-none">
              <p className="text-[10px] uppercase tracking-widest text-text-subtle font-mono font-bold">Code Intelligence Actions</p>
              <div className="grid grid-cols-1 gap-2">
                <button
                  onClick={() => onNeighbors(node.id)}
                  className="w-full text-left flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl
                             border border-border/80 hover:border-primary/30 hover:bg-primary/5
                             transition-all hover:scale-[1.01] active:scale-[0.99] duration-150 focus-visible:outline-none"
                >
                  <GitBranch className="h-4 w-4 text-primary shrink-0" />
                  <span className="font-medium">Show nearest neighbors</span>
                </button>
                <button
                  onClick={() => onBlastRadius(node.id)}
                  className="w-full text-left flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl
                             border border-border/80 hover:border-danger/40 hover:bg-danger/5
                             transition-all hover:scale-[1.01] active:scale-[0.99] duration-150 focus-visible:outline-none"
                >
                  <Zap className="h-4 w-4 text-danger shrink-0 animate-bounce" />
                  <span className="font-bold text-danger">Evaluate blast radius</span>
                </button>
              </div>
            </div>
          </>
        )}

        {panelTab === 'metadata' && (
          <div className="space-y-4">
            {/* Declared Path */}
            <div className="p-3 bg-canvas/30 border border-border/80 rounded-xl space-y-1">
              <span className="text-[9px] font-bold font-mono text-text-subtle block uppercase tracking-wider select-none">
                Declared Path
              </span>
              <p className="text-text-muted break-all font-mono leading-relaxed select-all">
                {node.file_path}
              </p>
            </div>

            {/* Badges */}
            <div className="space-y-2 select-none">
              <span className="text-[9px] font-bold font-mono text-text-subtle block uppercase tracking-wider">Properties</span>
              <div className="flex flex-wrap gap-1.5">
                <Badge tone="primary">{node.symbol_type}</Badge>
                <Badge tone="info">{node.language}</Badge>
                <Badge tone={riskLevel.tone}>{riskLevel.text}</Badge>
                {node.is_recursive && <Badge tone="warn">cyclic recursive</Badge>}
                {node.fan_in === 0 && <Badge tone="success">entry point</Badge>}
              </div>
            </div>

            {/* Parent namespace */}
            {node.parent_class && (
              <div className="space-y-1 font-mono text-[10px]">
                <span className="text-text-muted uppercase text-[9px] block">Parent Class</span>
                <span className="text-text font-semibold break-all">{node.parent_class}</span>
              </div>
            )}

            {/* Quality metrics */}
            <div className="border-t border-border/40 pt-3 space-y-2 font-mono text-[10px] select-none text-text-muted">
              <div className="flex justify-between">
                <span>Degree Centrality:</span>
                <span className="text-text font-semibold">{node.centrality.toFixed(4)}</span>
              </div>
              <div className="flex justify-between">
                <span>Degree Connections:</span>
                <span className="text-text font-semibold">{node.degree}</span>
              </div>
            </div>
          </div>
        )}

        {panelTab === 'callers' && (
          <div className="space-y-4 select-none">
            <p className="text-text-muted leading-relaxed">
              Trace callers recursively to map upstream modules and structural dependencies feeding into this function symbol.
            </p>
            <button
              onClick={() => onTrace(node.id, 'backward')}
              className="w-full text-left flex items-center justify-center gap-2 px-3.5 py-2.5 rounded-xl
                         border border-border/80 hover:border-primary/30 hover:bg-primary/5
                         transition-all hover:scale-[1.01] active:scale-[0.99] duration-150 focus-visible:outline-none"
            >
              <ArrowUpFromLine className="h-4 w-4 text-orange-400 shrink-0" />
              <span className="font-bold">Trace Upstream Callers</span>
            </button>
          </div>
        )}

        {panelTab === 'callees' && (
          <div className="space-y-4 select-none">
            <p className="text-text-muted leading-relaxed">
              Trace callees recursively to map downstream modules and execution flow branches triggered by this function symbol.
            </p>
            <button
              onClick={() => onTrace(node.id, 'forward')}
              className="w-full text-left flex items-center justify-center gap-2 px-3.5 py-2.5 rounded-xl
                         border border-border/80 hover:border-primary/30 hover:bg-primary/5
                         transition-all hover:scale-[1.01] active:scale-[0.99] duration-150 focus-visible:outline-none"
            >
              <ArrowDownToLine className="h-4 w-4 text-green-400 shrink-0" />
              <span className="font-bold">Trace Downstream Callees</span>
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
  <div className="card p-5 space-y-4 shadow-float border-border/80 fade-up">
    <div className="flex items-center justify-between border-b border-border/60 pb-3 select-none">
      <h3 className="panel-title flex items-center gap-2">
        <Zap className="h-4 w-4 text-danger animate-pulse" />
        <span>Blast Radius Risk Assessment</span>
      </h3>
      <button
        onClick={onClose}
        aria-label="Close blast radius"
        className="text-text-muted hover:text-text focus-visible:outline-none rounded p-1"
      >
        <X className="h-4 w-4" />
      </button>
    </div>

    <div className="grid grid-cols-3 gap-3.5 select-none">
      <div className="card p-3.5 text-center border-border/60">
        <p className="text-[10px] text-text-subtle font-mono uppercase tracking-wide">Callers affected</p>
        <p className="text-2xl font-black font-mono text-text mt-1">{br.affected_functions.length}</p>
      </div>
      <div className="card p-3.5 text-center border-border/60">
        <p className="text-[10px] text-text-subtle font-mono uppercase tracking-wide">Files affected</p>
        <p className="text-2xl font-black font-mono text-text mt-1">{br.affected_files.length}</p>
      </div>
      <div className="card p-3.5 text-center border-border/60">
        <p className="text-[10px] text-text-subtle font-mono uppercase tracking-wide">Max depth</p>
        <p className="text-2xl font-black font-mono text-text mt-1">{br.depth}</p>
      </div>
    </div>

    <div className="flex items-center gap-2.5 select-none">
      <span className="text-xs text-text-muted font-sans font-semibold">Change Risk Factor</span>
      <Badge tone={riskTone(br.risk_level)}>{br.risk_level.toUpperCase()}</Badge>
    </div>

    {br.recursive_cycles.length > 0 && (
      <div className="space-y-2 select-none">
        <p className="text-[10px] font-bold font-mono text-orange-400 flex items-center gap-1.5 uppercase tracking-wider">
          <Repeat2 className="h-4 w-4" /> {br.recursive_cycles.length} mutual recursion cycle{br.recursive_cycles.length > 1 ? 's' : ''} detected
        </p>
        <div className="space-y-1.5">
          {br.recursive_cycles.slice(0, 3).map((cycle, i) => (
            <div key={i} className="text-[10px] font-mono text-text-muted bg-canvas/40 border border-border/40 rounded-lg p-2.5">
              {cycle.map(shortId).join(' ↔ ')}
            </div>
          ))}
        </div>
      </div>
    )}

    {br.affected_files.length > 0 && (
      <div className="space-y-2">
        <p className="text-[10px] uppercase tracking-widest text-text-subtle font-mono font-bold select-none">Affected Files list</p>
        <div className="space-y-1 max-h-40 overflow-y-auto border border-border/60 bg-canvas/20 rounded-xl p-2.5">
          {br.affected_files.map((f) => (
            <p key={f} className="text-[10px] font-mono text-text-muted truncate select-all">{f}</p>
          ))}
        </div>
      </div>
    )}
  </div>
);

// ── Stats panel ────────────────────────────────────────────────────────────

const StatsPanel: React.FC<{ stats: CgStats }> = ({ stats }) => (
  <div className="space-y-5 fade-up">
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3.5">
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

    <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
      <div className="card p-5 space-y-3.5">
        <h3 className="panel-title"><ArrowUpFromLine className="h-4 w-4 text-primary" /> Top Fan-in (Most Referenced)</h3>
        <div className="space-y-2">
          {stats.top_fan_in.slice(0, 8).map((item, i) => (
            <div key={item.node_id} className="flex items-center gap-3 text-xs py-1 border-b border-border/30 last:border-0">
              <span className="text-text-muted font-mono w-4 shrink-0 font-bold">#{i + 1}</span>
              <span className="flex-1 font-mono text-text truncate" title={item.node_id}>{shortId(item.node_id)}</span>
              <Badge tone="primary">{item.fan_in}</Badge>
            </div>
          ))}
        </div>
      </div>
      <div className="card p-5 space-y-3.5">
        <h3 className="panel-title"><ArrowDownToLine className="h-4 w-4 text-primary" /> Top Fan-out (Most Outgoing Calls)</h3>
        <div className="space-y-2">
          {stats.top_fan_out.slice(0, 8).map((item, i) => (
            <div key={item.node_id} className="flex items-center gap-3 text-xs py-1 border-b border-border/30 last:border-0">
              <span className="text-text-muted font-mono w-4 shrink-0 font-bold">#{i + 1}</span>
              <span className="flex-1 font-mono text-text truncate" title={item.node_id}>{shortId(item.node_id)}</span>
              <Badge tone="info">{(item as any).fan_out}</Badge>
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
            if (ev.status === 'done') { setBuilding(false); loadGraph(''); loadStats(); return; }
            if (ev.message) setBuildProgress(ev.message);
          } catch { /* non-JSON */ }
        }
      }
    } catch (err: any) {
      setBuildError(extractErrorMessage(err));
    } finally {
      setBuilding(false);
    }
  }, [repoName, loadGraph, loadStats]);

  // ── Search debounce ──────────────────────────────────────────────────────
  const handleSearch = (val: string) => {
    setSearchQuery(val);
    if (searchDebounce.current) clearTimeout(searchDebounce.current);
    searchDebounce.current = setTimeout(() => loadGraph(val), 350);
  };

  const resetView = () => {
    setSearchQuery('');
    setSelectedNode(null);
    setBlastRadius(null);
    loadGraph('');
  };

  const notBuilt = !graphLoading && !graphData && !graphError;
  const hasData  = !!graphData && (graphData.node_count ?? 0) > 0;

  return (
    <div className="space-y-5 fade-up">

      {/* ── Header bar ─────────────────────────────────────────────────── */}
      <div className="card p-5 space-y-4 bg-surface-1/10">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 select-none">
          <div>
            <h2 className="panel-title">
              <Workflow className="h-4 w-4 text-primary" aria-hidden="true" />
              Function Call Graph
            </h2>
            <p className="text-xs text-text-muted font-sans mt-1">
              Function-to-function dependency graph. Blast radius, callers, callees, recursion detection.
            </p>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {hasData && (
              <button
                onClick={resetView}
                aria-label="Reset view"
                className="btn-ghost text-xs"
              >
                <RefreshCw className="h-3.5 w-3.5" /> Reset
              </button>
            )}
            <Button onClick={handleBuild} disabled={building}>
              {building
                ? <><RefreshCw className="h-3.5 w-3.5 animate-spin" /> Building…</>
                : hasData ? <><RefreshCw className="h-3.5 w-3.5" /> Rebuild</>
                : 'Build Call Graph'}
            </Button>
          </div>
        </div>

        {/* Build progress */}
        {building && (
          <div className="space-y-1.5" role="status" aria-live="polite">
            <div className="h-1 rounded-full bg-border overflow-hidden">
              <div className="h-full bg-primary rounded-full animate-pulse w-3/5" />
            </div>
            <p className="text-xs font-mono text-text-muted">{buildProgress}</p>
          </div>
        )}

        {/* Build error */}
        {buildError && (
          <div role="alert" className="text-xs text-danger bg-danger/10 border border-danger/30 p-3 rounded-lg font-sans">
            {buildError}
          </div>
        )}
      </div>

      {/* ── Loading skeleton ────────────────────────────────────────────── */}
      {(graphLoading || brLoading) && !hasData && (
        <SkeletonGroup label="Loading call graph">
          <div className="space-y-3">
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              {[0,1,2,3,4].map(i => <SkeletonCard key={i} />)}
            </div>
            <div className="h-[500px] card">
              <Skeleton size="h-full w-full" />
            </div>
          </div>
        </SkeletonGroup>
      )}

      {/* ── Not built empty state ────────────────────────────────────────── */}
      {notBuilt && !building && (
        <EmptyState
          icon={<Workflow className="h-6 w-6" aria-hidden="true" />}
          title="Call graph not built yet"
          description="Click 'Build Call Graph' to extract function call relationships from the codebase."
          action={<Button onClick={handleBuild}>Build Call Graph</Button>}
        />
      )}

      {/* ── Graph error ─────────────────────────────────────────────────── */}
      {graphError && !graphLoading && (
        <div role="alert" className="text-xs text-danger bg-danger/10 border border-danger/30 p-3 rounded-lg font-sans">
          {graphError}
        </div>
      )}

      {/* ── Main content ────────────────────────────────────────────────── */}
      {hasData && !graphLoading && (
        <div className="space-y-4 fade-up">

          {/* View toggle */}
          <div className="card p-1 flex gap-1 w-fit select-none bg-surface-1/40" role="tablist">
            {(['graph', 'stats'] as const).map((v) => (
              <button
                key={v}
                role="tab"
                aria-selected={activeView === v}
                onClick={() => setActiveView(v)}
                className={`px-4 py-1.5 text-xs font-semibold rounded-md transition-colors capitalize
                  focus-visible:outline-none focus-visible:shadow-ring
                  ${activeView === v ? 'bg-primary text-text shadow-sm' : 'text-text-muted hover:text-text hover:bg-canvas/40'}`}
              >
                {v === 'graph' ? '🔗 Graph' : '📊 Stats'}
              </button>
            ))}
          </div>

          {/* Stats view */}
          {activeView === 'stats' && stats && <StatsPanel stats={stats} />}
          {activeView === 'stats' && !stats && (
            <EmptyState compact icon={<Info className="h-5 w-5" />}
              title="Stats unavailable" description="Build the call graph to see statistics." />
          )}

          {/* Graph view */}
          {activeView === 'graph' && (
            <div className="space-y-3">

              {/* Controls and filters toolbar */}
              <div className="grid grid-cols-1 md:grid-cols-12 gap-3.5 items-center bg-card/25 p-3 rounded-xl border border-border text-xs select-none font-mono">
                {/* Search */}
                <div className="relative md:col-span-4">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-text-muted pointer-events-none" />
                  <input
                    type="search"
                    value={searchQuery}
                    onChange={(e) => handleSearch(e.target.value)}
                    placeholder="Search functions…"
                    className="input pl-9 pr-9 text-xs w-full"
                    aria-label="Search call graph"
                  />
                  {searchQuery && (
                    <button
                      onClick={() => { setSearchQuery(''); loadGraph(''); }}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text"
                      aria-label="Clear search"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>

                <div className="md:col-span-8 flex flex-wrap items-center justify-end gap-5 text-[10px] text-text-muted">
                  {/* Color selector */}
                  <div className="flex items-center gap-1.5">
                    <span>Color Nodes:</span>
                    <select
                      value={colorBy}
                      onChange={(e) => setColorBy(e.target.value as 'category' | 'language')}
                      className="bg-canvas border border-border rounded-lg px-2.5 py-1 text-text focus:outline-none focus:border-primary text-[10px] font-sans"
                    >
                      <option value="category">Category (Layer)</option>
                      <option value="language">Language</option>
                    </select>
                  </div>

                  {/* Hide External */}
                  <label className="flex items-center gap-1.5 cursor-pointer hover:text-text transition-colors">
                    <input
                      type="checkbox"
                      checked={hideExternal}
                      onChange={(e) => setHideExternal(e.target.checked)}
                      className="rounded border-border bg-canvas text-primary focus:ring-0"
                    />
                    <span>Hide External</span>
                  </label>

                  {/* Hide Recursive */}
                  <label className="flex items-center gap-1.5 cursor-pointer hover:text-text transition-colors">
                    <input
                      type="checkbox"
                      checked={hideCycles}
                      onChange={(e) => setHideCycles(e.target.checked)}
                      className="rounded border-border bg-canvas text-primary focus:ring-0"
                    />
                    <span>Hide Recursions</span>
                  </label>
                </div>
              </div>

              {/* Legend */}
              <div className="flex flex-wrap gap-3.5 text-[10px] font-mono text-text-muted select-none">
                {colorBy === 'category' ? (
                  [
                    { color: CAT_COLOR.entry_point, label: 'Entry point' },
                    { color: CAT_COLOR.core_module,  label: 'High fan-in' },
                    { color: CAT_COLOR.high_coupling,label: 'Recursive' },
                    { color: CAT_COLOR.regular,      label: 'Regular' },
                  ].map(({ color, label }) => (
                    <span key={label} className="flex items-center gap-1.5">
                      <span className="h-2.5 w-2.5 rounded-full shrink-0"
                            style={{ backgroundColor: color }} aria-hidden="true" />
                      {label}
                    </span>
                  ))
                ) : (
                  Object.entries(LANG_COLOR).map(([lang, color]) => (
                    <span key={lang} className="flex items-center gap-1.5">
                      <span className="h-2.5 w-2.5 rounded-full shrink-0"
                            style={{ backgroundColor: color }} aria-hidden="true" />
                      <span className="capitalize">{lang}</span>
                    </span>
                  ))
                )}
                <span className="flex items-center gap-1.5">
                  <span className="h-0.5 w-4 border-t-2 border-dashed border-amber-400" aria-hidden="true" />
                  Ambiguous call
                </span>
              </div>

              {/* Canvas + side panel */}
              <div className="flex gap-0 border border-border rounded-xl overflow-hidden bg-canvas/10"
                   style={{ height: 540 }}>
                <div className="flex-1 min-w-0">
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

                {/* Node details panel */}
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

              {/* Graph metadata */}
              <p className="text-[10px] font-mono text-text-muted text-right select-none">
                {filteredNodes.length} functions · {filteredEdges.length} call edges
                {searchQuery && ` · filtered by "${searchQuery}"`}
              </p>

              {/* Blast radius panel — shown below graph */}
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
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default CallGraphAnalyzer;
