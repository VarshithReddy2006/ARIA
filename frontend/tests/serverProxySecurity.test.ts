import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync, readdirSync, statSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { executeProxy, resolveTargetUrl } from '../src/lib/serverProxy.ts';
import { ALL, GET, POST } from '../src/pages/api/[...path].ts';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const frontendDir = resolve(__dirname, '..');

describe('Server-Side Proxy Security & Astro Endpoint Verification', () => {
  const DEFAULT_TEST_API_URL = 'https://aria-api.lemonriver-308dc42a.eastasia.azurecontainerapps.io';
  const SECRET_KEY = 'test-server-secret-key-12345';

  test('1. POST request gets X-API-Key added server-side', async () => {
    let capturedHeaders: Record<string, string> = {};
    let capturedMethod = '';
    let capturedUrl = '';

    const mockFetch: typeof fetch = async (input, init) => {
      capturedUrl = String(input);
      capturedMethod = init?.method || '';
      capturedHeaders = (init?.headers as Record<string, string>) || {};
      return new Response(JSON.stringify({ job_id: 'job-123', status: 'queued' }), {
        status: 202,
        headers: { 'Content-Type': 'application/json' },
      });
    };

    const result = await executeProxy(
      {
        method: 'POST',
        url: '/api/v1/analyze',
        body: { url: 'https://github.com/octocat/Hello-World' },
      },
      { apiUrl: DEFAULT_TEST_API_URL, apiKey: SECRET_KEY, fetchFn: mockFetch },
    );

    assert.equal(result.status, 202);
    assert.equal(capturedMethod, 'POST');
    assert.equal(capturedUrl, `${DEFAULT_TEST_API_URL}/api/v1/analyze`);
    assert.equal(capturedHeaders['X-API-Key'], SECRET_KEY);
  });

  test('2. Browser-supplied X-API-Key is ignored and replaced with server secret', async () => {
    let capturedHeaders: Record<string, string> = {};

    const mockFetch: typeof fetch = async (_input, init) => {
      capturedHeaders = (init?.headers as Record<string, string>) || {};
      return new Response(JSON.stringify({ status: 'ok' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    };

    await executeProxy(
      {
        method: 'POST',
        url: '/api/v1/analyze',
        headers: {
          'x-api-key': 'attacker-unauthorized-key',
          'X-API-KEY': 'fake-key',
          'content-type': 'application/json',
        },
        body: { url: 'https://github.com/octocat/Hello-World' },
      },
      { apiUrl: DEFAULT_TEST_API_URL, apiKey: SECRET_KEY, fetchFn: mockFetch },
    );

    assert.equal(capturedHeaders['X-API-Key'], SECRET_KEY);
    assert.equal(capturedHeaders['x-api-key'], undefined);
    assert.equal(capturedHeaders['X-API-KEY'], undefined);
  });

  test('3. GET request gets X-API-Key added', async () => {
    let capturedHeaders: Record<string, string> = {};
    let capturedUrl = '';

    const mockFetch: typeof fetch = async (input, init) => {
      capturedUrl = String(input);
      capturedHeaders = (init?.headers as Record<string, string>) || {};
      return new Response(JSON.stringify({ status: 'running' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    };

    const result = await executeProxy(
      {
        method: 'GET',
        url: '/api/v1/analyze/job-abc',
      },
      { apiUrl: DEFAULT_TEST_API_URL, apiKey: SECRET_KEY, fetchFn: mockFetch },
    );

    assert.equal(result.status, 200);
    assert.equal(capturedUrl, `${DEFAULT_TEST_API_URL}/api/v1/analyze/job-abc`);
    assert.equal(capturedHeaders['X-API-Key'], SECRET_KEY);
  });

  test('4. Query parameters are preserved across rewrites and direct calls', async () => {
    let capturedUrl = '';

    const mockFetch: typeof fetch = async (input) => {
      capturedUrl = String(input);
      return new Response(JSON.stringify([]), { status: 200, headers: { 'Content-Type': 'application/json' } });
    };

    // Case A: Direct URL with query
    await executeProxy(
      {
        method: 'GET',
        url: '/api/v1/repos/examples?limit=10&sort=stars',
      },
      { apiUrl: DEFAULT_TEST_API_URL, apiKey: SECRET_KEY, fetchFn: mockFetch },
    );
    assert.equal(capturedUrl, `${DEFAULT_TEST_API_URL}/api/v1/repos/examples?limit=10&sort=stars`);

    // Case B: Catch-all query object with path
    await executeProxy(
      {
        method: 'GET',
        url: '/api/v1/repos/examples?path=v1/repos/examples&limit=10&sort=stars',
        query: { path: ['v1', 'repos', 'examples'] },
      },
      { apiUrl: DEFAULT_TEST_API_URL, apiKey: SECRET_KEY, fetchFn: mockFetch },
    );
    assert.equal(capturedUrl, `${DEFAULT_TEST_API_URL}/api/v1/repos/examples?limit=10&sort=stars`);
  });

  test('5. Request body is preserved for JSON and strings', async () => {
    let capturedBody: any;
    let capturedContentType = '';

    const mockFetch: typeof fetch = async (_input, init) => {
      capturedBody = init?.body;
      capturedContentType = (init?.headers as Record<string, string>)?.['Content-Type'] || '';
      return new Response(JSON.stringify({ job_id: 'job-body-test' }), {
        status: 202,
        headers: { 'Content-Type': 'application/json' },
      });
    };

    const payload = { url: 'https://github.com/octocat/Hello-World' };
    await executeProxy(
      {
        method: 'POST',
        url: '/api/v1/analyze',
        body: payload,
      },
      { apiUrl: DEFAULT_TEST_API_URL, apiKey: SECRET_KEY, fetchFn: mockFetch },
    );

    assert.equal(capturedBody, JSON.stringify(payload));
    assert.equal(capturedContentType, 'application/json');
  });

  test('6. Upstream 401/403/404/500 responses are forwarded safely', async () => {
    const mockFetch: typeof fetch = async () => {
      return new Response(JSON.stringify({ detail: 'Invalid API Key' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      });
    };

    const result = await executeProxy(
      { method: 'GET', url: '/api/v1/analyze/job-1' },
      { apiUrl: DEFAULT_TEST_API_URL, apiKey: SECRET_KEY, fetchFn: mockFetch },
    );

    assert.equal(result.status, 401);
    const bodyStr = typeof result.body === 'string' ? result.body : new TextDecoder().decode(result.body);
    assert.ok(bodyStr.includes('Invalid API Key'));
    assert.ok(!bodyStr.includes(SECRET_KEY));
  });

  test('7. Upstream network failure returns 502/504 cleanly', async () => {
    // 502 connection failure
    const mockRefusedFetch: typeof fetch = async () => {
      throw new Error('connect ECONNREFUSED 127.0.0.1:8001');
    };

    const res502 = await executeProxy(
      { method: 'GET', url: '/api/v1/analyze/job-1' },
      { apiUrl: DEFAULT_TEST_API_URL, apiKey: SECRET_KEY, fetchFn: mockRefusedFetch },
    );

    assert.equal(res502.status, 502);
    const body502 = typeof res502.body === 'string' ? res502.body : new TextDecoder().decode(res502.body);
    assert.ok(body502.includes('Failed to connect to upstream backend service'));
    assert.ok(!body502.includes(SECRET_KEY));

    // 504 timeout
    const mockTimeoutFetch: typeof fetch = async () => {
      const err = new Error('request timed out');
      err.name = 'AbortError';
      throw err;
    };

    const res504 = await executeProxy(
      { method: 'GET', url: '/api/v1/analyze/job-1' },
      { apiUrl: DEFAULT_TEST_API_URL, apiKey: SECRET_KEY, fetchFn: mockTimeoutFetch },
    );

    assert.equal(res504.status, 504);
    const body504 = typeof res504.body === 'string' ? res504.body : new TextDecoder().decode(res504.body);
    assert.ok(body504.includes('Upstream backend timed out'));
  });

  test('8. Missing ARIA_API_KEY returns safe server error (500)', async () => {
    const origKey = process.env.ARIA_API_KEY;
    const origFallbackKey = process.env.API_KEY;
    try {
      delete process.env.ARIA_API_KEY;
      delete process.env.API_KEY;

      const result = await executeProxy(
        { method: 'POST', url: '/api/v1/analyze', body: { url: 'https://github.com/octocat/Hello-World' } },
        { apiUrl: DEFAULT_TEST_API_URL, apiKey: '' },
      );

      assert.equal(result.status, 500);
      const body = typeof result.body === 'string' ? result.body : new TextDecoder().decode(result.body);
      const parsed = JSON.parse(body);
      assert.equal(parsed.detail, 'API proxy is not configured.');
    } finally {
      if (origKey) process.env.ARIA_API_KEY = origKey;
      if (origFallbackKey) process.env.API_KEY = origFallbackKey;
    }
  });

  test('9 & 10. No API key appears in browser bundle or generated static HTML', () => {
    const distDir = resolve(frontendDir, 'dist');
    if (!existsSync(distDir)) {
      return;
    }

    const BANNED_PATTERNS = [
      'aria-azure-prod-2026',
      'PUBLIC_API_KEY',
      'ARIA_API_KEY',
      'GEMINI_API_KEY',
      'DEEPSEEK_API_KEY',
      'GITHUB_TOKEN',
      'QDRANT_API_KEY',
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
    for (const filePath of distFiles) {
      const content = readFileSync(filePath, 'utf8');
      for (const secret of BANNED_PATTERNS) {
        assert.ok(
          !content.includes(secret),
          `Security violation: Found forbidden pattern '${secret}' in client asset '${filePath}'`,
        );
      }
    }
  });

  test('11. /health and /ready routes work without requiring authentication', async () => {
    let capturedHealthUrl = '';
    let capturedReadyUrl = '';

    const mockFetch: typeof fetch = async (input) => {
      const url = String(input);
      if (url.includes('/health')) capturedHealthUrl = url;
      if (url.includes('/ready')) capturedReadyUrl = url;
      return new Response(JSON.stringify({ status: 'healthy' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    };

    // Health check without API key
    const healthRes = await executeProxy(
      { method: 'GET', url: '/health' },
      { apiUrl: DEFAULT_TEST_API_URL, apiKey: '', fetchFn: mockFetch },
    );
    assert.equal(healthRes.status, 200);
    assert.equal(capturedHealthUrl, `${DEFAULT_TEST_API_URL}/health`);

    // Ready check via rewrite /api/ready without API key
    const readyRes = await executeProxy(
      { method: 'GET', url: '/api/ready', query: { path: 'ready' } },
      { apiUrl: DEFAULT_TEST_API_URL, apiKey: '', fetchFn: mockFetch },
    );
    assert.equal(readyRes.status, 200);
    assert.equal(capturedReadyUrl, `${DEFAULT_TEST_API_URL}/ready`);
  });

  test('12. executeProxy handles binary buffers, headers, and nodeProxyHandler is absent', async () => {
    let reqBodyBuffer: Uint8Array | undefined;
    const mockFetch: typeof fetch = async (_input, init) => {
      reqBodyBuffer = init?.body as Uint8Array;
      return new Response(JSON.stringify({ job_id: 'job-binary-test', status: 'queued' }), {
        status: 202,
        headers: { 'Content-Type': 'application/json', 'X-Custom-Res': '123' },
      });
    };

    const payloadBytes = new TextEncoder().encode(JSON.stringify({ url: 'https://github.com/octocat/Hello-World' }));
    const result = await executeProxy(
      {
        method: 'POST',
        url: '/api/v1/analyze',
        headers: { 'content-type': 'application/json' },
        body: payloadBytes,
      },
      {
        apiUrl: DEFAULT_TEST_API_URL,
        apiKey: SECRET_KEY,
        fetchFn: mockFetch,
      },
    );

    assert.equal(result.status, 202);
    assert.equal(result.headers['content-type'] || result.headers['Content-Type'], 'application/json');
    assert.equal(result.headers['x-custom-res'], '123');
    assert.ok(reqBodyBuffer);
    assert.deepEqual(reqBodyBuffer, payloadBytes);

    // Verify nodeProxyHandler is not exported
    const proxyModule = await import('../src/lib/serverProxy.ts');
    assert.equal((proxyModule as any).nodeProxyHandler, undefined, 'nodeProxyHandler must be removed');
  });

  test('13. Astro server endpoint architecture & legacy Vercel function cleanup verification', () => {
    const astroEndpointPath = join(frontendDir, 'src', 'pages', 'api', '[...path].ts');
    const libProxyPath = join(frontendDir, 'src', 'lib', 'serverProxy.ts');
    const legacyApiDir = join(frontendDir, 'api');
    const legacyTsEntrypoint = join(frontendDir, 'api', '[...path].ts');
    const legacyLocalProxy = join(frontendDir, 'api', '_serverProxy.ts');
    const legacyJsEntrypoint = join(frontendDir, 'api', '[...path].js');
    const legacyProxyJs = join(frontendDir, 'api', 'proxy.js');

    // 1. Astro server endpoint and shared lib proxy must exist
    assert.ok(
      existsSync(astroEndpointPath),
      'Astro API server endpoint frontend/src/pages/api/[...path].ts must exist',
    );
    assert.ok(
      existsSync(libProxyPath),
      'Server proxy helper frontend/src/lib/serverProxy.ts must exist',
    );

    // 2. Legacy manual Vercel function files and directory must NOT exist
    assert.ok(
      !existsSync(legacyApiDir),
      'Legacy manual Vercel function directory frontend/api must NOT exist',
    );
    assert.ok(
      !existsSync(legacyTsEntrypoint),
      'Legacy entrypoint frontend/api/[...path].ts must NOT exist',
    );
    assert.ok(
      !existsSync(legacyLocalProxy),
      'Legacy proxy frontend/api/_serverProxy.ts must NOT exist',
    );
    assert.ok(
      !existsSync(legacyJsEntrypoint),
      'Legacy frontend/api/[...path].js must NOT exist',
    );
    assert.ok(
      !existsSync(legacyProxyJs),
      'Legacy frontend/api/proxy.js must NOT exist',
    );

    // 3. Inspect Astro endpoint structure
    const content = readFileSync(astroEndpointPath, 'utf8');

    // Must import executeProxy from lib
    assert.match(
      content,
      /import\s+\{\s*executeProxy\s*\}\s+from\s+['"](?:\.\.\/)+lib\/serverProxy(?:\.ts)?['"]/,
      'Must import executeProxy from lib/serverProxy',
    );

    // Must export ALL APIRoute
    assert.match(
      content,
      /export\s+const\s+ALL\s*:\s*APIRoute/,
      'Must export ALL APIRoute handler',
    );
  });

  test('14. Astro ALL handler processes Web Request and returns standard Response', async () => {
    let capturedUrl = '';
    let capturedHeaders: Record<string, string> = {};
    let capturedBody = '';

    const origKey = process.env.ARIA_API_KEY;
    const origUrl = process.env.ARIA_API_URL;
    const origFetch = globalThis.fetch;

    try {
      process.env.ARIA_API_KEY = SECRET_KEY;
      process.env.ARIA_API_URL = DEFAULT_TEST_API_URL;

      globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
        capturedUrl = String(input);
        capturedHeaders = (init?.headers as Record<string, string>) || {};
        capturedBody = String(init?.body || '');
        return new Response(JSON.stringify({ job_id: 'astro-job-789', status: 'queued' }), {
          status: 202,
          headers: { 'Content-Type': 'application/json' },
        });
      }) as typeof fetch;

      const mockRequest = new Request('http://localhost:4321/api/v1/analyze', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': 'client-should-be-stripped',
        },
        body: JSON.stringify({ url: 'https://github.com/octocat/Hello-World' }),
      });

      const response = await ALL({
        request: mockRequest,
        params: { path: 'v1/analyze' },
        url: new URL('http://localhost:4321/api/v1/analyze'),
      } as any);

      assert.ok(response instanceof Response);
      assert.equal(response.status, 202);
      const data = await response.json();
      assert.equal(data.job_id, 'astro-job-789');
      assert.equal(capturedUrl, `${DEFAULT_TEST_API_URL}/api/v1/analyze`);
      assert.equal(capturedHeaders['X-API-Key'], SECRET_KEY);
      assert.equal(capturedHeaders['x-api-key'], undefined);
      assert.equal(capturedBody, JSON.stringify({ url: 'https://github.com/octocat/Hello-World' }));
    } finally {
      process.env.ARIA_API_KEY = origKey;
      process.env.ARIA_API_URL = origUrl;
      globalThis.fetch = origFetch;
    }
  });

  test('15. Astro HTTP method exports route to ALL handler', async () => {
    const { ALL, GET, POST, PUT, DELETE, PATCH, HEAD, OPTIONS } = await import('../src/pages/api/[...path].ts');
    assert.equal(GET, ALL);
    assert.equal(POST, ALL);
    assert.equal(PUT, ALL);
    assert.equal(DELETE, ALL);
    assert.equal(PATCH, ALL);
    assert.equal(HEAD, ALL);
    assert.equal(OPTIONS, ALL);
  });
});
