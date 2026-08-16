import React from 'react';
import { ArrowUpRight } from 'lucide-react';
import type { ExampleRepo } from '../../lib/useRepoAnalysis';

/* ─────────────────────────────────────────────────────────────────────────────
 * SampleCodebases — chapter 11.
 *
 * Deliberately secondary to the input above it: three quiet rows separated by
 * hairlines, no card chrome, no accent fills. They are a shortcut, not a
 * competing call to action.
 * ────────────────────────────────────────────────────────────────────────── */

interface Props {
  repos: ExampleRepo[];
  disabled?: boolean;
  onSelect: (url: string) => void;
}

export const SampleCodebases: React.FC<Props> = ({ repos, disabled = false, onSelect }) => {
  if (repos.length === 0) return null;

  return (
    <section aria-label="Sample codebases">
      <div className="flex items-baseline justify-between mb-2">
        <span className="mono-label">SAMPLE CODEBASES</span>
        <span className="mono-detail" style={{ fontSize: 10 }}>
          Click to load
        </span>
      </div>

      <ul>
        {repos.slice(0, 3).map((repo) => (
          <li key={repo.name} className="hair-t last:border-b last:border-white/[0.055]">
            <button
              type="button"
              disabled={disabled}
              onClick={() => onSelect(repo.url)}
              className="group w-full text-left py-5 px-2 -mx-2 rounded flex flex-col sm:flex-row sm:items-baseline gap-2 sm:gap-6
                         transition-colors duration-300 disabled:opacity-40 disabled:cursor-not-allowed
                         focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary focus-visible:bg-white/[0.02]"
            >
              <span className="font-mono text-sm text-text sm:w-56 shrink-0 group-hover:text-primary transition-colors duration-300">
                {repo.name}
              </span>

              <span className="text-[13px] text-text-muted flex-1 min-w-0">
                {repo.description}
              </span>

              <span className="mono-detail sm:text-right shrink-0" style={{ fontSize: 10 }}>
                {repo.tech_stack.slice(0, 3).join(' · ')}
              </span>

              <ArrowUpRight
                className="hidden sm:block h-3.5 w-3.5 shrink-0 text-text-subtle
                           group-hover:text-primary group-hover:-translate-y-0.5 group-hover:translate-x-0.5
                           transition-all duration-300"
                aria-hidden="true"
              />
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
};

export default SampleCodebases;
