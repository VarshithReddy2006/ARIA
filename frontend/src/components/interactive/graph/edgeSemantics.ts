/**
 * Edge semantics shared by the File Graph and the Call Graph.
 *
 * Both surfaces previously distinguished relationship direction by stroke colour
 * alone: emerald for incoming, indigo for outgoing. That is unreadable for anyone
 * with a red/green deficiency, and it left two relationships with no treatment at
 * all — a dependency cycle in the File Graph and mutual recursion in the Call
 * Graph both rendered as two ordinary arrows.
 *
 * Every relationship here is therefore carried by at least two channels: colour
 * plus stroke width, dash pattern, or arrowheads at both ends.
 *
 * Pure module — no React, no React Flow — so the rules can be unit tested. The
 * caller attaches its own `MarkerType`, since that enum lives in React Flow.
 */

/** Tones. Kept literal so a test can assert the mapping. */
export const EDGE_TONE = {
  /** A traced dependency path. */
  path: '#f43f5e',
  /** Something the focused entity reaches: a dependency, or a callee. */
  outgoing: '#818cf8',
  /** Something that reaches the focused entity: a dependent, or a caller. */
  incoming: '#34d399',
  /** A cycle, or mutual recursion. */
  cyclic: '#f59e0b',
  /** A call the analyser could not resolve to a single target. */
  ambiguous: '#f59e0b',
  /** Present but not part of the current focus. */
  inactive: '#27272a',
  /** No selection anywhere — the resting state of the topology. */
  idle: '#3f3f46',
} as const;

/** Dash patterns. Distinct enough to read apart at 1x zoom. */
export const EDGE_DASH = {
  solid: undefined as string | undefined,
  /** Incoming: something depends on / calls this. */
  incoming: '6 3',
  /** Cyclic: tight ticks, reads as "goes both ways". */
  cyclic: '2 2',
  /** Unresolved: sparse dots, reads as "uncertain". */
  ambiguous: '4 4',
  /** Recursion: fine dots. */
  recursive: '1 3',
} as const;

export interface EdgeVisual {
  stroke: string;
  strokeWidth: number;
  opacity: number;
  /** `strokeDasharray`, or undefined for a solid line. */
  dash?: string;
  /** True when the relationship runs both ways and needs two arrowheads. */
  bothEnds: boolean;
}

/**
 * Keys (`"source|target"`) for every edge whose reverse also exists.
 *
 * In the File Graph these are dependency cycles; in the Call Graph they are
 * mutual recursion. Derived entirely from the edge list already on screen — no
 * additional request and no invented relationship.
 */
export function buildMutualPairSet(
  edges: readonly { source: string; target: string }[],
): Set<string> {
  const present = new Set<string>();
  for (const e of edges) present.add(`${e.source}|${e.target}`);

  const mutual = new Set<string>();
  for (const e of edges) {
    if (e.source === e.target) continue; // a self-loop is not a mutual pair
    if (present.has(`${e.target}|${e.source}`)) {
      mutual.add(`${e.source}|${e.target}`);
    }
  }
  return mutual;
}

export function isMutual(
  mutualPairs: Set<string>,
  source: string,
  target: string,
): boolean {
  return mutualPairs.has(`${source}|${target}`);
}

/* ─────────────────────────────────────────────────────────────────────────────
 * Focus choreography.
 *
 * The two graphs report different dimensions, so they should not react to a
 * selection in the same rhythm:
 *
 *   architecture — a topology. Direction is a property of the structure, so both
 *                  directions resolve together and the unrelated graph recedes
 *                  slightly after them.
 *   execution    — a flow. What runs *before* the selected function illuminates
 *                  first, the function is already lit, and what it calls resolves
 *                  after — so the eye reads the traversal in the order it happens.
 *
 * Expressed as delays rather than as an animation: the values are handed to CSS
 * transitions on properties that were already transitioning, so a focus change
 * costs no extra frames, nothing loops, and the motion ends as soon as it has
 * communicated the ordering. Pure, so the cadence can be unit tested.
 * ────────────────────────────────────────────────────────────────────────── */

export type GraphSurface = 'architecture' | 'execution';

export type FocusRole =
  /** The selected entity itself. */
  | 'focus'
  /** Reaches the selection: a dependent, or a caller. */
  | 'incoming'
  /** Reached by the selection: a dependency, or a callee. */
  | 'outgoing'
  /** Present, but not part of the current focus. */
  | 'unrelated'
  /** Nothing is selected anywhere. */
  | 'idle';

export interface Choreography {
  /** Milliseconds before this element responds to the focus change. */
  delayMs: number;
  /** Milliseconds the response takes. */
  durationMs: number;
}

/** Longest delay any role can carry, so callers can size a settle timeout. */
export const CHOREOGRAPHY_SETTLE_MS = 760;

export function resolveFocusChoreography(
  role: FocusRole,
  surface: GraphSurface,
): Choreography {
  // The focus is the reason the change happened; it never waits.
  if (role === 'focus') return { delayMs: 0, durationMs: 260 };
  if (role === 'idle') return { delayMs: 0, durationMs: 320 };

  if (surface === 'execution') {
    if (role === 'incoming') return { delayMs: 0, durationMs: 260 };
    if (role === 'outgoing') return { delayMs: 210, durationMs: 300 };
    return { delayMs: 340, durationMs: 420 }; // unrelated retreats last
  }

  // Architecture: direction is structural, not temporal.
  if (role === 'incoming' || role === 'outgoing') {
    return { delayMs: 70, durationMs: 280 };
  }
  return { delayMs: 280, durationMs: 420 };
}

