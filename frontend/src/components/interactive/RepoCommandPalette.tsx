import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  Search, FileCode2, Box, Code2, BookOpen, Network, CornerDownLeft,
  ArrowUp, ArrowDown, Command, SearchX, Compass,
} from 'lucide-react';
import { fuzzyMatchBest } from '../../lib/fuzzy';

export interface CommandItem {
  id: string;
  label: string;
  sublabel?: string;
  group: string;
  icon: React.ComponentType<{ className?: string }>;
  /** Extra text folded into the search corpus but never displayed */
  keywords?: string;
  run: () => void;
}

interface RepoCommandPaletteProps {
  open: boolean;
  onClose: () => void;
  items: CommandItem[];
  /** Shown as the palette's context line, e.g. "owner/repo" */
  scopeLabel?: string;
}

/** Caps keep very large repositories responsive. */
const MAX_PER_GROUP = 8;
const MAX_TOTAL = 50;

/** Renders a label with fuzzy-matched characters emphasised. */
const Highlight: React.FC<{ text: string; positions: number[] }> = ({ text, positions }) => {
  if (positions.length === 0) return <>{text}</>;

  const set = new Set(positions);
  const parts: React.ReactNode[] = [];
  let buffer = '';
  let bufferMatched = set.has(0);

  const flush = (key: number) => {
    if (!buffer) return;
    parts.push(
      bufferMatched
        ? <mark key={key} className="bg-transparent text-primary font-semibold">{buffer}</mark>
        : <React.Fragment key={key}>{buffer}</React.Fragment>,
    );
    buffer = '';
  };

  for (let i = 0; i < text.length; i++) {
    const matched = set.has(i);
    if (matched !== bufferMatched) {
      flush(i);
      bufferMatched = matched;
    }
    buffer += text[i];
  }
  flush(text.length);

  return <>{parts}</>;
};

