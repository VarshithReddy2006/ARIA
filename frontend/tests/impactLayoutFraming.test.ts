import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import {
  layoutImpactGraph,
  chooseGridColumns,
  fitZoomFor,
  NODE_WIDTH,
  NODE_HEIGHT,
  MIN_FIT_ZOOM,
  MAX_FIT_ZOOM,
} from '../src/components/interactive/graph/impactLayout.ts';

/**
 * Regression cover for the impact graph's initial framing.
 *
 * Two bugs are pinned here:
 *
 *  1. Dagre put every edge-less node in rank 0, stacking them into a column one
 *     node wide and hundreds tall.
 *  2. Balancing only the isolated grid still left the *total* box roughly square,
 *     so a wide short canvas had to zoom out to fit a tall graph and the nodes
 *     rendered as specks.
 */

interface N {
  id: string;
  position?: { x: number; y: number };
  [key: string]: unknown;
}
interface E {
  source: string;
  target: string;
  [key: string]: unknown;
}

function isolatedOnly(count: number): N[] {
  return Array.from({ length: count }, (_, i) => ({ id: `file-${i}.ts` }));
}

/** `chains` propagation chains of `len` nodes each, plus `isolated` loose files. */
function impactShape(chains: number, len: number, isolated: number) {
  const nodes: N[] = [];
  const edges: E[] = [];

  for (let c = 0; c < chains; c++) {
    for (let i = 0; i < len; i++) {
      const id = `chain${c}-step${i}.ts`;
      nodes.push({ id });
      if (i > 0) edges.push({ source: `chain${c}-step${i - 1}.ts`, target: id });
    }
  }
  for (let i = 0; i < isolated; i++) nodes.push({ id: `loose-${i}.ts` });

  return { nodes, edges };
}

function aspect(bounds: { width: number; height: number }): number {
  if (bounds.height === 0) return Infinity;
  return bounds.width / bounds.height;
}

