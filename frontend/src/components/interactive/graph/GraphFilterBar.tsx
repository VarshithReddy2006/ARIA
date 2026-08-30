import React from 'react';
import { Filter, X, Flame } from 'lucide-react';
import { useGraphWorkspace } from './workspaceStore';
import type { HeatmapMode } from './types';

interface FilterOption {
  id: string;
  label: string;
  color: string;
}

const FILTER_OPTIONS: FilterOption[] = [
  { id: 'entry_point', label: 'Entry Point', color: '#10b981' },
  { id: 'core_module', label: 'Core Module', color: '#3b82f6' },
  { id: 'domain', label: 'Domain', color: '#8b5cf6' },
  { id: 'service', label: 'Service', color: '#6366f1' },
  { id: 'controller', label: 'Controller', color: '#ec4899' },
  { id: 'high_coupling', label: 'High Coupling', color: '#f97316' },
  { id: 'infrastructure', label: 'Infra', color: '#0ea5e9' },
  { id: 'utility', label: 'Utility', color: '#64748b' },
  { id: 'test', label: 'Test', color: '#06b6d4' },
];

const HEATMAP_DESCRIPTIONS: Record<HeatmapMode, string> = {
  none: 'Standard architectural category colors',
  centrality: 'Highlights modules with high graph centrality in dependency paths',
  coupling: 'Highlights modules with high total connectivity (inbound + outbound)',
  fan_in: 'Highlights modules with high incoming caller dependents',
  fan_out: 'Highlights modules with high outgoing dependencies',
  complexity: 'Highlights modules with high cyclomatic complexity',
  churn: 'Highlights modules with frequent git modification churn',
  file_size: 'Highlights large modules by lines of code',
  violations: 'Highlights detected architectural layer boundary violations',
  impact: 'Highlights modules with large downstream change blast radius',
};

export const GraphFilterBar: React.FC = () => {
  const { activeFilters, toggleFilter, clearFilters, heatmapMode, setHeatmapMode } = useGraphWorkspace();

  return (
    <div className="flex items-center justify-between px-3 py-1.5 bg-zinc-950/90 border-b border-border/80 text-xs font-mono select-none gap-4">
      {/* Category Filter Chips */}
      <div className="flex items-center gap-1.5 overflow-x-auto min-w-0 py-0.5">
        <span className="flex items-center gap-1 text-[10px] text-zinc-400 uppercase font-bold tracking-wider shrink-0 mr-1">
          <Filter className="h-3 w-3 text-indigo-400" /> Category:
        </span>

        {FILTER_OPTIONS.map((opt) => {
          const isActive = activeFilters.includes(opt.id);
          return (
            <button
              key={opt.id}
              onClick={() => toggleFilter(opt.id)}
              className={`flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-[10px] font-semibold transition-all shrink-0 ${
                isActive
                  ? 'bg-indigo-500/20 border-indigo-500 text-zinc-100 shadow-sm'
                  : 'bg-zinc-900 border-zinc-800 text-zinc-400 hover:text-zinc-200 hover:border-zinc-700'
              }`}
              title={`Toggle ${opt.label} filter`}
            >
              <span
                className="h-1.5 w-1.5 rounded-full shrink-0"
                style={{ backgroundColor: opt.color }}
              />
              <span>{opt.label}</span>
            </button>
          );
        })}

        {activeFilters.length > 0 && (
          <button
            onClick={clearFilters}
            className="flex items-center gap-1 px-2 py-0.5 text-[10px] text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 rounded shrink-0 transition-colors"
          >
            <X className="h-3 w-3" /> Clear
          </button>
        )}
      </div>

      {/* Heatmap Overlay Selector */}
      <div className="flex items-center gap-2 shrink-0 border-l border-zinc-800/80 pl-3" title={HEATMAP_DESCRIPTIONS[heatmapMode]}>
        <Flame className="h-3.5 w-3.5 text-amber-400 shrink-0" />
        <span className="text-[10px] text-zinc-400 uppercase font-bold tracking-wider hidden sm:inline">Heatmap:</span>
        <select
          value={heatmapMode}
          onChange={(e) => setHeatmapMode(e.target.value as HeatmapMode)}
          className="bg-zinc-900 border border-zinc-800 rounded px-2 py-1 text-[10px] font-mono text-zinc-200 focus:outline-none focus:border-indigo-500 cursor-pointer"
        >
          <option value="none">Standard Colors</option>
          <option value="centrality">Graph Centrality</option>
          <option value="coupling">High Coupling</option>
          <option value="fan_in">Fan-In (Callers)</option>
          <option value="fan_out">Fan-Out (Dependencies)</option>
          <option value="complexity">Cyclomatic Complexity</option>
          <option value="churn">Git Churn</option>
          <option value="file_size">Module Size (LOC)</option>
          <option value="violations">Layer Violations</option>
          <option value="impact">Downstream Blast Radius</option>
        </select>
      </div>
    </div>
  );
};
