import React, { useState, useEffect } from 'react';
import {
  Compass, Command, Search, Target, Zap, LayoutGrid, ShieldCheck, Layers
} from 'lucide-react';
import { useWorkspace } from './WorkspaceProvider';
import { BreadcrumbBar } from './BreadcrumbBar';
import { CommandPalette } from './CommandPalette';
import type { EngineeringIntent } from './types';

interface UnifiedWorkspaceLayoutProps {
  repoName: string;
  onOpenGraphNode?: (path: string) => void;
  onOpenCallGraph?: () => void;
  onOpenArchitecture?: () => void;
}

export const UnifiedWorkspaceLayout: React.FC<UnifiedWorkspaceLayoutProps> = ({
  repoName,
  onOpenGraphNode,
  onOpenCallGraph,
  onOpenArchitecture,
}) => {
  const { intent, setIntent, contextState, confidencePct } = useWorkspace();
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);

  const intents: EngineeringIntent[] = [
    'Understand Repository',
    'Understand Feature',
    'Debug Issue',
    'Implement Feature',
    'Review Pull Request',
    'Refactor Code',
    'Trace Execution',
    'Investigate Performance',
    'Investigate Security',
    'Learn Architecture',
  ];

  return (
    <div className="flex flex-col h-full bg-canvas font-mono text-xs select-none">
      {/* Top Engineering Intent Header */}
      <div className="px-4 py-2 bg-zinc-950 border-b border-border flex items-center justify-between gap-3 flex-wrap z-20">
        <div className="flex items-center gap-2">
          <Target className="h-4 w-4 text-primary" />
          <span className="font-extrabold text-xs text-text uppercase">Engineering Intent:</span>
          <select
            value={intent}
            onChange={(e) => setIntent(e.target.value as EngineeringIntent)}
            className="bg-canvas border border-border rounded px-2.5 py-1 font-extrabold text-xs text-primary focus:outline-none focus:border-primary"
          >
            {intents.map((i) => (
              <option key={i} value={i} className="bg-zinc-900 text-text">{i}</option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setCommandPaletteOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1 rounded bg-canvas border border-border hover:border-primary text-[10px] text-text-muted hover:text-text font-bold"
          >
            <Command className="h-3 w-3 text-primary" /> Command Palette (Ctrl+K)
          </button>
        </div>
      </div>

      {/* Synchronized Breadcrumb Trail */}
      <BreadcrumbBar />

      {/* Main Workstation Container */}
      <div className="flex-grow min-h-0 overflow-hidden p-4">
        <div className="h-full border border-border rounded-lg bg-surface-1 flex items-center justify-center text-text-muted text-xs font-mono">
          Unified Workstation Active — {repoName}
        </div>
      </div>

      {/* Ctrl+K Command Palette Modal */}
      <CommandPalette
        isOpen={commandPaletteOpen}
        onClose={() => setCommandPaletteOpen(false)}
        onSelectAction={(act) => {
          if (act === 'graph' && onOpenGraphNode) onOpenGraphNode('backend/api.py');
          if (act === 'trace' && onOpenCallGraph) onOpenCallGraph();
        }}
      />
    </div>
  );
};
