import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { SCENE_IDS } from '../src/components/landing/sceneModel.ts';

const INDEX = 'src/pages/index.astro';
const HERO = 'src/components/landing/HeroStage.astro';
const STRUCTURE = 'src/components/landing/StructureTransform.tsx';
const CHAPTER_HEADING = 'src/components/landing/ChapterHeading.astro';
const CSS = 'src/styles/global.css';

const read = (p: string) => readFileSync(p, 'utf8');

describe('Typographic Narrative Reduction Pass', () => {
  const index = read(INDEX);
  const hero = read(HERO);
  const structure = read(STRUCTURE);
  const chapterHeading = read(CHAPTER_HEADING);
  const css = read(CSS);

  test('the four demoted giant headlines are no longer rendered as display headings', () => {
    // 1. Scene 04: "The codebase is a graph."
    assert.ok(
      !/lines=\{.*'The codebase'.*'is a graph'.*\}/s.test(index),
      'Scene 04 should not render "The codebase is a graph." as display lines in ChapterHeading',
    );

    // 2. Scene 06: "A repository has a history."
    assert.ok(
      !/lines=\{.*'A repository'.*'has a history'.*\}/s.test(index),
      'Scene 06 should not render "A repository has a history." as display lines in ChapterHeading',
    );

    // 3. Scene 08: "Read the codebase in the right order."
    assert.ok(
      !/lines=\{.*'Read the codebase'.*'in the right order'.*\}/s.test(index),
      'Scene 08 should not render "Read the codebase in the right order." as display lines in ChapterHeading',
    );

    // 4. Scene 09: "Deterministic analysis core."
    assert.ok(
      !/lines=\{.*'Deterministic'.*'analysis core'.*\}/s.test(index),
      'Scene 09 should not render "Deterministic analysis core." as display lines in ChapterHeading',
    );

    // Redundant extra statement in Scene 05: "Every change has a shadow."
    assert.ok(
      !index.includes('Every change has a shadow'),
      'Redundant display statement "Every change has a shadow." should be removed',
    );
  });

  test('primary signature statements remain with appropriate prominence', () => {
    // Scene 01: Hero
    assert.ok(
      hero.includes('Understand') && hero.includes('Any codebase.'),
      'Scene 01 Hero statement "Understand Any codebase." must remain',
    );

    // Scene 02: Premise
    assert.ok(
      index.includes('Structure is hidden.') && index.includes('Until you map it.'),
      'Scene 02 statement "Structure is hidden. Until you map it." must remain',
    );

    // Scene 03: Structural Transformation
    assert.ok(
      structure.includes('The repository stops being a list.') &&
        structure.includes('It becomes a topology.'),
      'Scene 03 statement "The repository stops being a list. It becomes a topology." must remain',
    );

    // Scene 05: Change Surface
    assert.ok(
      index.includes("lines={['Know what', 'a change touches.']}"),
      'Scene 05 signature statement "Know what a change touches." must remain',
    );

    // Scene 07: Grounded Retrieval
    assert.ok(
      index.includes("lines={['Ask the', 'codebase.']}"),
      'Scene 07 statement "Ask the codebase." must remain',
    );

    // Scene 11: Final Statement
    assert.ok(
      index.includes('Stop') && index.includes('reading') && index.includes('the codebase.'),
      'Scene 11 signature statement "Stop reading the codebase." must remain',
    );
    assert.ok(
      index.includes('Let ARIA') && index.includes('map it first.'),
      'Scene 11 resolution "Let ARIA map it first." must remain',
    );

    // Scene 12: Enter the System / CTA
    assert.ok(
      index.includes("lines={['Start with', 'a repository.']}"),
      'Scene 12 CTA statement "Start with a repository." must remain',
    );
  });

  test('chapter markers remain complete and correctly formatted', () => {
    const requiredMarkers = [
      '01 — THE PREMISE',
      '02 — STRUCTURAL TRANSFORMATION',
      '03 — STRUCTURAL INTELLIGENCE',
      '04 — CHANGE SURFACE',
      '05 — REPOSITORY MEMORY',
      '06 — GROUNDED RETRIEVAL',
      '07 — ONBOARDING',
      '08 — PIPELINE ARCHITECTURE',
      '09 — TECHNOLOGY',
      '10 — ENTER THE SYSTEM',
    ];

    const allMarkup = `${hero}\n${structure}\n${index}`;
    for (const marker of requiredMarkers) {
      assert.ok(allMarkup.includes(marker), `Missing chapter marker: ${marker}`);
    }
  });

  test('semantic headings remain intact for accessibility', () => {
    const requiredHeadingIds = [
      'hero-heading',
      'premise-heading',
      'graph-heading',
      'change-heading',
      'memory-heading',
      'retrieval-heading',
      'onboarding-heading',
      'pipeline-heading',
      'analyze-heading',
    ];

    const allMarkup = `${hero}\n${structure}\n${index}`;
    for (const id of requiredHeadingIds) {
      assert.ok(allMarkup.includes(id), `Missing semantic heading ID: ${id}`);
    }

    // Check that ChapterHeading preserves semantic <h2> even when compact
    assert.ok(
      chapterHeading.includes('headingId') && chapterHeading.includes('<h2'),
      'ChapterHeading must render semantic <h2> with headingId',
    );
  });

  test('product visualizations remain untouched and present in scenes', () => {
    assert.ok(hero.includes('HeroGraph'), 'HeroGraph must remain in HeroStage');
    assert.ok(index.includes('StructureTransform'), 'StructureTransform must remain');
    assert.ok(index.includes('CodebaseGraph'), 'CodebaseGraph must remain');
    assert.ok(index.includes('ChangeSurface'), 'ChangeSurface must remain');
    assert.ok(index.includes('RepositoryHistory'), 'RepositoryHistory must remain');
    assert.ok(index.includes('GroundedRetrieval'), 'GroundedRetrieval must remain');
    assert.ok(index.includes('ReadingPath'), 'ReadingPath must remain');
    assert.ok(index.includes('AnalysisPipeline'), 'AnalysisPipeline must remain');
    assert.ok(index.includes('RepositoryAnalyzer'), 'RepositoryAnalyzer must remain');
  });

  test('scene ordering remains unchanged', () => {
    const stages = Array.from(index.matchAll(/data-stage="([a-z]+)"/g)).map((m) => m[1]);
    const runs = stages.filter((s, i) => s !== stages[i - 1]);
    const expected = SCENE_IDS.filter((id) => stages.includes(id));
    assert.deepEqual(runs, expected);
  });

  test('Level 2 product-thesis style is defined in global CSS', () => {
    assert.ok(
      css.includes('.product-thesis'),
      '.product-thesis class must be defined in global.css',
    );
  });
});
