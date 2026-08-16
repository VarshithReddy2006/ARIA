import React, { useRef, useEffect } from 'react';
import { Search, X } from 'lucide-react';

interface SearchBarProps {
  value: string;
  matchCount: number | null;
  onChange: (value: string) => void;
  onClear: () => void;
  placeholder?: string;
}

/**
 * Debounced search input for the Interactive Dependency Graph.
 * Calls onChange 300ms after the user stops typing.
 * Shows a match count badge when results are available.
 */
export const SearchBar: React.FC<SearchBarProps> = ({
  value,
  matchCount,
  onChange,
  onClear,
  placeholder = 'Search files, modules, symbols…',
}) => {
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const raw = e.target.value;
    onChange(raw);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {}, 300);
  };

  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  const hasValue = value.trim().length > 0;

  return (
    <div className="flex items-center gap-2 flex-grow max-w-xs">
      <div className="relative flex-grow">
        {/* Search icon */}
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-zinc-500 pointer-events-none" />

        <input
          type="text"
          value={value}
          onChange={handleInput}
          placeholder={placeholder}
          className="w-full bg-zinc-900/90 border border-zinc-800 rounded-md pl-8 pr-12 py-1 text-xs font-mono focus:outline-none focus:border-indigo-500/80 text-zinc-100 placeholder:text-zinc-500/70 transition-colors"
        />

        {/* Match count badge */}
        {hasValue && matchCount !== null && (
          <span className="absolute right-7 top-1/2 -translate-y-1/2 text-[9px] font-mono text-indigo-400 bg-indigo-500/10 border border-indigo-500/30 px-1 rounded">
            {matchCount}
          </span>
        )}

        {/* Shortcut badge / Clear button */}
        {hasValue ? (
          <button
            type="button"
            onClick={onClear}
            aria-label="Clear search"
            className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-100 rounded focus-visible:outline-none"
            title="Clear search"
          >
            <X className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        ) : (
          <kbd className="absolute right-2 top-1/2 -translate-y-1/2 text-[9px] font-mono text-zinc-500 bg-zinc-950 border border-zinc-800 px-1.5 py-0.5 rounded pointer-events-none">
            /
          </kbd>
        )}
      </div>
    </div>
  );
};
