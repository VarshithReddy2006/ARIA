/**
 * Centralized API configuration for the ARIA frontend.
 *
 * Every backend request must go through this module so the base URL is defined
 * in exactly one place. In development the FastAPI backend runs on a different
 * origin (port 8001) than the Astro dev server (port 4321), so requests are
 * issued as absolute URLs and rely on the backend's permissive CORS policy.
 *
 * Override the target by setting `PUBLIC_API_URL` in `frontend/.env`.
 */

const DEFAULT_DEV_API_BASE_URL = 'http://127.0.0.1:8001';

/**
 * Resolved backend origin.
 * - In development mode (`npm run dev`), defaults to `http://127.0.0.1:8001`.
 * - In production mode (`npm run build` / Docker), defaults to `""` (same-origin relative URLs).
 * - Can be explicitly overridden via `PUBLIC_API_URL` environment variable.
 */
export const API_BASE_URL: string = (
  typeof import.meta.env.PUBLIC_API_URL === 'string' && import.meta.env.PUBLIC_API_URL.trim() !== ''
    ? import.meta.env.PUBLIC_API_URL.trim()
    : import.meta.env.DEV
      ? DEFAULT_DEV_API_BASE_URL
      : ''
).replace(/\/$/, '');

/**
 * Build a fully-qualified backend URL from an API path.
 *
 * Call sites should pass the canonical versioned path (e.g. `/api/v1/analyze`).
 * Un-versioned `/api/...` paths are still upgraded to `/api/v1/...` here as a
 * safety net so a stray legacy path never reaches the backend's deprecated
 * redirect, but new code should not rely on that.
 *
 * @param path - A path beginning with `/` (e.g. `/api/v1/analyze`). A leading
 *   slash is added if missing.
 */
export function apiUrl(path: string): string {
  let normalized = path.startsWith('/') ? path : `/${path}`;
  if (normalized.startsWith('/api/') && !normalized.startsWith('/api/v1/')) {
    normalized = `/api/v1${normalized.substring(4)}`;
  }
  return `${API_BASE_URL}${normalized}`;
}

export type EngineState = 'ready' | 'analyzing' | 'indexed' | 'degraded' | 'offline';

export interface EngineStatusResult {
  state: EngineState;
  label: string;
  uptimeSeconds?: number;
  provider?: string;
  model?: string;
}

/**
 * Contextual backend engine status probe.
 * Returns a rich status object distinguishing between ready, indexed, degraded, and offline.
 */
export async function getEngineStatus(timeoutMs = 4000): Promise<EngineStatusResult> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(apiUrl('/health'), {
      signal: controller.signal,
    });
    if (!response.ok) {
      return { state: 'degraded', label: 'DEGRADED' };
    }
    const data = await response.json().catch(() => ({}));
    
    // Check if active repository is in localStorage
    const hasActiveRepo = typeof window !== 'undefined' && Boolean(localStorage.getItem('activeRepo'));
    
    return {
      state: hasActiveRepo ? 'indexed' : 'ready',
      label: hasActiveRepo ? 'INDEXED' : 'ENGINE READY',
      uptimeSeconds: data.uptime_seconds,
      provider: data.llm_provider,
      model: data.llm_model,
    };
  } catch {
    return { state: 'offline', label: 'OFFLINE' };
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Lightweight backend liveness probe used by backward-compatible callers.
 */
export async function checkBackendHealth(timeoutMs = 4000): Promise<boolean> {
  const status = await getEngineStatus(timeoutMs);
  return status.state !== 'offline';
}

/**
 * Safely extracts a user-friendly error message from any given error object/response.
 * Conforms to Priority 3: handles FastAPI detail arrays, object fields, HTTP status codes,
 * and falls back gracefully so that `[object Object]` never appears in the UI.
 */
export function extractErrorMessage(error: any): string {
  if (!error) return 'An unknown error occurred.';
  if (typeof error === 'string') return error;

  // Handle FastAPI detail array or object
  if (error.detail) {
    if (typeof error.detail === 'string') {
      return error.detail;
    }
    if (Array.isArray(error.detail)) {
      return error.detail
        .map((e: any) => {
          const locStr = e.loc ? e.loc.join('.') : '';
          return `${locStr ? locStr + ': ' : ''}${e.msg || JSON.stringify(e)}`;
        })
        .join('; ');
    }
    if (typeof error.detail === 'object') {
      return error.detail.message || JSON.stringify(error.detail);
    }
  }

  // Handle standard JS Error message or custom response messages
  if (error.message && typeof error.message === 'string') {
    return error.message;
  }

  // Handle generic object payload
  try {
    const stringified = JSON.stringify(error);
    if (stringified === '{}') {
      return String(error);
    }
    return stringified;
  } catch {
    return String(error);
  }
}
