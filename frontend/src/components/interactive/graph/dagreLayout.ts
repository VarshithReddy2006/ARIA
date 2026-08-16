import dagre from 'dagre';
import type { Node, Edge } from 'reactflow';

export const NODE_W = 200;
export const NODE_H = 40;

interface NodeMetadata {
  category?: string;
  degree?: number;
  label?: string;
  is_focus?: boolean;
}

/**
 * Assigns an architectural tier (0-4) based on node category and filename patterns.
 */
function getArchitecturalTier(nodeId: string, category?: string, label?: string): number {
  const normId = nodeId.toLowerCase();
  const normCat = (category || '').toLowerCase();
  const normLabel = (label || '').toLowerCase();

  // Tier 4: Test suites & test verification
  if (
    normCat === 'test' ||
    normId.includes('/test') ||
    normId.includes('test_') ||
    normId.startsWith('test') ||
    normLabel.startsWith('test_')
  ) {
    return 4;
  }

  // Tier 0: Entry Points & Public Gateways
  if (
    normCat === 'entry_point' ||
    normId.endsWith('main.py') ||
    normId.endsWith('app.py') ||
    normId.endsWith('applications.py') ||
    normId.endsWith('routing.py') ||
    normId.endsWith('index.ts') ||
    normId.endsWith('server.ts')
  ) {
    return 0;
  }

  // Tier 1: Core Domain Modules & High Coupling Hubs
  if (
    normCat === 'core_module' ||
    normCat === 'high_coupling' ||
    normCat === 'controller'
  ) {
    return 1;
  }

  // Tier 2: Domain Services & Middleware
  if (
    normCat === 'service' ||
    normCat === 'directory'
  ) {
    return 2;
  }

  // Tier 3: Utilities, Shared Libraries, Config
  return 3;
}

/**
 * Applies architectural tier & cluster layout for large repository topologies,
 * and hierarchical Dagre layout for small neighborhood subgraphs.
 * 
 * Prevents 500-node graphs from collapsing into a 100,000px wide by 300px high horizontal strip.
 * Ensures the graph topology occupies 70-80% of the viewport with balanced vertical & horizontal distribution.
 */
export function applyDagreLayout(
  rfNodes: Node[],
  rfEdges: Edge[],
  direction: 'TB' | 'LR' = 'TB',
): { nodes: Node[]; edges: Edge[] } {
  if (!rfNodes || rfNodes.length === 0) {
    return { nodes: [], edges: rfEdges || [] };
  }

  const nodeIds = new Set(rfNodes.map((n) => n.id));
  const validEdges = (rfEdges || []).filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target));

  // For small graphs (<= 25 nodes, such as local focus/neighbors mode), use classic Dagre
  if (rfNodes.length <= 25) {
    const g = new dagre.graphlib.Graph();
    g.setDefaultEdgeLabel(() => ({}));
    g.setGraph({ rankdir: direction, ranksep: 90, nodesep: 50 });

    rfNodes.forEach((n) => g.setNode(n.id, { width: NODE_W, height: NODE_H }));
    validEdges.forEach((e) => g.setEdge(e.source, e.target));

    dagre.layout(g);

    const laid = rfNodes.map((n) => {
      const pos = g.node(n.id);
      return {
        ...n,
        position: pos ? { x: pos.x - NODE_W / 2, y: pos.y - NODE_H / 2 } : { x: 0, y: 0 },
      };
    });
    return { nodes: laid, edges: rfEdges };
  }

  // ── Large Graph Multi-Tier Architectural Layout ──────────────────────────
  // Compute degrees for centrality sorting
  const degreeMap = new Map<string, number>();
  rfNodes.forEach((n) => degreeMap.set(n.id, 0));
  validEdges.forEach((e) => {
    degreeMap.set(e.source, (degreeMap.get(e.source) || 0) + 1);
    degreeMap.set(e.target, (degreeMap.get(e.target) || 0) + 1);
  });

  // Group nodes by architectural tier
  const tiers: Node[][] = [[], [], [], [], []];
  rfNodes.forEach((n) => {
    const meta = (n.data?.raw || {}) as NodeMetadata;
    const tierIdx = getArchitecturalTier(n.id, meta.category, meta.label || n.data?.label);
    tiers[tierIdx].push(n);
  });

  // Sort nodes within each tier by degree (highest connected first in center)
  tiers.forEach((tier) => {
    tier.sort((a, b) => (degreeMap.get(b.id) || 0) - (degreeMap.get(a.id) || 0));
  });

  const laidNodes: Node[] = [];
  let currentY = 0;

  // Spacing constants
  const X_SPACING = NODE_W + 40; // 240px
  const Y_ROW_SPACING = NODE_H + 45; // 85px
  const TIER_GAP = 120; // gap between different tiers

  /*
    Column count is derived from the node count rather than fixed per tier.
    A fixed budget produced pathological framing at both ends of the range: a
    30-node graph filled a 10-wide row and only ~3 rows deep (a wide, shallow
    band that fitView then squashed), while a 500-node graph stacked ~40 rows
    into 10 columns (an over-tall column).

    Solving for a target aspect A:
        width  = cols * X_SPACING
        height ≈ (total / cols) * Y_ROW_SPACING
        A      = width / height   →   cols = sqrt(A * total * Y / X)

    Tier gaps add a little height on top, so small graphs land slightly taller
    than the target — which reads better than a shallow strip.
  */
  const TARGET_ASPECT = 1.6;
  const targetCols = Math.min(
    24,
    Math.max(4, Math.round(Math.sqrt((TARGET_ASPECT * rfNodes.length * Y_ROW_SPACING) / X_SPACING))),
  );

  tiers.forEach((tierNodes) => {
    if (tierNodes.length === 0) return;

    const maxCols = Math.max(1, Math.min(targetCols, tierNodes.length));
    const rowCount = Math.ceil(tierNodes.length / maxCols);

    for (let row = 0; row < rowCount; row++) {
      const rowStartIndex = row * maxCols;
      const rowEndIndex = Math.min(rowStartIndex + maxCols, tierNodes.length);
      const rowNodes = tierNodes.slice(rowStartIndex, rowEndIndex);
      const colsInThisRow = rowNodes.length;

      rowNodes.forEach((node, colIdx) => {
        // Center row nodes horizontally around X = 0
        const x = (colIdx - (colsInThisRow - 1) / 2) * X_SPACING;
        const y = currentY + row * Y_ROW_SPACING;

        laidNodes.push({
          ...node,
          position: {
            x: Math.round(x),
            y: Math.round(y),
          },
        });
      });
    }

    currentY += rowCount * Y_ROW_SPACING + TIER_GAP;
  });

  // Center bounding box around (0, 0)
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;

  laidNodes.forEach((n) => {
    if (n.position.x < minX) minX = n.position.x;
    if (n.position.x + NODE_W > maxX) maxX = n.position.x + NODE_W;
    if (n.position.y < minY) minY = n.position.y;
    if (n.position.y + NODE_H > maxY) maxY = n.position.y + NODE_H;
  });

  const offsetX = (minX + maxX) / 2;
  const offsetY = (minY + maxY) / 2;

  const normalizedNodes = laidNodes.map((n) => ({
    ...n,
    position: {
      x: n.position.x - offsetX,
      y: n.position.y - offsetY,
    },
  }));

  return { nodes: normalizedNodes, edges: rfEdges };
}
