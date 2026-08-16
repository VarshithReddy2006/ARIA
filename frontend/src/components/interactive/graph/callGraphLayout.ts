export const CG_NODE_W = 220;
export const CG_NODE_H = 75;

export interface CgNodeLike {
  id: string;
  category?: string;
  fan_in?: number;
  fan_out?: number;
  is_recursive?: boolean;
}

export interface CgEdgeLike {
  source: string;
  target: string;
  ambiguous?: boolean;
}

/**
 * Computes an aspect-ratio-balanced architectural tier & cluster layout for Call Graphs.
 * Prevents functions from clustering into a single narrow vertical column or overly stretched band.
 * Ensures the graph topology occupies 70-80% of the viewport centered on $(0, 0)$.
 */
export function computeCallGraphLayout(
  nodes: CgNodeLike[],
  edges: CgEdgeLike[],
): Record<string, { x: number; y: number }> {
  if (!nodes || nodes.length === 0) return {};

  // Build degree & adjacency maps
  const inDegreeMap = new Map<string, number>();
  const outDegreeMap = new Map<string, number>();
  const adj = new Map<string, string[]>();

  nodes.forEach((n) => {
    inDegreeMap.set(n.id, 0);
    outDegreeMap.set(n.id, 0);
    adj.set(n.id, []);
  });

  edges.forEach((e) => {
    if (adj.has(e.source)) adj.get(e.source)!.push(e.target);
    if (inDegreeMap.has(e.target)) inDegreeMap.set(e.target, (inDegreeMap.get(e.target) || 0) + 1);
    if (outDegreeMap.has(e.source)) outDegreeMap.set(e.source, (outDegreeMap.get(e.source) || 0) + 1);
  });

  // Classify nodes into 5 architectural horizontal tiers:
  // Tier 0: Root Entry Points (inDegree === 0 with callees, or category === 'entry_point')
  // Tier 1: Core Hubs / High Fan-In (inDegree >= 3 or fan_in >= 3 or category === 'core_module')
  // Tier 2: Domain Logic & Intermediary Callers (inDegree > 0 && outDegree > 0)
  // Tier 3: Leaf / Terminal Functions (outDegree === 0 && inDegree > 0)
  // Tier 4: Isolated / Standalone Functions (inDegree === 0 && outDegree === 0)
  const tiers: CgNodeLike[][] = [[], [], [], [], []];

  nodes.forEach((n) => {
    const inDeg = inDegreeMap.get(n.id) || (n.fan_in ?? 0);
    const outDeg = outDegreeMap.get(n.id) || (n.fan_out ?? 0);

    if (n.category === 'entry_point' || (inDeg === 0 && outDeg > 0)) {
      tiers[0].push(n);
    } else if (n.category === 'core_module' || inDeg >= 3 || (n.fan_in ?? 0) >= 3) {
      tiers[1].push(n);
    } else if (inDeg > 0 && outDeg > 0) {
      tiers[2].push(n);
    } else if (outDeg === 0 && inDeg > 0) {
      tiers[3].push(n);
    } else {
      tiers[4].push(n);
    }
  });

  // Sort within each tier by total connectivity descending (hubs first)
  tiers.forEach((tier) => {
    tier.sort((a, b) => {
      const scoreA = (a.fan_in ?? inDegreeMap.get(a.id) ?? 0) + (a.fan_out ?? outDegreeMap.get(a.id) ?? 0);
      const scoreB = (b.fan_in ?? inDegreeMap.get(b.id) ?? 0) + (b.fan_out ?? outDegreeMap.get(b.id) ?? 0);
      return scoreB - scoreA;
    });
  });

  const positions: Record<string, { x: number; y: number }> = {};
  let currentX = 0;

  const X_COL_STEP = CG_NODE_W + 40; // 260px
  const Y_ROW_STEP = CG_NODE_H + 35; // 110px

  // Compute balanced rows per column targeting ~1.6 aspect ratio:
  // sqrt(1.5 * totalNodes) gives equalized grid dimensions
  const maxRowsPerCol = Math.max(6, Math.round(Math.sqrt(1.5 * nodes.length)));

  tiers.forEach((tierNodes) => {
    if (tierNodes.length === 0) return;

    const colCount = Math.ceil(tierNodes.length / maxRowsPerCol);

    for (let col = 0; col < colCount; col++) {
      const colStart = col * maxRowsPerCol;
      const colEnd = Math.min(colStart + maxRowsPerCol, tierNodes.length);
      const colNodes = tierNodes.slice(colStart, colEnd);
      const rowsInCol = colNodes.length;

      colNodes.forEach((node, rowIdx) => {
        const x = currentX + col * X_COL_STEP;
        const y = (rowIdx - (rowsInCol - 1) / 2) * Y_ROW_STEP;

        positions[node.id] = {
          x: Math.round(x),
          y: Math.round(y),
        };
      });
    }

    currentX += colCount * X_COL_STEP + 50;
  });

  // Center bounding box around (0, 0)
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;

  Object.values(positions).forEach((pos) => {
    if (pos.x < minX) minX = pos.x;
    if (pos.x + CG_NODE_W > maxX) maxX = pos.x + CG_NODE_W;
    if (pos.y < minY) minY = pos.y;
    if (pos.y + CG_NODE_H > maxY) maxY = pos.y + CG_NODE_H;
  });

  const offsetX = (minX + maxX) / 2;
  const offsetY = (minY + maxY) / 2;

  const normalizedPositions: Record<string, { x: number; y: number }> = {};
  Object.keys(positions).forEach((id) => {
    normalizedPositions[id] = {
      x: positions[id].x - offsetX,
      y: positions[id].y - offsetY,
    };
  });

  return normalizedPositions;
}
