import React, { useState, useEffect } from 'react';
import { Search, X, Command, Zap, Layers, Network, Workflow } from 'lucide-react';
import { useWorkspace } from './WorkspaceProvider';
import type { EngineeringIntent } from './types';

interface CommandPaletteProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectAction?: (action: string) => void;
}

export const CommandPalette: React.FC<CommandPaletteProps> = ({
  isOpen,
  onClose,
  onSelectAction,
}) => {
  const [query, setQuery] = useState('');
  const { setIntent, selectFile } = useWorkspace();

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        if (isOpen) onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const items = [
    { title: 'Open File: backend/api.py', action: () => selectFile('backend/api.py') },
    { title: 'Intent: Debug Issue', action: () => setIntent('Debug Issue') },
    { title: 'Intent: Learn Architecture', action: () => setIntent('Learn Architecture') },
    { title: 'Intent: Implement Feature', action: () => setIntent('Implement Feature') },
    { title: 'Open Repository Graph', action: () => onSelectAction && onSelectAction('graph') },
    { title: 'Trace Dependency Flow', action: () => onSelectAction && onSelectAction('trace') },
  ];

  const filtered = items.filter((i) => !query || i.title.toLowerCase().includes(query.toLowerCase()));

  return (
    <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm z-50 flex items-start justify-center pt-20 p-4 font-mono text-xs select-none">
      <div className="bg-zinc-950 border border-border rounded-xl w-full max-w-xl shadow-2xl overflow-hidden">
        <div className="p-3 border-b border-border flex items-center gap-2 bg-canvas/40">
          <Search className="h-4 w-4 text-primary shrink-0" />
          <input
            type="text"
            autoFocus
            placeholder="Type a command or search entities (Ctrl+K)..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-full bg-transparent text-text focus:outline-none text-xs"
          />
          <button onClick={onClose} className="text-text-muted hover:text-text">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="p-2 max-h-72 overflow-y-auto space-y-1">
          {filtered.map((item, idx) => (
            <button
              key={idx}
              onClick={() => {
                item.action();
                onClose();
              }}
              className="w-full text-left p-2.5 rounded-lg bg-canvas hover:bg-primary/20 hover:border-primary border border-border flex items-center justify-between text-text transition-all"
            >
              <span className="font-bold">{item.title}</span>
              <Command className="h-3 w-3 text-text-muted" />
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};
