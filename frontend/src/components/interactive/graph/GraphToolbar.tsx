import React, { useState } from 'react';
import {
  Maximize2,
  Network,
  ArrowRight,
  ArrowLeft,
  ArrowLeftRight,
  RotateCcw,
  Loader2,
  HelpCircle,
  Palette,
  ChevronUp,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ZoomIn,
  ZoomOut,
  Crosshair,
} from 'lucide-react';
import type { GraphMode, AbstractionLevel } from './types';

interface GraphToolbarProps {
  mode: GraphMode;
  level?: AbstractionLevel;
  traceDir: 'forward' | 'backward' | 'both';
  focusNode: string | null;
  loading: boolean;
  nodeCount: number;
  edgeCount: number;
  onSetMode?: (mode: GraphMode) => void;
  onSetLevel?: (level: AbstractionLevel) => void;
  onFitView: () => void;
  onReset: () => void;
  onTraceForward: () => void;
  onTraceBackward: () => void;
  onTraceBoth: () => void;
  onNeighbors: () => void;
  onPanUp: () => void;
  onPanDown: () => void;
  onPanLeft: () => void;
  onPanRight: () => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onCenterGraph: () => void;
}

interface ToolButtonProps {
  onClick: () => void;
  active?: boolean;
  disabled?: boolean;
  title: string;
  children: React.ReactNode;
  variant?: 'default' | 'danger' | 'accent';
}

const ToolButton: React.FC<ToolButtonProps> = ({
  onClick,
  active,
  disabled,
  title,
  children,
  variant = 'default',
}) => {
  const base =
    'flex items-center gap-1.5 px-2.5 py-1.5 rounded text-[10px] font-mono font-semibold transition-all border shrink-0';
  const inactive =
    'bg-zinc-900/80 border-zinc-800 text-zinc-400 hover:text-zinc-100 hover:border-indigo-500/50';
  const activeStyle =
    'bg-indigo-500/20 border-indigo-500 text-indigo-200 shadow-sm';
  const accentStyle =
    'bg-amber-500/15 border-amber-500/40 text-amber-300 hover:bg-amber-500/25';
  const dangerStyle =
    'bg-red-500/10 border-red-500/30 text-red-400 hover:bg-red-500/20';
  const disabledStyle = 'opacity-40 cursor-not-allowed';

  const cls = [
    base,
    disabled ? disabledStyle : active ? activeStyle : variant === 'danger' ? dangerStyle : variant === 'accent' ? accentStyle : inactive,
  ].join(' ');

  return (
    <button className={cls} onClick={onClick} disabled={disabled} title={title}>
      {children}
    </button>
  );
};

const NODE_LEGEND = [
  { label: 'Entry Point',    color: '#10b981' },
  { label: 'Core Module',    color: '#3b82f6' },
  { label: 'Domain Layer',   color: '#8b5cf6' },
  { label: 'Service',        color: '#6366f1' },
  { label: 'Controller',     color: '#ec4899' },
  { label: 'High Coupling',  color: '#f97316' },
  { label: 'Infrastructure', color: '#0ea5e9' },
  { label: 'Utility',        color: '#64748b' },
  { label: 'Test Suite',     color: '#06b6d4' },
];

const SHORTCUTS = [
  { key: '/',          desc: 'Focus search' },
  { key: 'F',          desc: 'Fit view' },
  { key: 'R',          desc: 'Reset graph' },
  { key: 'Scroll',     desc: 'Zoom in / out' },
  { key: '↑ ↓ ← →',   desc: 'Pan canvas' },
  { key: 'Click node', desc: 'Select & inspect' },
];

