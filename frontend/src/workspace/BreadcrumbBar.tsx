import React from 'react';
import { ChevronRight, ArrowLeft, ArrowRight, Pin } from 'lucide-react';
import { useWorkspace } from './WorkspaceProvider';

export const BreadcrumbBar: React.FC = () => {
  const { breadcrumbs, navigateBack, navigateForward, contextState, confidencePct } = useWorkspace();

  return (
    <div className="px-3 py-1.5 bg-canvas border-b border-border flex items-center justify-between text-[10px] font-mono text-text-muted select-none">
      <div className="flex items-center gap-1.5 min-w-0">
        <div className="flex items-center gap-1 shrink-0">
          <button onClick={navigateBack} className="hover:text-text p-0.5 rounded">
            <ArrowLeft className="h-3 w-3" />
          </button>
          <button onClick={navigateForward} className="hover:text-text p-0.5 rounded">
            <ArrowRight className="h-3 w-3" />
          </button>
        </div>

        <div className="flex items-center gap-1 truncate border-l border-border/60 pl-2">
          {breadcrumbs.map((b, idx) => (
            <React.Fragment key={idx}>
              {idx > 0 && <ChevronRight className="h-3 w-3 text-text-subtle shrink-0" />}
              <span className={idx === breadcrumbs.length - 1 ? 'text-primary font-bold' : 'hover:text-text'}>
                {b}
              </span>
            </React.Fragment>
          ))}
        </div>
      </div>

      <div className="flex items-center gap-2 shrink-0">
        <span className="px-2 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 font-bold">
          Context: {contextState} ({confidencePct}%)
        </span>
      </div>
    </div>
  );
};
