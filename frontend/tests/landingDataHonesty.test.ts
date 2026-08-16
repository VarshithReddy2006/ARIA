import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  CHANGE_SCENARIOS,
  HISTORY_SUMMARY,
  REPOSITORY_HISTORY as REPOSITORY_HISTORY_SPANS,
} from '../src/components/landing/data.ts';

/**
 * Data-honesty invariants for the landing story.
 *
 * The landing page is allowed to be illustrative. It is not allowed to present
 * an invented score as if something measured it, and any illustrative figure has
 * to carry its disclosure at every breakpoint.
 */

const CHANGE_SURFACE = 'src/components/landing/ChangeSurface.tsx';
const CODEBASE_GRAPH = 'src/components/landing/CodebaseGraph.tsx';
const STRUCTURE_TRANSFORM = 'src/components/landing/StructureTransform.tsx';
const REPOSITORY_HISTORY = 'src/components/landing/RepositoryHistory.tsx';

/** Every landing surface that renders illustrative figures. */
const ILLUSTRATIVE_SURFACES = [
  CHANGE_SURFACE,
  CODEBASE_GRAPH,
  STRUCTURE_TRANSFORM,
  REPOSITORY_HISTORY,
];

/**
 * Source with comments stripped.
 *
 * These guards must test what the component renders, not what its comments
 * discuss — otherwise documenting "we removed the invented risk score" trips the
 * assertion that the invented risk score is gone.
 */
function read(path: string): string {
  return readFileSync(path, 'utf8')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/\{\s*\/\*[\s\S]*?\*\/\s*\}/g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1');
}


describe('Chapter 04 — change surface presents propagation, not prediction', () => {
  test('does not render an invented risk score or severity verdict', () => {
    const src = read(CHANGE_SURFACE);

    /*
      The chapter used to lead with "BLAST RADIUS RISK", a 0-100 `riskScore` and a
      High/Medium/Low badge. Nothing measures those, and the thresholds behind the
      severity were invented for the illustration.
    */
    assert.ok(!src.includes('BLAST RADIUS RISK'), 'the invented risk headline is back');
    assert.ok(!src.includes('RISK_TONE'), 'the severity tone map is back');
    assert.ok(
      !src.includes('scenario.riskScore'),
      'the invented risk score is being rendered again',
    );
    assert.ok(
      !src.includes('scenario.risk}'),
      'the invented severity badge is being rendered again',
    );
    assert.ok(!/\/ 100/.test(src), 'a score-out-of-100 framing is back');
  });

  test('reports structural reach instead', () => {
    const src = read(CHANGE_SURFACE);
    assert.ok(src.includes('AFFECTED SURFACE'), 'the affected-surface readout is missing');
    for (const field of ['scenario.files', 'scenario.depth', 'scenario.symbols']) {
      assert.ok(src.includes(field), `${field} is no longer reported`);
    }
    assert.ok(
      src.includes('scenario.chain.length'),
      'hop count is no longer derived from the chain',
    );
  });

  test('every metric it shows exists in the scenario model', () => {
    for (const s of CHANGE_SCENARIOS) {
      assert.equal(typeof s.files, 'number');
      assert.equal(typeof s.depth, 'number');
      assert.equal(typeof s.symbols, 'number');
      assert.ok(s.chain.length > 0, `${s.id} has no propagation chain`);
    }
  });

  test('the chain tells the CHANGED -> ... -> ENTRY story', () => {
    for (const s of CHANGE_SCENARIOS) {
      assert.match(
        s.chain[0].stage,
        /CHANGED/,
        `${s.id} does not begin at the changed symbol`,
      );
      assert.ok(
        s.chain.length >= 2,
        `${s.id} needs at least an origin and one affected stage to show propagation`,
      );
    }
  });

  test('direction is explicit on the propagation spine', () => {
    const src = read(CHANGE_SURFACE);
    assert.ok(
      src.includes("from '../interactive/graph/edgeSemantics'"),
      'propagation must reuse the shared outbound tone, not a local colour',
    );
    assert.ok(src.includes('EDGE_TONE.outgoing'), 'outbound tone is not the shared one');
    assert.ok(!src.includes('#818cf8'), 'the outbound tone is hardcoded');
  });

  test('carries no perpetual motion', () => {
    const src = read(CHANGE_SURFACE);
    assert.ok(!src.includes('animateMotion'), 'travelling packets are back');
    assert.ok(!src.includes('repeatCount'), 'an indefinite animation is back');
    assert.ok(!src.includes('animate-pulse'), 'a pulse animation is back');
  });
});

