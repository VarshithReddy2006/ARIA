import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { applyDagreLayout, NODE_W, NODE_H } from '../src/components/interactive/graph/dagreLayout.ts';
import type { Node, Edge } from 'reactflow';

describe('applyDagreLayout Safety and Resilience', () => {
  it('successfully calculates positions for valid connected nodes', () => {
    const nodes: Node[] = [
      { id: 'fastapi/routing.py', data: { label: 'routing.py' }, position: { x: 0, y: 0 } },
      { id: 'fastapi/applications.py', data: { label: 'applications.py' }, position: { x: 0, y: 0 } },
    ];
    const edges: Edge[] = [
      { id: 'e1', source: 'fastapi/applications.py', target: 'fastapi/routing.py' },
    ];

    const result = applyDagreLayout(nodes, edges);
    assert.strictEqual(result.nodes.length, 2);
    assert.strictEqual(result.edges.length, 1);
    assert.strictEqual(typeof result.nodes[0].position.x, 'number');
    assert.strictEqual(typeof result.nodes[0].position.y, 'number');
    assert.strictEqual(typeof result.nodes[1].position.x, 'number');
    assert.strictEqual(typeof result.nodes[1].position.y, 'number');
  });

  it('safely handles edges referencing nonexistent or filtered-out nodes without crashing', () => {
    const nodes: Node[] = [
      { id: 'fastapi/routing.py', data: { label: 'routing.py' }, position: { x: 0, y: 0 } },
      { id: 'fastapi/applications.py', data: { label: 'applications.py' }, position: { x: 0, y: 0 } },
    ];
    const edgesWithDangling: Edge[] = [
      { id: 'e1', source: 'fastapi/applications.py', target: 'fastapi/routing.py' },
      { id: 'e2', source: 'fastapi/routing.py', target: 'MISSING_TARGET_NODE.py' },
      { id: 'e3', source: 'MISSING_SOURCE_NODE.py', target: 'fastapi/applications.py' },
    ];

    assert.doesNotThrow(() => {
      const result = applyDagreLayout(nodes, edgesWithDangling);
      assert.strictEqual(result.nodes.length, 2);
      assert.strictEqual(result.edges.length, 3);
      assert.strictEqual(result.nodes[0].id, 'fastapi/routing.py');
      assert.strictEqual(result.nodes[1].id, 'fastapi/applications.py');
    });
  });

  it('safely handles empty graph inputs', () => {
    const result = applyDagreLayout([], []);
    assert.deepStrictEqual(result.nodes, []);
    assert.deepStrictEqual(result.edges, []);
  });

  it('safely lays out isolated nodes with zero edges', () => {
    const nodes: Node[] = [
      { id: 'isolated1.py', data: { label: 'isolated1.py' }, position: { x: 0, y: 0 } },
      { id: 'isolated2.py', data: { label: 'isolated2.py' }, position: { x: 0, y: 0 } },
    ];
    const result = applyDagreLayout(nodes, []);
    assert.strictEqual(result.nodes.length, 2);
    assert.strictEqual(typeof result.nodes[0].position.x, 'number');
    assert.strictEqual(typeof result.nodes[1].position.x, 'number');
  });

  it('produces balanced aspect ratio for 500-node repository graph without horizontal strip collapse', () => {
    const mock500Nodes: Node[] = [];
    const mockEdges: Edge[] = [];

    // 20 entry points / core modules
    for (let i = 0; i < 20; i++) {
      mock500Nodes.push({
        id: `fastapi/core_${i}.py`,
        data: { label: `core_${i}.py`, raw: { category: i < 5 ? 'entry_point' : 'core_module', degree: 15 } },
        position: { x: 0, y: 0 },
      });
    }

    // 80 services and utils
    for (let i = 0; i < 80; i++) {
      mock500Nodes.push({
        id: `fastapi/service_${i}.py`,
        data: { label: `service_${i}.py`, raw: { category: 'service', degree: 4 } },
        position: { x: 0, y: 0 },
      });
      mockEdges.push({
        id: `e_srv_${i}`,
        source: `fastapi/core_${i % 20}.py`,
        target: `fastapi/service_${i}.py`,
      });
    }

    // 400 test files
    for (let i = 0; i < 400; i++) {
      mock500Nodes.push({
        id: `tests/test_${i}.py`,
        data: { label: `test_${i}.py`, raw: { category: 'test', degree: 1 } },
        position: { x: 0, y: 0 },
      });
      mockEdges.push({
        id: `e_test_${i}`,
        source: `tests/test_${i}.py`,
        target: `fastapi/core_${i % 20}.py`,
      });
    }

    const result = applyDagreLayout(mock500Nodes, mockEdges);
    assert.strictEqual(result.nodes.length, 500);

    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    let maxY = -Infinity;

    result.nodes.forEach((n) => {
      assert.strictEqual(Number.isFinite(n.position.x), true);
      assert.strictEqual(Number.isFinite(n.position.y), true);
      if (n.position.x < minX) minX = n.position.x;
      if (n.position.x + NODE_W > maxX) maxX = n.position.x + NODE_W;
      if (n.position.y < minY) minY = n.position.y;
      if (n.position.y + NODE_H > maxY) maxY = n.position.y + NODE_H;
    });

    const width = maxX - minX;
    const height = maxY - minY;
    const aspectRatio = width / height;

    // Aspect ratio must be well-balanced (between 0.4 and 3.5), NOT 300:1 !
    assert.ok(
      aspectRatio >= 0.4 && aspectRatio <= 3.5,
      `Expected balanced aspect ratio (0.4-3.5), but got ${aspectRatio} (width: ${width}, height: ${height})`
    );

    // Height must be substantial (e.g. > 1000px), not a flat 100-300px
    assert.ok(height >= 1000, `Expected height >= 1000px, but got ${height}`);
  });
});
