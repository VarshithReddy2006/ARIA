import React from 'react';
import { ArrowLeft, ArrowRight, Eye, EyeOff, Folder, FileCode } from 'lucide-react';
import { useGraphWorkspace } from './workspaceStore';

export const GraphBreadcrumbNav: React.FC = () => {
  const {
    selectedNodeId,
    historyIndex,
    historyStack,
    navigateBack,
    navigateForward,
    focusMode,
    setFocusMode,
    selectNode,
  } = useGraphWorkspace();

  const pathParts = selectedNodeId ? selectedNodeId.split('/') : [];

  return (
    <div className="flex items-center justify-between px-3 py-1.5 bg-zinc-950/80 border-b border-border text-xs font-mono select-none">
      {/* Back / Forward History Controls */}
      <div className="flex items-center gap-1 shrink-0">
        <button
          onClick={navigateBack}
          disabled={historyIndex <= 0}
          className="p-1 text-text-muted hover:text-text disabled:opacity-30 rounded hover:bg-canvas transition-colors"
          title="Navigate Back (Alt+Left)"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
        </button>
        <button
          onClick={navigateForward}
          disabled={historyIndex >= historyStack.length - 1}
          className="p-1 text-text-muted hover:text-text disabled:opacity-30 rounded hover:bg-canvas transition-colors"
          title="Navigate Forward (Alt+Right)"
        >
          <ArrowRight className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Interactive Breadcrumb Trail */}
      <div className="flex items-center gap-1 text-[11px] text-text-muted overflow-x-auto mx-3 min-w-0">
        {!selectedNodeId ? (
          <span className="italic text-text-muted/60 text-[10px]">Select any graph node to inspect path</span>
        ) : (
          pathParts.map((part, i) => {
            const isLast = i === pathParts.length - 1;
            const fullPartialPath = pathParts.slice(0, i + 1).join('/');

            return (
              <React.Fragment key={i}>
                {i > 0 && <span className="text-text-muted/40">/</span>}
                <button
                  onClick={() => selectNode(fullPartialPath)}
                  className={`hover:text-primary transition-colors truncate ${
                    isLast ? 'text-primary font-bold' : 'text-text-muted'
                  }`}
                >
                  {isLast ? (
                    <span className="flex items-center gap-1">
                      <FileCode className="h-3 w-3 shrink-0" />
                      {part}
                    </span>
                  ) : (
                    <span className="flex items-center gap-1">
                      <Folder className="h-3 w-3 shrink-0" />
                      {part}
                    </span>
                  )}
                </button>
              </React.Fragment>
            );
          })
        )}
      </div>

      {/* Focus Mode Toggle */}
      <button
        onClick={() => setFocusMode(!focusMode)}
        className={`flex items-center gap-1.5 px-2.5 py-1 rounded border text-[10px] font-bold transition-all shrink-0 ${
          focusMode
            ? 'bg-emerald-500/20 border-emerald-500 text-emerald-400 shadow-sm'
            : 'bg-canvas border-border/70 text-text-muted hover:text-text'
        }`}
        title="Focus Mode hides nodes outside current selection neighborhood"
      >
        {focusMode ? <Eye className="h-3 w-3" /> : <EyeOff className="h-3 w-3" />}
        <span>Focus Mode</span>
      </button>
    </div>
  );
};