/** The role an edge plays relative to the current selection. */
export function edgeFocusRole(flags: {
  isIncoming: boolean;
  isOutgoing: boolean;
  hasActive: boolean;
}): FocusRole {
  if (!flags.hasActive) return 'idle';
  if (flags.isIncoming) return 'incoming';
  if (flags.isOutgoing) return 'outgoing';
  return 'unrelated';
}

/**
 * A CSS `transition` shorthand for the properties these graphs actually change
 * on a focus shift. Compositor-friendly where possible; `stroke` is not, but it
 * is a single paint on a handful of paths, not a per-frame recomputation.
 */
export function edgeTransition(c: Choreography): string {
  return (
    `stroke ${c.durationMs}ms ease ${c.delayMs}ms,` +
    ` stroke-width ${c.durationMs}ms ease ${c.delayMs}ms,` +
    ` opacity ${c.durationMs}ms ease ${c.delayMs}ms`
  );
}

export interface DependencyEdgeFlags {
  /** Part of an explicitly traced dependency path. */
  isPath: boolean;
  /** The focused file imports this edge's target. */
  isOutgoing: boolean;
  /** This edge's source imports the focused file. */
  isIncoming: boolean;
  /** The two files import each other. */
  isCyclic: boolean;
  /** Something is focused or hovered. */
  hasActive: boolean;
  /** Resting colour when nothing is focused, usually by source category. */
  idleTone?: string;
}

/**
 * File Graph: "what does this file depend on, and what depends on it?"
 *
 * Precedence is deliberate — a traced path outranks a cycle, which outranks
 * ordinary direction, because the trace is what the reader asked for.
 */
export function resolveDependencyEdgeStyle(flags: DependencyEdgeFlags): EdgeVisual {
  const { isPath, isOutgoing, isIncoming, isCyclic, hasActive, idleTone } = flags;

  if (isPath) {
    return {
      stroke: EDGE_TONE.path,
      strokeWidth: 2.75,
      opacity: 1,
      dash: EDGE_DASH.solid,
      bothEnds: false,
    };
  }

  if (isCyclic && (isOutgoing || isIncoming)) {
    return {
      stroke: EDGE_TONE.cyclic,
      strokeWidth: 2.25,
      opacity: 1,
      dash: EDGE_DASH.cyclic,
      bothEnds: true,
    };
  }

  if (isOutgoing) {
    return {
      stroke: EDGE_TONE.outgoing,
      strokeWidth: 2,
      opacity: 0.95,
      dash: EDGE_DASH.solid,
      bothEnds: false,
    };
  }

  if (isIncoming) {
    return {
      stroke: EDGE_TONE.incoming,
      strokeWidth: 2,
      opacity: 0.9,
      dash: EDGE_DASH.incoming,
      bothEnds: false,
    };
  }

  if (hasActive) {
    return {
      stroke: EDGE_TONE.inactive,
      strokeWidth: 1,
      opacity: 0.1,
      dash: EDGE_DASH.solid,
      bothEnds: false,
    };
  }

  return {
    stroke: idleTone ?? EDGE_TONE.idle,
    strokeWidth: 1.2,
    opacity: 0.42,
    dash: EDGE_DASH.solid,
    bothEnds: false,
  };
}

export interface CallEdgeFlags {
  /** The function calls itself. */
  isSelfCall: boolean;
  /** This function and the other call each other. */
  isMutualRecursion: boolean;
  /** The focused function calls this edge's target. */
  isOutgoing: boolean;
  /** This edge's source calls the focused function. */
  isIncoming: boolean;
  /** The analyser could not resolve the call target uniquely. */
  isAmbiguous: boolean;
  /** Something is focused. */
  hasActive: boolean;
}

/**
 * Call Graph: "what executes before and after this function?"
 *
 * Recursion outranks direction because it is a property of execution itself, and
 * an ambiguous call keeps its uncertainty treatment even inside the focus so a
 * reader never mistakes a guess for a resolved call.
 */
export function resolveCallEdgeStyle(flags: CallEdgeFlags): EdgeVisual {
  const {
    isSelfCall, isMutualRecursion, isOutgoing, isIncoming, isAmbiguous, hasActive,
  } = flags;

  if (isSelfCall || isMutualRecursion) {
    return {
      stroke: EDGE_TONE.path,
      strokeWidth: 2.25,
      opacity: 1,
      dash: EDGE_DASH.recursive,
      bothEnds: isMutualRecursion,
    };
  }

  if (isAmbiguous) {
    return {
      stroke: EDGE_TONE.ambiguous,
      // Still visible under focus, but never as strong as a resolved call.
      strokeWidth: isOutgoing || isIncoming ? 1.75 : 1.5,
      opacity: isOutgoing || isIncoming ? 0.85 : hasActive ? 0.3 : 0.65,
      dash: EDGE_DASH.ambiguous,
      bothEnds: false,
    };
  }

  if (isOutgoing) {
    return {
      stroke: EDGE_TONE.outgoing,
      strokeWidth: 2,
      opacity: 0.95,
      dash: EDGE_DASH.solid,
      bothEnds: false,
    };
  }

  if (isIncoming) {
    return {
      stroke: EDGE_TONE.incoming,
      strokeWidth: 2,
      opacity: 0.9,
      dash: EDGE_DASH.incoming,
      bothEnds: false,
    };
  }

  if (hasActive) {
    return {
      stroke: EDGE_TONE.inactive,
      strokeWidth: 1,
      opacity: 0.1,
      dash: EDGE_DASH.solid,
      bothEnds: false,
    };
  }

  return {
    stroke: EDGE_TONE.idle,
    strokeWidth: 1.2,
    opacity: 0.42,
    dash: EDGE_DASH.solid,
    bothEnds: false,
  };
}