export const GraphToolbar: React.FC<GraphToolbarProps> = ({
  mode,
  level = 'files',
  traceDir,
  focusNode,
  loading,
  nodeCount,
  edgeCount,
  onSetMode,
  onSetLevel,
  onFitView,
  onReset,
  onTraceForward,
  onTraceBackward,
  onTraceBoth,
  onNeighbors,
  onPanUp,
  onPanDown,
  onPanLeft,
  onPanRight,
  onZoomIn,
  onZoomOut,
  onCenterGraph,
}) => {
  const hasFocus = Boolean(focusNode);
  const focusLabel = focusNode
    ? focusNode.split('/').pop() ?? focusNode
    : null;
  const [showLegend,    setShowLegend]    = useState(false);
  const [showShortcuts, setShowShortcuts] = useState(false);

  return (
    <div className="px-3 py-2 border-b border-border/80 bg-zinc-950/60 flex flex-wrap items-center gap-2 z-10 relative select-none">
      {/* Abstraction Level Selector */}
      <div className="flex items-center bg-zinc-900 border border-zinc-800 rounded p-0.5 text-[9px] font-mono shrink-0">
        <span className="text-zinc-500 uppercase font-bold px-1.5 hidden sm:inline">Level:</span>
        <button
          onClick={() => onSetLevel && onSetLevel('system')}
          className={`px-2 py-1 rounded transition-all font-bold ${
            level === 'system'
              ? 'bg-indigo-600 text-white shadow-sm'
              : 'text-zinc-400 hover:text-zinc-200'
          }`}
          title="System Level: High-level architectural clusters"
        >
          SYSTEM
        </button>
        <button
          onClick={() => onSetLevel && onSetLevel('components')}
          className={`px-2 py-1 rounded transition-all font-bold ${
            level === 'components'
              ? 'bg-indigo-600 text-white shadow-sm'
              : 'text-zinc-400 hover:text-zinc-200'
          }`}
          title="Component Level: Expanded active components"
        >
          COMPONENTS
        </button>
        <button
          onClick={() => onSetLevel && onSetLevel('files')}
          className={`px-2 py-1 rounded transition-all font-bold ${
            level === 'files'
              ? 'bg-indigo-600 text-white shadow-sm'
              : 'text-zinc-400 hover:text-zinc-200'
          }`}
          title="File Level: Full granular file topology"
        >
          FILES
        </button>
      </div>

      {/* Divider */}
      <div className="h-4 w-px bg-border hidden sm:block" />

      {/* Left — Primary Investigation Modes */}
      <div className="flex items-center gap-1.5 overflow-x-auto py-0.5">
        <span className="text-[9px] font-bold text-zinc-500 uppercase tracking-wider mr-1 hidden lg:inline">
          Mode:
        </span>

        <ToolButton
          onClick={() => onSetMode ? onSetMode('overview') : onReset()}
          active={mode === 'overview' || mode === 'full'}
          title="Overview: Show major repository topology"
        >
          <Network className="h-3 w-3" />
          <span>Overview</span>
        </ToolButton>

        <ToolButton
          onClick={onTraceForward}
          active={mode === 'trace_fwd' || mode === 'dependencies'}
          disabled={!hasFocus}
          title={hasFocus ? `Dependencies: Trace forward deps of ${focusNode}` : 'Select a node first'}
        >
          <ArrowRight className="h-3 w-3" />
          <span>Dependencies →</span>
        </ToolButton>

        <ToolButton
          onClick={onTraceBackward}
          active={mode === 'trace_bwd' || mode === 'callers'}
          disabled={!hasFocus}
          title={hasFocus ? `Callers: Trace who imports ${focusNode}` : 'Select a node first'}
        >
          <ArrowLeft className="h-3 w-3" />
          <span>← Callers</span>
        </ToolButton>

        <ToolButton
          onClick={() => onSetMode ? onSetMode('impact') : onTraceBackward()}
          active={mode === 'impact'}
          disabled={!hasFocus}
          variant="accent"
          title={hasFocus ? `Impact: Show full downstream blast radius of ${focusNode}` : 'Select a node first'}
        >
          <ArrowLeftRight className="h-3 w-3" />
          <span>Impact</span>
        </ToolButton>

        <ToolButton
          onClick={() => onSetMode && onSetMode('hotspots')}
          active={mode === 'hotspots'}
          title="Hotspots: Highlight highly coupled and central nodes"
        >
          <span>🔥 Hotspots</span>
        </ToolButton>

        <ToolButton
          onClick={() => onSetMode && onSetMode('entry_points')}
          active={mode === 'entry_points'}
          title="Entry Points: Highlight application and executable roots"
        >
          <span>🚀 Entry Points</span>
        </ToolButton>
      </div>

      {/* Divider */}
      <div className="h-4 w-px bg-border hidden md:block" />

      {/* View controls */}
      <div className="flex items-center gap-1.5">
        <ToolButton onClick={onFitView} title="Fit all nodes in view">
          <Maximize2 className="h-3 w-3" />
          <span>Fit</span>
        </ToolButton>

        <ToolButton onClick={onReset} title="Reset to full graph" variant={mode !== 'full' && mode !== 'overview' ? 'danger' : 'default'}>
          <RotateCcw className="h-3 w-3" />
          <span>Reset</span>
        </ToolButton>
      </div>

      {/* Divider */}
      <div className="h-4 w-px bg-border hidden xl:block" />

      {/* Viewport Pan/Zoom Controls */}
      <div className="hidden xl:flex items-center gap-1">
        <ToolButton onClick={onPanLeft} title="Move Left">
          <ChevronLeft className="h-3 w-3" />
        </ToolButton>
        <ToolButton onClick={onPanUp} title="Move Up">
          <ChevronUp className="h-3 w-3" />
        </ToolButton>
        <ToolButton onClick={onPanDown} title="Move Down">
          <ChevronDown className="h-3 w-3" />
        </ToolButton>
        <ToolButton onClick={onPanRight} title="Move Right">
          <ChevronRight className="h-3 w-3" />
        </ToolButton>
        
        <div className="w-1" />
        
        <ToolButton onClick={onZoomIn} title="Zoom In">
          <ZoomIn className="h-3 w-3" />
        </ToolButton>
        <ToolButton onClick={onZoomOut} title="Zoom Out">
          <ZoomOut className="h-3 w-3" />
        </ToolButton>
        <ToolButton onClick={onCenterGraph} title="Center Graph">
          <Crosshair className="h-3 w-3" />
        </ToolButton>
      </div>

      {/* Divider */}
      <div className="h-4 w-px bg-border hidden md:block" />

      {/* Legend + shortcuts */}
      <div className="flex items-center gap-1.5">
        <ToolButton onClick={() => setShowLegend(v => !v)} active={showLegend} title="Toggle node colour legend">
          <Palette className="h-3 w-3" />
          <span>Legend</span>
        </ToolButton>
        <ToolButton onClick={() => setShowShortcuts(v => !v)} active={showShortcuts} title="Keyboard shortcuts">
          <HelpCircle className="h-3 w-3" />
          <span>Keys</span>
        </ToolButton>
      </div>

      {/* Status / focus indicator */}
      <div className="flex items-center gap-2 ml-auto text-[10px] font-mono text-text-muted">
        {loading && (
          <span className="flex items-center gap-1 text-primary">
            <Loader2 className="h-3 w-3 animate-spin" />
            Loading…
          </span>
        )}

        {focusLabel && !loading && (
          <span className="flex items-center gap-1">
            <span className="text-primary">⬤</span>
            <span className="truncate max-w-[140px]" title={focusNode ?? ''}>
              {focusLabel}
            </span>
          </span>
        )}

        {!loading && (
          <span className="text-text-subtle">
            {nodeCount}n · {edgeCount}e
          </span>
        )}
      </div>

      {/* Legend dropdown */}
      {showLegend && (
        <div className="absolute top-full left-0 mt-1 z-20 bg-surface-1 border border-border rounded-lg p-3 min-w-[160px]" style={{boxShadow:'var(--shadow-raised)'}}>
          <p className="text-[9px] font-mono uppercase tracking-widest text-text-subtle mb-2">Node Categories</p>
          <dl className="space-y-1.5">
            {NODE_LEGEND.map(({ label, color }) => (
              <div key={label} className="flex items-center gap-2">
                <dt className="h-3 w-3 rounded-full shrink-0" style={{ background: color }} />
                <dd className="text-[11px] font-mono text-text-muted">{label}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}

      {/* Shortcuts dropdown */}
      {showShortcuts && (
        <div className="absolute top-full left-36 mt-1 z-20 bg-surface-1 border border-border rounded-lg p-3 min-w-[210px]" style={{boxShadow:'var(--shadow-raised)'}}>
          <p className="text-[9px] font-mono uppercase tracking-widest text-text-subtle mb-2">Keyboard Shortcuts</p>
          <dl className="space-y-1.5">
            {SHORTCUTS.map(({ key, desc }) => (
              <div key={key} className="flex items-center justify-between gap-4">
                <dt className="text-[11px] font-mono text-primary bg-primary/10 border border-primary/20 px-1.5 py-0.5 rounded shrink-0">{key}</dt>
                <dd className="text-[11px] font-mono text-text-muted">{desc}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}
    </div>
  );
};
