import dagre from 'dagre';

/**
 * Layout for the predictive impact graph.
 *
 * The propagation chains are a genuine hierarchy, so they keep Dagre's
 * left-to-right ranking. Everything else is the problem: an impact result is
 * mostly *isolated* files — directly affected modules that appear in no
 * dependency path — and Dagre assigns every edge-less node to rank 0, stacking
 * them into a single vertical column. Thirty such files produced a canvas
 * roughly 260px wide and 2,800px tall.
 *
 * Isolated nodes are therefore reflowed into a grid. The column count is chosen
 * so the *whole* bounding box — chain block plus grid — tends toward the aspect
 * ratio of the canvas it will be framed in. Targeting the grid alone was not
 * enough: the chain block sits above it and dragged the total back to roughly
 * square, so a wide short canvas still had to zoom out to fit a tall graph,
 * which is what made the nodes small.
 *
 * The target aspect is supplied by the caller from its measured canvas, so no
 * constant here is tied to any particular repository or viewport.
 *
 * No node is added, removed, reclassified or re-parented — only the coordinates
 * of nodes that have no edges change.
 */

export const NODE_WIDTH = 200;
export const NODE_HEIGHT = 40;

/** Pitch of the isolated-node grid. Tighter than the node box, not touching. */
const GRID_PITCH_X = NODE_WIDTH + 44;
const GRID_PITCH_Y = NODE_HEIGHT + 24;

/** Gap between the connected topology and the isolated grid below it. */
const BAND_GAP = 72;

/** Fallback when the caller has not measured a canvas yet. */
export const DEFAULT_TARGET_ASPECT = 1.7;

const MIN_COLS = 1;
const MAX_COLS = 24;

/** Framing bounds, so callers cannot drift from the numbers used here. */
export const MIN_FIT_ZOOM = 0.15;
export const MAX_FIT_ZOOM = 1.15;
/** Proportion of the canvas the topology should occupy once framed. */
export const FIT_FILL = 0.88;

export interface LayoutNode {
  id: string;
  position?: { x: number; y: number };
  [key: string]: unknown;
}

export interface LayoutEdge {
  source: string;
  target: string;
  [key: string]: unknown;
}

export interface LayoutOptions {
  direction?: 'LR' | 'TB';
  /** Width / height of the canvas the graph will be framed in. */
  targetAspect?: number;
}

/**
 * Picks the grid column count whose resulting *total* bounding box comes closest
 * to `targetAspect`.
 *
 * Searched rather than solved in closed form: the total width is
 * `max(chainWidth, cols · pitchX)`, which makes the objective piecewise and not
 * worth inverting analytically. The search is at most 24 iterations.
 */
export function chooseGridColumns(
  isolatedCount: number,
  chainWidth: number,
  chainHeight: number,
  targetAspect: number = DEFAULT_TARGET_ASPECT,
): number {
  if (isolatedCount <= 1) return Math.max(MIN_COLS, isolatedCount);

  const aspect = targetAspect > 0 && Number.isFinite(targetAspect)
    ? targetAspect
    : DEFAULT_TARGET_ASPECT;
  const gap = chainHeight > 0 ? BAND_GAP : 0;

  let bestCols = MIN_COLS;
  let bestError = Infinity;

  const ceiling = Math.min(MAX_COLS, isolatedCount);
  for (let cols = MIN_COLS; cols <= ceiling; cols++) {
    const rows = Math.ceil(isolatedCount / cols);
    const width = Math.max(chainWidth, cols * GRID_PITCH_X);
    const height = chainHeight + gap + rows * GRID_PITCH_Y;
    if (height <= 0) continue;

    // Compare in log space so being 2x too wide and 2x too tall score equally.
    const error = Math.abs(Math.log(width / height) - Math.log(aspect));
    if (error < bestError) {
      bestError = error;
      bestCols = cols;
    }
  }

  return bestCols;
}

export interface ImpactLayoutResult<N extends LayoutNode, E extends LayoutEdge> {
  nodes: N[];
  edges: E[];
  /** Bounding box of the laid-out topology, in flow units. */
  bounds: { x: number; y: number; width: number; height: number };
}

/**
 * Computes the zoom that frames `bounds` inside a canvas, clamped so a small
 * graph is never blown up into a cartoon and a large one never collapses into
 * unreadable specks.
 */
