import React, { useState, useEffect, useRef } from 'react';

interface CommandItem {
  id: string;
  category: 'NAVIGATION' | 'DIAGNOSTIC' | 'REPOSITORY' | 'ACTION';
  title: string;
  subtitle: string;
  badge?: string;
  href?: string;
  shortcut?: string;
}

const COMMANDS: CommandItem[] = [
  {
    id: 'open-aria',
    category: 'NAVIGATION',
    title: 'Open Repository Analysis Engine',
    subtitle: 'Full codebase graph, dependencies, and file overview',
    badge: 'CORE',
    href: '/analysis',
    shortcut: '↵',
  },
  {
    id: 'health-report',
    category: 'DIAGNOSTIC',
    title: 'Codebase Health Report',
    subtitle: 'Diagnostic lens, risk clustering, test coverage integrity',
    badge: 'HEALTH',
    href: '/health-report',
  },
  {
    id: 'dead-code',
    category: 'DIAGNOSTIC',
    title: 'Dead Code & Unreferenced Symbols',
    subtitle: 'Orphaned AST functions, unused imports, safely reclaimable lines',
    badge: 'CLEANUP',
    href: '/dead-code',
  },
  {
    id: 'issues',
    category: 'DIAGNOSTIC',
    title: 'Automated Remediation Plans',
    subtitle: 'Traceable action items, impact radius, validation steps',
    badge: 'ISSUES',
    href: '/issues',
  },
  {
    id: 'pr-risk',
    category: 'DIAGNOSTIC',
    title: 'PR Risk & Regression Forecast',
    subtitle: 'Blast radius evaluation, untested call paths before merge',
    badge: 'RISK',
    href: '/risk',
  },
  {
    id: 'drift',
    category: 'DIAGNOSTIC',
    title: 'Architectural Drift & Circular Boundaries',
    subtitle: 'Layer violations, unexpected cross-boundary imports',
    badge: 'DRIFT',
    href: '/drift',
  },
  {
    id: 'impact',
    category: 'DIAGNOSTIC',
    title: 'Downstream Impact Analysis',
    subtitle: 'Traverse transitive caller paths for modified functions',
    badge: 'IMPACT',
    href: '/impact',
  },
  {
    id: 'sample-fastapi',
    category: 'REPOSITORY',
    title: 'Sample: fastapi/fastapi',
    subtitle: 'Python · 1,284 nodes · 4,890 call edges',
    badge: 'FASTAPI',
    href: '/analysis?repo=fastapi/fastapi',
  },
  {
    id: 'sample-flask',
    category: 'REPOSITORY',
    title: 'Sample: pallets/flask',
    subtitle: 'Python · WSGI Microframework topology',
    badge: 'FLASK',
    href: '/analysis?repo=pallets/flask',
  },
  {
    id: 'sample-nextjs',
    category: 'REPOSITORY',
    title: 'Sample: vercel/next.js',
    subtitle: 'TypeScript · Monorepo full dependency graph',
    badge: 'NEXT.JS',
    href: '/analysis?repo=vercel/next.js',
  },
];

