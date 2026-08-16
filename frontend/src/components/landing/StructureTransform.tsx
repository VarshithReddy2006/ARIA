import React, { useCallback, useRef } from 'react';
import { easeOutCubic, phase, useMediaQuery, useScrollDriver } from './hooks';
import {
  MODEL_WIDE,
  MODEL_COMPACT,
  STAGE_RANGES,
  STRUCTURE_STAGES,
} from './structureModel';

/* ─────────────────────────────────────────────────────────────────────────────
 * StructureTransform — chapter 02.
 *
 * Five accumulating stages turn a flat file list into a directed topology:
 *
 *   01 FILES        scattered, unordered, no relationships
 *   02 MODULES      files migrate into clusters; grouping edges appear
 *   03 SYMBOLS      clusters sprout the declarations inside them
 *   04 CALLERS      direction appears — inbound edges resolve onto one symbol
 *   05 DEPENDENCIES outbound reach completes the graph
 *
 * Each stage adds to the previous one rather than replacing it, so the reader
 * watches structure accumulate. The SYMBOLS → CALLERS boundary is the turn the
 * section exists to deliver: it is where position stops being alphabetical.
 *
 * Scroll position is the only driver. Every per-frame value is written straight
 * to the DOM inside one rAF callback — React state holds nothing but the coarse
 * stage index, so the section re-renders five times, not once per frame.
 * ────────────────────────────────────────────────────────────────────────── */

const CLOSING = 'The repository stops being a list. It becomes a topology.';

const THESIS =
  'Imports and call sites resolve. Position stops being alphabetical and starts being architectural.';

