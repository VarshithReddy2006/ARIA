/**
 * GitHub repository URL parsing for client-side input validation.
 *
 * This is a UX affordance only — the backend remains the authority on whether a
 * repository can actually be cloned and indexed. Nothing here changes what is
 * sent to `POST /api/v1/analyze`.
 */

export interface ParsedRepo {
  owner: string;
  repo: string;
  /** Canonical `owner/repo` form */
  slug: string;
}

/** GitHub allows alphanumerics, hyphens, underscores, and dots in these segments. */
const SEGMENT = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;

/** Paths that are GitHub product routes, never repository owners. */
const RESERVED_OWNERS = new Set([
  'settings', 'notifications', 'explore', 'topics', 'trending', 'collections',
  'events', 'sponsors', 'marketplace', 'pulls', 'issues', 'codespaces',
  'features', 'pricing', 'about', 'login', 'join', 'new', 'organizations',
  'orgs', 'apps', 'search', 'dashboard',
]);

/**
 * Accepts the shapes users actually paste:
 *   https://github.com/owner/repo
 *   http://www.github.com/owner/repo.git
 *   github.com/owner/repo/tree/main/src
 *   git@github.com:owner/repo.git
 *   owner/repo
 */
export function parseGitHubUrl(input: string): ParsedRepo | null {
  const raw = (input ?? '').trim();
  if (!raw) return null;

  let path = raw;

  // SSH remote form
  const sshMatch = /^git@github\.com:(.+)$/i.exec(path);
  if (sshMatch) {
    path = sshMatch[1];
  } else {
    // Strip scheme and host for HTTP(S) / bare-host forms
    path = path.replace(/^[a-z][a-z0-9+.-]*:\/\//i, '');
    const hostMatch = /^(?:www\.)?github\.com\/(.+)$/i.exec(path);
    if (hostMatch) {
      path = hostMatch[1];
    } else if (/github\.com/i.test(path)) {
      // Mentions github.com but not in a position we can parse
      return null;
    } else if (/[a-z]+:\/\//i.test(raw) || /\.[a-z]{2,}\//i.test(raw)) {
      // A URL on some other host — not a GitHub repository
      return null;
    }
  }

  // Drop query, fragment, and trailing slashes
  path = path.split(/[?#]/)[0].replace(/^\/+|\/+$/g, '');
  if (!path) return null;

  const segments = path.split('/').filter(Boolean);
  if (segments.length < 2) return null;

  const owner = segments[0];
  const repo = segments[1].replace(/\.git$/i, '');

  if (!SEGMENT.test(owner) || !SEGMENT.test(repo)) return null;
  if (RESERVED_OWNERS.has(owner.toLowerCase())) return null;
  // "." and ".." are never valid repository names
  if (repo === '.' || repo === '..') return null;

  return { owner, repo, slug: `${owner}/${repo}` };
}

export type ValidationState = 'empty' | 'checking' | 'valid' | 'invalid';

/** Human-readable reason shown when parsing fails. */
export function describeInvalidUrl(input: string): string {
  const raw = (input ?? '').trim();

  if (/github\.com\s*\/?$/i.test(raw)) {
    return 'Add the owner and repository name, e.g. github.com/facebook/react';
  }
  if (/^[a-z][a-z0-9+.-]*:\/\//i.test(raw) && !/github\.com/i.test(raw)) {
    return 'Only GitHub repositories are supported right now.';
  }
  if (!raw.includes('/')) {
    return 'Expected owner/repo — try a full GitHub URL.';
  }
  return 'That does not look like a GitHub repository URL.';
}