export const CommandPalette: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement | null>(null);

  // Keyboard shortcut listener (Ctrl+K or Cmd+K)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setIsOpen((prev) => !prev);
      } else if (e.key === 'Escape' && isOpen) {
        e.preventDefault();
        setIsOpen(false);
      }
    };

    // Also listen to custom open event from navbar
    const handleCustomOpen = () => setIsOpen(true);

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('open-aria-search', handleCustomOpen);
    window.addEventListener('open-command-palette', handleCustomOpen);

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('open-aria-search', handleCustomOpen);
      window.removeEventListener('open-command-palette', handleCustomOpen);
    };
  }, [isOpen]);

  // Focus input when opened
  useEffect(() => {
    if (isOpen) {
      setQuery('');
      setSelectedIndex(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [isOpen]);

  const filtered = COMMANDS.filter((cmd) => {
    const q = query.toLowerCase();
    return (
      cmd.title.toLowerCase().includes(q) ||
      cmd.subtitle.toLowerCase().includes(q) ||
      cmd.category.toLowerCase().includes(q) ||
      (cmd.badge && cmd.badge.toLowerCase().includes(q))
    );
  });

  const handleSelect = (item: CommandItem) => {
    if (item.href) {
      window.location.href = item.href;
    }
    setIsOpen(false);
  };

  const handleInputKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex((prev) => (prev + 1) % Math.max(1, filtered.length));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex((prev) => (prev - 1 + filtered.length) % Math.max(1, filtered.length));
    } else if (e.key === 'Enter' && filtered[selectedIndex]) {
      e.preventDefault();
      handleSelect(filtered[selectedIndex]);
    }
  };

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-[999] flex items-start justify-center pt-[12vh] px-4 bg-[#030407]/80 backdrop-blur-xl animate-fade-in"
      onClick={() => setIsOpen(false)}
    >
      <div
        className="w-full max-w-2xl rounded-2xl bg-gradient-to-b from-[#0D1220]/95 to-[#070A12]/98 border border-white/[0.12] shadow-[0_24px_80px_rgba(0,0,0,0.9)] overflow-hidden font-mono"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header Search Input */}
        <div className="flex items-center gap-3 px-5 py-4 border-b border-white/[0.08] bg-[#050608]/60">
          <span className="text-indigo-400 font-bold text-base">⌕</span>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setSelectedIndex(0);
            }}
            onKeyDown={handleInputKeyDown}
            placeholder="Search commands, diagnostics, repository routes..."
            className="flex-1 bg-transparent text-sm text-white placeholder-[#64748B] focus:outline-none"
          />
          <span className="px-2 py-0.5 rounded text-[10px] bg-white/[0.06] text-[#94A3B8] border border-white/[0.06]">
            ESC to close
          </span>
        </div>

        {/* Results List */}
        <div className="max-h-[380px] overflow-y-auto p-2 space-y-1">
          {filtered.length === 0 ? (
            <div className="p-8 text-center text-xs text-[#64748B]">
              No matching commands or routes found for "{query}".
            </div>
          ) : (
            filtered.map((item, idx) => {
              const isSelected = idx === selectedIndex;
              return (
                <button
                  key={item.id}
                  onClick={() => handleSelect(item)}
                  onMouseEnter={() => setSelectedIndex(idx)}
                  className={`w-full text-left p-3 rounded-xl transition-all duration-150 flex items-center justify-between gap-4 ${
                    isSelected
                      ? 'bg-indigo-500/20 border border-indigo-500/40 text-white shadow-[0_0_16px_rgba(99,102,241,0.2)]'
                      : 'border border-transparent text-[#CBD5E1] hover:bg-white/[0.03]'
                  }`}
                >
                  <div className="min-w-0 flex items-center gap-3">
                    <span
                      className={`w-2 h-2 rounded-full shrink-0 ${
                        isSelected
                          ? 'bg-indigo-400 shadow-[0_0_8px_rgba(129,140,248,0.9)]'
                          : 'bg-white/20'
                      }`}
                    />
                    <div className="min-w-0">
                      <div className="text-xs font-semibold text-white truncate">
                        {item.title}
                      </div>
                      <div className="text-[10px] text-[#94A3B8] truncate mt-0.5">
                        {item.subtitle}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    {item.badge && (
                      <span className="px-2 py-0.5 rounded text-[9px] font-bold bg-white/[0.06] text-indigo-300 border border-white/[0.06]">
                        {item.badge}
                      </span>
                    )}
                    <span className="text-xs text-[#64748B]">→</span>
                  </div>
                </button>
              );
            })
          )}
        </div>

        {/* Footer Navigation Bar */}
        <div className="px-5 py-2.5 bg-[#050608]/80 border-t border-white/[0.06] flex items-center justify-between text-[10px] text-[#64748B]">
          <div className="flex items-center gap-3">
            <span>Use ↑↓ to navigate</span>
            <span>·</span>
            <span>↵ to select</span>
          </div>
          <span className="text-indigo-400 font-semibold">ARIA REPOSITORY INTELLIGENCE</span>
        </div>
      </div>
    </div>
  );
};

export default CommandPalette;
