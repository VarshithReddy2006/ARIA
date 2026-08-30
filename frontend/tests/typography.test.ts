import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

function read(path: string): string {
  return readFileSync(path, 'utf8');
}

describe('ARIA Typography Upgrade — Two-Font System Verification', () => {
  const layout = read('src/layouts/Layout.astro');
  const tailwind = read('tailwind.config.mjs');
  const globalCss = read('src/styles/global.css');
  const readingPath = read('src/components/interactive/ReadingOrderTimeline.tsx');
  const repoHero = read('src/components/interactive/RepoHero.tsx');

  test('1. Layout.astro preloads Space Grotesk and JetBrains Mono', () => {
    assert.ok(layout.includes('Space+Grotesk'), 'Must load Space Grotesk');
    assert.ok(layout.includes('JetBrains+Mono'), 'Must load JetBrains Mono');
    assert.ok(layout.includes('rel="preload"'), 'Must preload fonts to prevent FOUT');
  });

  test('2. tailwind.config.mjs configures Space Grotesk for sans/display and JetBrains Mono for mono', () => {
    assert.ok(tailwind.includes('"Space Grotesk"'), 'Must declare Space Grotesk in font family');
    assert.ok(tailwind.includes('"JetBrains Mono"'), 'Must declare JetBrains Mono in font family');
  });

  test('3. global.css defines central typography tokens and hierarchy classes', () => {
    assert.ok(globalCss.includes('--font-ui:'), 'Must define --font-ui variable');
    assert.ok(globalCss.includes('--font-tech:'), 'Must define --font-tech variable');
    assert.ok(globalCss.includes('.page-title'), 'Must define .page-title token');
    assert.ok(globalCss.includes('.section-heading'), 'Must define .section-heading token');
    assert.ok(globalCss.includes('.body-ui'), 'Must define .body-ui token');
    assert.ok(globalCss.includes('.metric-display'), 'Must define .metric-display token');
    assert.ok(globalCss.includes('.tech-meta'), 'Must define .tech-meta token');
    assert.ok(globalCss.includes('.tech-eyebrow'), 'Must define .tech-eyebrow token');
  });

  test('4. mono-label uppercase letter-spacing is restrained (~0.16em)', () => {
    assert.ok(globalCss.includes('letter-spacing: 0.16em'), 'Must restrain letter spacing to ~0.16em');
    assert.ok(!globalCss.includes('letter-spacing: 0.28em'), 'Must not have excessive 0.28em tracking');
  });

  test('5. ReadingOrderTimeline uses Space Grotesk for descriptions, metrics, and buttons', () => {
    // Metrics in Space Grotesk (font-sans)
    assert.ok(readingPath.includes('font-sans text-2xl sm:text-3xl font-bold text-text tabular-nums'), 'Metrics use Space Grotesk');
    // Rationale paragraphs in Space Grotesk (font-sans)
    assert.ok(readingPath.includes('font-sans leading-relaxed'), 'Step reasons use Space Grotesk');
    // Buttons in Space Grotesk (font-sans)
    assert.ok(readingPath.includes('font-sans font-semibold') || readingPath.includes('font-sans font-medium'), 'Action buttons use Space Grotesk');
    // File paths and technical labels in JetBrains Mono (font-mono / mono-label)
    assert.ok(readingPath.includes('font-mono') && readingPath.includes('entry.file_path'), 'File paths use JetBrains Mono');
    assert.ok(readingPath.includes('mono-label'), 'Technical section labels use JetBrains Mono');
  });

  test('6. RepoHero uses Space Grotesk for repository identity and buttons', () => {
    assert.ok(repoHero.includes('font-sans font-bold tracking-tight text-text text-xl sm:text-2xl md:text-3xl'), 'Repo identity title uses Space Grotesk');
    assert.ok(repoHero.includes('font-sans font-semibold'), 'Primary action button uses Space Grotesk');
  });
});
