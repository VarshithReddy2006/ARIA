/**
 * Server-Side API Proxy for Azure FastAPI Backend.
 *
 * Runs exclusively in server-side environments (Astro Server Endpoints / Node.js).
 * Attaches the secret `X-API-Key` header from server environment variables so the
 * client browser bundle never receives or exposes the production API key.
 */

export const DEFAULT_AZURE_API_URL = 'https://aria-api.lemonriver-308dc42a.eastasia.azurecontainerapps.io';

export interface ProxyOptions {
  apiUrl?: string;
  apiKey?: string;
  fetchFn?: typeof fetch;
  timeoutMs?: number;
}

/**
 * Resolve target backend URL and path.
 */
export function resolveTargetUrl(
  incomingUrl: string | undefined,
  queryPath: string | string[] | undefined,
  baseBackendUrl: string = DEFAULT_AZURE_API_URL,
): string {
  const normalizedBase = (baseBackendUrl || DEFAULT_AZURE_API_URL).replace(/\/$/, '');

  let targetPath = '';
  let queryString = '';

  if (incomingUrl) {
    try {
      const parsed = new URL(incomingUrl, 'http://localhost');
      // If 'path' is in searchParams (from rewrite or catch-all), remove it from queryString
      parsed.searchParams.delete('path');
      const search = parsed.searchParams.toString();
      queryString = search ? `?${search}` : '';
      if (!queryPath) {
        targetPath = parsed.pathname;
      }
    } catch {
      if (!queryPath) {
        targetPath = incomingUrl.startsWith('/') ? incomingUrl : `/${incomingUrl}`;
      }
    }
  }

  if (queryPath) {
    const p = Array.isArray(queryPath) ? queryPath.join('/') : queryPath;
    targetPath = p.startsWith('/') ? p : `/${p}`;
  }

  if (!targetPath) {
    targetPath = '/';
  }

  // Health and readiness probes
  if (targetPath === '/health' || targetPath === '/health/' || targetPath === '/ready' || targetPath === '/ready/') {
    return `${normalizedBase}${targetPath}${queryString}`;
  }
  if (targetPath === '/api/health' || targetPath === '/api/health/' || targetPath === '/api/v1/health' || targetPath === '/api/v1/health/') {
    return `${normalizedBase}/health${queryString}`;
  }
  if (targetPath === '/api/ready' || targetPath === '/api/ready/' || targetPath === '/api/v1/ready' || targetPath === '/api/v1/ready/') {
    return `${normalizedBase}/ready${queryString}`;
  }

  // Canonicalize to /api/v1/...
  if (targetPath.startsWith('/api/v1/')) {
    // Already /api/v1/...
  } else if (targetPath === '/api/v1') {
    targetPath = '/api/v1';
  } else if (targetPath.startsWith('/v1/')) {
    targetPath = `/api${targetPath}`;
  } else if (targetPath === '/v1') {
    targetPath = '/api/v1';
  } else if (targetPath.startsWith('/api/')) {
    targetPath = `/api/v1${targetPath.substring(4)}`;
  } else if (targetPath === '/api') {
    targetPath = '/api/v1';
  } else {
    targetPath = `/api/v1/${targetPath.replace(/^\//, '')}`;
  }

  return `${normalizedBase}${targetPath}${queryString}`;
}

/**
 * Core proxy request handler returning a standardized response representation.
 */
