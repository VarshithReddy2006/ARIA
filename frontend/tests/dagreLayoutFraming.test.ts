import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { applyDagreLayout, NODE_W, NODE_H } from '../src/components/interactive/graph/dagreLayout.ts';
import type { Node, Edge } from 'reactflow';

/**
 * Regression cover for File Graph initial framing.
 *
 * The large-graph layout previously used a fixed per-tier column budget
 * (6/8/10/10/12) regardless of node count. That produced pathological framing at
 * both ends of the range:
 *
 *   ~30 nodes  → a 10-wide, ~3-row band (aspect ≈ 3.3), which fitView squashed
 *                into an unreadable horizontal strip.
 *   ~500 nodes → ~40 rows stacked into 10 columns (aspect ≈ 0.6), an over-tall
 *                column with large empty margins either side.
 *
 * Column count is now derived from the node count to target ~1.6, so both cases
 * land in a readable range.
 */

function buildGraph(count: number): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = [];
  const edges: Edge[] = [];

  for (let i = 0; i < count; i++) {
    // Spread across categories so several architectural tiers are populated.
    const category =
      i % 7 === 0 ? 'entry_point'
      : i % 7 === 1 ? 'core_module'
      : i % 7 === 2 ? 'service'
      : i % 7 === 3 ? 'test'
      : 'regular';

    nodes.push({
      id: `pkg/module_${i}.py`,
      data: { label: `module_${i}.py`, raw: { category } },
      position: { x: 0, y: 0 },
    });

    if (i > 0) {
      edges.push({ id: `e${i}`, source: `pkg/module_${i - 1}.py`, target: `pkg/module_${i}.py` });
    }
  }

  return { nodes, edges };
}

function measure(nodes: Node[]) {
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;

  nodes.forEach((n) => {
    assert.strictEqual(Number.isFinite(n.position.x), true, `non-finite x on ${n.id}`);
    assert.strictEqual(Number.isFinite(n.position.y), true, `non-finite y on ${n.id}`);
    if (n.position.x < minX) minX = n.position.x;
    if (n.position.x + NODE_W > maxX) maxX = n.position.x + NODE_W;
    if (n.position.y < minY) minY = n.position.y;
    if (n.position.y + NODE_H > maxY) maxY = n.position.y + NODE_H;
  });

  const width = maxX - minX;
  const height = maxY - minY;
  return { width, height, aspect: width / height };
}

describe('applyDagreLayout initial framing', () => {
  for (const count of [30, 60, 120, 300, 500]) {
    it(`frames a ${count}-node topology within a readable aspect ratio`, () => {
      const { nodes, edges } = buildGraph(count);
      const result = applyDagreLayout(nodes, edges);

      assert.strictEqual(result.nodes.length, count, 'every node must be laid out');

      const { width, height, aspect } = measure(result.nodes);

      // Neither a shallow horizontal band nor an over-tall column.
      assert.ok(
        aspect >= 0.5 && aspect <= 2.5,
        `${count} nodes: expected aspect 0.5–2.5, got ${aspect.toFixed(2)} (${width}×${height})`,
      );
    });
  }

  it('keeps nodes from overlapping horizontally within a row', () => {
    const { nodes, edges } = buildGraph(120);
    const result = applyDagreLayout(nodes, edges);

    // Group by row (identical y) and confirm horizontal gaps clear the node width.
    const rows = new Map<number, number[]>();
    result.nodes.forEach((n) => {
      const xs = rows.get(n.position.y) ?? [];
      xs.push(n.position.x);
      rows.set(n.position.y, xs);
    });

    rows.forEach((xs, y) => {
      const sorted = [...xs].sort((a, b) => a - b);
      for (let i = 1; i < sorted.length; i++) {
        assert.ok(
          sorted[i] - sorted[i - 1] >= NODE_W,
          `row y=${y}: nodes overlap (${sorted[i - 1]} → ${sorted[i]}, need ≥ ${NODE_W})`,
        );
      }
    });
  });

  it('still uses hierarchical dagre for small neighbourhood subgraphs', () => {
    const { nodes, edges } = buildGraph(8);
    const result = applyDagreLayout(nodes, edges);

    assert.strictEqual(result.nodes.length, 8);
    result.nodes.forEach((n) => {
      assert.strictEqual(Number.isFinite(n.position.x), true);
      assert.strictEqual(Number.isFinite(n.position.y), true);
    });
  });

  it('centres the topology around the origin', () => {
    const { nodes, edges } = buildGraph(200);
    const result = applyDagreLayout(nodes, edges);
    const { width, height } = measure(result.nodes);

    const cx = result.nodes.reduce((s, n) => s + n.position.x + NODE_W / 2, 0) / result.nodes.length;
    const cy = result.nodes.reduce((s, n) => s + n.position.y + NODE_H / 2, 0) / result.nodes.length;

    // Mean node centre should sit near the origin, not drift off-canvas.
    assert.ok(Math.abs(cx) < width / 2, `x centroid ${cx} drifted outside bounds`);
    assert.ok(Math.abs(cy) < height / 2, `y centroid ${cy} drifted outside bounds`);
  });
});
