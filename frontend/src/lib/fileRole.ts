/**
 * Client-side classification of a file's architectural role.
 *
 * This is a deterministic read of the path itself — filename and extension
 * patterns only. It is *inferred*, not reported by the backend, so surfaces that
 * display it must label it as such rather than presenting it as indexed data.
 * Nothing here calls the API or affects analysis.
 */

export type FileRole =
  | 'Documentation'
  | 'Entry point'
  | 'Configuration'
  | 'Dependency manifest'
  | 'Test'
  | 'Type definitions'
  | 'Stylesheet'
  | 'Template'
  | 'Source';

const MANIFESTS = new Set([
  'package.json',
  'requirements.txt',
  'pyproject.toml',
  'go.mod',
  'cargo.toml',
  'gemfile',
  'pom.xml',
  'build.gradle',
  'composer.json',
]);

const ENTRY_NAMES = /^(main|app|index|server|cli|manage|__main__|wsgi|asgi)\.[a-z0-9]+$/i;

export function inferFileRole(path: string): FileRole {
  const name = (path.split('/').pop() || path).toLowerCase();

  if (/^readme|^changelog|^contributing|^license|^security|\.(md|mdx|rst|txt)$/i.test(name)) {
    return 'Documentation';
  }
  if (MANIFESTS.has(name)) return 'Dependency manifest';
  if (ENTRY_NAMES.test(name)) return 'Entry point';
  if (/(^|[._-])(test|tests|spec|conftest)([._-]|$)/i.test(name)) return 'Test';
  if (/\.d\.ts$/i.test(name)) return 'Type definitions';
  if (/\.(css|scss|sass|less|styl)$/i.test(name)) return 'Stylesheet';
  if (/\.(html|htm|jinja|j2|hbs|ejs|astro|vue|svelte)$/i.test(name)) return 'Template';
  if (
    /\.(ya?ml|toml|ini|cfg|conf|env|editorconfig|lock)$/i.test(name) ||
    /^dockerfile|^makefile|^\./i.test(name)
  ) {
    return 'Configuration';
  }
  return 'Source';
}
