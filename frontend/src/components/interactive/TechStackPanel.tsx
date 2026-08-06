import React, { useMemo } from 'react';
import { Code2 } from 'lucide-react';
import { EmptyState } from '../ui/EmptyState';
import { groupTech, TONE_CHIP, TONE_DOT } from '../../lib/techCategories';

interface TechStackPanelProps {
  techStack: string[];
  className?: string;
}

/**
 * Renders the detected stack grouped by architectural category instead of a
 * single undifferentiated chip cloud, so the reader can tell backend from
 * frontend from data layer at a glance.
 */
export const TechStackPanel: React.FC<TechStackPanelProps> = ({ techStack, className = '' }) => {
  const groups = useMemo(() => groupTech(techStack), [techStack]);
  const total = useMemo(
    () => groups.reduce((sum, group) => sum + group.items.length, 0),
    [groups],
  );

  return (
    <div className={`card p-5 space-y-5 ${className}`}>
      <div className="flex items-center justify-between gap-3">
        <h2 className="panel-title">
          <Code2 className="h-4 w-4 text-primary" aria-hidden="true" /> Technology Stack
        </h2>
        {total > 0 && (
          <span className="text-[10px] font-mono text-text-subtle shrink-0">
            {total} {total === 1 ? 'technology' : 'technologies'} · {groups.length}{' '}
            {groups.length === 1 ? 'category' : 'categories'}
          </span>
        )}
      </div>

      {groups.length === 0 ? (
        <EmptyState
          compact
          icon={<Code2 className="h-5 w-5" aria-hidden="true" />}
          title="No technologies detected"
          description="The indexer did not find recognisable framework or language manifests in this repository."
          secondaryHelp="Manifests such as package.json, pyproject.toml, go.mod, or Cargo.toml improve detection."
        />
      ) : (
        <div className="space-y-4">
          {groups.map(({ meta, items }) => (
            <div key={meta.id} className="space-y-2">
              <div className="flex items-center gap-2">
                <span
                  className={`h-1.5 w-1.5 rounded-full shrink-0 ${TONE_DOT[meta.tone]}`}
                  aria-hidden="true"
                />
                <h3 className="text-[10px] font-mono font-bold uppercase tracking-wider text-text-muted">
                  {meta.label}
                </h3>
                <span className="text-[10px] font-mono text-text-subtle">{items.length}</span>
                <span className="sr-only">{meta.description}</span>
              </div>

              <ul className="flex flex-wrap gap-1.5 list-none pl-3.5">
                {items.map((item) => (
                  <li key={item}>
                    <span
                      className={`inline-block text-xs font-mono px-2.5 py-1 rounded-md border
                                  transition-colors duration-150 hover:border-primary/50 ${TONE_CHIP[meta.tone]}`}
                    >
                      {item}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default TechStackPanel;
