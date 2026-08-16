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
  primary: 'bg-primary/10 text-primary border-primary/25',
  success: 'bg-success/10 text-success border-success/25',
  warn:    'bg-warn/10 text-warn border-warn/25',
  danger:  'bg-danger/10 text-danger border-danger/25',
  info:    'bg-info/10 text-info border-info/25',
  neutral: 'bg-surface-2 text-text-muted border-white/[0.06]',
};

export const MetricCard: React.FC<MetricCardProps> = ({
  icon, label, value, hint, subHint, footnote, trailing, spark, sparkLabel,
  tone = 'primary', onClick, className = '',
}) => {
  const inner = (
    <>
      <div className="flex items-start gap-3">
        <div className={`p-2 border rounded shrink-0 ${toneIconClass[tone]}`} aria-hidden="true">
          {icon}
        </div>

        <div className="min-w-0 flex-grow space-y-1">
          <div className="flex items-start justify-between gap-2">
            <div className="text-[10px] uppercase tracking-wider font-mono font-medium text-text-subtle">
              {label}
            </div>
            {spark && spark.length > 1 && (
              <span
                title={sparkLabel}
                className="shrink-0 opacity-50 transition-opacity duration-200 group-hover:opacity-90"
              >
                <Sparkline
                  data={spark}
                  tone={tone === 'neutral' ? 'neutral' : tone}
                  ariaLabel={sparkLabel}
                />
              </span>
            )}
          </div>

          <div className="flex items-baseline gap-2">
            <div className="text-xl font-bold text-text font-mono leading-none">
              {value}
            </div>
            {trailing}
          </div>

          {hint && <div className="text-[10px] text-text-muted font-sans truncate">{hint}</div>}
          {subHint && <div className="text-[10px] text-text-subtle font-sans truncate">{subHint}</div>}
        </div>
      </div>

      {footnote && (
        <div className="text-[9px] font-mono text-text-subtle mt-2.5 pt-2 border-t border-white/[0.04] truncate">
          {footnote}
        </div>
      )}
    </>
  );

  const baseCls =
    'card p-3.5 flex flex-col group transition-all duration-200 ' +
    'hover:border-primary/30 hover:bg-surface-2';

  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        className={`${baseCls} text-left w-full focus-visible:outline-none ${className}`}
      >
        {inner}
      </button>
    );
  }

  return <div className={`${baseCls} ${className}`}>{inner}</div>;
};

export default MetricCard;
