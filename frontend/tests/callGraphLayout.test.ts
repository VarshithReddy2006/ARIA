import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { computeCallGraphLayout, CG_NODE_W, CG_NODE_H } from '../src/components/interactive/graph/callGraphLayout.ts';

describe('computeCallGraphLayout Geometry and Resilience', () => {
  it('safely handles empty graph inputs', () => {
    const result = computeCallGraphLayout([], []);
    assert.deepStrictEqual(result, {});
  });

  it('calculates valid centered coordinates for connected nodes', () => {
    const nodes = [
      { id: 'app::main', category: 'entry_point', fan_in: 0, fan_out: 2 },
      { id: 'app::router', category: 'core_module', fan_in: 2, fan_out: 1 },
      { id: 'app::helper', category: 'regular', fan_in: 1, fan_out: 0 },
    ];
    const edges = [
      { source: 'app::main', target: 'app::router' },
      { source: 'app::router', target: 'app::helper' },
    ];

    const positions = computeCallGraphLayout(nodes, edges);
    assert.strictEqual(Object.keys(positions).length, 3);
    assert.strictEqual(typeof positions['app::main'].x, 'number');
    assert.strictEqual(typeof positions['app::main'].y, 'number');
    assert.strictEqual(typeof positions['app::router'].x, 'number');
    assert.strictEqual(typeof positions['app::router'].y, 'number');
  });

  it('produces balanced aspect ratio for 60-node call graph without vertical strip collapse', () => {
    const nodes = [];
    const edges = [];

    // 20 entry functions
    for (let i = 0; i < 20; i++) {
      nodes.push({ id: `app::endpoint_${i}`, category: 'entry_point', fan_in: 0, fan_out: 2 });
    }

    // 20 middle services
    for (let i = 0; i < 20; i++) {
      nodes.push({ id: `app::service_${i}`, category: 'core_module', fan_in: 3, fan_out: 2 });
      edges.push({ source: `app::endpoint_${i}`, target: `app::service_${i}` });
    }

    // 20 leaf helpers
    for (let i = 0; i < 20; i++) {
      nodes.push({ id: `app::util_${i}`, category: 'regular', fan_in: 2, fan_out: 0 });
      edges.push({ source: `app::service_${i}`, target: `app::util_${i}` });
    }

    const positions = computeCallGraphLayout(nodes, edges);
    assert.strictEqual(Object.keys(positions).length, 60);

    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    let maxY = -Infinity;

    Object.values(positions).forEach((pos) => {
      assert.strictEqual(Number.isFinite(pos.x), true);
      assert.strictEqual(Number.isFinite(pos.y), true);
      if (pos.x < minX) minX = pos.x;
      if (pos.x + CG_NODE_W > maxX) maxX = pos.x + CG_NODE_W;
      if (pos.y < minY) minY = pos.y;
      if (pos.y + CG_NODE_H > maxY) maxY = pos.y + CG_NODE_H;
    });

    const width = maxX - minX;
    const height = maxY - minY;
    const aspectRatio = width / height;

    // Aspect ratio must be balanced (between 0.5 and 4.0), NOT 0.1 (tall vertical strip)!
    assert.ok(
      aspectRatio >= 0.5 && aspectRatio <= 4.0,
      `Expected balanced aspect ratio (0.5 - 4.0), got ${aspectRatio} (width: ${width}, height: ${height})`
    );

    // Height must be reasonably bounded (not 5000px+)
    assert.ok(height <= 1500, `Expected height <= 1500px, got ${height}`);
  });
});
