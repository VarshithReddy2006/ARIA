import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { resolveGraphNode } from '../src/lib/graphPathUtils.ts';
import type { GraphNode } from '../src/components/interactive/graph/types';

function createMockNode(id: string, label?: string): GraphNode {
  return {
    id,
    label: label ?? id.split('/').pop() ?? id,
    category: 'entry_point',
    degree: 5,
    centrality: 0.05,
    language: 'Python',
    highlighted: false,
    is_focus: false,
  };
}

describe('resolveGraphNode', () => {
  const sampleNodes: GraphNode[] = [
    createMockNode('fastapi/routing.py', 'routing.py'),
    createMockNode('fastapi/__init__.py', '__init__.py'),
    createMockNode('fastapi/dependencies/utils.py', 'utils.py'),
    createMockNode('tests/test_security_api_key_header_description.py', 'test_security_api_key_header_description.py'),
    createMockNode('fastapi/applications.py', 'applications.py'),
  ];

  it('resolves exact node.id match', () => {
    const node = resolveGraphNode('fastapi/routing.py', sampleNodes);
    assert.ok(node);
    assert.strictEqual(node?.id, 'fastapi/routing.py');
  });

  it('resolves case-insensitive exact match', () => {
    const node = resolveGraphNode('FASTAPI/ROUTING.PY', sampleNodes);
    assert.ok(node);
    assert.strictEqual(node?.id, 'fastapi/routing.py');
  });

  it('resolves normalized path match with ./ and Windows backslashes', () => {
    const nodeFromDotSlash = resolveGraphNode('./fastapi/routing.py', sampleNodes);
    assert.ok(nodeFromDotSlash);
    assert.strictEqual(nodeFromDotSlash?.id, 'fastapi/routing.py');

    const nodeFromBackslash = resolveGraphNode('fastapi\\routing.py', sampleNodes);
    assert.ok(nodeFromBackslash);
    assert.strictEqual(nodeFromBackslash?.id, 'fastapi/routing.py');
  });

  it('resolves URL-encoded graph targets', () => {
    const node = resolveGraphNode('fastapi%2Frouting.py', sampleNodes);
    assert.ok(node);
    assert.strictEqual(node?.id, 'fastapi/routing.py');
  });

  it('resolves repository-prefixed match', () => {
    const node = resolveGraphNode('fastapi/fastapi/routing.py', sampleNodes, 'fastapi');
    assert.ok(node);
    assert.strictEqual(node?.id, 'fastapi/routing.py');
  });

  it('resolves suffix match when target is prefixed by src or subpath', () => {
    const nodesWithSrc: GraphNode[] = [
      createMockNode('src/fastapi/routing.py'),
      createMockNode('src/fastapi/applications.py'),
    ];
    const node = resolveGraphNode('fastapi/routing.py', nodesWithSrc);
    assert.ok(node);
    assert.strictEqual(node?.id, 'src/fastapi/routing.py');
  });

  it('resolves unique basename fallback match', () => {
    const node = resolveGraphNode('test_security_api_key_header_description.py', sampleNodes);
    assert.ok(node);
    assert.strictEqual(node?.id, 'tests/test_security_api_key_header_description.py');
  });

  it('rejects ambiguous basename when multiple nodes share the same filename', () => {
    const ambiguousNodes: GraphNode[] = [
      createMockNode('fastapi/routing.py'),
      createMockNode('legacy/routing.py'),
      createMockNode('fastapi/applications.py'),
    ];
    // "routing.py" alone is ambiguous and must not resolve
    const node = resolveGraphNode('routing.py', ambiguousNodes);
    assert.strictEqual(node, null);

    // Full exact paths must still resolve correctly
    const exact1 = resolveGraphNode('fastapi/routing.py', ambiguousNodes);
    assert.ok(exact1);
    assert.strictEqual(exact1?.id, 'fastapi/routing.py');

    const exact2 = resolveGraphNode('legacy/routing.py', ambiguousNodes);
    assert.ok(exact2);
    assert.strictEqual(exact2?.id, 'legacy/routing.py');
  });

  it('returns null for empty target or empty nodes array', () => {
    assert.strictEqual(resolveGraphNode('', sampleNodes), null);
    assert.strictEqual(resolveGraphNode('fastapi/routing.py', []), null);
    assert.strictEqual(resolveGraphNode('nonexistent/file.py', sampleNodes), null);
  });
});
