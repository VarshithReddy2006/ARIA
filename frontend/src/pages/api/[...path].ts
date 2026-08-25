import type { APIRoute } from 'astro';
import { executeProxy } from '../../lib/serverProxy.ts';

export const prerender = false;

const handle: APIRoute = async ({ request, params, url }) => {
  let body: any = undefined;
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    const contentType = request.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      try {
        body = await request.json();
      } catch {
        body = await request.text();
      }
    } else {
      const buffer = await request.arrayBuffer();
      body = new Uint8Array(buffer);
    }
  }

  const result = await executeProxy({
    method: request.method,
    url: url.toString(),
    headers: request.headers,
    query: { path: params.path },
    body,
  });

  return new Response(result.body as BodyInit, {
    status: result.status,
    statusText: result.statusText,
    headers: result.headers,
  });
};

export const ALL: APIRoute = handle;
export const GET: APIRoute = handle;
export const POST: APIRoute = handle;
export const PUT: APIRoute = handle;
export const DELETE: APIRoute = handle;
export const PATCH: APIRoute = handle;
export const HEAD: APIRoute = handle;
export const OPTIONS: APIRoute = handle;
