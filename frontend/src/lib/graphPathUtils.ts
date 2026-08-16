import type { GraphNode } from '../components/interactive/graph/types';

/**
 * Normalizes file paths for robust comparison across platforms and representations.
 *
 * Handles:
 * - Backslashes (Windows) -> forward slashes
 * - Leading `./` or `/`
 * - Redundant trailing slashes
 * - Repository slug prefixes (e.g. `fastapi/fastapi/fastapi/routing.py` -> `fastapi/routing.py`)
 */
export function normalizeGraphPath(path: string, repoSlug?: string): string {
  if (!path) return '';

  let normalized = path;
  try {
    if (normalized.includes('%')) {
      normalized = decodeURIComponent(normalized);
    }
  } catch {
    // Keep raw if malformed URL encoding
  }

  normalized = normalized.replace(/\\/g, '/').trim();

  // Strip leading ./ or /
  normalized = normalized.replace(/^\.?\//, '');

  // Strip trailing slash
  normalized = normalized.replace(/\/+$/, '');

  // If repoSlug (e.g. "fastapi/fastapi" or "fastapi") is prefixed, strip it once
  if (repoSlug) {
    const slugNorm = repoSlug.replace(/\\/g, '/').replace(/^\.?\//, '').replace(/\/+$/, '');
    if (slugNorm && normalized.startsWith(`${slugNorm}/`)) {
      normalized = normalized.slice(slugNorm.length + 1);
    } else {
      const repoPart = slugNorm.split('/').pop();
      if (repoPart && normalized.startsWith(`${repoPart}/`)) {
        normalized = normalized.slice(repoPart.length + 1);
      }
    }
  }

  return normalized;
}

/**
 * Resolves a target file path against available graph nodes.
 *
 * Priority order:
 * 1. Exact node.id match
 * 2. Case-insensitive exact match
 * 3. Normalized path match
 * 4. Suffix match (e.g., `fastapi/routing.py` vs `src/fastapi/routing.py`)
 * 5. Unique basename match (e.g. `routing.py`)
 */
export function resolveGraphNode(
  targetPath: string,
  nodes: GraphNode[],
  repoSlug?: string,
): GraphNode | null {
  if (!targetPath || !nodes || nodes.length === 0) return null;

  const rawTarget = targetPath.replace(/\\/g, '/').trim();
  const normTarget = normalizeGraphPath(targetPath, repoSlug);
  const targetBasename = normTarget.split('/').pop()?.toLowerCase();

  // 1. Exact match on node.id
  const exact = nodes.find((n) => n.id === rawTarget || n.id === normTarget);
  if (exact) return exact;

  // 2. Case-insensitive match on node.id
  const caseInsensitive = nodes.find(
    (n) => n.id.toLowerCase() === rawTarget.toLowerCase() || n.id.toLowerCase() === normTarget.toLowerCase(),
  );
  if (caseInsensitive) return caseInsensitive;

  // 3. Normalized match
  const normalizedMatch = nodes.find((n) => {
    const normNode = normalizeGraphPath(n.id, repoSlug);
    return normNode === normTarget;
  });
  if (normalizedMatch) return normalizedMatch;

  // 4. Suffix match (only if target or node contains path segments)
  if (normTarget.includes('/')) {
    const suffixMatches = nodes.filter((n) => {
      const normNode = normalizeGraphPath(n.id, repoSlug);
      return (
        normNode.endsWith(`/${normTarget}`) ||
        normTarget.endsWith(`/${normNode}`)
      );
    });
    if (suffixMatches.length === 1) return suffixMatches[0];
  }

  // 5. Basename match (if unique or clear match)
  if (targetBasename) {
    const basenameMatches = nodes.filter((n) => {
      const nodeBase = n.id.split('/').pop()?.toLowerCase();
      return nodeBase === targetBasename;
    });
    if (basenameMatches.length === 1) {
      return basenameMatches[0];
    }
  }

  return null;
}
