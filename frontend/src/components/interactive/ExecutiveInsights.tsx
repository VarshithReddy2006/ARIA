import React, { useMemo } from 'react';
import {
  ShieldCheck, Package, DoorOpen, Layers3, Clock, Boxes, Code2,
  RefreshCcwDot, FileText, FlaskConical, Globe,
  AlertTriangle, CheckCircle2, Info, XCircle,
} from 'lucide-react';
import { Reveal } from '../ui/Reveal';
import type { Insight, InsightIcon, InsightSeverity } from '../../lib/repoInsights';

interface ExecutiveInsightsProps {
  insights: Insight[];
  className?: string;
}

const ICONS: Record<InsightIcon, React.ComponentType<{ className?: string }>> = {
  architecture: ShieldCheck,
  dependency:   Package,
  entrypoint:   DoorOpen,
  scale:        Layers3,
  onboarding:   Clock,
  monorepo:     Boxes,
  language:     Code2,
  cycle:        RefreshCcwDot,
  docs:         FileText,
  tests:        FlaskConical,
  api:          Globe,
};

/** Severity drives the accent, the status glyph, and the screen-reader prefix. */
const SEVERITY: Record<InsightSeverity, {
  accent: string;
  rule: string;
  glyph: React.ComponentType<{ className?: string }>;
  srLabel: string;
}> = {
  good:    { accent: 'text-success',    rule: 'bg-success/50',  glyph: CheckCircle2,   srLabel: 'Healthy' },
  warn:    { accent: 'text-warn',       rule: 'bg-warn/60',     glyph: AlertTriangle,  srLabel: 'Needs attention' },
  risk:    { accent: 'text-danger',     rule: 'bg-danger/60',   glyph: XCircle,        srLabel: 'Risk' },
  neutral: { accent: 'text-text-muted', rule: 'bg-white/10',    glyph: Info,           srLabel: 'Informational' },
};

/**
 * Derived repository findings.
 *
 * Previously a horizontally-scrolling strip of fixed 19rem cards, which clipped
 * the final card at every desktop width. Now a responsive grid of hairline rows:
 * every finding is visible at once, nothing is cut off, and no scroll affordance
 * is needed. Risks and warnings still sort first.
 *
 * The derivation note is rendered inline as quiet metadata rather than in a
 * hover tooltip, so it is reachable without hovering and adds no focus traps.
 */
export const ExecutiveInsights: React.FC<ExecutiveInsightsProps> = ({ insights, className = '' }) => {
  const counts = useMemo(() => {
    const attention = insights.filter((i) => i.severity === 'warn' || i.severity === 'risk').length;
    return { attention, total: insights.length };
  }, [insights]);

  if (insights.length === 0) return null;

  return (
    <section className={className} aria-labelledby="executive-insights-heading">
      <div className="flex items-baseline justify-between gap-4 mb-1">
        <h2 id="executive-insights-heading" className="mono-label">
          REPOSITORY INSIGHTS
        </h2>
        <span className="mono-detail shrink-0" style={{ fontSize: 10 }}>
          {counts.attention > 0 ? (
            <>
              <span className="text-warn tabular-nums">
                {String(counts.attention).padStart(2, '0')}
              </span>
              <span className="text-text-subtle">
                {' '}/ {String(counts.total).padStart(2, '0')} NEED ATTENTION
              </span>
            </>
          ) : (
            <span className="text-success">
              {String(counts.total).padStart(2, '0')} FINDINGS · ALL HEALTHY
            </span>
          )}
        </span>
      </div>

      {/*
        Column count steps with width so five findings never overflow: one column
        on mobile, two on tablet, three at lg. Rows share hairlines, so a wrapped
        final item reads as part of the list rather than as a clipped card.
      */}
      <ul className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-x-8 list-none">
        {insights.map((insight, index) => {
          const Icon = ICONS[insight.icon] ?? Info;
          const tone = SEVERITY[insight.severity];
          const Glyph = tone.glyph;

          return (
            <Reveal
              key={insight.id}
              as="li"
              tabIndex={0}
              delay={Math.min(index * 55, 330)}
              className="spec-row spec-row--slide group relative flex items-start gap-3.5 py-4 hair-t min-w-0
                         focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary/40 rounded-sm"
            >
              {/* Severity rule — the only chrome each row gets */}
              <span
                className={`insight-rule absolute left-0 top-4 bottom-4 w-px ${tone.rule} transition-opacity duration-200 group-hover:opacity-100 group-focus-within:opacity-100`}
                aria-hidden="true"
              />

              <Icon className={`h-4 w-4 shrink-0 mt-0.5 ml-3 ${tone.accent} transition-all duration-200`} aria-hidden="true" />

              <div className="min-w-0 flex-1">
                <h3 className="flex items-center gap-1.5 text-[13px] font-semibold text-text transition-colors duration-200">
                  <span className="truncate">{insight.title}</span>
                  <Glyph className={`h-3 w-3 shrink-0 ${tone.accent}`} aria-hidden="true" />
                  <span className="sr-only">{tone.srLabel}.</span>
                </h3>

                <p className="text-xs text-text-muted leading-relaxed mt-1 break-words">
                  {insight.detail}
                </p>

                {/* Provenance — visible on hover/focus, always in the a11y tree */}
                <p className="mono-detail mt-2 leading-relaxed opacity-0 group-hover:opacity-100
                              group-focus-within:opacity-100 transition-opacity duration-200"
                   style={{ fontSize: 10 }}>
                  {insight.tooltip}
                </p>
              </div>
            </Reveal>
          );
        })}
      </ul>
    </section>
  );
};

export default ExecutiveInsights;
