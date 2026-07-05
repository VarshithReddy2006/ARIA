/**
 * Unit tests for the API client.
 *
 * Uses a mock HTTP server to avoid requiring a running backend.
 * Tests cover: health, getRecentRepos, getAnalysis, getFileSymbols,
 * getDependencyGraph, getCallGraph, getAPISurface, and error handling.
 */

import * as assert from 'assert';
import * as http from 'http';
import { AddressInfo } from 'net';

// We need to test the client without a real VS Code instance.
// The vscode module is aliased to ./mocks/vscode in package.json
// Set config overrides per test via global.__vscodeConfig__
const mockConfig: Record<string, unknown> = {
  backendUrl: '',      // set per test
  apiToken: '',
  requestTimeoutMs: 5000,
};

// Override vscode config for this test suite
(global as unknown as Record<string, unknown>).__vscodeConfig__ = mockConfig;

import { RepoIntelligenceClient, extractErrorMessage } from '../api';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function startMockServer(
  handler: (req: http.IncomingMessage, res: http.ServerResponse) => void
): Promise<{ server: http.Server; url: string }> {
  return new Promise((resolve, reject) => {
    const server = http.createServer(handler);
    server.listen(0, '127.0.0.1', () => {
      const port = (server.address() as AddressInfo).port;
      resolve({ server, url: `http://127.0.0.1:${port}` });
    });
    server.on('error', reject);
  });
}

function stopServer(server: http.Server): Promise<void> {
  return new Promise((resolve, reject) => {
    server.close((err) => (err ? reject(err) : resolve()));
  });
}

