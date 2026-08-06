import React, { useState, useEffect, useCallback } from 'react';
import { apiUrl } from '../../lib/api';
import ReactFlow, {
  MiniMap,
  Controls,
  Background,
  useNodesState,
  useEdgesState,
  MarkerType,
  ReactFlowProvider,
} from 'reactflow';
import { PanControls } from './graph/PanControls';
import dagre from 'dagre';
import { Search, Info, X } from 'lucide-react';
import 'reactflow/dist/style.css';

interface NodeData {
  id: string;
  label: string;
  category: string;
  degree: number;
  centrality: number;
}

interface EdgeData {
  source: string;
  target: string;
  relationship: string;
}

interface GraphProps {
  repoName: string;
}

const nodeWidth = 200;
const nodeHeight = 40;

const getLayoutedElements = (nodes: any[], edges: any[], direction = 'TB') => {
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));
  dagreGraph.setGraph({ rankdir: direction, ranksep: 60, nodesep: 40 });

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: nodeWidth, height: nodeHeight });
  });

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  dagre.layout(dagreGraph);

  const layoutedNodes = nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    return {
      ...node,
      position: {
        x: nodeWithPosition.x - nodeWidth / 2,
        y: nodeWithPosition.y - nodeHeight / 2,
      },
    };
  });

  return { nodes: layoutedNodes, edges };
};

