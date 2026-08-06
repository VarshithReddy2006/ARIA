import React from 'react';
import { Sparkline } from './Sparkline';

type Tone = 'primary' | 'success' | 'warn' | 'danger' | 'info' | 'neutral';

interface MetricCardProps {
  icon: React.ReactNode;
  label: string;
  value: React.ReactNode;
  /** Small contextual suffix below the value (e.g. "+12 this PR", "2 cycles") */
  hint?: React.ReactNode;
  /** Secondary metadata line rendered under the hint (e.g. "2.1M LOC") */
  subHint?: React.ReactNode;
  /**
   * Dimmed provenance line pinned to the bottom of the card
   * (e.g. "Indexed 14 sec ago").
   */
  footnote?: React.ReactNode;
  /** Optional Badge node — usually for trend or status */
  trailing?: React.ReactNode;
  /** Real data series shown top-right as a compact profile */
  spark?: number[];
  /** Describes what `spark` plots — required for it to be meaningful, not decorative */
  sparkLabel?: string;
  tone?: Tone;
  /** When provided, makes the card a focusable button */
  onClick?: () => void;
  className?: string;
}

const toneIconClass: Record<Tone, string> = {
  primary: 'bg-primary/10 text-primary border-primary/30',
  success: 'bg-success/10 text-success border-success/30',
  warn:    'bg-warn/10 text-warn border-warn/30',
  danger:  'bg-danger/10 text-danger border-danger/30',
  info:    'bg-info/10 text-info border-info/30',
  neutral: 'bg-surface-2 text-text-muted border-border',
};

export const MetricCard: React.FC<MetricCardProps> = ({
  icon, label, value, hint, subHint, footnote, trailing, spark, sparkLabel,
  tone = 'primary', onClick, className = '',
}) => {
  const inner = (
    <>
      <div className="flex items-start gap-3.5">
        <div className={`p-2.5 border rounded-lg shrink-0 ${toneIconClass[tone]}`} aria-hidden="true">
          {icon}
        </div>

        <div className="min-w-0 flex-grow">
          <div className="flex items-start justify-between gap-2">
            <div className="text-[10px] uppercase tracking-wider font-mono font-semibold text-text-subtle">
              {label}
            </div>
            {spark && spark.length > 1 && (
              <span
                title={sparkLabel}
                className="shrink-0 opacity-60 transition-opacity duration-300 group-hover:opacity-100"
              >
                <Sparkline
                  data={spark}
                  tone={tone === 'neutral' ? 'neutral' : tone}
                  ariaLabel={sparkLabel}
                />
              </span>
            )}
          </div>

          <div className="flex items-baseline gap-2 mt-1">
            <div className="text-2xl font-extrabold text-text tracking-tight font-mono leading-none">
              {value}
            </div>
            {trailing}
          </div>

          {hint && <div className="text-[11px] text-text-muted mt-1.5 font-sans truncate">{hint}</div>}
          {subHint && <div className="text-[11px] text-text-muted font-sans truncate">{subHint}</div>}
        </div>
      </div>

      {footnote && (
        <div className="text-[10px] font-mono text-text-subtle mt-3 pt-2.5 border-t border-border/60 truncate">
          {footnote}
        </div>
      )}
    </>
  );

  const baseCls =
    'card p-4 flex flex-col group transition-all duration-200 ' +
    'hover:border-primary/40 hover:-translate-y-0.5 hover:shadow-raised';

  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        className={`${baseCls} text-left w-full focus-visible:outline-none focus-visible:shadow-ring ${className}`}
      >
        {inner}
      </button>
    );
  }

  return <div className={`${baseCls} ${className}`}>{inner}</div>;
};

export default MetricCard;
