import { describe, test } from 'node:test';
import assert from 'node:assert';
import {
  computeCallGraphSignals,
  extractExecutionFlows,
  extractBranchPoints,
  extractFailureBoundaries,
  simulateChangeImpact,
  buildAbstractedCallGraph,
  tracePathToNode,
  traceDetailedRoute,
  findRecursiveClusters,
  rankHotspots,
  generateCallGraphQuestions,
  deriveConfidenceLevel,
  deriveExecutionRole,
  generateWhyItMatters,
} from '../src/components/interactive/graph/callGraphIntelligence.ts';
import type { CgNode, CgEdge } from '../src/components/interactive/graph/callGraphIntelligence.ts';

describe('Call Graph Behavioral & Execution Intelligence Engine', () => {
  const sampleNodes: CgNode[] = [
    {
      id: 'Backend/app.py::main',
      label: 'main',
      category: 'entry_point',
      degree: 2,
      centrality: 0.2,
      language: 'python',
      highlighted: false,
      is_focus: false,
      qualified: 'Backend.app.main',
      file_path: 'Backend/app.py',
      fan_in: 0,
      fan_out: 2,
      is_recursive: false,
      symbol_type: 'function',
    },
    {
      id: 'Backend/app.py::validate_request',
      label: 'validate_request',
      category: 'controller',
      degree: 4,
      centrality: 0.35,
      language: 'python',
      highlighted: false,
      is_focus: false,
      qualified: 'Backend.app.validate_request',
      file_path: 'Backend/app.py',
      fan_in: 1,
      fan_out: 3,
      is_recursive: false,
      symbol_type: 'function',
    },
    {
      id: 'Backend/features.py::extract_features',
      label: 'extract_features',
      category: 'service',
      degree: 6,
      centrality: 0.55,
      language: 'python',
      highlighted: true,
      is_focus: false,
      qualified: 'Backend.features.extract_features',
      file_path: 'Backend/features.py',
      fan_in: 5,
      fan_out: 1,
      is_recursive: false,
      symbol_type: 'function',
    },
    {
      id: 'Backend/db.py::save_record',
      label: 'save_record',
      category: 'infrastructure',
      degree: 3,
      centrality: 0.3,
      language: 'python',
      highlighted: false,
      is_focus: false,
      qualified: 'Backend.db.save_record',
      file_path: 'Backend/db.py',
      fan_in: 2,
      fan_out: 0,
      is_recursive: false,
      symbol_type: 'function',
    },
    {
      id: 'Backend/utils.py::recurse_helper',
      label: 'recurse_helper',
      category: 'high_coupling',
      degree: 2,
      centrality: 0.1,
      language: 'python',
      highlighted: false,
      is_focus: false,
      qualified: 'Backend.utils.recurse_helper',
      file_path: 'Backend/utils.py',
      fan_in: 1,
      fan_out: 1,
      is_recursive: true,
      symbol_type: 'function',
    },
    {
      id: 'Backend/utils.py::mutual_a',
      label: 'mutual_a',
      category: 'regular',
      degree: 2,
      centrality: 0.15,
      language: 'python',
      file_path: 'Backend/utils.py',
      fan_in: 1,
      fan_out: 1,
      is_recursive: true,
      symbol_type: 'function',
    },
    {
      id: 'Backend/utils.py::mutual_b',
      label: 'mutual_b',
      category: 'regular',
      degree: 2,
      centrality: 0.15,
      language: 'python',
      file_path: 'Backend/utils.py',
      fan_in: 1,
      fan_out: 1,
      is_recursive: true,
      symbol_type: 'function',
    },
  ];

  const sampleEdges: CgEdge[] = [
    { source: 'Backend/app.py::main', target: 'Backend/app.py::validate_request', relationship: 'calls', ambiguous: false },
    { source: 'Backend/app.py::validate_request', target: 'Backend/features.py::extract_features', relationship: 'calls', ambiguous: false },
    { source: 'Backend/app.py::validate_request', target: 'Backend/db.py::save_record', relationship: 'calls', ambiguous: false },
    { source: 'Backend/features.py::extract_features', target: 'Backend/db.py::save_record', relationship: 'calls', ambiguous: false },
    // Self recursive call
    { source: 'Backend/utils.py::recurse_helper', target: 'Backend/utils.py::recurse_helper', relationship: 'calls', ambiguous: false },
    // Mutual recursive calls
    { source: 'Backend/utils.py::mutual_a', target: 'Backend/utils.py::mutual_b', relationship: 'calls', ambiguous: false },
    { source: 'Backend/utils.py::mutual_b', target: 'Backend/utils.py::mutual_a', relationship: 'calls', ambiguous: false },
  ];

  test('deriveExecutionRole maps AST nodes to temporal execution semantics', () => {
    assert.strictEqual(deriveExecutionRole(sampleNodes[0]), 'ENTRY');
    assert.strictEqual(deriveExecutionRole(sampleNodes[1]), 'BRANCH');
    assert.strictEqual(deriveExecutionRole(sampleNodes[3]), 'SIDE EFFECT');
    assert.strictEqual(deriveExecutionRole(sampleNodes[4]), 'RECURSIVE');
  });

  test('computeCallGraphSignals calculates execution story, narrative paragraphs, and failure boundaries', () => {
    const signals = computeCallGraphSignals(sampleNodes, sampleEdges);

    assert.strictEqual(signals.entryPointCount, 1);
    assert.strictEqual(signals.primaryEntryPoint?.id, 'Backend/app.py::main');
    assert.strictEqual(signals.mostCentralSymbol?.id, 'Backend/features.py::extract_features');
    assert.strictEqual(signals.highestFanInSymbol?.id, 'Backend/features.py::extract_features');
    assert.strictEqual(signals.highestFanInSymbol?.fan_in, 5);
    assert.strictEqual(signals.recursiveSymbolsCount, 3);
    assert.strictEqual(signals.recursiveClustersCount, 2);
    assert.ok(signals.executionStory);
    assert.strictEqual(signals.executionStory?.entryCount, 1);
    assert.ok(signals.executionStory?.whatHappensFirst.length > 0);
    assert.ok(signals.executionStory?.narrativeParagraphs.length > 0);
    assert.ok(signals.failureBoundaries && signals.failureBoundaries.length > 0);
  });

  test('extractExecutionFlows identifies ranked deterministic execution flows with steps', () => {
    const flows = extractExecutionFlows(sampleNodes, sampleEdges, 5);

    assert.ok(flows.length >= 1);
    const topFlow = flows[0];
    assert.ok(topFlow.path.includes('Backend/app.py::main'));
    assert.ok(topFlow.length >= 2);
    assert.ok(topFlow.steps && topFlow.steps.length >= 2);
    assert.strictEqual(topFlow.steps[0].role, 'ENTRY');
    assert.ok(topFlow.rankingReason.includes('entry point') || topFlow.rankingReason.includes('centrality'));
  });

  test('extractFailureBoundaries identifies database, validation, recursive, and hub failure boundaries', () => {
    const flows = extractExecutionFlows(sampleNodes, sampleEdges, 5);
    const boundaries = extractFailureBoundaries(sampleNodes, sampleEdges, flows);

    assert.ok(boundaries.length >= 3);
    const dbBoundary = boundaries.find((b) => b.boundaryType === 'Database / Persistence');
    const valBoundary = boundaries.find((b) => b.boundaryType === 'Validation Gate');
    const recBoundary = boundaries.find((b) => b.boundaryType === 'Recursive Cycle');

    assert.ok(dbBoundary);
    assert.ok(dbBoundary?.whyItIsRisky.includes('Database') || dbBoundary?.whyItIsRisky.includes('mutation'));
    assert.ok(valBoundary);
    assert.ok(recBoundary);
  });

  test('extractBranchPoints detects divergent execution routes', () => {
    const branchPoints = extractBranchPoints(sampleNodes, sampleEdges);

    assert.ok(branchPoints.length >= 1);
    const validateBranch = branchPoints.find((b) => b.nodeId === 'Backend/app.py::validate_request');
    assert.ok(validateBranch);
    assert.strictEqual(validateBranch?.branchCount, 2);
    assert.ok(validateBranch?.divergentBranches.some((d) => d.targetId === 'Backend/features.py::extract_features'));
  });

  test('simulateChangeImpact calculates downstream behavioral cascade and narrative', () => {
    const impact = simulateChangeImpact('Backend/app.py::validate_request', sampleNodes, sampleEdges);

    assert.strictEqual(impact.targetId, 'Backend/app.py::validate_request');
    assert.ok(impact.downstreamCount >= 2);
    assert.ok(impact.upstreamCount >= 1);
    assert.strictEqual(impact.staticGraphImpact, true);
    assert.ok(impact.narrativeImpact.includes('validate_request'));
    assert.ok(['Low', 'Medium', 'High', 'Critical'].includes(impact.riskRating));
  });

  test('traceDetailedRoute separates upstream and downstream paths', () => {
    const path = ['Backend/app.py::main', 'Backend/app.py::validate_request', 'Backend/features.py::extract_features'];
    const details = traceDetailedRoute(path, sampleNodes, sampleEdges, 'Backend/app.py::validate_request');

    assert.strictEqual(details.pathLength, 3);
    assert.deepStrictEqual(details.upstreamPath, ['Backend/app.py::main', 'Backend/app.py::validate_request']);
    assert.deepStrictEqual(details.downstreamPath, ['Backend/app.py::validate_request', 'Backend/features.py::extract_features']);
    assert.strictEqual(details.steps[0].role, 'ENTRY');
    assert.strictEqual(details.steps[1].isTarget, true);
  });

  test('findRecursiveClusters detects both self-loops and mutual cycles', () => {
    const clusters = findRecursiveClusters(sampleNodes, sampleEdges);

    assert.strictEqual(clusters.length, 2);
    const selfCluster = clusters.find((c) => c.isSelfLoop);
    const mutualCluster = clusters.find((c) => !c.isSelfLoop);

    assert.ok(selfCluster);
    assert.strictEqual(selfCluster?.symbols[0], 'Backend/utils.py::recurse_helper');
    assert.ok(mutualCluster);
    assert.strictEqual(mutualCluster?.cycleLength, 2);
    assert.ok(mutualCluster?.symbols.includes('Backend/utils.py::mutual_a'));
    assert.ok(mutualCluster?.symbols.includes('Backend/utils.py::mutual_b'));
  });

  test('rankHotspots correctly scores and ranks high route-participation symbols', () => {
    const hotspots = rankHotspots(sampleNodes, sampleEdges, 'top5');

    assert.ok(hotspots.length >= 1);
    assert.strictEqual(hotspots[0].rank, 1);
    assert.ok(hotspots[0].riskReason.length > 0);
  });

  test('generateCallGraphQuestions produces repository-grounded behavioral questions', () => {
    const signals = computeCallGraphSignals(sampleNodes, sampleEdges);
    const questions = generateCallGraphQuestions(sampleNodes[2], signals);

    assert.strictEqual(questions.length, 3);
    assert.ok(questions.some((q) => q.includes('extract_features')));
    assert.ok(questions.some((q) => q.includes('Backend/features.py')));
  });
});
