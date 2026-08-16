import React from 'react';

interface Props {
  useUrl: boolean;
  setUseUrl: (v: boolean) => void;
  prUrl: string;
  setPrUrl: (v: string) => void;
  owner: string;
  setOwner: (v: string) => void;
  repo: string;
  setRepo: (v: string) => void;
  prNumber: string;
  setPrNumber: (v: string) => void;
  /** unique prefix so id attributes don't collide when both PR & Drift forms mount */
  idPrefix?: string;
}

/**
 * Shared PR reference input — used by PR Intelligence and Architecture Drift.
 * Owns: URL vs (owner/repo/number) toggle + labelled inputs.
 *
 * The mode toggle is a thin underlined rail matching the analysis tab rail, and
 * the fields are `console-field` surfaces so a pasted PR URL reads as input
 * rather than as a form widget. Roles, ids and state wiring are unchanged.
 */
export const PRReferenceForm: React.FC<Props> = ({
  useUrl, setUseUrl,
  prUrl, setPrUrl,
  owner, setOwner,
  repo, setRepo,
  prNumber, setPrNumber,
  idPrefix = 'pr',
}) => (
  <div className="flex flex-col gap-5 min-w-0">
    <div
      role="tablist"
      aria-label="Reference type"
      className="flex gap-6 border-b border-white/[0.055]"
    >
      {(['url', 'coords'] as const).map((k) => {
        const active = (k === 'url') === useUrl;
        return (
          <button
            key={k}
            role="tab"
            type="button"
            aria-selected={active}
            tabIndex={active ? 0 : -1}
            onClick={() => setUseUrl(k === 'url')}
            className={[
              'relative shrink-0 pb-2.5 pt-0.5',
              'font-mono text-[11px] uppercase tracking-[0.14em] whitespace-nowrap',
              'transition-colors duration-200 focus-visible:outline-none',
              'focus-visible:ring-1 focus-visible:ring-primary/40 rounded-sm',
              active ? 'text-white font-medium' : 'text-text-muted hover:text-text',
            ].join(' ')}
          >
            {k === 'url' ? 'PR URL' : 'Repository Coordinates'}
            {active && (
              <span
                className="absolute left-0 right-0 -bottom-px h-px bg-primary"
                aria-hidden="true"
              />
            )}
          </button>
        );
      })}
    </div>

    {useUrl ? (
      <Field id={`${idPrefix}-url`} label="GITHUB PULL REQUEST URL">
        <input
          id={`${idPrefix}-url`}
          type="text"
          className="console-field font-mono text-[11.5px]"
          placeholder="https://github.com/owner/repo/pull/123"
          value={prUrl}
          onChange={(e) => setPrUrl(e.target.value)}
        />
      </Field>
    ) : (
      <div className="grid grid-cols-1 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_6rem] gap-4 min-w-0">
        <Field id={`${idPrefix}-owner`} label="OWNER">
          <input
            id={`${idPrefix}-owner`}
            type="text"
            className="console-field font-mono text-[11.5px]"
            placeholder="VarshithReddy2006"
            value={owner}
            onChange={(e) => setOwner(e.target.value)}
          />
        </Field>
        <Field id={`${idPrefix}-repo`} label="REPOSITORY">
          <input
            id={`${idPrefix}-repo`}
            type="text"
            className="console-field font-mono text-[11.5px]"
            placeholder="Repo-Intelligence-Agent"
            value={repo}
            onChange={(e) => setRepo(e.target.value)}
          />
        </Field>
        <Field id={`${idPrefix}-number`} label="PR #">
          <input
            id={`${idPrefix}-number`}
            type="text"
            inputMode="numeric"
            className="console-field font-mono text-[11.5px] tabular-nums"
            placeholder="1"
            value={prNumber}
            onChange={(e) => setPrNumber(e.target.value)}
          />
        </Field>
      </div>
    )}
  </div>
);

const Field: React.FC<{ id: string; label: string; children: React.ReactNode }> = ({
  id, label, children,
}) => (
  <div className="flex flex-col gap-2 min-w-0">
    <label htmlFor={id} className="mono-label">
      {label}
    </label>
    {children}
  </div>
);

export default PRReferenceForm;
