import React, { useMemo, useState } from 'react';
import { Box, Search, ChevronRight, X, SearchX } from 'lucide-react';
import { EmptyState } from '../ui/EmptyState';
import { groupTech, TONE_CHIP, TONE_DOT, type TechCategory } from '../../lib/techCategories';

interface DependencyExplorerProps {
  dependencies: string[];
  className?: string;
}

/** Groups larger than this collapse by default. */
const AUTO_COLLAPSE_THRESHOLD = 12;
/** Items shown before the "show all" affordance inside an expanded group. */
const PREVIEW_COUNT = 24;

export const DependencyExplorer: React.FC<DependencyExplorerProps> = ({
  dependencies,
  className = '',
}) => {
  const [query, setQuery] = useState('');
  const [collapsedOverrides, setCollapsedOverrides] = useState<Record<string, boolean>>({});
  const [expandedAll, setExpandedAll] = useState<Record<string, boolean>>({});

  const allGroups = useMemo(() => groupTech(dependencies), [dependencies]);
  const totalCount = useMemo(
    () => allGroups.reduce((sum, group) => sum + group.items.length, 0),
    [allGroups],
  );

  const trimmedQuery = query.trim().toLowerCase();

  const visibleGroups = useMemo(() => {
    if (!trimmedQuery) return allGroups;
    return allGroups
      .map((group) => ({
        ...group,
        items: group.items.filter((item) => item.toLowerCase().includes(trimmedQuery)),
      }))
      .filter((group) => group.items.length > 0);
  }, [allGroups, trimmedQuery]);

  const matchCount = useMemo(
    () => visibleGroups.reduce((sum, group) => sum + group.items.length, 0),
    [visibleGroups],
  );

  /**
   * A group is collapsed when it is large, unless the user overrode it.
   * While searching, everything stays open so matches are never hidden.
   */
  const isCollapsed = (id: TechCategory, size: number): boolean => {
    if (trimmedQuery) return false;
    const override = collapsedOverrides[id];
    if (override !== undefined) return override;
    return size > AUTO_COLLAPSE_THRESHOLD;
  };

  const toggleGroup = (id: TechCategory, size: number) => {
    setCollapsedOverrides((prev) => ({ ...prev, [id]: !isCollapsed(id, size) }));
  };

  return (
    <section className={`min-w-0 ${className}`} aria-labelledby="dependencies-heading">
      {/* Header */}
      <div className="flex items-baseline justify-between gap-4 pb-3 hair-b">
        <h2 id="dependencies-heading" className="mono-label">
          DEPENDENCIES
        </h2>
        <span className="mono-detail shrink-0 tabular-nums" style={{ fontSize: 10 }}>
          {trimmedQuery
            ? `${matchCount} OF ${totalCount} MATCH`
            : `${totalCount} ${totalCount === 1 ? 'PACKAGE' : 'PACKAGES'}`}
        </span>
      </div>

      {totalCount === 0 ? (
        /* Compact empty state — the old one occupied a full card of dead space. */
        <div className="py-5">
          <p className="text-[13px] text-text-muted leading-relaxed max-w-md">
            No dependency manifest resolved.
          </p>

          <div className="mt-5">
            <span className="mono-label block mb-2.5">SUPPORTED MANIFESTS</span>
            <ul className="min-w-0">
              {[
                'package.json',
                'requirements.txt',
                'pyproject.toml',
                'go.mod',
                'Cargo.toml',
              ].map((manifest) => (
                <li
                  key={manifest}
                  className="font-mono text-[11px] text-text-subtle py-1.5 hair-t last:border-b last:border-white/[0.055] truncate"
                >
                  {manifest}
                </li>
              ))}
            </ul>
          </div>
        </div>
      ) : (
        <div className="space-y-4 mt-4">
          {/* Search */}
          <div className="relative">
            <label htmlFor="dependency-search" className="sr-only">
              Search dependencies
            </label>
            <span
              className="absolute inset-y-0 left-3 flex items-center text-text-subtle pointer-events-none"
              aria-hidden="true"
            >
              <Search className="h-3.5 w-3.5" />
            </span>
            <input
              id="dependency-search"
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Filter packages…"
              className="input pl-9 pr-9 text-xs py-1.5"
            />
            {query && (
              <button
                type="button"
                onClick={() => setQuery('')}
                aria-label="Clear dependency filter"
                className="absolute inset-y-0 right-2 flex items-center text-text-subtle hover:text-text
                           transition-colors focus-visible:outline-none focus-visible:shadow-ring rounded"
              >
                <X className="h-3.5 w-3.5" aria-hidden="true" />
              </button>
            )}
          </div>

          {/* Live region so screen readers hear filter results */}
          <p className="sr-only" role="status" aria-live="polite">
            {trimmedQuery
              ? `${matchCount} dependencies match ${query}`
              : `${totalCount} dependencies total`}
          </p>

          {visibleGroups.length === 0 ? (
            <EmptyState
              compact
              icon={<SearchX className="h-5 w-5" aria-hidden="true" />}
              title={`No packages match "${query}"`}
              description="Try a shorter fragment, or clear the filter to browse every category."
              action={
                <button type="button" onClick={() => setQuery('')} className="btn-ghost text-xs">
                  Clear filter
                </button>
              }
            />
          ) : (
            <div className="space-y-2 max-h-[28rem] overflow-y-auto pr-1 -mr-1">
              {visibleGroups.map(({ meta, items }) => {
                const collapsed = isCollapsed(meta.id, items.length);
                const showAll = expandedAll[meta.id] || items.length <= PREVIEW_COUNT;
                const shown = showAll ? items : items.slice(0, PREVIEW_COUNT);
                const panelId = `dependency-group-${meta.id}`;

                return (
                  <div key={meta.id} className="rounded-lg border border-border/60 bg-canvas/30">
                    <button
                      type="button"
                      onClick={() => toggleGroup(meta.id, items.length)}
                      aria-expanded={!collapsed}
                      aria-controls={panelId}
                      className="w-full flex items-center gap-2 px-3 py-2 text-left rounded-lg
                                 hover:bg-surface-2/60 transition-colors
                                 focus-visible:outline-none focus-visible:shadow-ring"
                    >
                      <ChevronRight
                        className={`h-3.5 w-3.5 shrink-0 text-text-subtle transition-transform duration-200 ${
                          collapsed ? '' : 'rotate-90'
                        }`}
                        aria-hidden="true"
                      />
                      <span
                        className={`h-1.5 w-1.5 rounded-full shrink-0 ${TONE_DOT[meta.tone]}`}
                        aria-hidden="true"
                      />
                      <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-text-muted">
                        {meta.label}
                      </span>
                      <span className="text-[10px] font-mono text-text-subtle">{items.length}</span>
                    </button>

                    {!collapsed && (
                      <div id={panelId} className="px-3 pb-3 pt-0.5 space-y-2">
                        <ul className="flex flex-wrap gap-1.5 list-none">
                          {shown.map((item) => (
                            <li key={item}>
                              <span
                                title={item}
                                className={`inline-block text-[10px] font-mono px-2 py-0.5 rounded border
                                            max-w-[16rem] truncate transition-colors duration-150
                                            hover:border-primary/50 ${TONE_CHIP[meta.tone]}`}
                              >
                                {item}
                              </span>
                            </li>
                          ))}
                        </ul>

                        {!showAll && (
                          <button
                            type="button"
                            onClick={() => setExpandedAll((prev) => ({ ...prev, [meta.id]: true }))}
                            className="text-[10px] font-mono text-primary hover:underline
                                       focus-visible:outline-none focus-visible:shadow-ring rounded"
                          >
                            Show all {items.length} packages
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </section>
  );
};

export default DependencyExplorer;
