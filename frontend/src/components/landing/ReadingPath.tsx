import React from 'react';
import { useScrollDriver } from './hooks';
import { READING_PATH } from './data';

/* ─────────────────────────────────────────────────────────────────────────────
 * ReadingPath — chapter 06.
 *
 * A centrality-ranked sequence, and the reason the ranking exists.
 *
 * The rows are a fixed-height list: emphasis is carried entirely by colour and
 * weight, never by size or padding, so advancing the active item cannot shift
 * anything below it. The commentary for the active step lives in the rail on the
 * left instead of expanding inline, which is what used to cause the jump.
 * ────────────────────────────────────────────────────────────────────────── */

export const ReadingPath: React.FC = () => {
  const { ref, step } = useScrollDriver<HTMLDivElement>({
    from: 0.16,
    to: 0.72,
    steps: READING_PATH.length,
  });

  const active = READING_PATH[step];
  const totalMinutes = READING_PATH.reduce((sum, s) => sum + s.minutes, 0);

  return (
    <div ref={ref} className="grid grid-cols-1 lg:grid-cols-12 gap-10 lg:gap-14">
      {/* ── Rail: why the order exists, and where we are in it ───────────── */}
      <div className="lg:col-span-4 lg:sticky lg:top-24 lg:self-start">
        <p className="text-[13px] text-text-muted leading-relaxed max-w-sm">
          Start where the architecture says the code matters most — not at the top of the
          alphabet.
        </p>

        <div className="mt-8 flex items-baseline gap-2">
          <span className="font-mono text-4xl text-text tabular-nums leading-none">
            {String(step + 1).padStart(2, '0')}
          </span>
          <span className="mono-detail">/ {String(READING_PATH.length).padStart(2, '0')}</span>
          <span className="mono-detail ml-auto">~{totalMinutes} MIN TOTAL</span>
        </div>

        {/* Progress rail — height driven by --p */}
        <div className="mt-5 h-[3px] w-full bg-white/[0.07] relative overflow-hidden">
          <span
            className="absolute left-0 top-0 h-full w-full origin-left bg-primary"
            style={{ transform: 'scaleX(var(--p, 0))' }}
            aria-hidden="true"
          />
        </div>

        {/*
          Commentary for the active step. Height is reserved so switching steps
          never reflows the rail or the list beside it.
        */}
        <div className="mt-8 min-h-[7.5rem] sm:min-h-[6.5rem]" aria-live="polite">
          <span className="mono-label mono-label-accent block mb-3">{active.role}</span>
          <p className="text-[13px] text-text leading-relaxed max-w-sm">{active.note}</p>
          <p className="mono-detail mt-3" style={{ fontSize: 10 }}>
            PAGERANK {active.rank.toFixed(2)} · ~{active.minutes} MIN
          </p>
        </div>

        <p className="mono-label mt-2" style={{ letterSpacing: '0.2em' }}>
          ILLUSTRATIVE RANKING
        </p>
      </div>

      {/* ── The route ────────────────────────────────────────────────────────
          Not a list of files: a way through the repository. A faint route runs
          down the left edge, each segment lighting as the reader reaches it, with
          a marker on every stop. The reader should come away feeling ARIA knows
          where to start, which a plain ranked list does not communicate.
      --------------------------------------------------------------------- */}
      <ol className="lg:col-span-8">
        {READING_PATH.map((s, i) => {
          const isActive = i === step;
          const isPast = i < step;
          const isReached = i <= step;
          const isLast = i === READING_PATH.length - 1;

          return (
            <li key={s.index} className="hair-t last:border-b last:border-white/[0.055]">
              <div
                className="relative flex items-center gap-4 sm:gap-6 py-6 sm:py-7"
                style={{
                  opacity: isActive ? 1 : isPast ? 0.55 : 0.6,
                  transition: 'opacity 600ms cubic-bezier(0.16,1,0.3,1)',
                }}
              >
                {/* Route: the resting path, always present so the shape reads */}
                {!isLast && (
                  <span
                    className="absolute left-[4px] top-1/2 bottom-0 w-px bg-white/[0.07]"
                    aria-hidden="true"
                  />
                )}
                {/* Route: the travelled segment, drawn on arrival */}
                {!isLast && (
                  <span
                    className={`route-seg absolute left-[4px] top-1/2 bottom-0 w-px ${isPast ? 'is-lit' : ''
                      }`}
                    style={{ backgroundColor: isPast ? 'var(--primary)' : 'rgba(94,106,210,0.4)' }}
                    aria-hidden="true"
                  />
                )}

                {/* Stop marker on the route */}
                <span
                  className="absolute left-0 top-1/2 -translate-y-1/2 h-[9px] w-[9px] rounded-full border"
                  style={{
                    borderColor: isReached ? 'var(--primary)' : 'rgba(255,255,255,0.16)',
                    backgroundColor: isActive ? 'var(--primary)' : 'var(--canvas)',
                    boxShadow: isActive ? '0 0 14px 2px rgba(94,106,210,0.45)' : 'none',
                    transition:
                      'background-color 500ms ease, border-color 500ms ease, box-shadow 500ms ease',
                  }}
                  aria-hidden="true"
                />

                <span
                  className={`font-mono text-sm tabular-nums shrink-0 pl-6 sm:pl-7 transition-colors duration-500 ${isActive ? 'text-primary' : 'text-text-subtle'
                    }`}
                >
                  {s.index}
                </span>

                <div className="min-w-0 flex-1">
                  <p
                    className={`font-mono text-[13px] sm:text-[15px] leading-snug transition-colors duration-500 ${
                      isActive ? 'text-text' : 'text-text-muted'
                    }`}
                    style={{
                      fontWeight: isActive ? 600 : 400,
                      wordBreak: 'break-word',
                      overflowWrap: 'anywhere',
                    }}
                  >
                    {s.path.includes('/') ? (
                      <>
                        <span className="text-text-subtle/70">{s.path.slice(0, s.path.lastIndexOf('/') + 1)}</span>
                        <span>{s.path.slice(s.path.lastIndexOf('/') + 1)}</span>
                      </>
                    ) : (
                      s.path
                    )}
                  </p>
                  <span className="mono-label mt-2 flex items-center gap-3">
                    <span>{s.role}</span>
                    {/*
                      The estimate belongs to the stop, and arrives with it —
                      reserved inline so appearing never reflows the row.
                    */}
                    <span
                      className="mono-label-accent"
                      style={{
                        opacity: isActive ? 1 : 0,
                        transition: 'opacity 500ms ease',
                      }}
                    >
                      ~{s.minutes} MIN
                    </span>
                  </span>
                </div>

                <div className="shrink-0 w-16 sm:w-28 text-right">
                  <span
                    className={`font-mono text-sm tabular-nums transition-colors duration-500 ${isActive ? 'text-text' : 'text-text-subtle'
                      }`}
                  >
                    {s.rank.toFixed(2)}
                  </span>
                  <span
                    className="mt-2 hidden sm:block h-[2px] w-full bg-white/[0.06] overflow-hidden"
                    aria-hidden="true"
                  >
                    <span
                      className={`block h-full origin-left transition-colors duration-500 ${isActive ? 'bg-primary' : 'bg-white/20'
                        }`}
                      style={{
                        transform: `scaleX(${s.rank})`,
                        transition: 'transform 900ms cubic-bezier(0.16,1,0.3,1)',
                      }}
                    />
                  </span>
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
};

export default ReadingPath;
