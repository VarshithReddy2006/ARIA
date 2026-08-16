import React, { useCallback } from 'react';
import { useReactFlow } from 'reactflow';
import { ArrowUp, ArrowDown, ArrowLeft, ArrowRight } from 'lucide-react';

export const PanControls: React.FC = () => {
  const { getViewport, setViewport } = useReactFlow();

  const handlePan = useCallback((dx: number, dy: number) => {
    const { x, y, zoom } = getViewport();
    setViewport({ x: x + dx, y: y + dy, zoom }, { duration: 200 });
  }, [getViewport, setViewport]);

  return (
    <div className="absolute bottom-4 left-16 z-10 flex flex-col items-center gap-1 nodrag nopan select-none">
      {/* Up Button */}
      <div className="bg-zinc-950/80 border border-zinc-800/80 rounded-md shadow-lg backdrop-blur-sm">
        <button
          type="button"
          onClick={() => handlePan(0, 150)}
          className="w-7 h-7 flex items-center justify-center hover:bg-zinc-900 text-zinc-400 hover:text-zinc-100 transition-colors rounded-md focus:outline-none"
          title="Pan Up"
        >
          <ArrowUp className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Row 2: Left, Down, Right */}
      <div className="flex bg-zinc-950/80 border border-zinc-800/80 rounded-md shadow-lg backdrop-blur-sm divide-x divide-zinc-800/80">
        <button
          type="button"
          onClick={() => handlePan(150, 0)}
          className="w-7 h-7 flex items-center justify-center hover:bg-zinc-900 text-zinc-400 hover:text-zinc-100 transition-colors rounded-l-md focus:outline-none"
          title="Pan Left"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          onClick={() => handlePan(0, -150)}
          className="w-7 h-7 flex items-center justify-center hover:bg-zinc-900 text-zinc-400 hover:text-zinc-100 transition-colors focus:outline-none"
          title="Pan Down"
        >
          <ArrowDown className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          onClick={() => handlePan(-150, 0)}
          className="w-7 h-7 flex items-center justify-center hover:bg-zinc-900 text-zinc-400 hover:text-zinc-100 transition-colors rounded-r-md focus:outline-none"
          title="Pan Right"
        >
          <ArrowRight className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
};

export default PanControls;
