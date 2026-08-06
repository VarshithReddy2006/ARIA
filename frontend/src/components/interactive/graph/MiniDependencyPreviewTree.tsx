import React, { useState } from 'react';
import { ChevronRight, ChevronDown, FileCode, ArrowRight, ArrowLeft } from 'lucide-react';

interface DependencyTreeProps {
  nodeId: string;
  dependsOn: string[];
  importedBy: string[];
  onSelectNode: (id: string) => void;
}

export const MiniDependencyPreviewTree: React.FC<DependencyTreeProps> = ({
  nodeId,
  dependsOn,
  importedBy,
  onSelectNode,
}) => {
  const [openDependsOn, setOpenDependsOn] = useState(true);
  const [openImportedBy, setOpenImportedBy] = useState(true);

  const shortName = (id: string) => id.split('/').pop() || id;

  return (
    <div className="space-y-3 font-mono text-xs select-none">
      {/* Depends On Subtree */}
      <div className="border border-border/60 bg-canvas/30 rounded-lg overflow-hidden">
        <button
          onClick={() => setOpenDependsOn(!openDependsOn)}
          className="w-full flex items-center justify-between px-3 py-2 bg-canvas/50 hover:bg-canvas/80 text-[10px] font-bold text-text-muted uppercase tracking-wider transition-colors"
        >
          <span className="flex items-center gap-1.5 text-blue-400">
            <ArrowRight className="h-3 w-3" /> Depends On ({dependsOn.length})
          </span>
          {openDependsOn ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        </button>

        {openDependsOn && (
          <div className="p-2 space-y-1 max-h-36 overflow-y-auto">
            {dependsOn.length === 0 ? (
              <span className="text-[10px] text-text-muted italic px-2 block">No outgoing dependencies</span>
            ) : (
              dependsOn.map((dep) => (
                <button
                  key={dep}
                  onClick={() => onSelectNode(dep)}
                  className="w-full flex items-center gap-2 px-2 py-1 rounded hover:bg-primary/10 text-left transition-colors text-text group"
                >
                  <FileCode className="h-3 w-3 text-text-muted group-hover:text-primary shrink-0" />
                  <span className="truncate text-[11px]" title={dep}>
                    {shortName(dep)}
                  </span>
                </button>
              ))
            )}
          </div>
        )}
      </div>

      {/* Imported By Subtree */}
      <div className="border border-border/60 bg-canvas/30 rounded-lg overflow-hidden">
        <button
          onClick={() => setOpenImportedBy(!openImportedBy)}
          className="w-full flex items-center justify-between px-3 py-2 bg-canvas/50 hover:bg-canvas/80 text-[10px] font-bold text-text-muted uppercase tracking-wider transition-colors"
        >
          <span className="flex items-center gap-1.5 text-emerald-400">
            <ArrowLeft className="h-3 w-3" /> Imported By ({importedBy.length})
          </span>
          {openImportedBy ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        </button>

        {openImportedBy && (
          <div className="p-2 space-y-1 max-h-36 overflow-y-auto">
            {importedBy.length === 0 ? (
              <span className="text-[10px] text-text-muted italic px-2 block">No incoming importers</span>
            ) : (
              importedBy.map((imp) => (
                <button
                  key={imp}
                  onClick={() => onSelectNode(imp)}
                  className="w-full flex items-center gap-2 px-2 py-1 rounded hover:bg-primary/10 text-left transition-colors text-text group"
                >
                  <FileCode className="h-3 w-3 text-text-muted group-hover:text-primary shrink-0" />
                  <span className="truncate text-[11px]" title={imp}>
                    {shortName(imp)}
                  </span>
                </button>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
};
