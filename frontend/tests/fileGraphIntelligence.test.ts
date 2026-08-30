import { describe, test } from 'node:test';
import assert from 'node:assert';
import { computeGraphStats, computeGraphSignals, computeBlastRadius } from '../src/components/interactive/graph/graphStats.ts';
import { CATEGORY_COLORS, CATEGORY_LABELS } from '../src/components/interactive/graph/types.ts';
import type { GraphNode, GraphEdge } from '../src/components/interactive/graph/types.ts';

describe('File Graph Architecture Intelligence — Signals & Statistics', () => {
  const sampleNodes: GraphNode[] = [
    { id: 'src/index.ts', label: 'index.ts', category: 'entry_point', degree: 3, centrality: 0.25, language: 'typescript', highlighted: false, is_focus: false },
    { id: 'src/core/engine.ts', label: 'engine.ts', category: 'core_module', degree: 6, centrality: 0.45, language: 'typescript', highlighted: false, is_focus: false },
    { id: 'src/utils/helpers.ts', label: 'helpers.ts', category: 'utility', degree: 4, centrality: 0.1, language: 'typescript', highlighted: false, is_focus: false },
    { id: 'src/services/api.ts', label: 'api.ts', category: 'service', degree: 5, centrality: 0.2, language: 'typescript', highlighted: false, is_focus: false },
    { id: 'src/models/user.ts', label: 'user.ts', category: 'domain', degree: 2, centrality: 0.05, language: 'typescript', highlighted: false, is_focus: false },
  ];

  const sampleEdges: GraphEdge[] = [
    { source: 'src/index.ts', target: 'src/core/engine.ts', relationship: 'imports' },
    { source: 'src/core/engine.ts', target: 'src/services/api.ts', relationship: 'imports' },
    { source: 'src/services/api.ts', target: 'src/utils/helpers.ts', relationship: 'imports' },
    { source: 'src/core/engine.ts', target: 'src/utils/helpers.ts', relationship: 'imports' },
    { source: 'src/core/engine.ts', target: 'src/models/user.ts', relationship: 'imports' },
    // Cycle: helpers imports engine
    { source: 'src/utils/helpers.ts', target: 'src/core/engine.ts', relationship: 'imports' },
  ];

  test('computeGraphStats detects components and cycle clusters accurately', () => {
    const stats = computeGraphStats(sampleNodes, sampleEdges);
    assert.strictEqual(stats.components, 1, 'All nodes are weakly connected into 1 component');
    assert.strictEqual(stats.cycleClusters, 1, 'Tarjan SCC detects 1 cycle cluster between engine, api, and helpers');
  });

  test('computeGraphSignals identifies most central and highest coupling nodes', () => {
    const signals = computeGraphSignals(sampleNodes, sampleEdges);
    assert.ok(signals.mostCentralNode, 'Most central node must be identified');
    assert.strictEqual(signals.mostCentralNode?.id, 'src/core/engine.ts');
    assert.strictEqual(signals.mostCentralNode?.centrality, 0.45);

    assert.ok(signals.highestCouplingNode, 'Highest coupling node must be identified');
    assert.strictEqual(signals.highestCouplingNode?.id, 'src/core/engine.ts');

    assert.strictEqual(signals.entryPointCount, 1, 'src/index.ts is the entry point');
    assert.ok(signals.architecturalStory.includes('ARIA identified'), 'Story begins with ARIA identified');
    assert.ok(signals.architecturalStory.includes('engine.ts'), 'Story references central node');
  });

  test('computeBlastRadius correctly calculates direct and transitive dependents', () => {
    // When helpers.ts changes, who is affected?
    // Direct callers: api.ts, engine.ts
    // Transitive callers from engine: index.ts
    const blast = computeBlastRadius('src/utils/helpers.ts', sampleEdges, sampleNodes);

    assert.strictEqual(blast.nodeId, 'src/utils/helpers.ts');
    assert.ok(blast.directDependents.includes('src/services/api.ts'), 'api.ts directly imports helpers.ts');
    assert.ok(blast.directDependents.includes('src/core/engine.ts'), 'engine.ts directly imports helpers.ts');
    assert.ok(blast.transitiveDependents.includes('src/index.ts'), 'index.ts transitively imports helpers.ts via engine');
    assert.strictEqual(blast.totalAffectedCount, 3);
    assert.ok(blast.affectedEntryPoints.includes('src/index.ts'), 'index.ts is the affected entry point');
    assert.ok(blast.riskLevel === 'High' || blast.riskLevel === 'Critical' || blast.riskLevel === 'Medium');
  });

  test('computeBlastRadius returns empty dependents for leaf node without callers', () => {
    const blast = computeBlastRadius('src/index.ts', sampleEdges, sampleNodes);
    assert.strictEqual(blast.directCount, 0, 'No module imports index.ts');
    assert.strictEqual(blast.transitiveCount, 0);
    assert.strictEqual(blast.totalAffectedCount, 0);
    assert.strictEqual(blast.riskLevel, 'Low');
  });

  test('Semantic categories are properly registered with distinct colors and labels', () => {
    const requiredCategories = [
      'entry_point',
      'core_module',
      'domain',
      'service',
      'controller',
      'high_coupling',
      'infrastructure',
      'utility',
      'test',
      'config',
    ];

    for (const cat of requiredCategories) {
      assert.ok(CATEGORY_COLORS[cat], `Color must exist for category ${cat}`);
      assert.ok(CATEGORY_LABELS[cat], `Label must exist for category ${cat}`);
    }
  });
});
