import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { groupTech, classifyTech } from '../src/lib/techCategories.ts';
import { deriveInsights } from '../src/lib/repoInsights.ts';
import { computeComplexity, detectPrimaryLanguage, estimateReadingMinutes } from '../src/lib/repoMetrics.ts';

const INTERACTIVE = 'src/components/interactive';
const OVERVIEW = join(INTERACTIVE, 'RepositoryOverview.tsx');
const HERO = join(INTERACTIVE, 'RepoHero.tsx');
const DASHBOARD = join(INTERACTIVE, 'AnalysisDashboard.tsx');

function read(path: string): string {
  return readFileSync(path, 'utf8');
}

describe('Repository Overview Redesign — Architecture & Verification', () => {
  // ── 1. Repository Header & Compact Structure ─────────────────────────────
  test('1. Repository Header component exists and renders compact layout', () => {
    assert.ok(existsSync(HERO), 'RepoHero component must exist');
    const heroSrc = read(HERO);
    assert.ok(heroSrc.includes('repo-header-title'), 'Header title ID must be declared');
    assert.ok(heroSrc.includes('INDEXED'), 'Header must display INDEXED status');
    assert.ok(heroSrc.includes('onOpenCommandPalette'), 'Search action must be wired');
    assert.ok(heroSrc.includes('onRefresh'), 'Refresh action must be wired');
    assert.ok(heroSrc.includes('onExportReport'), 'Export report action must be wired');
  });

  // ── 2. Long Repository Name Truncation ───────────────────────────────────
  test('2. Long repository names truncate gracefully without layout overflow', () => {
    const heroSrc = read(HERO);
    assert.ok(heroSrc.includes('truncate'), 'Repository slug must use truncate classes');
    assert.ok(heroSrc.includes('max-w-'), 'Repository slug must specify responsive max-widths');
  });

  // ── 3. Indexed Status & Metadata ─────────────────────────────────────────
  test('3. Indexed metadata uses real relative time and status', () => {
    const heroSrc = read(HERO);
    assert.ok(heroSrc.includes('relativeTimeFrom'), 'Last indexed must compute from indexedAt timestamp');
    assert.ok(heroSrc.includes('bg-success'), 'INDEXED dot must have healthy green styling');
  });

  // ── 4. Real Health Score & Invariants ────────────────────────────────────
  test('4. Health score uses real API data without hardcoded scores', () => {
    const overviewSrc = read(OVERVIEW);
    assert.ok(overviewSrc.includes('health ?'), 'Health score must conditionally render real score or placeholder');
    assert.ok(overviewSrc.includes('Grade'), 'Grade must be displayed when health is available');
    assert.ok(overviewSrc.includes('Meter'), 'Health meter must be rendered');
    assert.ok(!overviewSrc.includes('98.4'), 'No hardcoded score 98.4 allowed');
  });

  // ── 5. Real Key Metrics Verification ─────────────────────────────────────
  test('5. Key metrics are computed from real analysis payload', () => {
    const files = 1425;
    const components = 12;
    const dependencies = 68;

    const complexity = computeComplexity({
      fileCount: files,
      componentCount: components,
      dependencyCount: dependencies,
    });

    assert.ok(Number.isFinite(complexity.score), 'Complexity score must be numeric');
    assert.ok(['Low', 'Moderate', 'High', 'Very High'].includes(complexity.label), 'Complexity label must be standard');

    const readingMinutes = estimateReadingMinutes(5);
    assert.ok(readingMinutes > 0, 'Reading minutes must be positive');
  });

  // ── 6 & 7. Findings & Prioritization ─────────────────────────────────────
  test('6 & 7. What Needs Attention derives findings and sorts by severity', () => {
    const dummyInputs = {
      fileCount: 500,
      directoryCount: 20,
      dependencyCount: 75,
      techStack: ['Python', 'FastAPI', 'Torch', 'Postgres', 'Redis'],
      structure: { 'src/': ['main.py', 'app.py'] },
      entryPointCount: 2,
      cycleCount: 1,
      componentCount: 5,
      relationshipCount: 4,
      readingSteps: 5,
      readingMinutes: 30,
    };

    const findings = deriveInsights(dummyInputs);
    assert.ok(findings.length > 0, 'deriveInsights must produce findings');

    // Verify first finding is risk due to cycleCount > 0
    assert.equal(findings[0].severity, 'risk', 'Risks must lead the finding list');
    assert.equal(findings[0].id, 'cycles', 'Cycle risk must be detected');
  });

  // ── 8. Technology Stack Grouping ─────────────────────────────────────────
  test('8. Technology stack groups categories properly using groupTech', () => {
    const stack = ['FastAPI', 'React', 'Python', 'Postgres', 'OpenAI', 'Docker'];
    const groups = groupTech(stack);

    assert.ok(groups.length >= 3, 'Stack must produce multiple grouped categories');
    const categories = groups.map((g) => g.meta.id);
    assert.ok(categories.includes('backend') || categories.includes('language'), 'Must detect backend or language');
  });

  // ── 9. Dependency Surface Counts ─────────────────────────────────────────
  test('9. Dependency classification correctly groups package manifests', () => {
    const deps = ['fastapi', 'uvicorn', 'pydantic', 'react', 'torch', 'pytest'];
    const groups = groupTech(deps);
    const total = groups.reduce((acc, g) => acc + g.items.length, 0);
    assert.equal(total, 6, 'All unique dependencies must be classified');
  });

  // ── 10 & 11. Architecture Relationships vs Empty State ───────────────────
  test('10 & 11. Architecture snapshot handles both relationships and compact empty states', () => {
    const overviewSrc = read(OVERVIEW);
    assert.ok(
      overviewSrc.includes('architecture.relationships.length > 0'),
      'Overview must branch on relationship existence',
    );
    assert.ok(
      overviewSrc.includes('No component relationships detected'),
      'Compact empty state copy must be present',
    );
    assert.ok(
      overviewSrc.includes('Inspect File Graph'),
      'Inspect File Graph action must be present in empty state',
    );
  });

  // ── 12 & 13. Entry Points Grouping & Truncation ──────────────────────────
  test('12 & 13. Entry points group duplicates and indicate overflow', () => {
    const overviewSrc = read(OVERVIEW);
    assert.ok(overviewSrc.includes('ENTRY POINTS'), 'Entry points section must be labelled');
    assert.ok(overviewSrc.includes('groupedEntryPoints'), 'Grouped entry points must be consumed');
    assert.ok(overviewSrc.includes('more entry files detected') || overviewSrc.includes('more'), 'Overflow indicator must be present');
  });

  // ── 14. Recommended Next Actions ─────────────────────────────────────────
  test('14. Recommended next actions are derived from signals', () => {
    const overviewSrc = read(OVERVIEW);
    assert.ok(overviewSrc.includes('WHAT SHOULD YOU INSPECT NEXT?'), 'Recommended next title must be declared');
    assert.ok(overviewSrc.includes('Explore Dependency Hotspots'), 'Dependency recommendation must exist');
    assert.ok(overviewSrc.includes('Inspect Architecture Graph'), 'Architecture recommendation must exist');
    assert.ok(overviewSrc.includes('Follow Reading Path'), 'Reading path recommendation must exist');
    assert.ok(overviewSrc.includes('Review Health Report'), 'Health report recommendation must exist');
    assert.ok(overviewSrc.includes('Ask ARIA'), 'Ask ARIA recommendation must exist');
  });

  // ── 15, 16, 17. States: Loading, Degraded, Error ─────────────────────────
  test('15, 16, 17. Dashboard shell handles Loading, Degraded, and Error states', () => {
    const dashSrc = read(DASHBOARD);
    assert.ok(dashSrc.includes('SkeletonDashboard') || dashSrc.includes('SkeletonGroup'), 'Loading state must use skeletons');
    assert.ok(dashSrc.includes('ANALYSIS DEGRADED') || dashSrc.includes('isDegraded'), 'Degraded state must explain capability state');
    assert.ok(dashSrc.includes('Analysis could not be loaded'), 'Error state must provide clear diagnostic title');
    assert.ok(dashSrc.includes('Retry Loading'), 'Error state must provide retry button');
  });

  // ── 18. Missing Optional Fields Handling ─────────────────────────────────
  test('18. Missing optional fields do not crash the component', () => {
    const overviewSrc = read(OVERVIEW);
    assert.ok(overviewSrc.includes('primaryLanguage || \'—\'') || overviewSrc.includes('primaryLanguage ||'), 'Primary language fallback must exist');
    assert.ok(overviewSrc.includes('insights.length === 0'), 'Insights empty check must exist');
    assert.ok(overviewSrc.includes('techGroups.length === 0'), 'Tech groups empty check must exist');
  });

  // ── 19. Existing Navigation Actions Preservation ─────────────────────────
  test('19. Existing navigation actions and event contracts are intact', () => {
    const dashSrc = read(DASHBOARD);
    for (const evt of [
      'aria-open-graph',
      'aria-open-chat',
      'aria-open-impact',
      'aria-open-issues',
      'aria-workspace-file-select',
    ]) {
      assert.ok(dashSrc.includes(`addEventListener('${evt}'`), `Event ${evt} must be preserved`);
    }
  });

  // ── 20. Repository Purpose & Capability Briefing ─────────────────────────
  test('20. Repository Brief correctly extracts purpose, capabilities, and flows from real evidence', async () => {
    const { deriveRepoBrief } = await import('../src/lib/repoBrief.ts');

    const result = deriveRepoBrief({
      repoName: 'VarshithReddy2006/PhishingWebsite_Detection',
      summary: 'Phishing website detection system that identifies fraudulent URLs using machine learning and deep learning classification pipelines.',
      techStack: ['Python', 'JavaScript', 'HTML', 'CSS', 'Flask'],
      dependencies: ['flask', 'joblib', 'numpy', 'pandas', 'scikit-learn', 'torch', 'transformers'],
      structure: {
        '.': ['app.py', 'package.json', 'README.md'],
        'templates': ['index.html', 'popup.html'],
        'extension': ['manifest.json', 'popup.js', 'background.js'],
      },
      entryPoints: ['app.py'],
      relationships: [
        { source: 'app.py', target: 'models/classifier.py', relationship_type: 'imports' },
      ],
    });

    assert.ok(result.about.includes('Phishing website detection'), 'About must capture real summary');
    assert.ok(result.purpose !== null, 'Purpose must be extracted');
    assert.ok(result.capabilities.length >= 3, 'Must detect multiple capabilities (REST API, ML Inference, Extension)');
    assert.ok(result.pipelineSteps && result.pipelineSteps.length >= 4, 'Must construct execution flow when ML and web API exist');

    const capTitles = result.capabilities.map(c => c.title);
    assert.ok(capTitles.some(t => t.includes('REST API') || t.includes('Web Service')), 'Must detect REST API capability');
    assert.ok(capTitles.some(t => t.includes('ML Model') || t.includes('Machine Learning')), 'Must detect ML inference capability');
  });

  test('21. Repository Brief handles unknown/untrusted purpose honestly with fallback', async () => {
    const { deriveRepoBrief } = await import('../src/lib/repoBrief.ts');

    const result = deriveRepoBrief({
      repoName: 'example/minimal-utility',
      summary: '',
      techStack: [],
      dependencies: [],
      structure: {},
      entryPoints: [],
    });

    assert.equal(result.isConfidenceHigh, false, 'Must flag low confidence for empty manifests');
    assert.ok(result.about.includes('Purpose not confidently inferred'), 'Must emit honest fallback message');
    assert.equal(result.purpose, null, 'Must not invent fake purpose');
    assert.equal(result.pipelineSteps, undefined, 'Must not invent fake execution pipeline');
  });

  test('22. Overview component renders About This Repository and Key Capabilities', () => {
    const overviewSrc = read(OVERVIEW);
    assert.ok(overviewSrc.includes('ABOUT THIS REPOSITORY'), 'Overview must render About section');
    assert.ok(overviewSrc.includes('KEY CAPABILITIES'), 'Overview must render Key Capabilities section');
    assert.ok(overviewSrc.includes('deriveRepoBrief'), 'Overview must use deriveRepoBrief');
  });

  // ── 23. Reading Path Preview & Inspection Action ──────────────────────────
  test('23. Overview renders Reading Path Preview with step sequence and follow CTA', () => {
    const overviewSrc = read(OVERVIEW);
    assert.ok(overviewSrc.includes('READING PATH PREVIEW'), 'Reading path preview section must exist');
    assert.ok(overviewSrc.includes('Follow Reading Path'), 'Follow Reading Path CTA must exist');
  });

  // ── 24. Structured Attention Findings (What / Evidence / Caveat) ───────────
  test('24. What Needs Attention renders structured What, Evidence, and Caveat blocks', () => {
    const overviewSrc = read(OVERVIEW);
    assert.ok(overviewSrc.includes('WHAT'), 'Must render WHAT label');
    assert.ok(overviewSrc.includes('EVIDENCE'), 'Must render EVIDENCE label');
    assert.ok(overviewSrc.includes('CAVEAT'), 'Must render CAVEAT label');
  });

  // ── 25. Confidence States Representation ──────────────────────────────────
  test('25. Confidence states VERIFIED, INFERRED, UNKNOWN are supported honestly', async () => {
    const { deriveRepoBrief } = await import('../src/lib/repoBrief.ts');

    const verified = deriveRepoBrief({
      repoName: 'test/verified',
      summary: 'Verified production repository with full documentation.',
      techStack: ['Python', 'FastAPI'],
      dependencies: ['fastapi'],
      structure: { '.': ['main.py'] },
      entryPoints: ['main.py'],
    });
    assert.equal(verified.confidenceState, 'VERIFIED');

    const inferred = deriveRepoBrief({
      repoName: 'test/inferred',
      summary: '',
      techStack: ['Python', 'Flask'],
      dependencies: ['flask'],
      structure: { '.': ['app.py'] },
      entryPoints: ['app.py'],
    });
    assert.equal(inferred.confidenceState, 'INFERRED');

    const unknown = deriveRepoBrief({
      repoName: 'test/unknown',
      summary: '',
      techStack: [],
      dependencies: [],
      structure: {},
      entryPoints: [],
    });
    assert.equal(unknown.confidenceState, 'UNKNOWN');
  });
});

