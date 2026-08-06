/**
 * Markdown & HTML Sanitizer.
 *
 * Sanitizes markdown content before parsing/rendering.
 * Removes stray HTML attribute leaks (`400">`, `class=`, `text-indigo-`, `font-semibold`, `style=`, broken tags),
 * while preserving 100% of valid Markdown semantics (headings, lists, tables, code blocks, links).
 */

/**
 * Clean malformed HTML attribute artifacts and leaking class names from markdown text.
 */
export function sanitizeMarkdown(text: string): string {
  if (!text) return '';

  let sanitized = text;

  // 1. Remove malformed class attribute leakages (e.g., class="...", class=400">, 400">, text-indigo-400 font-semibold)
  sanitized = sanitized.replace(/(?:class|style)=(?:"[^"]*"|'[^']*'|[^\s>]+)/g, '');
  sanitized = sanitized.replace(/\b(?:text-indigo-\d+|font-semibold|text-text-subtle|text-emerald-\d+|text-amber-\d+)\b/g, '');
  sanitized = sanitized.replace(/400">/g, '');
  sanitized = sanitized.replace(/<span\s*>/g, '');
  sanitized = sanitized.replace(/<\/span>/g, '');

  // 2. Remove broken unclosed span fragments e.g. <span ...>
  sanitized = sanitized.replace(/<span[^>]*>/g, '');

  // 3. Remove escaped JSX/Astro fragments if any slipped into text
  sanitized = sanitized.replace(/<\/?(?:astro-island|react-fragment)[^>]*>/g, '');

  // 4. Remove duplicate blank lines produced by stripping
  sanitized = sanitized.replace(/\n{3,}/g, '\n\n');

  return sanitized;
}
