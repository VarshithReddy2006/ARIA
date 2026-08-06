import React, { createContext, useContext, useState, useCallback, useMemo } from 'react';
import type { GraphMode, HeatmapMode, DependencyPath } from './types';

export interface GraphWorkspaceState {
  selectedNodeId: string | null;
  hoveredNodeId: string | null;
  focusedNodeId: string | null;
  focusMode: boolean;
  heatmapMode: HeatmapMode;
  pathSourceNodeId: string | null;
  pathTargetNodeId: string | null;
  dependencyPath: DependencyPath | null;
  historyStack: string[];
  historyIndex: number;
  activeFilters: string[];
  searchQuery: string;
  inspectorTab: 'overview' | 'architecture' | 'metrics' | 'deps' | 'git' | 'guidance' | 'impact' | 'recommendations';
  mode: GraphMode;
  
  selectNode: (id: string | null) => void;
  hoverNode: (id: string | null) => void;
  toggleFilter: (filterId: string) => void;
  clearFilters: () => void;
  navigateBack: () => void;
  navigateForward: () => void;
  setFocusMode: (enabled: boolean) => void;
  setHeatmapMode: (mode: HeatmapMode) => void;
  setPathSourceNodeId: (id: string | null) => void;
  setPathTargetNodeId: (id: string | null) => void;
  setDependencyPath: (path: DependencyPath | null) => void;
  setInspectorTab: (tab: GraphWorkspaceState['inspectorTab']) => void;
  setMode: (mode: GraphMode) => void;
  setSearchQuery: (query: string) => void;
}

const GraphWorkspaceContext = createContext<GraphWorkspaceState | null>(null);

export const GraphWorkspaceProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const [focusedNodeId, setFocusedNodeId] = useState<string | null>(null);
  const [focusMode, setFocusMode] = useState<boolean>(false);
  const [heatmapMode, setHeatmapMode] = useState<HeatmapMode>('none');
  const [pathSourceNodeId, setPathSourceNodeId] = useState<string | null>(null);
  const [pathTargetNodeId, setPathTargetNodeId] = useState<string | null>(null);
  const [dependencyPath, setDependencyPath] = useState<DependencyPath | null>(null);
  const [historyStack, setHistoryStack] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState<number>(-1);
  const [activeFilters, setActiveFilters] = useState<string[]>([]);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [inspectorTab, setInspectorTab] = useState<GraphWorkspaceState['inspectorTab']>('overview');
  const [mode, setMode] = useState<GraphMode>('full');

  const selectNode = useCallback((id: string | null) => {
    setSelectedNodeId(id);
    if (id) {
      setHistoryStack((prev) => {
        const next = prev.slice(0, historyIndex + 1);
        next.push(id);
        return next;
      });
      setHistoryIndex((prev) => prev + 1);
    }
  }, [historyIndex]);

  const hoverNode = useCallback((id: string | null) => {
    setHoveredNodeId(id);
  }, []);

  const toggleFilter = useCallback((filterId: string) => {
    setActiveFilters((prev) =>
      prev.includes(filterId) ? prev.filter((f) => f !== filterId) : [...prev, filterId]
    );
  }, []);

  const clearFilters = useCallback(() => {
    setActiveFilters([]);
  }, []);

  const navigateBack = useCallback(() => {
    if (historyIndex > 0) {
      const prevIdx = historyIndex - 1;
      setHistoryIndex(prevIdx);
      setSelectedNodeId(historyStack[prevIdx]);
    }
  }, [historyIndex, historyStack]);

  const navigateForward = useCallback(() => {
    if (historyIndex < historyStack.length - 1) {
      const nextIdx = historyIndex + 1;
      setHistoryIndex(nextIdx);
      setSelectedNodeId(historyStack[nextIdx]);
    }
  }, [historyIndex, historyStack]);

  const value = useMemo(
    () => ({
      selectedNodeId,
      hoveredNodeId,
      focusedNodeId,
      focusMode,
      heatmapMode,
      pathSourceNodeId,
      pathTargetNodeId,
      dependencyPath,
      historyStack,
      historyIndex,
      activeFilters,
      searchQuery,
      inspectorTab,
      mode,
      selectNode,
      hoverNode,
      toggleFilter,
      clearFilters,
      navigateBack,
      navigateForward,
      setFocusMode,
      setHeatmapMode,
      setPathSourceNodeId,
      setPathTargetNodeId,
      setDependencyPath,
      setInspectorTab,
      setMode,
      setSearchQuery,
    }),
    [
      selectedNodeId,
      hoveredNodeId,
      focusedNodeId,
      focusMode,
      heatmapMode,
      pathSourceNodeId,
      pathTargetNodeId,
      dependencyPath,
      historyStack,
      historyIndex,
      activeFilters,
      searchQuery,
      inspectorTab,
      mode,
      selectNode,
      hoverNode,
      toggleFilter,
      clearFilters,
      navigateBack,
      navigateForward,
    ]
  );

  return (
    <GraphWorkspaceContext.Provider value={value}>
      {children}
    </GraphWorkspaceContext.Provider>
  );
};

export const useGraphWorkspace = () => {
  const ctx = useContext(GraphWorkspaceContext);
  if (!ctx) {
    throw new Error('useGraphWorkspace must be used within GraphWorkspaceProvider');
  }
  return ctx;
};
