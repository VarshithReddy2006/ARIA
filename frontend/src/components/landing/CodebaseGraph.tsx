import React, { useEffect, useMemo, useState } from 'react';
import { useCountUp, useInView, useMediaQuery, useReducedMotion } from './hooks';
import {
  AMBIENT_EDGES,
  AMBIENT_NODES,
  GRAPH_EDGES,
  GRAPH_NODES,
  type GraphNode,
} from './data';
/*
  Direction speaks the product's language, not a landing-page dialect: the same
  tones and dash pattern the File Graph and Call Graph use for inbound versus
  outbound relationships. Importing them means the two can never drift apart.
*/
import { EDGE_TONE, EDGE_DASH } from '../interactive/graph/edgeSemantics';

/* ─────────────────────────────────────────────────────────────────────────────
 * CodebaseGraph — chapter 03.
 *
 * The visual centre of the section. Four deliberate brightness tiers keep it
 * readable rather than uniformly lit:
 *
 *   background — ambient topology, no meaning, barely visible
 *   tertiary   — unrelated modules, dimmed when something is selected
 *   secondary  — direct neighbours of the selection
 *   primary    — the selected module and its edges
 *
 * Labels are HTML rather than SVG <text> so their size never scales with the
 * viewBox — at 375px an 11px SVG label would render near 4px and be unreadable.
 * ────────────────────────────────────────────────────────────────────────── */

const VIEW_W = 1000;
/** Wide layout is landscape; the curated mobile subset uses a taller canvas. */
const VIEW_H_WIDE = 620;
const VIEW_H_COMPACT = 900;

const GROUP_LABEL: Record<GraphNode['group'], string> = {
  service: 'SERVICE',
  core: 'CORE',
  router: 'ROUTER',
  mcp: 'MCP',
  model: 'MODEL',
};

interface MetricProps {
  label: string;
  value: number;
  suffix?: string;
  active: boolean;
  tone?: 'default' | 'success';
}

/** A metric read-out that counts up once the section is on screen. */
const Metric: React.FC<MetricProps> = ({ label, value, suffix = '', active, tone = 'default' }) => {
  const shown = useCountUp(value, active);
  return (
    <div className="flex-1 min-w-0">
      <div className="mono-label mb-2">{label}</div>
      <div
        className={`font-mono text-2xl sm:text-[1.75rem] font-bold tabular-nums leading-none ${tone === 'success' ? 'text-success' : 'text-text'
          }`}
      >
        {Math.round(shown)}
        {suffix}
      </div>
    </div>
  );
};

