import { describe, test } from 'node:test';
import assert from 'node:assert';
import {
  buildArchitectureClusters,
  buildAbstractedGraph,
  getClusterId,
  deriveClusterRole,
} from '../src/components/interactive/graph/architectureClustering.ts';
import type { GraphNode, GraphEdge } from '../src/components/interactive/graph/types.ts';

describe('Architecture Clustering & Progressive Abstraction Engine', () => {
  const sampleNodes: GraphNode[] = [
    { id: 'ria/api/server.py', label: 'server.py', category: 'entry_point', degree: 4, centrality: 0.35, language: 'python', highlighted: false, is_focus: false },
    { id: 'ria/api/routes.py', label: 'routes.py', category: 'controller', degree: 3, centrality: 0.25, language: 'python', highlighted: false, is_focus: false },
    { id: 'ria/domain/models.py', label: 'models.py', category: 'domain', degree: 5, centrality: 0.40, language: 'python', highlighted: false, is_focus: false },
    { id: 'ria/domain/entities.py', label: 'entities.py', category: 'domain', degree: 2, centrality: 0.15, language: 'python', highlighted: false, is_focus: false },
    { id: 'ria/services/engine.py', label: 'engine.py', category: 'service', degree: 6, centrality: 0.50, language: 'python', highlighted: true, is_focus: false },
    { id: 'ria/services/pipeline.py', label: 'pipeline.py', category: 'service', degree: 3, centrality: 0.20, language: 'python', highlighted: false, is_focus: false },
    { id: 'ria/infra/database.py', label: 'database.py', category: 'infrastructure', degree: 2, centrality: 0.10, language: 'python', highlighted: false, is_focus: false },
    { id: 'ria/tests/test_engine.py', label: 'test_engine.py', category: 'test', degree: 1, centrality: 0.05, language: 'python', highlighted: false, is_focus: false },
  ];

  const sampleEdges: GraphEdge[] = [
    // Internal API edge
    { source: 'ria/api/server.py', target: 'ria/api/routes.py', relationship: 'imports' },
    // API -> Services
    { source: 'ria/api/routes.py', target: 'ria/services/engine.py', relationship: 'imports' },
    // Internal Services edge
    { source: 'ria/services/engine.py', target: 'ria/services/pipeline.py', relationship: 'imports' },
    // Services -> Domain
    { source: 'ria/services/engine.py', target: 'ria/domain/models.py', relationship: 'imports' },
    // Internal Domain edge
    { source: 'ria/domain/models.py', target: 'ria/domain/entities.py', relationship: 'imports' },
    // Services -> Infra
    { source: 'ria/services/engine.py', target: 'ria/infra/database.py', relationship: 'imports' },
    // Test -> Services
    { source: 'ria/tests/test_engine.py', target: 'ria/services/engine.py', relationship: 'imports' },
  ];

  test('getClusterId correctly extracts top-level or module cluster name', () => {
    assert.strictEqual(getClusterId(sampleNodes[0]), 'ria/api');
    assert.strictEqual(getClusterId(sampleNodes[2]), 'ria/domain');
    assert.strictEqual(getClusterId(sampleNodes[4]), 'ria/services');
    assert.strictEqual(getClusterId({ id: 'main.py', label: 'main.py', category: 'entry_point', degree: 1, centrality: 0.1, language: 'py', highlighted: false, is_focus: false }), 'Entry Points');
  });

  test('deriveClusterRole assigns truthful architectural descriptions', () => {
    const apiRole = deriveClusterRole('ria/api', [sampleNodes[0], sampleNodes[1]]);
    assert.match(apiRole, /API Gateways/i);

    const domainRole = deriveClusterRole('ria/domain', [sampleNodes[2], sampleNodes[3]]);
    assert.match(domainRole, /Domain Logic/i);

    const serviceRole = deriveClusterRole('ria/services', [sampleNodes[4], sampleNodes[5]]);
    assert.match(serviceRole, /Business Services/i);

    const testRole = deriveClusterRole('ria/tests', [sampleNodes[7]]);
    assert.match(testRole, /Test Suites/i);
  });

  test('buildArchitectureClusters computes truthful internal and external edge counts', () => {
    const clusters = buildArchitectureClusters(sampleNodes, sampleEdges);
    assert.ok(clusters.length >= 4);

    const serviceCluster = clusters.find((c) => c.id === 'ria/services');
    assert.ok(serviceCluster);
    assert.strictEqual(serviceCluster.fileCount, 2);
    assert.strictEqual(serviceCluster.internalEdgeCount, 1); // engine -> pipeline
    assert.strictEqual(serviceCluster.externalEdgeCount, 4); // routes->engine, engine->models, engine->db, test->engine
    assert.strictEqual(serviceCluster.mostCentralModule?.id, 'ria/services/engine.py');
  });

  test('buildAbstractedGraph Level 1 (SYSTEM) aggregates nodes into clusters with inter-cluster edges', () => {
    const { nodes, edges, clusters } = buildAbstractedGraph(sampleNodes, sampleEdges, 'system', new Set());

    // Should return cluster nodes
    assert.ok(nodes.every((n) => n.id.startsWith('cluster:')));
    assert.ok(clusters.length > 0);

    // Edges connect cluster IDs
    assert.ok(edges.every((e) => e.source.startsWith('cluster:') && e.target.startsWith('cluster:')));
    // Must contain aggregated relationship text
    assert.ok(edges.some((e) => e.relationship.includes('deps')));
  });

  test('buildAbstractedGraph Level 2 (COMPONENTS) expands only the active/expanded cluster', () => {
    const expanded = new Set<string>(['ria/services']);
    const { nodes } = buildAbstractedGraph(sampleNodes, sampleEdges, 'components', expanded);

    // Services files are expanded
    assert.ok(nodes.some((n) => n.id === 'ria/services/engine.py'));
    assert.ok(nodes.some((n) => n.id === 'ria/services/pipeline.py'));

    // Domain files are collapsed as a single cluster node
    assert.ok(nodes.some((n) => n.id === 'cluster:ria/domain'));
    assert.ok(!nodes.some((n) => n.id === 'ria/domain/models.py'));
  });

  test('buildAbstractedGraph Level 3 (FILES) returns full uncollapsed file graph', () => {
    const { nodes, edges } = buildAbstractedGraph(sampleNodes, sampleEdges, 'files', new Set());
    assert.strictEqual(nodes.length, sampleNodes.length);
    assert.strictEqual(edges.length, sampleEdges.length);
  });
});