function jsonResponse(res: http.ServerResponse, body: unknown, status = 200): void {
  res.writeHead(status, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(body));
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('RepoIntelligenceClient', () => {
  let server: http.Server;
  let client: RepoIntelligenceClient;

  afterEach(async () => {
    if (server) {
      await stopServer(server);
    }
  });

  // ── health ──────────────────────────────────────────────────────────────

  it('health() returns parsed response', async () => {
    const body = {
      backend: 'online',
      llm_provider: 'deepseek',
      llm_model: 'deepseek-ai/deepseek-v4-flash',
      embedding_provider: 'BAAI/bge-small-en-v1.5',
      vector_db: 'chromadb',
      status: 'healthy',
    };
    ({ server } = await startMockServer((_req, res) => jsonResponse(res, body)));
    mockConfig.backendUrl = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
    client = new RepoIntelligenceClient();

    const result = await client.health();
    assert.strictEqual(result.status, 'healthy');
    assert.strictEqual(result.llm_provider, 'deepseek');
  });

  // ── getRecentRepos ──────────────────────────────────────────────────────

  it('getRecentRepos() returns array of repos', async () => {
    const body = [
      { name: 'owner/repo', url: 'https://github.com/owner/repo', tech_stack: ['Python'], analyzed_at: 'Just now' },
    ];
    ({ server } = await startMockServer((_req, res) => jsonResponse(res, body)));
    mockConfig.backendUrl = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
    client = new RepoIntelligenceClient();

    const repos = await client.getRecentRepos();
    assert.strictEqual(repos.length, 1);
    assert.strictEqual(repos[0].name, 'owner/repo');
  });

  // ── getFileSymbols ──────────────────────────────────────────────────────

  it('getFileSymbols() returns symbols for a file', async () => {
    const body = {
      file: 'backend/api.py',
      repo: 'owner/repo',
      symbol_count: 2,
      symbols: [
        { name: 'health', qualified: 'health', symbol_type: 'function', file_path: 'backend/api.py', line_number: 10, language: 'python', parent_class: null },
        { name: 'MyClass', qualified: 'MyClass', symbol_type: 'class', file_path: 'backend/api.py', line_number: 20, language: 'python', parent_class: null },
      ],
    };
    ({ server } = await startMockServer((_req, res) => jsonResponse(res, body)));
    mockConfig.backendUrl = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
    client = new RepoIntelligenceClient();

    const result = await client.getFileSymbols('owner', 'repo', 'backend/api.py');
    assert.strictEqual(result.symbol_count, 2);
    assert.strictEqual(result.symbols[0].name, 'health');
  });

  // ── getDependencyGraph ──────────────────────────────────────────────────

  it('getDependencyGraph() returns nodes and edges', async () => {
    const body = {
      nodes: [
        { id: 'a.py', data: { label: 'a.py' }, position: { x: 0, y: 0 } },
        { id: 'b.py', data: { label: 'b.py' }, position: { x: 100, y: 0 } },
      ],
      edges: [{ id: 'e1', source: 'a.py', target: 'b.py' }],
    };
    ({ server } = await startMockServer((_req, res) => jsonResponse(res, body)));
    mockConfig.backendUrl = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
    client = new RepoIntelligenceClient();

    const graph = await client.getDependencyGraph('owner', 'repo');
    assert.strictEqual(graph.nodes.length, 2);
    assert.strictEqual(graph.edges.length, 1);
  });

  // ── getAPISurfaceStats ──────────────────────────────────────────────────

  it('getAPISurfaceStats() returns stats object', async () => {
    const body = {
      total_symbols: 100,
      public_count: 40,
      internal_count: 30,
      private_count: 20,
      deprecated_count: 5,
      experimental_count: 2,
      route_count: 8,
      orphan_public_count: 3,
      by_language: { python: 90, typescript: 10 },
    };
    ({ server } = await startMockServer((_req, res) => jsonResponse(res, body)));
    mockConfig.backendUrl = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
    client = new RepoIntelligenceClient();

    const stats = await client.getAPISurfaceStats('owner', 'repo');
    assert.strictEqual(stats.total_symbols, 100);
    assert.strictEqual(stats.public_count, 40);
  });

  // ── Error handling ──────────────────────────────────────────────────────

  it('rejects with error message on HTTP 404', async () => {
    const body = { detail: 'Repository not found' };
    ({ server } = await startMockServer((_req, res) => jsonResponse(res, body, 404)));
    mockConfig.backendUrl = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
    client = new RepoIntelligenceClient();

    await assert.rejects(
      () => client.getAnalysis('owner', 'nonexistent'),
      (err: Error) => {
        assert.ok(err.message.includes('Repository not found') || err.message.includes('404'));
        return true;
      }
    );
  });

  it('rejects with timeout error when server hangs', async () => {
    ({ server } = await startMockServer((_req, _res) => {
      // Never respond
    }));
    mockConfig.backendUrl = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
    mockConfig.requestTimeoutMs = 200;
    client = new RepoIntelligenceClient();

    await assert.rejects(
      () => client.health(),
      (err: Error) => {
        assert.ok(err.message.toLowerCase().includes('timed out'));
        return true;
      }
    );
    mockConfig.requestTimeoutMs = 5000;
  });

  it('generateExecutionPlan() calls /execution-plan endpoint (regression RIVSC-200)', async () => {
    let requestedUrl = '';
    let requestedMethod = '';
    ({ server } = await startMockServer((req, res) => {
      requestedUrl = req.url || '';
      requestedMethod = req.method || '';
      jsonResponse(res, { status: 'success' });
    }));
    mockConfig.backendUrl = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
    client = new RepoIntelligenceClient();

    await client.generateExecutionPlan('owner', 'repo');
    assert.strictEqual(requestedUrl, '/api/repositories/owner/repo/execution-plan');
    assert.strictEqual(requestedMethod, 'POST');
  });
});

// ---------------------------------------------------------------------------
// extractErrorMessage tests
// ---------------------------------------------------------------------------

describe('extractErrorMessage', () => {
  it('handles Error instances', () => {
    assert.strictEqual(extractErrorMessage(new Error('boom')), 'boom');
  });
  it('handles string input', () => {
    assert.strictEqual(extractErrorMessage('oops'), 'oops');
  });
  it('handles unknown input gracefully', () => {
    const msg = extractErrorMessage(null);
    assert.ok(typeof msg === 'string' && msg.length > 0);
  });
  it('handles undefined input gracefully', () => {
    const msg = extractErrorMessage(undefined);
    assert.ok(typeof msg === 'string' && msg.length > 0);
  });
});
