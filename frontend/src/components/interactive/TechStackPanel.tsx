import React, { useMemo } from 'react';
import { groupTech, TONE_DOT } from '../../lib/techCategories';

interface TechStackPanelProps {
  techStack: string[];
  className?: string;
}

/**
 * Detected stack as an engineering specification.
 *
 * Numbered hairline rows grouped by architectural category, instead of a cloud
 * of pills — the reader can still tell backend from frontend from data layer,
 * but the section reads as a spec sheet rather than as decoration.
 */
export const TechStackPanel: React.FC<TechStackPanelProps> = ({ techStack, className = '' }) => {
  const groups = useMemo(() => groupTech(techStack), [techStack]);
  const total = useMemo(() => groups.reduce((sum, g) => sum + g.items.length, 0), [groups]);

  return (
    <section className={`min-w-0 ${className}`} aria-labelledby="tech-stack-heading">
      <div className="flex items-baseline justify-between gap-4 pb-3 hair-b">
        <h2 id="tech-stack-heading" className="mono-label">
          TECHNOLOGY STACK
        </h2>
        {total > 0 && (
          <span className="mono-detail shrink-0 tabular-nums" style={{ fontSize: 10 }}>
            {total} DETECTED · {groups.length}{' '}
            {groups.length === 1 ? 'CATEGORY' : 'CATEGORIES'}
          </span>
        )}
      </div>

      {groups.length === 0 ? (
        <div className="py-5">
          <p className="text-[13px] text-text-muted leading-relaxed">
            No technologies detected. The indexer found no recognisable framework or language
            manifests.
          </p>
          <p className="mono-detail mt-2.5" style={{ fontSize: 10 }}>
            Detection improves with package.json · pyproject.toml · go.mod · Cargo.toml
          </p>
        </div>
      ) : (
        <div className="mt-1">
          {groups.map(({ meta, items }) => (
            <div key={meta.id} className="min-w-0">
              <div className="flex items-center gap-2 pt-4 pb-1.5">
                <span
                  className={`h-1 w-1 rounded-full shrink-0 ${TONE_DOT[meta.tone]}`}
                  aria-hidden="true"
                />
                <h3 className="mono-label">{meta.label}</h3>
                <span className="mono-detail tabular-nums" style={{ fontSize: 10 }}>
                  · {String(items.length).padStart(2, '0')}
                </span>
                <span className="sr-only">{meta.description}</span>
              </div>

              <ol className="min-w-0">
                {items.map((item, i) => (
                  <li
                    key={item}
                    className="spec-row group flex items-baseline gap-3.5 py-2 hair-t min-w-0"
                  >
                    <span className="font-mono text-[11px] text-text-muted/80 group-hover:text-primary shrink-0 tabular-nums transition-colors" style={{ letterSpacing: '0.14em' }}>
                      {String(i + 1).padStart(2, '0')}
                    </span>
                    <span className="font-mono text-[12px] text-text-muted group-hover:text-text truncate transition-colors">{item}</span>
                  </li>
                ))}
              </ol>
            </div>
          ))}
        </div>
      )}
    </section>
  );
};

export default TechStackPanel;