const ArchitectureGraphInner: React.FC<GraphProps> = ({ repoName }) => {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<NodeData | null>(null);

  const fetchGraphData = useCallback(async (query = '') => {
    setLoading(true);
    setError(null);
    const [owner, name] = repoName.split('/');
    try {
      const url = apiUrl(`/api/v1/architecture/${owner}/${name}/graph` + (query ? `?q=${encodeURIComponent(query)}` : ''));
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(await response.text() || 'Failed to fetch graph data');
      }
      const data = await response.json();

      if (!data.nodes || data.nodes.length === 0) {
        setNodes([]);
        setEdges([]);
        setLoading(false);
        return;
      }

      // Map raw nodes into React Flow nodes with classes
      const rawNodes = data.nodes.map((n: NodeData) => {
        let styleClass = '!bg-zinc-900 !border !border-zinc-700 !text-zinc-300 rounded px-3 py-2 text-center text-xs font-mono truncate shadow cursor-pointer hover:!border-zinc-500 transition-all';
        if (n.category === 'entry_point') {
          styleClass = '!bg-emerald-950/60 !border-2 !border-emerald-500 !text-emerald-400 rounded px-3 py-2 text-center text-xs font-mono font-semibold truncate shadow-lg shadow-emerald-500/5 cursor-pointer hover:!bg-emerald-900/40 transition-all';
        } else if (n.category === 'core_module') {
          styleClass = '!bg-blue-950/60 !border-2 !border-blue-500 !text-blue-400 rounded px-3 py-2 text-center text-xs font-mono font-semibold truncate shadow-lg shadow-blue-500/5 cursor-pointer hover:!bg-blue-900/40 transition-all';
        } else if (n.category === 'high_coupling') {
          styleClass = '!bg-orange-950/60 !border !border-orange-500 !text-orange-400 rounded px-3 py-2 text-center text-xs font-mono truncate shadow cursor-pointer hover:!bg-orange-900/40 transition-all';
        } else if (n.category === 'directory') {
          styleClass = '!bg-purple-950/60 !border !border-purple-500 !text-purple-400 rounded px-3 py-2 text-center text-xs font-mono truncate shadow font-semibold cursor-pointer hover:!bg-purple-900/40 transition-all';
        }
        return {
          id: n.id,
          data: { label: n.label, raw: n },
          className: styleClass,
          type: 'default',
        };
      });

      // Create a map of node id -> category
      const categoryMap = new Map<string, string>();
      data.nodes.forEach((n: NodeData) => categoryMap.set(n.id, n.category));

      // Map raw edges into React Flow edges
      const rawEdges = data.edges.map((e: EdgeData) => {
        const srcCategory = categoryMap.get(e.source) ?? 'regular';
        let strokeColor = '#4b5563'; // default gray
        
        if (srcCategory === 'entry_point') {
          strokeColor = '#10b981'; // emerald
        } else if (srcCategory === 'core_module') {
          strokeColor = '#3b82f6'; // blue
        } else if (srcCategory === 'high_coupling') {
          strokeColor = '#f97316'; // orange
        } else if (srcCategory === 'directory') {
          strokeColor = '#a855f7'; // purple
        }

        return {
          id: `${e.source}->${e.target}`,
          source: e.source,
          target: e.target,
          animated: e.relationship === 'imports',
          style: { stroke: strokeColor, strokeWidth: 1.5 },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            width: 12,
            height: 12,
            color: strokeColor,
          },
        };
      });

      // Apply Dagre auto-layout
      const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(
        rawNodes,
        rawEdges,
        'TB' // Top-to-bottom layout
      );

      setNodes(layoutedNodes);
      setEdges(layoutedEdges);
    } catch (err: any) {
      console.error(err);
      setError(err.message || 'An error occurred loading the graph.');
    } finally {
      setLoading(false);
    }
  }, [repoName, setNodes, setEdges]);

  // Initial load
  useEffect(() => {
    fetchGraphData();
  }, [fetchGraphData]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    fetchGraphData(searchQuery);
  };

  const handleClearSearch = () => {
    setSearchQuery('');
    fetchGraphData('');
  };

  const onNodeClick = (_event: any, node: any) => {
    setSelectedNode(node.data.raw);
  };

  return (
    <div className="border border-border bg-card/5 rounded-lg flex flex-col h-[600px] relative overflow-hidden">
      {/* Search Bar */}
      <div className="p-3 border-b border-border bg-canvas/40 flex justify-between items-center gap-3 z-10">
        <form onSubmit={handleSearchSubmit} className="flex items-center gap-2 flex-grow max-w-md">
          <div className="relative flex-grow">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search files (e.g. api, auth)..."
              className="w-full bg-canvas border border-border rounded pl-8 pr-8 py-1.5 text-xs font-mono focus:outline-none focus:border-primary/80 text-text"
            />
            <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-text-muted" />
            {searchQuery && (
              <button
                type="button"
                onClick={handleClearSearch}
                className="absolute right-2.5 top-2.5 h-3.5 w-3.5 text-text-muted hover:text-text"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
          <button
            type="submit"
            className="bg-primary hover:bg-primary/90 text-canvas font-mono text-xs font-semibold px-3 py-1.5 rounded transition-colors"
          >
            Search
          </button>
        </form>

        <div className="text-[10px] font-mono text-text-muted hidden sm:block">
          Click nodes to view detail analysis
        </div>
      </div>

      <div className="flex-grow relative flex">
        {/* React Flow Area */}
        <div className="flex-grow h-full bg-canvas/10">
          {loading && (
            <div className="absolute inset-0 bg-canvas/80 flex flex-col items-center justify-center font-mono text-xs text-text-muted gap-2 z-20">
              <div className="h-5 w-5 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
              <span>Loading Architecture Graph...</span>
            </div>
          )}

          {error && (
            <div className="absolute inset-0 bg-canvas/80 flex flex-col items-center justify-center font-mono text-xs text-text-muted gap-2 z-20 p-4 text-center">
              <Info className="h-6 w-6 text-primary" />
              <span>{error}</span>
              <button
                onClick={() => fetchGraphData(searchQuery)}
                className="mt-2 text-primary border border-primary/20 px-3 py-1 rounded hover:bg-primary/5"
              >
                Retry
              </button>
            </div>
          )}

          {!loading && !error && nodes.length === 0 && (
            <div className="absolute inset-0 flex flex-col items-center justify-center font-mono text-xs text-text-muted gap-1 z-20">
              <Info className="h-5 w-5 text-primary" />
              <span>No nodes matched search.</span>
            </div>
          )}

          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={onNodeClick}
            fitView
            minZoom={0.1}
            maxZoom={2}
          >
            <Controls showInteractive={false} />
            <PanControls />
            <MiniMap
              nodeColor={(node) => {
                const raw = node.data?.raw;
                if (!raw) return '#27272a';
                if (raw.category === 'entry_point') return '#10b981';
                if (raw.category === 'core_module') return '#3b82f6';
                if (raw.category === 'high_coupling') return '#f97316';
                if (raw.category === 'directory') return '#a855f7';
                return '#71717a';
              }}
              maskColor="rgba(9, 9, 11, 0.7)"
              style={{ backgroundColor: '#09090b', border: '1px solid #27272a' }}
            />
            <Background color="#27272a" gap={16} />
          </ReactFlow>
        </div>

        {/* Node Detail Panel */}
        {selectedNode && (
          <div className="absolute right-0 top-0 bottom-0 w-80 bg-zinc-950 border-l border-border p-4 z-10 flex flex-col justify-between shadow-2xl animate-in slide-in-from-right duration-200">
            <div className="space-y-4">
              <div className="flex justify-between items-start">
                <span className="text-[10px] font-bold text-primary uppercase tracking-wider font-mono">
                  Node Analysis Detail
                </span>
                <button
                  onClick={() => setSelectedNode(null)}
                  className="text-text-muted hover:text-text rounded p-0.5"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              <div className="space-y-3 font-mono text-xs">
                <div>
                  <span className="text-text-muted block text-[10px]">FILE PATH</span>
                  <span className="text-text font-semibold break-all text-xs block mt-0.5">{selectedNode.id}</span>
                </div>

                <div>
                  <span className="text-text-muted block text-[10px]">CATEGORY</span>
                  <span className={`inline-block text-[10px] font-bold uppercase px-2 py-0.5 rounded border mt-1 ${
                    selectedNode.category === 'entry_point' ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400' :
                    selectedNode.category === 'core_module' ? 'bg-blue-500/10 border-blue-500/20 text-blue-400' :
                    selectedNode.category === 'high_coupling' ? 'bg-orange-500/10 border-orange-500/20 text-orange-400' :
                    selectedNode.category === 'directory' ? 'bg-purple-500/10 border-purple-500/20 text-purple-400' :
                    'bg-zinc-800 border-zinc-700 text-zinc-300'
                  }`}>
                    {selectedNode.category.replace('_', ' ')}
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-3 pt-2">
                  <div className="border border-border bg-canvas/30 rounded p-2">
                    <span className="text-text-muted block text-[9px] uppercase">Degree</span>
                    <span className="text-text text-sm font-bold block mt-0.5">{selectedNode.degree}</span>
                  </div>
                  <div className="border border-border bg-canvas/30 rounded p-2">
                    <span className="text-text-muted block text-[9px] uppercase">Centrality</span>
                    <span className="text-text text-sm font-bold block mt-0.5">{selectedNode.centrality}</span>
                  </div>
                </div>
              </div>
            </div>

            <div className="text-[10px] text-text-muted leading-relaxed font-sans border-t border-border/40 pt-3">
              <span className="font-semibold text-text block mb-1">Legend:</span>
              <ul className="space-y-1 list-disc list-inside">
                <li><span className="text-emerald-400">Green</span>: Entry execution point</li>
                <li><span className="text-blue-400">Blue</span>: Central hub class</li>
                <li><span className="text-orange-400">Orange</span>: High-coupling interface</li>
                <li><span className="text-purple-400">Purple</span>: Grouped directory</li>
              </ul>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export const ArchitectureGraph: React.FC<GraphProps> = (props) => {
  return (
    <ReactFlowProvider>
      <ArchitectureGraphInner {...props} />
    </ReactFlowProvider>
  );
};
