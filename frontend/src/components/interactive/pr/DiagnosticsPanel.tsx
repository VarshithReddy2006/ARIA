import React from 'react';
import type { HealthStatus } from './usePrerequisites';
import { LeaderRow, StatusText } from './instrument';

interface Props {
  title?: string;
  healthStatus: HealthStatus | null;
  description?: string;
  showSymbolIndex?: boolean;
}

/**
 * Shared diagnostics readout — used by PR Intelligence and Architecture Drift.
 *
 * A hairline label→value readout rather than a card of badges. Each reading
 * reports only what `usePrerequisites` actually returns: an absent rate limit
 * shows NOT AVAILABLE rather than implying a healthy quota, and nothing here
 * claims security or performance state.
 */
export const DiagnosticsPanel: React.FC<Props> = ({
  title = 'DIAGNOSTICS',
  healthStatus,
  description,
  showSymbolIndex = true,
}) => {
  const rateLimit = healthStatus?.rate_limit_remaining;
  const hasRateLimit = rateLimit !== undefined && rateLimit !== null;

  return (
    <div className="min-w-0">
      <h3 className="mono-label pb-3 hair-b">{title}</h3>

      <dl className="mt-1 min-w-0">
        <LeaderRow label="GITHUB TOKEN" first>
          {healthStatus?.github_token ? (
            <StatusText tone="text-success">ACTIVE</StatusText>
          ) : (
            <StatusText tone="text-danger">INACTIVE</StatusText>
          )}
        </LeaderRow>

        <LeaderRow label="GITHUB RATE LIMIT">
          {hasRateLimit ? (
            <span className="font-mono text-[11px] text-text tabular-nums">
              {rateLimit}
              <span className="text-text-subtle"> left</span>
            </span>
          ) : (
            <StatusText tone="text-text-subtle">NOT AVAILABLE</StatusText>
          )}
        </LeaderRow>

        <LeaderRow label="DEPENDENCY GRAPH">
          {healthStatus?.graph_available ? (
            <StatusText tone="text-success">AVAILABLE</StatusText>
          ) : (
            <StatusText tone="text-text-subtle">UNAVAILABLE</StatusText>
          )}
        </LeaderRow>

        {showSymbolIndex && (
          <LeaderRow label="SYMBOL INDEX">
            {healthStatus?.symbol_index_available ? (
              <StatusText tone="text-success">AVAILABLE</StatusText>
            ) : (
              <StatusText tone="text-text-subtle">UNAVAILABLE</StatusText>
            )}
          </LeaderRow>
        )}
      </dl>

      {description && (
        <p className="text-[12px] text-text-subtle leading-relaxed mt-5 max-w-sm">
          {description}
        </p>
      )}
    </div>
  );
};

export default DiagnosticsPanel;
