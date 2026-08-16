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
  { id: 'entry_point', label: 'Entry Points', color: '#10b981' },
  { id: 'core_module', label: 'Core Modules', color: '#3b82f6' },
  { id: 'service', label: 'Services', color: '#6366f1' },
  { id: 'controller', label: 'Controllers', color: '#ec4899' },
  { id: 'high_coupling', label: 'High Coupling', color: '#f97316' },
  { id: 'utility', label: 'Utilities', color: '#64748b' },
  { id: 'test', label: 'Tests', color: '#06b6d4' },
];

export const GraphFilterBar: React.FC = () => {
  const { activeFilters, toggleFilter, clearFilters, heatmapMode, setHeatmapMode } = useGraphWorkspace();

  return (
    <div className="flex items-center justify-between px-3 py-2 bg-zinc-950/90 border-b border-border/80 text-xs font-mono select-none gap-4">
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
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[10px] font-semibold transition-all shrink-0 ${
                isActive
                  ? 'bg-indigo-500/20 border-indigo-500 text-zinc-100 shadow-sm'
                  : 'bg-zinc-900 border-zinc-800 text-zinc-400 hover:text-zinc-200 hover:border-zinc-700'
              }`}
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
            className="flex items-center gap-1 px-2 py-1 text-[10px] text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 rounded shrink-0 transition-colors"
          >
            <X className="h-3 w-3" /> Clear
          </button>
        )}
      </div>

      {/* Heatmap Overlay Selector */}
      <div className="flex items-center gap-2 shrink-0 border-l border-zinc-800/80 pl-3">
        <Flame className="h-3.5 w-3.5 text-amber-400 shrink-0" />
        <span className="text-[10px] text-zinc-400 uppercase font-bold tracking-wider hidden sm:inline">Heatmap:</span>
        <select
          value={heatmapMode}
          onChange={(e) => setHeatmapMode(e.target.value as HeatmapMode)}
          className="bg-zinc-900 border border-zinc-800 rounded px-2 py-1 text-[10px] font-mono text-zinc-200 focus:outline-none focus:border-indigo-500"
        >
          <option value="none">Standard Colors</option>
          <option value="coupling">High Coupling</option>
          <option value="complexity">High Complexity</option>
          <option value="fan_out">High Fan-Out</option>
          <option value="churn">High Churn</option>
          <option value="file_size">Large Files</option>
          <option value="violations">Architecture Violations</option>
        </select>
      </div>
    </div>
  );
};
