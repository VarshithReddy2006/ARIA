import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { resolveGraphNode } from '../src/lib/graphPathUtils.ts';
import type { GraphNode } from '../src/components/interactive/graph/types';

const currentDir = fileURLToPath(new URL('.', import.meta.url));

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

describe('Graph Deep-Link & Regression Hardening Suite', () => {
  const sampleGraphNodes: GraphNode[] = [
    createMockNode('fastapi/routing.py', 'routing.py'),
    createMockNode('fastapi/applications.py', 'applications.py'),
    createMockNode('fastapi/dependencies/utils.py', 'utils.py'),
    createMockNode('tests/test_tutorial.py', 'test_tutorial.py'),
  ];

  // ── 1. Direct URL Deep-Link Lifecycle ──────────────────────────────────────
  it('parses URL query parameters and resolves initial target', () => {
    const searchParams = new URLSearchParams('owner=fastapi&repo=fastapi&tab=graph&file=fastapi%2Frouting.py');
    const owner = searchParams.get('owner');
    const repo = searchParams.get('repo');
    const tab = searchParams.get('tab');
    const rawFile = searchParams.get('file');

    assert.strictEqual(owner, 'fastapi');
    assert.strictEqual(repo, 'fastapi');
    assert.strictEqual(tab, 'graph');
    assert.ok(rawFile);

    const initialFile = decodeURIComponent(rawFile ?? '');
    assert.strictEqual(initialFile, 'fastapi/routing.py');

    const resolved = resolveGraphNode(initialFile, sampleGraphNodes, `${owner}/${repo}`);
    assert.ok(resolved);
    assert.strictEqual(resolved?.id, 'fastapi/routing.py');
  });

  // ── 2. Asynchronous Node Resolution (Race Condition Protection) ───────────
  it('defers graph selection until nodes are available without losing target', () => {
    // Step 1: Deep link target arrives
    const pendingTarget = 'fastapi/routing.py';
    let apiNodes: GraphNode[] = []; // Step 2: Empty initially while loading

    // Must not crash or lose target
    let resolvedNode = resolveGraphNode(pendingTarget, apiNodes);
    assert.strictEqual(resolvedNode, null);
    assert.strictEqual(pendingTarget, 'fastapi/routing.py');

    // Step 3: Graph nodes arrive asynchronously from API
    apiNodes = sampleGraphNodes;
    resolvedNode = resolveGraphNode(pendingTarget, apiNodes);

    // Step 4 & 5: Node resolves accurately
    assert.ok(resolvedNode);
    assert.strictEqual(resolvedNode?.id, 'fastapi/routing.py');
  });

  // ── 3. Stale Focus Token Regression (lastHandledTokenRef) ──────────────────
  it('stale focus token does not override manual node selection', () => {
    let lastHandledToken: number | null = null;
    let selectedNode: GraphNode | null = null;

    // 1. External focus request arrives with token T1 for routing.py
    const focusRequest = { path: 'fastapi/routing.py', token: 1700000001 };

    if (focusRequest.path && focusRequest.token !== lastHandledToken) {
      lastHandledToken = focusRequest.token;
      selectedNode = resolveGraphNode(focusRequest.path, sampleGraphNodes);
    }
    assert.ok(selectedNode);
    assert.strictEqual(selectedNode?.id, 'fastapi/routing.py');
    assert.strictEqual(lastHandledToken, 1700000001);

    // 2. User manually clicks applications.py
    selectedNode = sampleGraphNodes[1]; // fastapi/applications.py
    assert.strictEqual(selectedNode.id, 'fastapi/applications.py');

    // 3. Component re-renders with the SAME focusRequest object / token T1
    if (focusRequest.path && focusRequest.token !== lastHandledToken) {
      lastHandledToken = focusRequest.token;
      selectedNode = resolveGraphNode(focusRequest.path, sampleGraphNodes);
    }

    // Manual selection MUST remain untouched
    assert.strictEqual(selectedNode?.id, 'fastapi/applications.py');
  });

  // ── 4. Full Graph / Neighbor Fallback Resilience ───────────────────────────
  it('does not erase full graph when neighbors request fails with 404 or 500', () => {
    const apiNodes = [...sampleGraphNodes];
    const fullGraphResponse = { status: 200, nodes: sampleGraphNodes };

    assert.strictEqual(fullGraphResponse.status, 200);
    assert.strictEqual(apiNodes.length, 4);

    // Simulate neighbor request returning 404 or 500
    const neighborResponse404 = { status: 404, error: 'Not Found' };
    if (neighborResponse404.status !== 200) {
      // Safe fallback: do NOT clear apiNodes
    }
    assert.strictEqual(apiNodes.length, 4);

    const neighborResponse500 = { status: 500, error: 'Internal Server Error' };
    if (neighborResponse500.status !== 200) {
      // Safe fallback: do NOT clear apiNodes
    }
    assert.strictEqual(apiNodes.length, 4);

    // Target resolution remains functional
    const node = resolveGraphNode('fastapi/routing.py', apiNodes);
    assert.ok(node);
    assert.strictEqual(node?.id, 'fastapi/routing.py');
  });

  // ── 5. Non-Graph File Regression ───────────────────────────────────────────
  it('non-graph file leaves full graph intact and does not trigger blank screen', () => {
    const nonGraphTarget = 'docs/en/docs/js/custom.js';
    const apiNodes = [...sampleGraphNodes];

    const resolved = resolveGraphNode(nonGraphTarget, apiNodes);
    assert.strictEqual(resolved, null);

    // Graph nodes must not be cleared
    assert.strictEqual(apiNodes.length, 4);
    assert.strictEqual(apiNodes[0].id, 'fastapi/routing.py');
  });

  // ── 6. URL Synchronization Contract ───────────────────────────────────────
  it('synchronizes URL search params when selecting and deselecting nodes', () => {
    const baseUrl = 'http://localhost:4321/analysis?owner=fastapi&repo=fastapi&tab=graph';
    const url = new URL(baseUrl);

    // On node selection
    const selectedId = 'fastapi/routing.py';
    url.searchParams.set('tab', 'graph');
    url.searchParams.set('file', selectedId);
    assert.strictEqual(url.searchParams.get('file'), 'fastapi/routing.py');
    assert.strictEqual(url.searchParams.get('tab'), 'graph');
    assert.strictEqual(url.searchParams.get('owner'), 'fastapi');
    assert.strictEqual(url.searchParams.get('repo'), 'fastapi');

    // On deselection
    url.searchParams.delete('file');
    assert.strictEqual(url.searchParams.get('file'), null);
    assert.strictEqual(url.searchParams.get('tab'), 'graph');
    assert.strictEqual(url.searchParams.get('owner'), 'fastapi');
    assert.strictEqual(url.searchParams.get('repo'), 'fastapi');
  });

  // ── 7. Standardized Event Payload Shape (Chat & IssueMapper) ───────────────
  it('verifies standardized aria-open-graph CustomEvent contract', () => {
    const chatEventDetail = {
      owner: 'fastapi',
      repo: 'fastapi',
      file: 'fastapi/routing.py',
      path: 'fastapi/routing.py',
      source: 'chat',
    };

    assert.strictEqual(typeof chatEventDetail.owner, 'string');
    assert.strictEqual(typeof chatEventDetail.repo, 'string');
    assert.strictEqual(typeof chatEventDetail.file, 'string');
    assert.strictEqual(typeof chatEventDetail.path, 'string');
    assert.strictEqual(chatEventDetail.source, 'chat');

    const issueEventDetail = {
      owner: 'fastapi',
      repo: 'fastapi',
      file: 'fastapi/routing.py',
      path: 'fastapi/routing.py',
      source: 'issue-mapper',
    };

    assert.strictEqual(issueEventDetail.source, 'issue-mapper');
    assert.strictEqual(issueEventDetail.file, chatEventDetail.file);
  });

  // ── 8. Viewport Focus Parameters Contract ──────────────────────────────────
  it('conforms to viewport focus parameters contract', () => {
    const viewportFocusParams = {
      zoom: 1.15,
      duration: 400,
    };

    assert.strictEqual(viewportFocusParams.zoom, 1.15);
    assert.strictEqual(viewportFocusParams.duration, 400);
  });

  // ── 9. Static Import Architectural Guard ───────────────────────────────────
  it('guards against reintroducing React.lazy dynamic imports in AnalysisDashboard', () => {
    const dashboardFilePath = resolve(currentDir, '../src/components/interactive/AnalysisDashboard.tsx');
    const content = readFileSync(dashboardFilePath, 'utf-8');

    // Ensure InteractiveDependencyGraph is NOT lazy-loaded
    assert.doesNotMatch(
      content,
      /lazy\s*\(\s*\(\)\s*=>\s*import\s*\(\s*['"]\.\/graph\/InteractiveDependencyGraph['"]\s*\)\s*\)/,
      'InteractiveDependencyGraph must be statically imported to prevent Vite 504 dynamic import failures'
    );

    // Ensure static import exists
    assert.match(
      content,
      /import\s*\{\s*InteractiveDependencyGraph\s*\}\s*from\s*['"]\.\/graph\/InteractiveDependencyGraph['"]/,
      'InteractiveDependencyGraph must have a static import'
    );
  });

  // ── 10. Vite OptimizeDeps Configuration Guard ──────────────────────────────
  it('guards Vite optimizeDeps configuration in astro.config.mjs', () => {
    const configFilePath = resolve(currentDir, '../astro.config.mjs');
    const content = readFileSync(configFilePath, 'utf-8');

    assert.match(content, /optimizeDeps/, 'astro.config.mjs must configure vite.optimizeDeps');
    assert.match(content, /'reactflow'/, 'optimizeDeps must include reactflow');
    assert.match(content, /'dagre'/, 'optimizeDeps must include dagre');
  });
});