export const StructureTransform: React.FC = () => {
  const compact = useMediaQuery('(max-width: 639px)');
  const model = compact ? MODEL_COMPACT : MODEL_WIDE;

  const stageRef = useRef<HTMLDivElement>(null);
  /*
    The file layer is blurred as a single composited layer rather than per node:
    nine independent `filter` values would be nine separate rasterisations every
    frame, and the depth cue is a property of the layer, not of each file.
  */
  const fileLayerRef = useRef<HTMLDivElement>(null);
  const lastBlur = useRef(-1);
  const fileRefs = useRef<Array<HTMLSpanElement | null>>([]);
  const moduleRefs = useRef<Array<HTMLDivElement | null>>([]);
  /** Cluster regions — the boundary a module occupies, lit as grouping resolves. */
  const clusterRefs = useRef<Array<SVGCircleElement | null>>([]);
  const symbolRefs = useRef<Array<HTMLSpanElement | null>>([]);
  const moduleEdgeRefs = useRef<Array<SVGLineElement | null>>([]);
  const callerEdgeRefs = useRef<Array<SVGLineElement | null>>([]);
  const depEdgeRefs = useRef<Array<SVGLineElement | null>>([]);

  const size = useRef({ w: 0, h: 0 });
  const progressRef = useRef(0);

  const measureStage = useCallback(() => {
    const el = stageRef.current;
    if (!el) return;
    size.current = { w: el.clientWidth, h: el.clientHeight };
  }, []);

  /** One frame. Writes transforms, opacities and SVG geometry; never setState. */
  const onFrame = useCallback(
    (p: number) => {
      progressRef.current = p;
      if (size.current.w === 0) measureStage();
      const { w, h } = size.current;
      if (w === 0 || h === 0) return;

      const s1 = phase(p, STAGE_RANGES[0][0], STAGE_RANGES[0][1]);
      const s2 = easeOutCubic(phase(p, STAGE_RANGES[1][0], STAGE_RANGES[1][1]));
      const s3 = phase(p, STAGE_RANGES[2][0], STAGE_RANGES[2][1]);
      const s4 = phase(p, STAGE_RANGES[3][0], STAGE_RANGES[3][1]);
      const s5 = phase(p, STAGE_RANGES[4][0], STAGE_RANGES[4][1]);

      const toPx = (xPct: number, yPct: number) =>
        `translate3d(${((xPct / 100) * w).toFixed(1)}px, ${((yPct / 100) * h).toFixed(1)}px, 0) translate(-50%, -50%)`;

      /*
        Once direction exists the file layer is no longer the subject, so it
        recedes rather than disappearing — the grouping it established is still
        part of what the reader is looking at.
      */
      const fileRecede = 1 - 0.55 * Math.max(s4, s5);

      /*
        Depth, not perspective. As grouping becomes context the file layer loses
        a little focus, so the reader's attention is pulled to the layer that is
        currently the subject. Written only when the rounded value changes.
      */
      const layer = fileLayerRef.current;
      if (layer) {
        const blur = Math.round((1 - fileRecede) * 2.6 * 10) / 10;
        if (blur !== lastBlur.current) {
          lastBlur.current = blur;
          layer.style.filter = blur > 0.05 ? `blur(${blur}px)` : 'none';
        }
      }

      // ── 01 FILES → 02 MODULES: scatter migrates into clusters ────────────
      const filePos: { x: number; y: number }[] = [];
      for (let i = 0; i < model.files.length; i++) {
        const { scatter, clustered } = model.files[i];
        const x = scatter.x + (clustered.x - scatter.x) * s2;
        const y = scatter.y + (clustered.y - scatter.y) * s2;

        const el = fileRefs.current[i];
        // Staggered arrival so the list reads as being enumerated.
        const appear = Math.min(1, Math.max(0, s1 * 1.6 - i * 0.08));

        /*
          A file does not snap onto its coordinate — it settles onto it. The
          offset is deterministic (derived from the index, not random, so it is
          identical on every render and on the server) and decays to nothing as
          the file finishes arriving.
        */
        const settle = (1 - appear) * 2.4;
        const jx = x + Math.sin(i * 2.399) * settle;
        const jy = y + Math.cos(i * 1.717) * settle;

        // Edges attach to the settled position, so nothing detaches mid-flight.
        filePos.push({ x: jx, y: jy });

        if (!el) continue;
        el.style.transform = toPx(jx, jy);
        el.style.opacity = (appear * 0.85 * fileRecede).toFixed(3);
      }

      /*
        ── 02 MODULES: cluster boundaries ─────────────────────────────────────
        The region a module occupies briefly illuminates as its files arrive, then
        recedes to a faint boundary. It answers "what just became a group?"
        without adding a label the reader has to parse.
      */
      for (let i = 0; i < model.modules.length; i++) {
        const circle = clusterRefs.current[i];
        if (!circle) continue;
        const t = Math.min(1, Math.max(0, s2 * 1.5 - i * 0.12));
        // One peak as the cluster forms, settling to a quiet resting boundary.
        const peak = Math.sin(Math.PI * t) * 0.55 + t * 0.16;
        circle.style.opacity = peak.toFixed(3);
        circle.setAttribute('r', (7 + t * 6).toFixed(2));
      }

      // ── 02 MODULES: cluster labels and grouping edges ────────────────────
      for (let i = 0; i < model.modules.length; i++) {
        const el = moduleRefs.current[i];
        if (!el) continue;
        const t = Math.min(1, Math.max(0, s2 * 1.5 - i * 0.12));
        el.style.opacity = t.toFixed(3);
        el.style.transform = `${toPx(model.modules[i].at.x, model.modules[i].at.y)} scale(${(
          0.9 + t * 0.1
        ).toFixed(3)})`;
      }

      for (let i = 0; i < model.moduleEdges.length; i++) {
        const line = moduleEdgeRefs.current[i];
        if (!line) continue;
        const [m, f] = model.moduleEdges[i];
        const anchor = model.modules[m].at;
        const file = filePos[f];
        line.setAttribute('x1', anchor.x.toFixed(2));
        line.setAttribute('y1', anchor.y.toFixed(2));
        line.setAttribute('x2', file.x.toFixed(2));
        line.setAttribute('y2', file.y.toFixed(2));
        const t = Math.min(1, Math.max(0, s2 * 1.4 - i * 0.05));
        line.style.strokeDashoffset = String(1 - t);
        // Grouping is context once direction arrives, so it fades back.
        line.style.opacity = (t * 0.9 * fileRecede).toFixed(3);
      }

      /*
        ── 05 arrival reactions ───────────────────────────────────────────────
        A destination reacts as the trace reaches it: a brief scale bump timed to
        the moment its own edge completes, so reach reads as something arriving
        rather than as a line simply existing. Computed before the symbol pass so
        it can fold into the same transform write — no second layout.
      */
      const arrival = new Map<number, number>();
      for (let i = 0; i < model.dependencyEdges.length; i++) {
        const slice = 1 / model.dependencyEdges.length;
        const t = Math.min(1, Math.max(0, (s5 - i * slice * 0.55) / slice));
        // Peaks as the edge lands, then gone.
        arrival.set(model.dependencyEdges[i], Math.sin(Math.PI * t) * 0.42);
      }

      // ── 03 SYMBOLS: declarations emerge inside each module ───────────────
      for (let i = 0; i < model.symbols.length; i++) {
        const el = symbolRefs.current[i];
        if (!el) continue;
        const t = Math.min(1, Math.max(0, s3 * 1.5 - i * 0.07));
        const isFocus = i === model.focus;
        /*
          §9: the final state must feel more understandable despite more edges.
          Non-participating symbols step back once the caller/dependency story
          starts, leaving hierarchy and direction as the dominant reading.
        */
        const participates =
          isFocus ||
          model.callerEdges.includes(i) ||
          model.dependencyEdges.includes(i);
        const recede = participates ? 1 : 1 - 0.92 * Math.max(s4, s5);

        /*
          Declarations bloom outward as they emerge — a small overshoot that
          settles, so a symbol appearing reads as something being discovered
          inside the module rather than a dot fading up.
        */
        const bloom = Math.sin(Math.PI * t) * 0.22;
        // A brief reaction when an outbound trace lands here.
        const reacts = arrival.get(i) ?? 0;

        el.style.opacity = (t * recede).toFixed(3);
        el.style.transform = `${toPx(model.symbols[i].at.x, model.symbols[i].at.y)} scale(${(
          0.42 + t * 0.58 + bloom + reacts + (isFocus ? s4 * 0.5 : 0)
        ).toFixed(3)})`;
      }

      // ── 04 CALLERS: inbound direction resolves onto the focus symbol ─────
      const focusAt = model.symbols[model.focus].at;
      for (let i = 0; i < model.callerEdges.length; i++) {
        const line = callerEdgeRefs.current[i];
        if (!line) continue;
        const from = model.symbols[model.callerEdges[i]].at;
        const slice = 1 / model.callerEdges.length;
        const t = Math.min(1, Math.max(0, (s4 - i * slice * 0.55) / slice));
        line.setAttribute('x1', from.x.toFixed(2));
        line.setAttribute('y1', from.y.toFixed(2));
        line.setAttribute('x2', focusAt.x.toFixed(2));
        line.setAttribute('y2', focusAt.y.toFixed(2));
        line.style.strokeDashoffset = String(1 - t);
        line.style.opacity = t > 0 ? '1' : '0';
      }

      // ── 05 DEPENDENCIES: outbound reach completes the topology ───────────
      for (let i = 0; i < model.dependencyEdges.length; i++) {
        const line = depEdgeRefs.current[i];
        if (!line) continue;
        const to = model.symbols[model.dependencyEdges[i]].at;
        const slice = 1 / model.dependencyEdges.length;
        const t = Math.min(1, Math.max(0, (s5 - i * slice * 0.55) / slice));
        line.setAttribute('x1', focusAt.x.toFixed(2));
        line.setAttribute('y1', focusAt.y.toFixed(2));
        line.setAttribute('x2', to.x.toFixed(2));
        line.setAttribute('y2', to.y.toFixed(2));
        line.style.strokeDashoffset = String(1 - t);
        line.style.opacity = t > 0 ? '1' : '0';
      }

      // Discrete mode drives the CSS-side type/scale shifts.
      const el = stageRef.current;
      if (el) {
        const mode = s4 > 0.15 ? 'directed' : s2 > 0.5 ? 'grouped' : 'flat';
        if (el.dataset.mode !== mode) el.dataset.mode = mode;
      }
    },
    [model, measureStage]
  );

  const { ref, step, reduced } = useScrollDriver<HTMLDivElement>({
    from: 0.14,
    to: 0.9,
    steps: 5,
    onFrame,
  });

  React.useEffect(() => {
    measureStage();
    onFrame(reduced ? 1 : progressRef.current);

    const el = stageRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(() => {
      measureStage();
      onFrame(reduced ? 1 : progressRef.current);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [measureStage, onFrame, reduced]);

  /*
    Reduced motion: the wrapper collapses to its natural height, nothing pins,
    and the resolved topology is applied once. All five stage entries stay
    readable, so no content depends on the animation having run.
  */
  const wrapperClass = reduced ? 'relative' : 'relative h-[260vh]';
  /*
    Names the scene for the page-wide backdrop controller: while this chapter owns
    the middle of the frame, the background field forms clusters and firms up its
    grid — the same transformation happening on the stage, one layer back.
  */
  const stickyClass = reduced
    ? 'flex flex-col justify-center py-16'
    : 'sticky top-0 min-h-screen flex flex-col justify-center overflow-hidden py-20';

  return (
    <div ref={ref} className={wrapperClass} data-stage="structure" data-pin="self">
      <div className={stickyClass}>
        {/* ── Section intro ───────────────────────────────────────────────── */}
        <div className="story-shell">
          <div className="flex items-center gap-4 mb-7">
            <span className="h-px w-8 bg-primary/60" aria-hidden="true" />
            <span className="mono-label">02 — STRUCTURAL TRANSFORMATION</span>
          </div>
          <h2 className="display-2 text-text max-w-4xl">
            The repository stops being a list.
            <br />
            <span className="display-dim">It becomes a topology.</span>
          </h2>
        </div>

        {/* ── Narrative rail + stage ──────────────────────────────────────── */}
        <div className="story-shell mt-10 sm:mt-12">
          <div className="grid grid-cols-1 gap-y-8 lg:grid-cols-[minmax(0,32fr)_minmax(0,68fr)] lg:gap-x-10 items-start min-w-0">
            {/* Stage narrative */}
            <ol className="min-w-0">
              {STRUCTURE_STAGES.map((s, i) => {
                const active = i === step;
                const reached = i <= step;
                return (
                  <li
                    key={s.label}
                    aria-current={active ? 'step' : undefined}
                    className={`relative border-l pl-4 py-2.5 transition-colors duration-300 ${active
                      ? 'border-primary'
                      : reached
                        ? 'border-white/[0.14]'
                        : 'border-white/[0.05]'
                      }`}
                  >
                    <div className="flex items-baseline gap-3 min-w-0">
                      <span
                        className={`mono-label tabular-nums shrink-0 transition-colors duration-300 ${active ? 'text-primary' : ''
                          }`}
                      >
                        {String(i + 1).padStart(2, '0')}
                      </span>
                      <span
                        className={`font-mono text-[13px] sm:text-sm font-semibold tracking-[0.14em] transition-colors duration-300 ${active
                          ? 'text-white'
                          : reached
                            ? 'text-text-muted'
                            : 'text-text-subtle'
                          }`}
                      >
                        {s.label}
                      </span>
                    </div>
                    <p
                      className={`text-[12px] leading-relaxed mt-1 transition-colors duration-300 ${active ? 'text-text-muted' : 'text-text-subtle'
                        }`}
                    >
                      {s.detail}
                    </p>
                  </li>
                );
              })}
            </ol>

            {/* The stage */}
            <div className="min-w-0">
              <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5 mb-3">
                <span className="mono-label truncate">
                  {STRUCTURE_STAGES[step].label} · {STRUCTURE_STAGES[step].detail}
                </span>
                {/* Never hidden at any width: the composition is illustrative. */}
                <span className="mono-label shrink-0">
                  ILLUSTRATIVE · ARIA&apos;S OWN REPOSITORY
                </span>
              </div>

              <div
                ref={stageRef}
                data-mode="flat"
                data-pointer="precision"
                className="structure-stage relative w-full h-[44vh] min-h-[280px] sm:h-[52vh] lg:h-[56vh]"
                role="img"
                aria-label="A scattered list of repository files groups into modules, splits into declared symbols, then resolves inbound callers and outbound dependencies into a directed topology as the page scrolls."
              >
                <svg
                  className="absolute inset-0 h-full w-full overflow-visible"
                  viewBox="0 0 100 100"
                  preserveAspectRatio="none"
                  aria-hidden="true"
                >
                  <defs>
                    {/* Direction is carried by an arrowhead, not by colour alone. */}
                    <marker
                      id="st-caller-head"
                      viewBox="0 0 8 8"
                      refX="7"
                      refY="4"
                      markerWidth="5"
                      markerHeight="5"
                      orient="auto-start-reverse"
                      markerUnits="strokeWidth"
                    >
                      <path d="M0,1 L7,4 L0,7 z" fill="#34d399" />
                    </marker>
                    <marker
                      id="st-dep-head"
                      viewBox="0 0 8 8"
                      refX="7"
                      refY="4"
                      markerWidth="5"
                      markerHeight="5"
                      orient="auto-start-reverse"
                      markerUnits="strokeWidth"
                    >
                      <path d="M0,1 L7,4 L0,7 z" fill="#818cf8" />
                    </marker>
                  </defs>

                  {/*
                    02 — cluster boundaries. Drawn first so they sit behind every
                    edge and node: this is the region a module occupies, not an
                    object in the graph.
                  */}
                  {model.modules.map((m, i) => (
                    <circle
                      key={`cl-${m.label}`}
                      ref={(el) => {
                        clusterRefs.current[i] = el;
                      }}
                      cx={m.at.x}
                      cy={m.at.y}
                      r={7}
                      fill="rgba(94,106,210,0.05)"
                      stroke="rgba(94,106,210,0.28)"
                      strokeWidth="0.12"
                      strokeDasharray="4 4"
                      style={{ opacity: reduced ? 0.18 : 0 }}
                      vectorEffect="non-scaling-stroke"
                    />
                  ))}

                  {/* 02 — grouping edges, deliberately the faintest layer */}
                  {model.moduleEdges.map((_, i) => (
                    <line
                      key={`m-${i}`}
                      ref={(el) => {
                        moduleEdgeRefs.current[i] = el;
                      }}
                      stroke="rgba(255,255,255,0.10)"
                      strokeWidth="0.1"
                      pathLength={1}
                      strokeDasharray={1}
                      style={{ strokeDashoffset: reduced ? 0 : 1, opacity: reduced ? 0.4 : 0 }}
                      vectorEffect="non-scaling-stroke"
                    />
                  ))}

                  {/* 04 — inbound callers */}
                  {model.callerEdges.map((_, i) => (
                    <line
                      key={`c-${i}`}
                      ref={(el) => {
                        callerEdgeRefs.current[i] = el;
                      }}
                      stroke="#34d399"
                      strokeWidth="0.22"
                      strokeDasharray={1}
                      pathLength={1}
                      markerEnd="url(#st-caller-head)"
                      style={{ strokeDashoffset: reduced ? 0 : 1, opacity: reduced ? 0.9 : 0 }}
                      vectorEffect="non-scaling-stroke"
                    />
                  ))}

                  {/* 05 — outbound dependencies */}
                  {model.dependencyEdges.map((_, i) => (
                    <line
                      key={`d-${i}`}
                      ref={(el) => {
                        depEdgeRefs.current[i] = el;
                      }}
                      stroke="#818cf8"
                      strokeWidth="0.22"
                      strokeDasharray={1}
                      pathLength={1}
                      markerEnd="url(#st-dep-head)"
                      style={{ strokeDashoffset: reduced ? 0 : 1, opacity: reduced ? 0.9 : 0 }}
                      vectorEffect="non-scaling-stroke"
                    />
                  ))}
                </svg>

                {/* 01 — file nodes, on their own composited depth layer */}
                <div
                  ref={fileLayerRef}
                  className="absolute inset-0 pointer-events-none"
                  aria-hidden="true"
                >
                  {model.files.map((_, i) => (
                    <span
                      key={`f-${i}`}
                      ref={(el) => {
                        fileRefs.current[i] = el;
                      }}
                      className="structure-file absolute left-0 top-0 block h-[3px] w-[3px] rounded-sm bg-white/70"
                      style={{ opacity: reduced ? 0.4 : 0 }}
                    />
                  ))}
                </div>

                {/* 03 — symbol nodes */}
                {model.symbols.map((_, i) => (
                  <span
                    key={`s-${i}`}
                    ref={(el) => {
                      symbolRefs.current[i] = el;
                    }}
                    className={`structure-symbol absolute left-0 top-0 block rounded-full ${i === model.focus ? 'structure-symbol--focus' : ''
                      }`}
                    style={{ opacity: reduced ? 1 : 0 }}
                    aria-hidden="true"
                  />
                ))}

                {/* 02 — module labels */}
                {model.modules.map((m, i) => (
                  <div
                    key={m.label}
                    ref={(el) => {
                      moduleRefs.current[i] = el;
                    }}
                    className="structure-module absolute left-0 top-0 whitespace-nowrap"
                    style={{ opacity: reduced ? 1 : 0 }}
                  >
                    <span className="font-mono text-[10px] tracking-[0.16em] text-text-muted">
                      {m.label}
                    </span>
                  </div>
                ))}
              </div>

              {/*
                The thesis sits directly beneath the stage so it is read at the
                moment direction appears, not as a detached caption.
              */}
              <p className="mono-detail max-w-2xl hair-t pt-4 mt-4">
                {step >= 3 ? THESIS : CLOSING}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default StructureTransform;
