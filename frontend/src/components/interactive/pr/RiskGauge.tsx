import React from 'react';

interface Props {
  /** 0-100 score */
  score: number;
  /** Visible label above the ring (e.g. "ARCHITECTURE RISK") */
  label: string;
  /** Optional level text rendered as the aria-label suffix and visible under the ring */
  level?: string;
  /** Tailwind text class for the level line. */
  levelTone?: string;
  /** Override stroke color — default derives from score */
  stroke?: string;
  caption?: React.ReactNode;
}

const RADIUS = 46;
const CIRC = 2 * Math.PI * RADIUS;

function scoreColor(score: number): string {
  if (score > 75) return '#ef4444';
  if (score > 50) return '#f97316';
  if (score > 25) return '#eab308';
  return '#10b981';
}

/**
 * Accessible score ring, sized to anchor a diagnostic band rather than to fill a
 * KPI card. No container, no centring and no padding of its own — the caller
 * places it, so the same gauge works beside a signal list on PR Risk and beside
 * a second gauge on PR Drift.
 *
 * Score thresholds and colour mapping are unchanged.
 */
export const RiskGauge: React.FC<Props> = ({
  score, label, level, levelTone = 'text-text-muted', stroke, caption,
}) => {
  const clamped = Math.max(0, Math.min(100, Math.round(score)));
  const color = stroke ?? scoreColor(clamped);

  return (
    <div className="flex items-center gap-5 min-w-0">
      <div
        role="img"
        aria-label={`${label}: ${clamped} of 100${level ? `, ${level}` : ''}`}
        className="relative h-[104px] w-[104px] shrink-0"
      >
        <svg className="h-full w-full -rotate-90" viewBox="0 0 104 104">
          <circle
            cx="52" cy="52" r={RADIUS}
            stroke="rgba(255,255,255,0.07)" strokeWidth="6" fill="transparent"
          />
          <circle
            cx="52" cy="52" r={RADIUS}
            stroke={color} strokeWidth="6" fill="transparent"
            strokeLinecap="round"
            strokeDasharray={CIRC}
            strokeDashoffset={CIRC - (CIRC * clamped) / 100}
            className="transition-[stroke-dashoffset] duration-700 ease-out motion-reduce:transition-none"
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="font-mono text-[26px] font-semibold text-text tabular-nums leading-none">
            {clamped}
          </span>
          <span className="mono-label mt-1" style={{ fontSize: 9 }}>
            / 100
          </span>
        </div>
      </div>

      <div className="min-w-0">
        <span className="mono-label block mb-2">{label}</span>
        {level && (
          <span
            className={`block font-mono text-[13px] uppercase tracking-[0.14em] ${levelTone}`}
          >
            {level}
          </span>
        )}
        {caption}
      </div>
    </div>
  );
};

export default RiskGauge;
