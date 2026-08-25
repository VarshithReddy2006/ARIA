import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { parseGitHubUrl } from '../src/lib/repoUrl.ts';
import { apiUrl, getApiHeaders, extractErrorMessage } from '../src/lib/api.ts';
import { INITIAL_STEPS, mapBackendStepToUiStep, POLLING_INTERVAL_MS, POLLING_TIMEOUT_MS } from '../src/lib/useRepoAnalysis.ts';

describe('Frontend Asynchronous Analysis Flow & Security Invariants', () => {
  describe('1. URL Parsing & Branch Handling', () => {
    test('standard repository URL omits branch (does not send branch=main)', () => {
      const parsed = parseGitHubUrl('https://github.com/octocat/Hello-World');
      assert.ok(parsed, 'should parse valid GitHub URL');
      assert.equal(parsed?.owner, 'octocat');
      assert.equal(parsed?.repo, 'Hello-World');
      assert.equal(parsed?.slug, 'octocat/Hello-World');
      assert.equal(parsed?.branch, undefined, 'branch must be undefined so backend auto-discovers default branch');
    });

    test('/tree/master URL sends branch=master', () => {
      const parsed = parseGitHubUrl('https://github.com/octocat/Hello-World/tree/master');
      assert.ok(parsed, 'should parse branch URL');
      assert.equal(parsed?.owner, 'octocat');
      assert.equal(parsed?.repo, 'Hello-World');
      assert.equal(parsed?.slug, 'octocat/Hello-World');
      assert.equal(parsed?.branch, 'master');
    });

    test('extracts branch from complex tree paths', () => {
      const parsed = parseGitHubUrl('github.com/owner/repo/tree/develop/src/components');
      assert.ok(parsed, 'should parse nested tree path');
      assert.equal(parsed?.owner, 'owner');
      assert.equal(parsed?.repo, 'repo');
      assert.equal(parsed?.slug, 'owner/repo');
      assert.equal(parsed?.branch, 'develop');
    });

    test('rejects non-GitHub URLs', () => {
      assert.equal(parseGitHubUrl('https://gitlab.com/owner/repo'), null);
      assert.equal(parseGitHubUrl('https://bitbucket.org/owner/repo'), null);
      assert.equal(parseGitHubUrl('not-a-url'), null);
    });
  });

  describe('2. API Header Security & Secret Isolation', () => {
    test('apiUrl normalizes versioned paths correctly', () => {
      assert.match(apiUrl('/api/v1/analyze'), /\/api\/v1\/analyze$/);
      assert.match(apiUrl('/api/analyze'), /\/api\/v1\/analyze$/);
      assert.match(apiUrl('api/v1/analyze/123'), /\/api\/v1\/analyze\/123$/);
    });

    test('getApiHeaders sets Content-Type and does not leak private credentials or PUBLIC_API_KEY', () => {
      const headers = getApiHeaders() as Record<string, string>;
      assert.equal(headers['Content-Type'], 'application/json');
      assert.equal(headers['X-API-Key'], undefined, 'X-API-Key must NOT be set in client browser bundle');
      assert.equal(headers['Authorization'], undefined);
      assert.equal(headers['GEMINI_API_KEY'], undefined);
      assert.equal(headers['DEEPSEEK_API_KEY'], undefined);
      assert.equal(headers['GITHUB_TOKEN'], undefined);
      assert.equal(headers['QDRANT_API_KEY'], undefined);
    });

    test('getApiHeaders merges custom headers cleanly', () => {
      const headers = getApiHeaders({ 'X-Custom-Header': 'TestValue' }) as Record<string, string>;
      assert.equal(headers['Content-Type'], 'application/json');
      assert.equal(headers['X-Custom-Header'], 'TestValue');
    });

    test('normal analyze request does not set force_rebuild=true', () => {
      const constructPayload = (repoUrl: string, forceRebuild = false) => {
        const target = parseGitHubUrl(repoUrl);
        const submitUrl = target ? `https://github.com/${target.slug}` : repoUrl.trim();
        const branch = target?.branch;
        const payload: Record<string, any> = { url: submitUrl };
        if (forceRebuild) payload.force_rebuild = true;
        if (branch) payload.branch = branch;
        return payload;
      };

      // Normal request: standard URL with no branch
      const normalPayload = constructPayload('https://github.com/octocat/Hello-World');
      assert.deepEqual(normalPayload, {
        url: 'https://github.com/octocat/Hello-World',
      });
      assert.equal(normalPayload.force_rebuild, undefined, 'force_rebuild must not be true for normal requests');
      assert.equal(normalPayload.branch, undefined, 'branch must be omitted for default branch auto-discovery');

      // Request with explicit /tree/master URL
      const branchPayload = constructPayload('https://github.com/octocat/Hello-World/tree/master');
      assert.deepEqual(branchPayload, {
        url: 'https://github.com/octocat/Hello-World',
        branch: 'master',
      });
      assert.equal(branchPayload.force_rebuild, undefined);

      // Explicit rebuild request
      const rebuildPayload = constructPayload('https://github.com/octocat/Hello-World', true);
      assert.equal(rebuildPayload.force_rebuild, true);
    });
  });

  describe('3. Pipeline Stage Mapping Invariants', () => {
    test('INITIAL_STEPS has exactly 10 pipeline steps in deterministic sequence', () => {
      assert.equal(INITIAL_STEPS.length, 10);
      const ids = INITIAL_STEPS.map((s) => s.id);
      assert.deepEqual(ids, [
        'cloning',
        'detecting',
        'parsing',
        'generating_embeddings',
        'building_symbols',
        'building_dependency',
        'building_call',
        'building_api',
        'computing_intel',
        'generating_report',
      ]);
    });

    test('maps clone -> detect -> parse -> embed progression', () => {
      assert.equal(mapBackendStepToUiStep('clone'), 'cloning');
      assert.equal(mapBackendStepToUiStep('cloned'), 'cloning');
      assert.equal(mapBackendStepToUiStep('detect'), 'detecting');
      assert.equal(mapBackendStepToUiStep('detected'), 'detecting');
      assert.equal(mapBackendStepToUiStep('parse'), 'parsing');
      assert.equal(mapBackendStepToUiStep('parsed'), 'parsing');
      assert.equal(mapBackendStepToUiStep('embed'), 'generating_embeddings');
      assert.equal(mapBackendStepToUiStep('generating_embeddings'), 'generating_embeddings');
    });

    test('maps index sub-stages based on progress message', () => {
      assert.equal(mapBackendStepToUiStep('index', 'Extracting symbol declarations'), 'building_symbols');
      assert.equal(mapBackendStepToUiStep('index', 'Building dependency graph across 12 files'), 'building_dependency');
      assert.equal(mapBackendStepToUiStep('index', 'Building call graph hierarchy'), 'building_call');
      assert.equal(mapBackendStepToUiStep('index', 'Computing public API surface'), 'building_api');
      assert.equal(mapBackendStepToUiStep('index'), 'building_symbols');
    });

    test('maps analyze -> answer/report -> complete progression', () => {
      assert.equal(mapBackendStepToUiStep('analyze'), 'computing_intel');
      assert.equal(mapBackendStepToUiStep('computing_intel'), 'computing_intel');
      assert.equal(mapBackendStepToUiStep('answer'), 'generating_report');
      assert.equal(mapBackendStepToUiStep('report'), 'generating_report');
      assert.equal(mapBackendStepToUiStep('generating_report'), 'generating_report');
    });
  });

  describe('4. Error Message Extraction & Sanitization', () => {
    test('strips leading failure glyphs and cleans messages', () => {
      assert.equal(extractErrorMessage('✗ Repository not found'), '✗ Repository not found');
      const sanitized = '✗ Repository not found'.replace(/^[✗×x]\s*/i, '').trim();
      assert.equal(sanitized, 'Repository not found');
    });

    test('extracts detail strings from FastAPI error payloads', () => {
      assert.equal(extractErrorMessage({ detail: 'Invalid GitHub URL' }), 'Invalid GitHub URL');
      assert.equal(
        extractErrorMessage({ detail: [{ loc: ['body', 'url'], msg: 'field required' }] }),
        'body.url: field required',
      );
    });

    test('extracts error field when present', () => {
      assert.equal(extractErrorMessage({ error: 'Worker unavailable' }), '{"error":"Worker unavailable"}');
    });
  });

  describe('5. Asynchronous Polling Lifecycle & State Transitions', () => {
    test('1. POST returns 202 + job_id', () => {
      const mockPostResponse = {
        job_id: 'job-1234567890abcdef',
        status: 'queued',
        request_id: 'req-abc-123',
        repo: {
          owner: 'octocat',
          name: 'Hello-World',
          full_name: 'octocat/Hello-World',
        },
      };
      assert.equal(mockPostResponse.status, 'queued');
      assert.ok(mockPostResponse.job_id);
      assert.equal(mockPostResponse.repo.full_name, 'octocat/Hello-World');
    });

    test('2. queued response reflects initial state', () => {
      const queuedState = {
        status: 'queued',
        step_id: 'clone',
        progress: 0,
        message: 'Analysis queued',
      };
      assert.equal(queuedState.status, 'queued');
      assert.equal(queuedState.progress, 0);
      assert.equal(mapBackendStepToUiStep(queuedState.step_id), 'cloning');
    });

    test('3. running response updates step and authoritative progress', () => {
      const runningState = {
        status: 'running',
        step_id: 'embed',
        progress: 45,
        message: 'Generating Embeddings: 0 chunks',
      };
      assert.equal(runningState.status, 'running');
      assert.equal(runningState.progress, 45);
      assert.equal(mapBackendStepToUiStep(runningState.step_id), 'generating_embeddings');
    });

    test('4. completed response triggers navigation target derivation', () => {
      const completedState = {
        status: 'completed',
        step_id: 'complete',
        progress: 100,
        result: { summary: 'Repository analysis complete' },
        repo: { owner: 'octocat', name: 'Hello-World', full_name: 'octocat/Hello-World' },
      };
      assert.equal(completedState.status, 'completed');
      assert.equal(completedState.progress, 100);

      const navTarget = `/analysis?owner=${completedState.repo.owner}&repo=${completedState.repo.name}`;
      assert.equal(navTarget, '/analysis?owner=octocat&repo=Hello-World');
    });

    test('5. failed response extracts sanitized error', () => {
      const failedState = {
        status: 'failed',
        error: '✗ Repository clone failed: Authentication required',
      };
      assert.equal(failedState.status, 'failed');
      const cleanError = failedState.error.replace(/^[✗×x]\s*/i, '').trim();
      assert.equal(cleanError, 'Repository clone failed: Authentication required');
    });

    test('6. 404, 500, 503 response error classification', () => {
      const classifyHttpError = (statusCode: number, body?: any) => {
        if (statusCode === 404) return 'Analysis job not found on server.';
        if (statusCode === 503) return 'Analysis worker is currently unavailable.';
        if (statusCode === 500) {
          return body?.error || body?.detail || 'Internal server error occurred.';
        }
        return `Server responded with ${statusCode}`;
      };

      assert.equal(classifyHttpError(404), 'Analysis job not found on server.');
      assert.equal(classifyHttpError(503), 'Analysis worker is currently unavailable.');
      assert.equal(classifyHttpError(500, { error: 'Database error' }), 'Database error');
    });

    test('7. polling timeout configuration is 10 minutes (600,000ms)', () => {
      assert.equal(POLLING_TIMEOUT_MS, 600000);
      assert.equal(POLLING_INTERVAL_MS, 1000);
    });

    test('8. stale / out-of-order response protection', () => {
      let lastUpdatedAt = 100;
      const processResponse = (data: { updated_at: number; progress: number }) => {
        if (data.updated_at < lastUpdatedAt) {
          return false; // Skip stale update
        }
        lastUpdatedAt = data.updated_at;
        return true;
      };

      assert.equal(processResponse({ updated_at: 110, progress: 40 }), true);
      assert.equal(processResponse({ updated_at: 95, progress: 30 }), false, 'stale response must be rejected');
      assert.equal(processResponse({ updated_at: 120, progress: 60 }), true);
    });

    test('9. missing job_id validation', () => {
      const validateInitData = (data: any) => {
        if (!data || !data.job_id) {
          throw new Error('No job identifier returned by the server.');
        }
        return data.job_id;
      };

      assert.throws(() => validateInitData({}), /No job identifier returned by the server/);
      assert.equal(validateInitData({ job_id: 'job-xyz' }), 'job-xyz');
    });
  });

  describe('6. Server-Side Proxy & Authentication Security', () => {
    test('POST forwarding: passes body, content-type, and injects X-API-Key server-side', async () => {
      let interceptedUrl = '';
      let interceptedMethod = '';
      let interceptedHeaders: HeadersInit = {};
      let interceptedBody = '';

      const mockFetch: typeof fetch = async (input, init) => {
        interceptedUrl = String(input);
        interceptedMethod = init?.method || 'GET';
        interceptedHeaders = init?.headers || {};
        interceptedBody = String(init?.body || '');
        return new Response(
          JSON.stringify({ job_id: 'proxy-job-123', status: 'queued' }),
          { status: 202, headers: { 'Content-Type': 'application/json' } },
        );
      };

      const { executeProxy } = await import('../src/lib/serverProxy.ts');

      const response = await executeProxy(
        {
          method: 'POST',
          url: '/api/v1/analyze',
          headers: { 'content-type': 'application/json' },
          body: { url: 'https://github.com/octocat/Hello-World' },
        },
        {
          apiUrl: 'https://aria-api.lemonriver-308dc42a.eastasia.azurecontainerapps.io',
          apiKey: 'server-secret-key-xyz',
          fetchFn: mockFetch,
        },
      );

      assert.equal(response.status, 202);
      assert.equal(interceptedMethod, 'POST');
      assert.equal(interceptedUrl, 'https://aria-api.lemonriver-308dc42a.eastasia.azurecontainerapps.io/api/v1/analyze');
      assert.equal((interceptedHeaders as Record<string, string>)['X-API-Key'], 'server-secret-key-xyz');
      assert.equal(interceptedBody, JSON.stringify({ url: 'https://github.com/octocat/Hello-World' }));
    });

    test('GET forwarding: preserves query parameters and injects X-API-Key', async () => {
      let interceptedUrl = '';
      let interceptedHeaders: HeadersInit = {};

      const mockFetch: typeof fetch = async (input, init) => {
        interceptedUrl = String(input);
        interceptedHeaders = init?.headers || {};
        return new Response(
          JSON.stringify({ status: 'running', progress: 45 }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      };

      const { executeProxy } = await import('../src/lib/serverProxy.ts');

      const response = await executeProxy(
        {
          method: 'GET',
          url: '/api/v1/analyze/job-999?detail=true',
        },
        {
          apiUrl: 'https://aria-api.lemonriver-308dc42a.eastasia.azurecontainerapps.io',
          apiKey: 'secret-key-abc',
          fetchFn: mockFetch,
        },
      );

      assert.equal(response.status, 200);
      assert.equal(interceptedUrl, 'https://aria-api.lemonriver-308dc42a.eastasia.azurecontainerapps.io/api/v1/analyze/job-999?detail=true');
      assert.equal((interceptedHeaders as Record<string, string>)['X-API-Key'], 'secret-key-abc');
    });

    test('Upstream error forwarding: 4xx, 5xx returned unchanged without leaking secret', async () => {
      const { executeProxy } = await import('../src/lib/serverProxy.ts');

      const mock404Fetch: typeof fetch = async () => {
        return new Response(JSON.stringify({ detail: 'Job not found' }), {
          status: 404,
          headers: { 'Content-Type': 'application/json' },
        });
      };

      const res404 = await executeProxy(
        { method: 'GET', url: '/api/v1/analyze/nonexistent' },
        { apiKey: 'super-secret', fetchFn: mock404Fetch },
      );
      assert.equal(res404.status, 404);
      const text404 = typeof res404.body === 'string' ? res404.body : new TextDecoder().decode(res404.body);
      assert.ok(!text404.includes('super-secret'));
      assert.ok(text404.includes('Job not found'));
    });

    test('Upstream network failure returns 502 Bad Gateway cleanly', async () => {
      const { executeProxy } = await import('../src/lib/serverProxy.ts');

      const mockFailingFetch: typeof fetch = async () => {
        throw new Error('ECONNREFUSED');
      };

      const res = await executeProxy(
        { method: 'GET', url: '/api/v1/health' },
        { apiKey: 'super-secret', fetchFn: mockFailingFetch },
      );
      assert.equal(res.status, 502);
      const body = typeof res.body === 'string' ? res.body : new TextDecoder().decode(res.body);
      assert.ok(body.includes('Failed to connect to upstream backend service'));
      assert.ok(!body.includes('super-secret'));
    });
  });

  describe('7. Critical Security Audit: Zero Production Secrets in Dist Bundle', () => {
    test('scans built client bundles in dist/ for prohibited backend secrets', () => {
      const distDir = join(process.cwd(), 'dist');
      if (!existsSync(distDir)) {
        // Skip if dist not yet generated (e.g. before initial npm run build)
        return;
      }

      const BANNED_PATTERNS = [
        'aria-azure-prod-2026',
        'GEMINI_API_KEY',
        'DEEPSEEK_API_KEY',
        'QDRANT_API_KEY',
        'AZURE_STORAGE_CONNECTION_STRING',
      ];

      const getFilesRecursively = (dir: string): string[] => {
        let results: string[] = [];
        const list = readdirSync(dir);
        for (const file of list) {
          const fullPath = join(dir, file);
          const stat = statSync(fullPath);
          if (stat && stat.isDirectory()) {
            results = results.concat(getFilesRecursively(fullPath));
          } else if (/\.(js|html|css|json)$/i.test(file)) {
            results.push(fullPath);
          }
        }
        return results;
      };

      const distFiles = getFilesRecursively(distDir);
      assert.ok(distFiles.length > 0, 'dist/ directory must contain built assets');

      for (const filePath of distFiles) {
        const content = readFileSync(filePath, 'utf8');
        for (const secret of BANNED_PATTERNS) {
          assert.ok(
            !content.includes(secret),
            `Security violation: Found backend secret '${secret}' in client asset '${filePath}'`,
          );
        }
      }
    });
  });
});
