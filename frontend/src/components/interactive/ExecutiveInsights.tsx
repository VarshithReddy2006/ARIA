import React, { useMemo, useRef, useState } from 'react';
import {
  ShieldCheck, Package, DoorOpen, Layers3, Clock, Boxes, Code2,
  RefreshCcwDot, FileText, FlaskConical, Globe, Sparkles,
  ChevronLeft, ChevronRight, AlertTriangle, CheckCircle2, Info, XCircle,
} from 'lucide-react';
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
  ring: string;
  iconWrap: string;
  glyph: React.ComponentType<{ className?: string }>;
  glyphColor: string;
  srLabel: string;
}> = {
  good: {
    ring: 'hover:border-success/40',
    iconWrap: 'border-success/30 bg-success/10 text-success',
    glyph: CheckCircle2,
    glyphColor: 'text-success',
    srLabel: 'Healthy',
  },
  warn: {
    ring: 'hover:border-warn/40',
    iconWrap: 'border-warn/30 bg-warn/10 text-warn',
    glyph: AlertTriangle,
    glyphColor: 'text-warn',
    srLabel: 'Needs attention',
  },
  risk: {
    ring: 'hover:border-danger/40',
    iconWrap: 'border-danger/30 bg-danger/10 text-danger',
    glyph: XCircle,
    glyphColor: 'text-danger',
    srLabel: 'Risk',
  },
  neutral: {
    ring: 'hover:border-primary/40',
    iconWrap: 'border-border bg-surface-2 text-text-muted',
    glyph: Info,
    glyphColor: 'text-text-muted',
    srLabel: 'Informational',
  },
};

const InsightCard: React.FC<{ insight: Insight; index: number }> = ({ insight, index }) => {
  const Icon = ICONS[insight.icon] ?? Info;
  const tone = SEVERITY[insight.severity];
  const Glyph = tone.glyph;

  return (
    <li
      className={`group relative shrink-0 w-[19rem] snap-start card p-4 fade-up
                  transition-all duration-200 hover:-translate-y-0.5 hover:shadow-raised ${tone.ring}`}
      // Stagger the entrance so the strip resolves left-to-right.
      style={{ animationDelay: `${Math.min(index * 45, 360)}ms` }}
    >
      <div className="flex items-start gap-3">
        <div className={`h-9 w-9 shrink-0 rounded-lg border flex items-center justify-center ${tone.iconWrap}`} aria-hidden="true">
          <Icon className="h-4 w-4" />
        </div>

        <div className="min-w-0 flex-grow">
          <div className="flex items-center gap-1.5">
            <h3 className="text-sm font-semibold text-text truncate">{insight.title}</h3>
            <Glyph className={`h-3.5 w-3.5 shrink-0 ${tone.glyphColor}`} aria-hidden="true" />
            <span className="sr-only">{tone.srLabel}.</span>
          </div>
          <p className="text-xs text-text-muted leading-relaxed font-sans mt-1">
            {insight.detail}
          </p>
        </div>
      </div>

      {/* Derivation tooltip — also exposed to assistive tech via aria-describedby */}
      <div
        id={`insight-tip-${insight.id}`}
        role="tooltip"
        className="pointer-events-none absolute left-4 right-4 top-full z-20 mt-2 rounded-lg border
                   border-border-strong bg-surface-2 p-3 text-[11px] leading-relaxed text-text-muted
                   opacity-0 shadow-float transition-opacity duration-150
                   group-hover:opacity-100 group-focus-within:opacity-100"
      >
        {insight.tooltip}
      </div>

      {/* Focusable target so keyboard users can reach the tooltip */}
      <button
        type="button"
        aria-describedby={`insight-tip-${insight.id}`}
        aria-label={`${insight.title}. ${tone.srLabel}. ${insight.detail} How this was derived: ${insight.tooltip}`}
        className="absolute inset-0 rounded-xl focus-visible:outline-none focus-visible:shadow-ring"
      />
    </li>
  );
};

/**
 * Horizontally scrollable strip of derived repository findings.
 *
 * Risks and warnings sort first, so the leftmost cards are the ones worth acting on.
 */
export const ExecutiveInsights: React.FC<ExecutiveInsightsProps> = ({ insights, className = '' }) => {
  const scrollerRef = useRef<HTMLOListElement>(null);
  const [atStart, setAtStart] = useState(true);
  const [atEnd, setAtEnd] = useState(false);

  const counts = useMemo(() => {
    const attention = insights.filter((i) => i.severity === 'warn' || i.severity === 'risk').length;
    return { attention, total: insights.length };
  }, [insights]);

  const updateEdges = () => {
    const el = scrollerRef.current;
    if (!el) return;
    setAtStart(el.scrollLeft <= 4);
    setAtEnd(el.scrollLeft + el.clientWidth >= el.scrollWidth - 4);
  };

  const scrollByCards = (direction: -1 | 1) => {
    const el = scrollerRef.current;
    if (!el) return;
    el.scrollBy({ left: direction * Math.max(320, el.clientWidth * 0.8), behavior: 'smooth' });
  };

  if (insights.length === 0) return null;

  return (
    <section className={`space-y-3 ${className}`} aria-labelledby="executive-insights-heading">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <Sparkles className="h-4 w-4 text-primary shrink-0" aria-hidden="true" />
          <h2
            id="executive-insights-heading"
            className="text-[11px] font-mono font-bold uppercase tracking-wider text-text-muted"
          >
            Repository Insights
          </h2>
          <span className="text-[10px] font-mono text-text-subtle shrink-0">
            {counts.attention > 0
              ? `${counts.attention} of ${counts.total} need attention`
              : `${counts.total} findings · all healthy`}
          </span>
        </div>

        {/* Scroll controls — hidden from AT since the list itself is navigable */}
        <div className="hidden sm:flex items-center gap-1 shrink-0">
          <button
            type="button"
            onClick={() => scrollByCards(-1)}
            disabled={atStart}
            aria-label="Scroll insights left"
            className="h-6 w-6 rounded border border-border bg-surface-2 text-text-muted
                       hover:text-text hover:border-primary/40 disabled:opacity-30
                       disabled:cursor-not-allowed transition-colors flex items-center justify-center
                       focus-visible:outline-none focus-visible:shadow-ring"
          >
            <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={() => scrollByCards(1)}
            disabled={atEnd}
            aria-label="Scroll insights right"
            className="h-6 w-6 rounded border border-border bg-surface-2 text-text-muted
                       hover:text-text hover:border-primary/40 disabled:opacity-30
                       disabled:cursor-not-allowed transition-colors flex items-center justify-center
                       focus-visible:outline-none focus-visible:shadow-ring"
          >
            <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        </div>
      </div>

      <div className="relative">
        <ol
          ref={scrollerRef}
          onScroll={updateEdges}
          className="flex gap-3 overflow-x-auto snap-x snap-mandatory pb-2 -mx-1 px-1
                     scroll-smooth list-none"
        >
          {insights.map((insight, index) => (
            <InsightCard key={insight.id} insight={insight} index={index} />
          ))}
        </ol>

        {/* Edge fades hint at additional content */}
        {!atStart && (
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-y-0 left-0 w-10 bg-gradient-to-r from-canvas to-transparent"
          />
        )}
        {!atEnd && (
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-y-0 right-0 w-10 bg-gradient-to-l from-canvas to-transparent"
          />
        )}
      </div>
    </section>
  );
};

export default ExecutiveInsights;