export const RepoCommandPalette: React.FC<RepoCommandPaletteProps> = ({
  open,
  onClose,
  items,
  scopeLabel,
}) => {
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);

  /** Ranked, capped, and grouped results. */
  const results = useMemo(() => {
    const trimmed = query.trim();

    const scored = items
      .map((item) => {
        if (!trimmed) return { item, score: 0, positions: [] as number[] };
        const match = fuzzyMatchBest(
          [
            { text: item.label, weight: 1 },
            { text: item.sublabel ?? '', weight: 0.6 },
            { text: item.keywords ?? '', weight: 0.35 },
          ],
          trimmed,
        );
        if (!match) return null;
        // Only highlight when the hit was on the visible label.
        return {
          item,
          score: match.score,
          positions: match.fieldIndex === 0 ? match.positions : [],
        };
      })
      .filter((entry): entry is { item: CommandItem; score: number; positions: number[] } => entry !== null);

    if (trimmed) scored.sort((a, b) => b.score - a.score);

    // Group while respecting per-group and overall caps.
    const groups: { name: string; entries: typeof scored }[] = [];
    const counts = new Map<string, number>();
    let total = 0;

    for (const entry of scored) {
      if (total >= MAX_TOTAL) break;
      const groupName = entry.item.group;
      const used = counts.get(groupName) ?? 0;
      if (used >= MAX_PER_GROUP) continue;

      counts.set(groupName, used + 1);
      total++;

      let group = groups.find((g) => g.name === groupName);
      if (!group) {
        group = { name: groupName, entries: [] };
        groups.push(group);
      }
      group.entries.push(entry);
    }

    const flat = groups.flatMap((g) => g.entries);
    return { groups, flat };
  }, [items, query]);

  // Reset transient state each time the palette opens.
  useEffect(() => {
    if (!open) return;
    restoreFocusRef.current = document.activeElement as HTMLElement | null;
    setQuery('');
    setActiveIndex(0);

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    // Defer so the input exists before we focus it.
    const raf = requestAnimationFrame(() => inputRef.current?.focus());

    return () => {
      cancelAnimationFrame(raf);
      document.body.style.overflow = previousOverflow;
      restoreFocusRef.current?.focus?.();
    };
  }, [open]);

  // Keep the highlighted row in view and within bounds.
  useEffect(() => {
    if (activeIndex >= results.flat.length) setActiveIndex(0);
  }, [results.flat.length, activeIndex]);

  useEffect(() => {
    const active = listRef.current?.querySelector('[data-active="true"]');
    active?.scrollIntoView({ block: 'nearest' });
  }, [activeIndex, query]);

  const runActive = useCallback(() => {
    const entry = results.flat[activeIndex];
    if (!entry) return;
    onClose();
    entry.item.run();
  }, [results.flat, activeIndex, onClose]);

  const handleKeyDown = (event: React.KeyboardEvent) => {
    const count = results.flat.length;

    switch (event.key) {
      case 'Escape':
        event.preventDefault();
        onClose();
        break;
      case 'ArrowDown':
        event.preventDefault();
        if (count) setActiveIndex((i) => (i + 1) % count);
        break;
      case 'ArrowUp':
        event.preventDefault();
        if (count) setActiveIndex((i) => (i - 1 + count) % count);
        break;
      case 'Home':
        event.preventDefault();
        setActiveIndex(0);
        break;
      case 'End':
        event.preventDefault();
        if (count) setActiveIndex(count - 1);
        break;
      case 'Enter':
        event.preventDefault();
        runActive();
        break;
      case 'Tab':
        // Nothing else is focusable inside; keep focus in the palette.
        event.preventDefault();
        break;
      default:
        break;
    }
  };

  if (!open || typeof document === 'undefined') return null;

  let flatIndex = -1;

  return createPortal(
    <div
      className="fixed inset-0 z-[100] flex items-start justify-center px-4 pt-[10vh] sm:pt-[14vh]"
      role="dialog"
      aria-modal="true"
      aria-label="Repository command palette"
    >
      {/* Backdrop */}
      <button
        type="button"
        aria-label="Close command palette"
        onClick={onClose}
        className="absolute inset-0 bg-canvas/80 backdrop-blur-sm cursor-default"
        tabIndex={-1}
      />

      {/* Panel */}
      <div
        className="relative w-full max-w-2xl rounded-2xl border border-border-strong bg-surface-1
                   shadow-float overflow-hidden fade-up"
        onKeyDown={handleKeyDown}
      >
        {/* Search row */}
        <div className="flex items-center gap-3 px-4 py-3.5 border-b border-border">
          <Search className="h-4 w-4 text-text-subtle shrink-0" aria-hidden="true" />
          <input
            ref={inputRef}
            type="text"
            role="combobox"
            aria-expanded="true"
            aria-controls="command-palette-list"
            aria-autocomplete="list"
            aria-activedescendant={
              results.flat[activeIndex] ? `command-option-${results.flat[activeIndex].item.id}` : undefined
            }
            autoComplete="off"
            spellCheck={false}
            value={query}
            onChange={(event) => { setQuery(event.target.value); setActiveIndex(0); }}
            placeholder="Search files, dependencies, and destinations…"
            className="flex-grow bg-transparent border-0 outline-none text-sm font-sans
                       text-text placeholder:text-text-subtle min-w-0"
          />
          {scopeLabel && (
            <span className="hidden sm:inline shrink-0 text-[10px] font-mono text-text-subtle
                             border border-border rounded px-1.5 py-0.5 max-w-[14rem] truncate">
              {scopeLabel}
            </span>
          )}
        </div>

        {/* Results */}
        <div
          ref={listRef}
          id="command-palette-list"
          role="listbox"
          aria-label="Command results"
          className="max-h-[min(24rem,60vh)] overflow-y-auto py-2"
        >
          {results.flat.length === 0 ? (
            <div className="px-4 py-10 flex flex-col items-center gap-3 text-center">
              <div className="h-10 w-10 rounded-full border border-border bg-surface-2/50
                              flex items-center justify-center text-text-muted" aria-hidden="true">
                <SearchX className="h-4 w-4" />
              </div>
              <div className="space-y-1">
                <p className="text-sm font-semibold text-text">No matches for "{query}"</p>
                <p className="text-xs text-text-muted max-w-xs leading-relaxed">
                  Try a file name, a package, or a destination like "reading path" or "health".
                </p>
              </div>
            </div>
          ) : (
            results.groups.map((group) => (
              <div key={group.name} role="group" aria-labelledby={`command-group-${group.name}`}>
                <div
                  id={`command-group-${group.name}`}
                  className="px-4 pt-2.5 pb-1 text-[10px] font-mono font-bold uppercase
                             tracking-wider text-text-subtle"
                >
                  {group.name}
                </div>

                {group.entries.map(({ item, positions }) => {
                  flatIndex++;
                  const isActive = flatIndex === activeIndex;
                  const rowIndex = flatIndex;
                  const Icon = item.icon;

                  return (
                    <div
                      key={item.id}
                      id={`command-option-${item.id}`}
                      role="option"
                      aria-selected={isActive}
                      data-active={isActive}
                      onMouseMove={() => setActiveIndex(rowIndex)}
                      onClick={() => { onClose(); item.run(); }}
                      className={`mx-2 px-2.5 py-2 rounded-lg flex items-center gap-3 cursor-pointer
                                  transition-colors duration-100 ${
                                    isActive ? 'bg-primary/10 border border-primary/30' : 'border border-transparent'
                                  }`}
                    >
                      <Icon
                        className={`h-4 w-4 shrink-0 ${isActive ? 'text-primary' : 'text-text-subtle'}`}
                      />
                      <div className="min-w-0 flex-grow">
                        <div className="text-sm text-text truncate font-mono">
                          <Highlight text={item.label} positions={positions} />
                        </div>
                        {item.sublabel && (
                          <div className="text-[11px] text-text-muted truncate font-sans">
                            {item.sublabel}
                          </div>
                        )}
                      </div>
                      {isActive && (
                        <CornerDownLeft className="h-3.5 w-3.5 text-primary shrink-0" aria-hidden="true" />
                      )}
                    </div>
                  );
                })}
              </div>
            ))
          )}
        </div>

        {/* Footer hints */}
        <div className="flex items-center justify-between gap-3 px-4 py-2.5 border-t border-border bg-canvas/50">
          <div className="flex items-center gap-3 text-[10px] font-mono text-text-subtle">
            <span className="flex items-center gap-1">
              <ArrowUp className="h-3 w-3" aria-hidden="true" />
              <ArrowDown className="h-3 w-3" aria-hidden="true" />
              navigate
            </span>
            <span className="flex items-center gap-1">
              <CornerDownLeft className="h-3 w-3" aria-hidden="true" />
              open
            </span>
            <span className="hidden sm:flex items-center gap-1">
              <kbd className="border border-border rounded px-1 bg-surface-2">esc</kbd>
              close
            </span>
          </div>
          <span className="text-[10px] font-mono text-text-subtle">
            {results.flat.length} {results.flat.length === 1 ? 'result' : 'results'}
          </span>
        </div>
      </div>
    </div>,
    document.body,
  );
};

/** Icon set exported so callers build items without importing lucide directly. */
export const COMMAND_ICONS = {
  file: FileCode2,
  dependency: Box,
  tech: Code2,
  reading: BookOpen,
  component: Network,
  navigate: Compass,
  command: Command,
} as const;

export default RepoCommandPalette;