describe('layoutImpactGraph framing', () => {
  test('does not stack isolated files into a single tall column', () => {
    // The reported shape: 30 directly affected files, 5 short chains.
    const { nodes, edges } = impactShape(5, 3, 30);
    const out = layoutImpactGraph<N, E>(nodes, edges);

    const xs = new Set(out.nodes.map((n) => n.position!.x));
    assert.ok(xs.size > 3, `expected several columns, got ${xs.size}`);
    assert.ok(aspect(out.bounds) > 0.35, 'still a vertical sliver');
  });

  for (const count of [8, 30, 80, 200, 600]) {
    test(`frames ${count} isolated files within a readable aspect ratio`, () => {
      const out = layoutImpactGraph<N, E>(isolatedOnly(count), []);
      const a = aspect(out.bounds);
      assert.ok(
        a >= 0.4 && a <= 6,
        `aspect ${a.toFixed(2)} outside the readable band for ${count} nodes`,
      );
    });
  }

  /*
    The behaviour that fixes small nodes: a wider canvas must produce a wider
    total bounding box, so the fit does not have to shrink to accommodate height.
  */
  test('adapts the total bounding box toward the requested canvas aspect', () => {
    const { nodes, edges } = impactShape(5, 3, 30);

    const wide = layoutImpactGraph<N, E>(nodes, edges, { targetAspect: 2.4 });
    const square = layoutImpactGraph<N, E>(nodes, edges, { targetAspect: 0.8 });

    assert.ok(
      aspect(wide.bounds) > aspect(square.bounds),
      `a 2.4 target should be wider than a 0.8 target ` +
        `(${aspect(wide.bounds).toFixed(2)} vs ${aspect(square.bounds).toFixed(2)})`,
    );
  });

  test('a wide canvas target yields a zoom that keeps nodes readable', () => {
    // A realistic desktop impact canvas: ~830 x 500 css px.
    const CANVAS_W = 830;
    const CANVAS_H = 500;
    const { nodes, edges } = impactShape(5, 3, 30);

    const tuned = layoutImpactGraph<N, E>(nodes, edges, {
      targetAspect: CANVAS_W / CANVAS_H,
    });
    const zoom = fitZoomFor(tuned.bounds, CANVAS_W, CANVAS_H);

    // Below ~0.45 a 200x40 node is too small to read its label.
    assert.ok(zoom >= 0.45, `fit zoom ${zoom.toFixed(2)} would render tiny nodes`);
  });

  test('keeps connected chains laid out left to right', () => {
    const { nodes, edges } = impactShape(1, 4, 0);
    const out = layoutImpactGraph<N, E>(nodes, edges);

    const byId = new Map(out.nodes.map((n) => [n.id, n.position!]));
    for (let i = 1; i < 4; i++) {
      const prev = byId.get(`chain0-step${i - 1}.ts`)!;
      const cur = byId.get(`chain0-step${i}.ts`)!;
      assert.ok(cur.x > prev.x, `step ${i} should sit right of step ${i - 1}`);
    }
  });

  test('places the isolated grid clear of the connected topology', () => {
    const { nodes, edges } = impactShape(2, 3, 12);
    const out = layoutImpactGraph<N, E>(nodes, edges);
    const byId = new Map(out.nodes.map((n) => [n.id, n.position!]));

    let chainMaxY = -Infinity;
    for (const n of out.nodes) {
      if (n.id.startsWith('chain')) chainMaxY = Math.max(chainMaxY, byId.get(n.id)!.y);
    }
    for (const n of out.nodes) {
      if (n.id.startsWith('loose')) {
        assert.ok(
          byId.get(n.id)!.y > chainMaxY,
          'isolated files must not overlap the propagation chains',
        );
      }
    }
  });

  test('ignores edges pointing at nodes that are not present', () => {
    const nodes: N[] = [{ id: 'a.ts' }, { id: 'b.ts' }];
    const edges: E[] = [
      { source: 'a.ts', target: 'b.ts' },
      { source: 'a.ts', target: 'ghost.ts' },
      { source: 'missing.ts', target: 'b.ts' },
    ];

    const out = layoutImpactGraph<N, E>(nodes, edges);
    assert.equal(out.nodes.length, 2);
    for (const n of out.nodes) {
      assert.ok(Number.isFinite(n.position!.x), `${n.id} has a non-finite x`);
      assert.ok(Number.isFinite(n.position!.y), `${n.id} has a non-finite y`);
    }
  });

  test('handles an empty graph without throwing', () => {
    const out = layoutImpactGraph<N, E>([], []);
    assert.equal(out.nodes.length, 0);
    assert.equal(out.bounds.width, 0);
    assert.equal(out.bounds.height, 0);
  });

  test("never mutates the caller's nodes", () => {
    const nodes: N[] = [{ id: 'a.ts' }, { id: 'b.ts' }];
    layoutImpactGraph<N, E>(nodes, [{ source: 'a.ts', target: 'b.ts' }]);
    assert.equal(nodes[0].position, undefined);
    assert.equal(nodes[1].position, undefined);
  });

  test('reports bounds that enclose every node', () => {
    const { nodes, edges } = impactShape(3, 3, 20);
    const out = layoutImpactGraph<N, E>(nodes, edges);
    const { x, y, width, height } = out.bounds;

    for (const n of out.nodes) {
      const p = n.position!;
      assert.ok(p.x >= x - 0.001, `${n.id} left of bounds`);
      assert.ok(p.y >= y - 0.001, `${n.id} above bounds`);
      assert.ok(p.x + NODE_WIDTH <= x + width + 0.001, `${n.id} right of bounds`);
      assert.ok(p.y + NODE_HEIGHT <= y + height + 0.001, `${n.id} below bounds`);
    }
  });

  test('grid column count stays clamped and responds to the target', () => {
    assert.equal(chooseGridColumns(1, 0, 0), 1);
    assert.ok(chooseGridColumns(30, 0, 0) >= 1);
    assert.ok(chooseGridColumns(100000, 0, 0) <= 24, 'column count must stay clamped');
    assert.ok(
      chooseGridColumns(60, 0, 0, 3.0) > chooseGridColumns(60, 0, 0, 0.6),
      'a wider target must use more columns',
    );
  });

  test('falls back to the default target when given a nonsense aspect', () => {
    const base = chooseGridColumns(40, 500, 300);
    assert.equal(chooseGridColumns(40, 500, 300, Number.NaN), base);
    assert.equal(chooseGridColumns(40, 500, 300, 0), base);
    assert.equal(chooseGridColumns(40, 500, 300, -3), base);
  });

  test('fit zoom is clamped at both ends', () => {
    // Tiny graph in a huge canvas would otherwise blow up past 1:1.
    const small = fitZoomFor({ width: 100, height: 50 }, 4000, 3000);
    assert.ok(small <= MAX_FIT_ZOOM, `zoom ${small} exceeded the cap`);

    // Enormous graph in a small canvas must not collapse below the floor.
    const huge = fitZoomFor({ width: 90000, height: 60000 }, 800, 400);
    assert.ok(huge >= MIN_FIT_ZOOM, `zoom ${huge} fell under the floor`);
  });

  test('fit zoom degrades safely on empty or zero-size input', () => {
    assert.equal(fitZoomFor({ width: 0, height: 0 }, 800, 400), 1);
    assert.equal(fitZoomFor({ width: 500, height: 500 }, 0, 0), 1);
  });

  test('node dimensions stay in sync with the rendered node size', () => {
    assert.equal(NODE_WIDTH, 200);
    assert.equal(NODE_HEIGHT, 40);
  });
});