export function fitZoomFor(
  bounds: { width: number; height: number },
  canvasWidth: number,
  canvasHeight: number,
): number {
  if (bounds.width <= 0 || bounds.height <= 0) return 1;
  if (canvasWidth <= 0 || canvasHeight <= 0) return 1;

  const raw = Math.min(
    (canvasWidth * FIT_FILL) / bounds.width,
    (canvasHeight * FIT_FILL) / bounds.height,
  );
  return Math.max(MIN_FIT_ZOOM, Math.min(MAX_FIT_ZOOM, raw));
}

/**
 * Positions an impact graph. Pure: returns new node objects and never mutates
 * the inputs.
 */
export function layoutImpactGraph<N extends LayoutNode, E extends LayoutEdge>(
  nodes: N[],
  edges: E[],
  options: LayoutOptions = {},
): ImpactLayoutResult<N, E> {
  const { direction = 'LR', targetAspect = DEFAULT_TARGET_ASPECT } = options;

  if (nodes.length === 0) {
    return { nodes: [], edges, bounds: { x: 0, y: 0, width: 0, height: 0 } };
  }

  const ids = new Set(nodes.map((n) => n.id));

  // Only edges whose endpoints both exist may reach Dagre — a dangling edge
  // makes dagre synthesise a phantom node and corrupt the ranking.
  const safeEdges = edges.filter((e) => ids.has(e.source) && ids.has(e.target));

  const connected = new Set<string>();
  safeEdges.forEach((e) => {
    connected.add(e.source);
    connected.add(e.target);
  });

  const connectedNodes = nodes.filter((n) => connected.has(n.id));
  const isolatedNodes = nodes.filter((n) => !connected.has(n.id));

  const positions = new Map<string, { x: number; y: number }>();

  // ── Connected topology: Dagre keeps the propagation hierarchy ─────────────
  let chainWidth = 0;
  let chainHeight = 0;
  let chainBottom = 0;

  if (connectedNodes.length > 0) {
    const g = new dagre.graphlib.Graph();
    g.setDefaultEdgeLabel(() => ({}));
    g.setGraph({ rankdir: direction, ranksep: 72, nodesep: 32 });

    connectedNodes.forEach((n) => {
      g.setNode(n.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
    });
    safeEdges.forEach((e) => g.setEdge(e.source, e.target));

    dagre.layout(g);

    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;

    connectedNodes.forEach((n) => {
      const p = g.node(n.id);
      // Dagre can omit a node it could not rank; fall back to the origin rather
      // than emitting NaN coordinates that would blank the canvas.
      const x = Number.isFinite(p?.x) ? p.x - NODE_WIDTH / 2 : 0;
      const y = Number.isFinite(p?.y) ? p.y - NODE_HEIGHT / 2 : 0;
      positions.set(n.id, { x, y });
      minX = Math.min(minX, x);
      minY = Math.min(minY, y);
      maxX = Math.max(maxX, x + NODE_WIDTH);
      maxY = Math.max(maxY, y + NODE_HEIGHT);
    });

    chainWidth = Number.isFinite(minX) ? maxX - minX : 0;
    chainHeight = Number.isFinite(minY) ? maxY - minY : 0;
    chainBottom = Number.isFinite(maxY) ? maxY : 0;
  }

  // ── Isolated files: a grid sized to balance the whole bounding box ────────
  if (isolatedNodes.length > 0) {
    const cols = chooseGridColumns(
      isolatedNodes.length,
      chainWidth,
      chainHeight,
      targetAspect,
    );
    const originY = connectedNodes.length > 0 ? chainBottom + BAND_GAP : 0;

    isolatedNodes.forEach((n, i) => {
      positions.set(n.id, {
        x: (i % cols) * GRID_PITCH_X,
        y: originY + Math.floor(i / cols) * GRID_PITCH_Y,
      });
    });
  }

  const laidOut = nodes.map((n) => ({
    ...n,
    position: positions.get(n.id) ?? { x: 0, y: 0 },
  })) as N[];

  // ── Bounds ───────────────────────────────────────────────────────────────
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;

  laidOut.forEach((n) => {
    const { x, y } = n.position as { x: number; y: number };
    minX = Math.min(minX, x);
    minY = Math.min(minY, y);
    maxX = Math.max(maxX, x + NODE_WIDTH);
    maxY = Math.max(maxY, y + NODE_HEIGHT);
  });

  const finite = Number.isFinite(minX) && Number.isFinite(minY);

  return {
    nodes: laidOut,
    edges,
    bounds: {
      x: finite ? minX : 0,
      y: finite ? minY : 0,
      width: finite ? maxX - minX : 0,
      height: finite ? maxY - minY : 0,
    },
  };
}