describe('Landing illustrative disclosures', () => {
  test('every illustrative surface discloses itself, unhidden', () => {
    for (const file of ILLUSTRATIVE_SURFACES) {
      const src = read(file);
      assert.ok(src.includes('ILLUSTRATIVE'), `${file} shows figures without disclosing them`);
      assert.ok(
        !/hidden\s+(sm|md|lg):block[^>]*>\s*\n?\s*ILLUSTRATIVE/.test(src),
        `${file} hides its illustrative disclosure at a breakpoint`,
      );
    }
  });

  test('the disclosure wording is consistent across chapters', () => {
    for (const file of ILLUSTRATIVE_SURFACES) {
      assert.ok(
        read(file).includes("ARIA&apos;S OWN REPOSITORY"),
        `${file} uses a different disclosure phrasing`,
      );
    }
  });
});

describe('Chapter 05 — repository memory reports change, not health', () => {
  test('the temporal chapter invents no score or verdict', () => {
    const src = read(REPOSITORY_HISTORY);
    for (const banned of ['RISK', 'HEALTH', 'SCORE', 'SEVERITY', 'CONFIDENCE']) {
      assert.ok(!src.includes(banned), `${banned} is being asserted from git history`);
    }
  });

  test('nothing animates as though commits were arriving live', () => {
    const src = read(REPOSITORY_HISTORY);
    assert.ok(!src.includes('setInterval'), 'a ticking clock implies live history');
    assert.ok(!src.includes('animate-pulse'), 'a pulse animation is back');
    assert.ok(!src.includes('infinite'), 'an indefinite animation is back');
  });

  test('every read-out is derived from the spans, never hardcoded', () => {
    const src = read(REPOSITORY_HISTORY);
    assert.ok(src.includes('HISTORY_SUMMARY'), 'summary figures are not derived from the model');
    for (const span of REPOSITORY_HISTORY_SPANS) {
      assert.ok(span.to > span.from, `${span.path} has a span that does not advance`);
      assert.ok(span.from >= 0 && span.to <= 1, `${span.path} falls outside the 0-1 window`);
      assert.ok(span.churn >= 0 && span.churn <= 1, `${span.path} has churn outside 0-1`);
      assert.ok(span.commits > 0, `${span.path} has no commits`);
    }
  });

  test('the summary matches the spans it claims to summarise', () => {
    assert.equal(HISTORY_SUMMARY.files, REPOSITORY_HISTORY_SPANS.length);
    assert.equal(
      HISTORY_SUMMARY.commits,
      REPOSITORY_HISTORY_SPANS.reduce((sum, s) => sum + s.commits, 0),
    );
    assert.equal(
      HISTORY_SUMMARY.hotspots,
      REPOSITORY_HISTORY_SPANS.filter((s) => s.hotspot).length,
    );
  });

  test('mobile recomposes the window rather than shrinking it', () => {
    const compact = REPOSITORY_HISTORY_SPANS.filter((s) => s.compact);
    assert.ok(compact.length > 0, 'mobile needs a curated subset');
    assert.ok(
      compact.length < REPOSITORY_HISTORY_SPANS.length,
      'mobile should carry fewer modules, not the same set at a smaller size',
    );
    assert.ok(
      compact.some((s) => s.hotspot),
      'the hotspot argument must survive on mobile',
    );
  });
});