export async function executeProxy(
  req: {
    method?: string;
    url?: string;
    headers?: Record<string, string | string[] | undefined> | Headers;
    query?: Record<string, string | string[] | undefined>;
    body?: any;
  },
  options: ProxyOptions = {},
): Promise<{
  status: number;
  statusText: string;
  headers: Record<string, string>;
  body: Uint8Array | string;
}> {
  const fetchImpl = options.fetchFn || globalThis.fetch;
  const backendBase =
    options.apiUrl ||
    process.env.ARIA_API_URL ||
    process.env.BACKEND_API_URL ||
    DEFAULT_AZURE_API_URL;
  const apiKey =
    options.apiKey ||
    process.env.ARIA_API_KEY ||
    process.env.API_KEY ||
    '';

  const queryPath = req.query?.path;
  const targetUrl = resolveTargetUrl(req.url, queryPath, backendBase);
  const method = (req.method || 'GET').toUpperCase();

  // Check if API key is required and configured
  const isHealthOrReady =
    targetUrl.endsWith('/health') ||
    targetUrl.endsWith('/ready') ||
    targetUrl.includes('/health?') ||
    targetUrl.includes('/ready?');

  if (!backendBase || (!apiKey && !isHealthOrReady)) {
    return {
      status: 500,
      statusText: 'Internal Server Error',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ detail: 'API proxy is not configured.' }),
    };
  }

  const forwardHeaders: Record<string, string> = {};

  // Extract relevant client headers, strictly dropping client-supplied X-API-Key and hop-by-hop headers
  if (req.headers) {
    if (typeof Headers !== 'undefined' && req.headers instanceof Headers) {
      req.headers.forEach((val, key) => {
        const lower = key.toLowerCase();
        if (
          lower !== 'host' &&
          lower !== 'x-api-key' &&
          lower !== 'content-length' &&
          lower !== 'connection' &&
          lower !== 'transfer-encoding'
        ) {
          forwardHeaders[key] = val;
        }
      });
    } else if (typeof req.headers === 'object') {
      for (const [key, val] of Object.entries(req.headers)) {
        if (!val) continue;
        const lower = key.toLowerCase();
        if (
          lower !== 'host' &&
          lower !== 'x-api-key' &&
          lower !== 'content-length' &&
          lower !== 'connection' &&
          lower !== 'transfer-encoding'
        ) {
          forwardHeaders[key] = Array.isArray(val) ? val.join(', ') : String(val);
        }
      }
    }
  }

  // Inject secret X-API-Key header to Azure backend
  if (apiKey) {
    forwardHeaders['X-API-Key'] = apiKey;
  }

  let requestBody: any = undefined;
  if (method !== 'GET' && method !== 'HEAD') {
    if (req.body !== undefined && req.body !== null) {
      if (typeof req.body === 'string' || req.body instanceof Uint8Array || Buffer.isBuffer(req.body)) {
        requestBody = req.body;
      } else if (typeof req.body === 'object') {
        requestBody = JSON.stringify(req.body);
        if (!forwardHeaders['content-type'] && !forwardHeaders['Content-Type']) {
          forwardHeaders['Content-Type'] = 'application/json';
        }
      }
    }
  }

  const timeoutMs = options.timeoutMs || 30000;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const upstreamRes = await fetchImpl(targetUrl, {
      method,
      headers: forwardHeaders,
      body: requestBody,
      signal: controller.signal,
    });

    const resHeaders: Record<string, string> = {};
    upstreamRes.headers.forEach((val, key) => {
      const lower = key.toLowerCase();
      // Omit hop-by-hop headers, content-length, and content-encoding (as fetch auto-decodes responseBuffer)
      if (
        lower !== 'transfer-encoding' &&
        lower !== 'connection' &&
        lower !== 'content-encoding' &&
        lower !== 'content-length'
      ) {
        resHeaders[key] = val;
      }
    });

    const responseBuffer = await upstreamRes.arrayBuffer();
    return {
      status: upstreamRes.status,
      statusText: upstreamRes.statusText,
      headers: resHeaders,
      body: new Uint8Array(responseBuffer),
    };
  } catch (err: any) {
    const isTimeout =
      err.name === 'AbortError' ||
      err.code === 'ETIMEDOUT' ||
      String(err.message || '').toLowerCase().includes('timeout');
    const status = isTimeout ? 504 : 502;
    const errorMessage = isTimeout
      ? 'Upstream backend timed out.'
      : 'Failed to connect to upstream backend service.';

    return {
      status,
      statusText: isTimeout ? 'Gateway Timeout' : 'Bad Gateway',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ detail: errorMessage, error: errorMessage, status: 'failed' }),
    };
  } finally {
    clearTimeout(timeoutId);
  }
}