export const CodebaseGraph: React.FC = () => {
  const [ref, inView] = useInView<HTMLDivElement>({ threshold: 0.2 });
  const compact = useMediaQuery('(max-width: 767px)');
  const reduced = useReducedMotion();

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [focusedId, setFocusedId] = useState<string | null>(null);

  const viewH = compact ? VIEW_H_COMPACT : VIEW_H_WIDE;
  /** Ambient decoration is authored on the wide canvas; gently scale and center on mobile without stretching diagonals */
  const ambientScaleY = compact ? 1.15 : 1.0;
  const ambientOffsetY = compact ? (VIEW_H_COMPACT - VIEW_H_WIDE * 1.15) / 2 : 0;

  /** Small screens show a curated subset at its own coordinates. */
  const nodes = useMemo(() => {
    if (!compact) return GRAPH_NODES;
    return GRAPH_NODES.filter((n) => n.compact).map((n) => ({
      ...n,
      x: n.cx ?? n.x,
      y: n.cy ?? n.y,
    }));
  }, [compact]);

  const nodeIds = useMemo(() => new Set(nodes.map((n) => n.id)), [nodes]);
  const edges = useMemo(
    () => GRAPH_EDGES.filter((e) => nodeIds.has(e.from) && nodeIds.has(e.to)),
    [nodeIds]
  );

  // The graph settles on its own hub so the composition reads without input.
  useEffect(() => {
    if (!inView || selectedId) return;
    if (reduced) {
      setSelectedId('orchestrator');
      return;
    }
    const t = window.setTimeout(() => setSelectedId('orchestrator'), 1400);
    return () => window.clearTimeout(t);
  }, [inView, selectedId, reduced]);

  const activeId = hoveredId ?? focusedId ?? selectedId ?? 'orchestrator';
  const active = nodes.find((n) => n.id === activeId) ?? nodes[0];

  const neighbours = useMemo(() => {
    const set = new Set<string>([activeId]);
    edges.forEach((e) => {
      if (e.from === activeId) set.add(e.to);
      if (e.to === activeId) set.add(e.from);
    });
    return set;
  }, [activeId, edges]);

  const hasSelection = Boolean(selectedId || hoveredId || focusedId);

  /*
    ── Magnetic attention ───────────────────────────────────────────────────────
    Labels lean a couple of pixels toward the pointer as it passes. It is the
    smallest possible signal that the topology is aware of the reader, and it is
    what stops the field feeling printed.

    Deliberately cheap: one rAF loop, at most a handful of transform writes, and
    it only runs while the pointer is actually inside the figure. Node geometry is
    read from the model rather than the DOM, so nothing measures layout per frame.
  */
  const fieldRef = React.useRef<HTMLDivElement>(null);
  const labelRefs = React.useRef<Array<HTMLButtonElement | null>>([]);

  React.useEffect(() => {
    const field = fieldRef.current;
    if (!field || reduced) return;
    if (!window.matchMedia('(hover: hover) and (pointer: fine)').matches) return;

    const pointer = { x: 0, y: 0, inside: false };
    let raf = 0;

    const frame = () => {
      raf = 0;
      const w = field.clientWidth;
      const h = field.clientHeight;
      if (w === 0 || h === 0) return;

      // Attraction falls off over a fifth of the figure's width.
      const range = w * 0.2;

      for (let i = 0; i < nodes.length; i++) {
        const el = labelRefs.current[i];
        if (!el) continue;

        let dx = 0;
        let dy = 0;
        if (pointer.inside) {
          const nx = (nodes[i].x / VIEW_W) * w;
          const ny = (nodes[i].y / viewH) * h;
          const ox = pointer.x - nx;
          const oy = pointer.y - ny;
          const dist = Math.hypot(ox, oy);
          if (dist < range && dist > 0.5) {
            const pull = (1 - dist / range) * 3.5;
            dx = (ox / dist) * pull;
            dy = (oy / dist) * pull;
          }
        }
        /*
          Written as custom properties, not as a full transform: the label's
          centring offset differs by breakpoint, and composing in CSS keeps that
          rule in one place instead of duplicating it here.
        */
        el.style.setProperty('--mx', `${dx.toFixed(2)}px`);
        el.style.setProperty('--my', `${dy.toFixed(2)}px`);
      }
    };

    const schedule = () => {
      if (!raf) raf = requestAnimationFrame(frame);
    };

    const onMove = (event: PointerEvent) => {
      const r = field.getBoundingClientRect();
      pointer.x = event.clientX - r.left;
      pointer.y = event.clientY - r.top;
      pointer.inside = true;
      schedule();
    };

    const onLeave = () => {
      pointer.inside = false;
      schedule();
    };

    field.addEventListener('pointermove', onMove, { passive: true });
    field.addEventListener('pointerleave', onLeave, { passive: true });
    return () => {
      field.removeEventListener('pointermove', onMove);
      field.removeEventListener('pointerleave', onLeave);
      if (raf) cancelAnimationFrame(raf);
    };
  }, [nodes, viewH, reduced]);

  /**
   * Relationships of the *selected* module, ordered inbound first so the trace
   * reads as "what reaches this, then what this reaches". Hover is excluded on
   * purpose — see the trace group below.
   */
  const tracedEdges = useMemo(() => {
    if (!selectedId) return [];
    const inbound = edges.filter((e) => e.to === selectedId);
    const outbound = edges.filter((e) => e.from === selectedId);
    return [...inbound, ...outbound];
  }, [selectedId, edges]);

  return (
    <div ref={ref} className="relative">
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 mb-5">
        <span className="mono-label truncate">NETWORKX · DIRECTED GRAPH</span>

        {/*
          Names the two directions in words. The arrowheads and dash pattern do
          the work in the graph; this makes the convention explicit rather than
          leaving the reader to infer it from two similar-weight lines.
        */}
        <div className="flex items-center gap-5 shrink-0">
          <span className="flex items-center gap-2">
            <svg width="20" height="6" viewBox="0 0 20 6" aria-hidden="true">
              <line
                x1="0" y1="3" x2="15" y2="3"
                stroke={EDGE_TONE.incoming}
                strokeWidth="1.4"
                strokeDasharray={EDGE_DASH.incoming}
              />
              <path d="M15,0.6 L19,3 L15,5.4 z" fill={EDGE_TONE.incoming} />
            </svg>
            <span className="mono-label">CALLERS</span>
          </span>
          <span className="flex items-center gap-2">
            <svg width="20" height="6" viewBox="0 0 20 6" aria-hidden="true">
              <line x1="0" y1="3" x2="15" y2="3" stroke={EDGE_TONE.outgoing} strokeWidth="1.4" />
              <path d="M15,0.6 L19,3 L15,5.4 z" fill={EDGE_TONE.outgoing} />
            </svg>
            <span className="mono-label">IMPORTS</span>
          </span>
        </div>

        {/*
          Never hidden at any width: the figures in this section are illustrative,
          and the disclosure has to travel with them.
        */}
        <span className="mono-label shrink-0 basis-full lg:basis-auto lg:text-right">
          ILLUSTRATIVE · ARIA&apos;S OWN REPOSITORY
        </span>
      </div>

      <div className="relative">
        {/*
          Accessible equivalent of the graph. The SVG itself is decorative;
          everything it conveys is available as text to assistive technology.
        */}
        <p className="sr-only">
          Repository dependency graph, {nodes.length} modules shown of 1,284 indexed nodes and
          3,940 edges. Selected module: {active.path}. {active.role}. {active.callers} callers,{' '}
          {active.imports} imports, PageRank {Math.round(active.rank * 100)} percent. Figures are
          illustrative, drawn from ARIA's own repository.
        </p>
        <ul className="sr-only">
          {nodes.map((n) => (
            <li key={n.id}>
              {n.path} — {n.role}, {n.callers} callers, {n.imports} imports, PageRank{' '}
              {Math.round(n.rank * 100)} percent.
            </li>
          ))}
        </ul>

        {/*
          Graph canvas + HTML label layer share one positioning context. The box
          is locked to the viewBox aspect ratio so percentage-positioned labels
          land exactly on their SVG circles, and capped in vh so it never grows
          taller than the viewport.
        */}
        {/*
          `data-brackets` puts two corner marks on the figure — a measured frame,
          the way a technical drawing is bounded. It is the only chrome the
          topology gets; anything more would compete with the graph itself.
        */}
        <div
          ref={fieldRef}
          className="relative w-full mx-auto data-brackets"
          data-pointer="precision"
          style={{
            aspectRatio: `${VIEW_W} / ${viewH}`,
            maxWidth: `calc(${compact ? 56 : 62}vh * ${VIEW_W / viewH})`,
          }}
        >
          <svg
            viewBox={`0 0 ${VIEW_W} ${viewH}`}
            className="absolute inset-0 w-full h-full"
            preserveAspectRatio="none"
            aria-hidden="true"
            focusable="false"
          >
            <defs>
              <radialGradient id="cg-halo">
                <stop offset="0%" stopColor="#5e6ad2" stopOpacity="0.26" />
                <stop offset="100%" stopColor="#5e6ad2" stopOpacity="0" />
              </radialGradient>

              {/* Arrowheads: direction never depends on colour alone. */}
              <marker
                id="cg-head-in"
                viewBox="0 0 8 8"
                refX="7"
                refY="4"
                markerWidth="4.5"
                markerHeight="4.5"
                orient="auto-start-reverse"
                markerUnits="strokeWidth"
              >
                <path d="M0,1 L7,4 L0,7 z" fill={EDGE_TONE.incoming} />
              </marker>
              <marker
                id="cg-head-out"
                viewBox="0 0 8 8"
                refX="7"
                refY="4"
                markerWidth="4.5"
                markerHeight="4.5"
                orient="auto-start-reverse"
                markerUnits="strokeWidth"
              >
                <path d="M0,1 L7,4 L0,7 z" fill={EDGE_TONE.outgoing} />
              </marker>
            </defs>

            {/* ── Background tier: ambient topology, no meaning ───────────── */}
            <g opacity={compact ? 0.35 : 0.55}>
              {AMBIENT_EDGES.map(([a, b], i) => {
                const p = AMBIENT_NODES[a];
                const q = AMBIENT_NODES[b];
                if (!p || !q) return null;
                return (
                  <line
                    key={`amb-e-${i}`}
                    x1={p.x}
                    y1={p.y * ambientScaleY + ambientOffsetY}
                    x2={q.x}
                    y2={q.y * ambientScaleY + ambientOffsetY}
                    stroke="rgba(255,255,255,0.045)"
                    strokeWidth="0.75"
                  />
                );
              })}
              {AMBIENT_NODES.map((n, i) => (
                <circle
                  key={`amb-n-${i}`}
                  cx={n.x}
                  cy={n.y * ambientScaleY + ambientOffsetY}
                  r={1.6}
                  fill="rgba(255,255,255,0.12)"
                />
              ))}
            </g>

            {/* ── Edges ───────────────────────────────────────────────────── */}
            {edges.map((edge, i) => {
              const a = nodes.find((n) => n.id === edge.from);
              const b = nodes.find((n) => n.id === edge.to);
              if (!a || !b) return null;

              /*
                Direction relative to the selection is the whole point of this
                graph: an inbound edge is a caller, an outbound edge is something
                the module reaches. Carried by three channels — tone, dash and an
                arrowhead — so it is readable without decoding colour.
              */
              const isInbound = edge.to === activeId;
              const isOutbound = edge.from === activeId;
              const isLinked = isInbound || isOutbound;
              const delay = 380 + i * 80;

              const stroke = isInbound
                ? EDGE_TONE.incoming
                : isOutbound
                  ? EDGE_TONE.outgoing
                  : 'rgba(255,255,255,0.07)';

              // Inbound is dashed, outbound solid — matching the product.
              const dash = isInbound ? EDGE_DASH.incoming : undefined;

              // Only linked edges get a head; unrelated topology stays quiet.
              const marker = isInbound
                ? 'url(#cg-head-in)'
                : isOutbound
                  ? 'url(#cg-head-out)'
                  : undefined;

              /*
                An undashed edge can draw itself with a dashoffset trick, but a
                semantically dashed one cannot — the reveal would fight the dash
                pattern. Inbound edges therefore fade in instead.
              */
              const drawStyle: React.CSSProperties = reduced
                ? { strokeDasharray: dash, opacity: 1 }
                : dash
                  ? {
                    strokeDasharray: dash,
                    opacity: inView ? 1 : 0,
                    transition: `opacity 900ms ease ${delay}ms, stroke 400ms ease, stroke-width 400ms ease`,
                  }
                  : {
                    strokeDasharray: 1,
                    strokeDashoffset: inView ? 0 : 1,
                    transition: `stroke-dashoffset 1200ms cubic-bezier(0.16,1,0.3,1) ${delay}ms, stroke 400ms ease, stroke-width 400ms ease`,
                  };

              return (
                <line
                  key={`${edge.from}-${edge.to}`}
                  x1={a.x}
                  y1={a.y}
                  x2={b.x}
                  y2={b.y}
                  stroke={stroke}
                  strokeWidth={isLinked ? 1.6 : 0.8}
                  strokeOpacity={isLinked ? 0.9 : 1}
                  pathLength={1}
                  markerEnd={marker}
                  style={drawStyle}
                />
              );
            })}

            {/* ── Attention propagation ───────────────────────────────────────
                When ARIA re-targets, a light travels each relationship of the
                new selection exactly once: source → edge → target. It is keyed
                on the selection, so a new selection remounts the group and the
                animation restarts from the beginning rather than looping.

                Deliberately bound to `selectedId`, not to hover: this represents
                ARIA tracing a relationship, not the pointer moving, and it must
                never read as live network traffic.
            ------------------------------------------------------------------ */}
            {!reduced && inView && selectedId && (
              <g key={`trace-${selectedId}`} aria-hidden="true">
                {tracedEdges.map((edge, i) => {
                  const a = nodes.find((n) => n.id === edge.from);
                  const b = nodes.find((n) => n.id === edge.to);
                  if (!a || !b) return null;
                  return (
                    <line
                      key={`trace-${edge.from}-${edge.to}`}
                      className="attn-trace"
                      x1={a.x}
                      y1={a.y}
                      x2={b.x}
                      y2={b.y}
                      stroke="#e8ecff"
                      strokeWidth="2"
                      strokeLinecap="round"
                      pathLength={1}
                      style={{ '--trace-delay': `${i * 120}ms` } as React.CSSProperties}
                    />
                  );
                })}
              </g>
            )}

            {/* ── Inspector Physical Tether ───────────────────────────────── */}
            {inView && selectedId && (
              <line
                x1={active.x}
                y1={active.y}
                x2={compact ? active.x : VIEW_W - 380}
                y2={compact ? viewH : viewH - 140}
                stroke="rgba(94,106,210,0.25)"
                strokeWidth="1"
                strokeDasharray="4 4"
                style={{
                  opacity: inView ? 1 : 0,
                  transition: 'opacity 900ms ease 500ms'
                }}
              />
            )}

            {/* ── Nodes ───────────────────────────────────────────────────── */}
            {nodes.map((node, i) => {
              const isActive = node.id === activeId;
              const isNeighbour = neighbours.has(node.id);
              const dim = hasSelection && !isNeighbour;
              const r = isActive ? 12 : 5 + node.rank * 5;

              return (
                <g
                  key={node.id}
                  transform={`translate(${node.x} ${node.y})`}
                  style={{
                    opacity: inView ? (dim ? 0.14 : 1) : 0,
                    transition: reduced
                      ? undefined
                      : `opacity 900ms cubic-bezier(0.16,1,0.3,1) ${i * 110}ms`,
                  }}
                >
                  {/*
                    Node attention. Nothing pulses: a local bloom settles in
                    behind the node that matters, a static ring marks it, and —
                    only when ARIA re-targets — one ring expands out of it and
                    dissipates. Perpetual motion would imply live traffic the
                    graph is not measuring.
                  */}
                  {isActive && (
                    <circle
                      key={`bloom-${activeId}`}
                      className={reduced ? undefined : 'node-bloom'}
                      r={46}
                      fill="url(#cg-halo)"
                    />
                  )}
                  {isActive && (
                    <circle r={24} fill="none" stroke="rgba(94,106,210,0.35)" strokeWidth="1" />
                  )}
                  {/* The one-time expansion, bound to deliberate selection. */}
                  {!reduced && isActive && node.id === selectedId && (
                    <circle
                      key={`ring-${selectedId}`}
                      className="node-ring"
                      r={40}
                      fill="none"
                      stroke="rgba(143,155,245,0.55)"
                      strokeWidth="1.25"
                    />
                  )}
                  {node.id === focusedId && (
                    <circle r={r + 9} fill="none" stroke="#ffffff" strokeWidth="1.5" />
                  )}

                  <circle
                    r={r}
                    fill={isActive ? '#5e6ad2' : isNeighbour ? '#3c4360' : '#20232e'}
                    stroke={isActive ? '#ffffff' : 'rgba(255,255,255,0.22)'}
                    strokeWidth={isActive ? 1.6 : 1}
                    style={{ transition: 'r 320ms ease, fill 320ms ease' }}
                  />
                </g>
              );
            })}
          </svg>

          {/*
            Label + hit-target layer. Buttons give real keyboard focus and
            accessible names; the circles below are purely visual.
          */}
          <div className="absolute inset-0">
            {nodes.map((node, i) => {
              const isActive = node.id === activeId;
              const isNeighbour = neighbours.has(node.id);
              const dim = hasSelection && !isNeighbour;

              return (
                <button
                  key={node.id}
                  ref={(el) => {
                    labelRefs.current[i] = el;
                  }}
                  type="button"
                  onMouseEnter={() => setHoveredId(node.id)}
                  onMouseLeave={() => setHoveredId(null)}
                  onFocus={() => setFocusedId(node.id)}
                  onBlur={() => setFocusedId(null)}
                  onClick={() => setSelectedId(node.id)}
                  aria-pressed={node.id === selectedId}
                  className="graph-node-btn mag absolute font-mono whitespace-nowrap
                             focus-visible:outline-none"
                  style={{
                    left: `${(node.x / VIEW_W) * 100}%`,
                    top: `${(node.y / viewH) * 100}%`,
                    opacity: inView ? (dim ? 0.14 : 1) : 0,
                    transition: 'opacity 500ms ease',
                    /* Tokens rather than literals, so the label tiers track the
                     * design system instead of drifting from it. */
                    color: isActive
                      ? 'var(--text)'
                      : isNeighbour
                        ? 'var(--text-muted)'
                        : '#5a5d66',
                    fontWeight: isActive ? 600 : 400,
                  }}
                >
                  {node.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* ── Floating inspector ───────────────────────────────────────────
            Not a modal. It resolves out of a blur, as though the system has just
            finished identifying the module — and it re-resolves whenever ARIA
            re-targets. Keyed on `selectedId` rather than the hover-inclusive
            active id, so sweeping the pointer across the graph swaps the contents
            quietly instead of replaying the animation on every node.
        -------------------------------------------------------------------- */}
        {/*
          The live region is the stable outer element. The panel inside it is
          keyed, so re-targeting replays the resolve animation without tearing
          down and rebuilding the region a screen reader is listening to.
        */}
        <div
          className="mt-6 md:mt-0 md:absolute md:right-0 md:bottom-0 md:w-[26rem]"
          aria-live="polite"
          style={{
            opacity: inView ? 1 : 0,
            transform: inView || reduced ? 'none' : 'translateY(18px)',
            transition: reduced
              ? undefined
              : 'opacity 900ms cubic-bezier(0.16,1,0.3,1) 500ms, transform 900ms cubic-bezier(0.16,1,0.3,1) 500ms',
          }}
        >
          <div
            key={`inspector-${selectedId ?? 'initial'}`}
            className={`spec-panel p-6 sm:p-7 ${
              inView && !reduced && selectedId ? 'inspector-resolve evidence-stack' : ''
            }`}
          >
            <div className="flex items-center justify-between mb-4">
              <span className="mono-label mono-label-accent">SELECTED MODULE</span>
              <span className="mono-label">{GROUP_LABEL[active.group]}</span>
            </div>

            {/* Identity, then explanation, then figures — in that order. */}
            <div>
              <p
                className="font-mono text-[13px] sm:text-sm text-text font-semibold leading-relaxed"
                style={{ wordBreak: 'break-word', overflowWrap: 'anywhere' }}
              >
                {active.path.includes('/') ? (
                  <>
                    <span className="text-text-subtle/70">{active.path.slice(0, active.path.lastIndexOf('/') + 1)}</span>
                    <span>{active.path.slice(active.path.lastIndexOf('/') + 1)}</span>
                  </>
                ) : (
                  active.path
                )}
              </p>

              <p className="mt-3 text-[13px] text-text-muted leading-relaxed">{active.summary}</p>
            </div>

            <p className="mt-3.5 text-[13px] text-text leading-relaxed">
              <span className="mono-label mr-2">WHY</span>
              {active.why}
            </p>

            <div className="mt-6 pt-5 hair-t flex gap-5">
              <Metric label="CALLERS" value={active.callers} active={inView} />
              <Metric label="IMPORTS" value={active.imports} active={inView} />
              <Metric
                label="PAGERANK"
                value={Math.round(active.rank * 100)}
                suffix="%"
                active={inView}
                tone="success"
              />
            </div>

            {/*
              An affordance, not a status light — so the dot rests. A breathing
              dot beside "select any module" implied the graph was doing something
              while the reader was doing nothing.
            */}
            <p className="mt-6 mono-detail flex items-center gap-2" style={{ fontSize: 10 }}>
              <span className="h-1 w-1 rounded-full bg-primary" aria-hidden="true" />
              Select any module to re-target
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default CodebaseGraph;
