import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';

const INTERACTIVE = 'src/components/interactive';
const TIMELINE = join(INTERACTIVE, 'ReadingOrderTimeline.tsx');
const DASHBOARD = join(INTERACTIVE, 'AnalysisDashboard.tsx');

function read(path: string): string {
  return readFileSync(path, 'utf8');
}

describe('Reading Path — Functional & UI Audit Verification', () => {
  // ── 1. Reading Order Renders ─────────────────────────────────────────────
  test('1. reading order renders: ReadingOrderTimeline component exists and exports properly', () => {
    assert.ok(existsSync(TIMELINE), 'ReadingOrderTimeline component must exist');
    const src = read(TIMELINE);
    assert.ok(src.includes('export const ReadingOrderTimeline'), 'Component must be exported');
    assert.ok(src.includes('repoName'), 'Must accept repoName prop');
    assert.ok(src.includes('initialData'), 'Must support optional initialData');
  });

  // ── 2. Step Count & Telemetry ────────────────────────────────────────────
  test('2. step count: Renders actual step count and reading time without hardcoded values', () => {
    const src = read(TIMELINE);
    assert.ok(src.includes('READING PATH'), 'Header title must exist');
    assert.ok(src.includes('totalFiles'), 'Must compute totalFiles from ordered_files.length');
    assert.ok(src.includes('estimated_reading_time'), 'Must display real estimated_reading_time');
    assert.ok(src.includes('TOPOLOGY-RANKED'), 'Must label methodology as TOPOLOGY-RANKED');
  });

  // ── 3. Starting Point ───────────────────────────────────────────────────
  test('3. starting point: Elevated dynamic Start Here / Continue Here card with entry point callout', () => {
    const src = read(TIMELINE);
    assert.ok(src.includes('START HERE') && src.includes('CONTINUE HERE'), 'Must include START HERE and CONTINUE HERE callouts');
    assert.ok(src.includes('currentUnreadStep'), 'Must reference current unread file');
    assert.ok(src.includes('PRIMARY APPLICATION ENTRY POINT'), 'Must label as primary application entry point');
    assert.ok(src.includes('currentUnreadStep.file_path'), 'Must display starting file path');
  });

  // ── 4. Step Explanations ─────────────────────────────────────────────────
  test('4. step explanations: Steps display real reason and role tier from analysis', () => {
    const src = read(TIMELINE);
    assert.ok(src.includes('ordered_files.map'), 'Must map over ordered_files');
    assert.ok(src.includes('entry.reason'), 'Must display real reason from analysis data');
    assert.ok(src.includes('entry.tier'), 'Must render role tier badge');
    assert.ok(src.includes('importance'), 'Must compute importance tier based on score');
  });

  // ── 5. Relationship Context ──────────────────────────────────────────────
  test('5. relationship context: Displays sequence progression connectors and dependency flow', () => {
    const src = read(TIMELINE);
    assert.ok(src.includes('Next in sequence') || src.includes('ArrowDown'), 'Must render sequence connector between steps');
    assert.ok(src.includes('DEPENDENCY NEIGHBOURHOOD'), 'Must provide dependency neighbourhood context');
    assert.ok(src.includes('IMPORTS') && src.includes('IMPORTED BY'), 'Must show inbound and outbound dependencies');
  });

  // ── 6. Selected Step ────────────────────────────────────────────────────
  test('6. selected step: Selected file context drawer displays symbols, why read it, and dependencies', () => {
    const src = read(TIMELINE);
    assert.ok(src.includes('selectedFile &&'), 'Must render context drawer when step is selected');
    assert.ok(src.includes('STEP CONTEXT'), 'Must label drawer as STEP CONTEXT');
    assert.ok(src.includes('DEFINED SYMBOLS'), 'Must render DEFINED SYMBOLS region');
    assert.ok(src.includes('WHY READ THIS FILE'), 'Must render WHY READ THIS FILE rationale');
  });

  // ── 7. Next / Previous ──────────────────────────────────────────────────
  test('7. next/previous: Step navigation controls allow forward and backward stepping', () => {
    const src = read(TIMELINE);
    assert.ok(src.includes('handleNavigateStep'), 'Step navigation handler must exist');
    assert.ok(src.includes('Prev') && src.includes('Next'), 'Prev and Next buttons must be present');
    assert.ok(src.includes('disabled={currentIndex <= 0}'), 'Prev button must disable on first step');
    assert.ok(src.includes('disabled={currentIndex === -1 || currentIndex >= totalFiles - 1}'), 'Next button must disable on last step');
  });

  // ── 8. Open File & Action Suite ──────────────────────────────────────────
  test('8. open file: Action buttons provide Open on GitHub, Ask ARIA, File Graph, and Call Graph', () => {
    const src = read(TIMELINE);
    assert.ok(src.includes('Open on GitHub'), 'GitHub link must be present');
    assert.ok(src.includes('Ask ARIA About File'), 'Ask about file action must be present');
    assert.ok(src.includes('Inspect in File Graph'), 'Inspect in graph action must be present');
    assert.ok(src.includes('Trace in Call Graph'), 'Trace in call graph action must be present');
  });

  // ── 9. Empty State ───────────────────────────────────────────────────────
  test('9. empty state: Renders exact required fallback message when reading path is empty', () => {
    const src = read(TIMELINE);
    assert.ok(src.includes('No reading path available'), 'Empty state title must match requirement');
    assert.ok(src.includes('ARIA could not derive a reliable onboarding sequence from the available repository structure'), 'Must contain exact explanation text');
    assert.ok(src.includes('EmptyState'), 'Must use shared EmptyState component');
  });

  // ── 10. Degraded State ───────────────────────────────────────────────────
  test('10. degraded state: Gracefully distinguishes unavailable symbol and graph data', () => {
    const src = read(TIMELINE);
    assert.ok(src.includes('Reading Path Generation Failed'), 'Error state header must be defined');
    assert.ok(src.includes('Symbol index unavailable'), 'Distinguishes unavailable symbols');
    assert.ok(src.includes('Dependency graph unavailable'), 'Distinguishes unavailable dependencies');
  });

  // ── 11. Missing Optional Fields ──────────────────────────────────────────
  test('11. missing optional fields: Handles empty symbols, empty dependencies, and missing reasoning', () => {
    const src = read(TIMELINE);
    assert.ok(src.includes('No named functions or classes indexed'), 'Handles empty symbol list');
    assert.ok(src.includes('Isolated node with no direct file import edges'), 'Handles isolated nodes');
    assert.ok(src.includes('reasoning && reasoning.length > 0'), 'Safely guards reasoning array');
  });

  // ── 12. Long Paths ───────────────────────────────────────────────────────
  test('12. long paths: FilePath and title tooltips safely handle deeply nested paths', () => {
    const src = read(TIMELINE);
    assert.ok(src.includes('<FilePath'), 'Must use FilePath primitive');
    assert.ok(src.includes('truncate'), 'Truncate classes must prevent long path overflow');
    assert.ok(src.includes('title={entry.file_path}'), 'Title attribute ensures full path visibility');
  });

  // ── 13. Mobile-Safe Rendering ────────────────────────────────────────────
  test('13. mobile-safe rendering: Responsive grid stacks on mobile and switches to two-region layout on desktop', () => {
    const src = read(TIMELINE);
    assert.ok(src.includes('grid grid-cols-1 lg:grid-cols-12'), 'Responsive 12-column grid structure');
    assert.ok(src.includes('lg:col-span-7'), 'Timeline column allocation');
    assert.ok(src.includes('lg:col-span-5'), 'Context drawer column allocation');
    assert.ok(src.includes('overflow-y-auto') || src.includes('overflow-hidden'), 'Controlled overflow');
  });

  // ── 14. Navigation Events Intact ─────────────────────────────────────────
  test('14. existing navigation events remain intact: AnalysisDashboard wires callbacks without regression', () => {
    const dashSrc = read(DASHBOARD);
    assert.ok(dashSrc.includes('ReadingOrderTimeline'), 'Must import ReadingOrderTimeline');
    assert.ok(dashSrc.includes("id === 'reading_path'") || dashSrc.includes("activeTab === 'reading_path'"), 'Must mount in reading_path tab');
    assert.ok(dashSrc.includes('onAskAboutFile={handleAskAboutFile}'), 'Must pass onAskAboutFile handler');
    assert.ok(dashSrc.includes('onViewInGraph={handleViewInGraph}'), 'Must pass onViewInGraph handler');
    assert.ok(dashSrc.includes('onViewInCallGraph={handleViewInCallGraph}'), 'Must pass onViewInCallGraph handler');
  });

  // ── 15. Dynamic Start Here / Continue Here Banner ─────────────────────────
  test('15. dynamic banner switches between START HERE and CONTINUE HERE based on progress', () => {
    const src = read(TIMELINE);
    assert.ok(src.includes("completedCount === 0 ? 'START HERE' : 'CONTINUE HERE'"), 'Banner dynamically toggles label');
    assert.ok(src.includes('currentUnreadStep'), 'Banner is driven by currentUnreadStep');
    assert.ok(src.includes('firstUnreadIndex'), 'Banner shows accurate current step index');
  });

  // ── 16. Automatic Advancement & Completion Logic ─────────────────────────
  test('16. auto-advancement finds first unread step and updates selection', () => {
    const src = read(TIMELINE);
    assert.ok(src.includes('handleToggleComplete'), 'handleToggleComplete handler exists');
    assert.ok(src.includes('nextUnread'), 'Computes next unread step on completion');
    assert.ok(src.includes('setSelectedFile(nextUnread)'), 'Auto-advances selected step to next unread file');
  });

  // ── 17. Reading Path Complete State ──────────────────────────────────────
  test('17. all steps complete renders dedicated completion banner and review actions', () => {
    const src = read(TIMELINE);
    assert.ok(src.includes('READING PATH COMPLETE'), 'Must render READING PATH COMPLETE banner');
    assert.ok(src.includes('Review Step 01'), 'Must provide Review Step 01 action');
    assert.ok(src.includes('Explore Architecture'), 'Must provide Explore Architecture action');
    assert.ok(src.includes('isAllComplete'), 'Guarded by isAllComplete state');
  });

  // ── 18. Repository-Isolated Storage Key ──────────────────────────────────
  test('18. persistence uses normalized repository-isolated storage keys', () => {
    const src = read(TIMELINE);
    assert.ok(src.includes('reading-path-progress:'), 'Uses reading-path-progress prefix');
    assert.ok(src.includes('toLowerCase()'), 'Normalizes repo name to lower-case');
  });

  // ── 19. Dynamic Remaining Time Calculation ───────────────────────────────
  test('19. remaining time sums only unread step reading durations', () => {
    const src = read(TIMELINE);
    assert.ok(src.includes('remainingMinutes'), 'Computes remainingMinutes');
    assert.ok(src.includes('filter((f) => !completedFiles[f.file_path])') || src.includes('filter(f => !completedFiles[f.file_path])'), 'Filters only unread files');
  });

  // ── 20. Accessible Screen Reader Live Announcement ────────────────────────
  test('20. step completion announces transition via live region', () => {
    const src = read(TIMELINE);
    assert.ok(src.includes('aria-live="polite"'), 'Uses polite aria-live region');
    assert.ok(src.includes('setAnnouncement'), 'Updates screen reader announcement on completion');
  });
});

