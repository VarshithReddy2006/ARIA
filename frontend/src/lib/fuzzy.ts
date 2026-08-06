/**
 * Small, allocation-light fuzzy matcher for command-palette style filtering.
 *
 * Scores a candidate against a query using subsequence matching, then rewards
 * matches that look intentional: exact substrings, prefixes, word/path-segment
 * boundaries, and consecutive runs. Returns matched indices so callers can
 * highlight the hit without re-running the search.
 */

export interface FuzzyMatch {
  score: number;
  /** Indices in the original `text` that matched, ascending. */
  positions: number[];
}

/** True when the character at `i` starts a new word or path segment. */
function isBoundary(text: string, i: number): boolean {
  if (i === 0) return true;
  const prev = text[i - 1];
  if (prev === '/' || prev === '\\' || prev === '.' || prev === '-' || prev === '_' || prev === ' ') {
    return true;
  }
  // camelCase / PascalCase transition
  return prev === prev.toLowerCase() && text[i] === text[i].toUpperCase() && /[a-z]/i.test(prev);
}

/**
 * Match `query` against `text`.
 *
 * @returns `null` when the query is not a subsequence of the text, otherwise a
 *   score (higher is better) plus the matched character positions.
 */
export function fuzzyMatch(text: string, query: string): FuzzyMatch | null {
  if (!query) return { score: 0, positions: [] };
  if (!text) return null;

  const lowerText = text.toLowerCase();
  const lowerQuery = query.toLowerCase();

  // Fast path: contiguous substring is always the strongest kind of match.
  const exactIdx = lowerText.indexOf(lowerQuery);
  if (exactIdx !== -1) {
    const positions: number[] = [];
    for (let i = 0; i < lowerQuery.length; i++) positions.push(exactIdx + i);

    let score = 1000 - exactIdx * 2;
    if (exactIdx === 0) score += 400;
    else if (isBoundary(text, exactIdx)) score += 250;
    // Prefer tighter candidates so "api" ranks `api.py` above `api_surface_service.py`.
    score -= Math.min(text.length - lowerQuery.length, 120);
    return { score, positions };
  }

  // Subsequence scan.
  const positions: number[] = [];
  let ti = 0;
  let score = 0;
  let run = 0;

  for (let qi = 0; qi < lowerQuery.length; qi++) {
    const ch = lowerQuery[qi];
    let found = -1;
    while (ti < lowerText.length) {
      if (lowerText[ti] === ch) { found = ti; break; }
      ti++;
    }
    if (found === -1) return null;

    positions.push(found);
    score += 12;
    if (isBoundary(text, found)) score += 45;
    // Reward consecutive characters, escalating with run length.
    if (qi > 0 && positions[qi - 1] === found - 1) {
      run += 1;
      score += 18 * run;
    } else {
      run = 0;
      // Penalise how far we had to jump to find this character.
      if (qi > 0) score -= Math.min(found - positions[qi - 1], 12);
    }
    ti = found + 1;
  }

  score -= Math.min(text.length, 80) * 0.4;
  return { score, positions };
}

/**
 * Score a candidate across several fields, returning the best field's match.
 *
 * `weights` scales each field's score so a title hit can outrank a keyword hit.
 */
export function fuzzyMatchBest(
  fields: { text: string; weight: number }[],
  query: string,
): { score: number; fieldIndex: number; positions: number[] } | null {
  let best: { score: number; fieldIndex: number; positions: number[] } | null = null;

  for (let i = 0; i < fields.length; i++) {
    const m = fuzzyMatch(fields[i].text, query);
    if (!m) continue;
    const scaled = m.score * fields[i].weight;
    if (!best || scaled > best.score) {
      best = { score: scaled, fieldIndex: i, positions: m.positions };
    }
  }
  return best;
}
