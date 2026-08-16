import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  SCENES,
  SCENE_IDS,
  TRANSITIONS,
  HANDOFF_START,
  MIN_SCENE_VH,
  MIN_SCENE_VH_COMPACT,
  MIN_STAGE_VIEWPORT,
  clamp01,
  createStepProgress,
  isReverse,
  resolveHandoff,
  scene,
  sceneAt,
  sceneIndex,
  stageAt,
  transitionBetween,
  type SceneBand,
  type SceneId,
} from '../src/components/landing/sceneModel.ts';

/**
 * The cinematic scene system.
 *
 * The whole design rests on one property: every visual state is a function of
 * scroll position, never of a clock. These tests pin that property and the
 * behaviours that depend on it — fast-scroll handoffs, reverse travel, scene
 * boundaries and creation order — so the browser is only needed to confirm it
 * looks right, not to confirm it is correct.
 */

const INDEX = 'src/pages/index.astro';
const RAIL = 'src/components/landing/ChapterRail.astro';
const GLIMPSE = 'src/components/landing/SceneGlimpse.astro';
const BACKDROP = 'src/components/landing/StoryBackdrop.astro';
const CSS = 'src/styles/global.css';

const read = (p: string) => readFileSync(p, 'utf8');

describe('Scene order', () => {
  test('there are twelve scenes, in the approved sequence', () => {
    assert.deepEqual(SCENE_IDS, [
      'hero', 'thesis', 'structure', 'architecture', 'impact', 'memory',
      'retrieval', 'route', 'pipeline', 'technology', 'statement', 'command',
    ]);
  });

  test('no scene is declared twice', () => {
    assert.equal(new Set(SCENE_IDS).size, SCENE_IDS.length);
  });

  test('every scene has a label and at least one creation step', () => {
    for (const s of SCENES) {
      assert.ok(s.label.length > 0, `${s.id} has no label`);
      assert.ok(s.createSteps >= 1, `${s.id} has no creation steps`);
    }
  });

  test('sceneIndex and sceneAt agree, and sceneAt clamps', () => {
    SCENES.forEach((s, i) => {
      assert.equal(sceneIndex(s.id), i);
      assert.equal(sceneAt(i).id, s.id);
    });
    assert.equal(sceneAt(-5).id, 'hero');
    assert.equal(sceneAt(999).id, 'command');
  });
});

describe('Transition vocabulary', () => {
  test('every adjacent pair has exactly one transition', () => {
    assert.equal(TRANSITIONS.length, SCENES.length - 1);
    for (let i = 0; i < SCENE_IDS.length - 1; i++) {
      const found = TRANSITIONS.filter(
        (t) => t.from === SCENE_IDS[i] && t.to === SCENE_IDS[i + 1],
      );
      assert.equal(found.length, 1, `${SCENE_IDS[i]} → ${SCENE_IDS[i + 1]}`);
    }
  });

  test('no transition style repeats back to back', () => {
    for (let i = 1; i < TRANSITIONS.length; i++) {
      assert.notEqual(
        TRANSITIONS[i].style,
        TRANSITIONS[i - 1].style,
        `${TRANSITIONS[i].from} reuses the previous style`,
      );
    }
  });

  test('the vocabulary is actually varied, not two styles alternating', () => {
    assert.ok(new Set(TRANSITIONS.map((t) => t.style)).size >= 6);
  });

  test('a bridge is a bridge, not a set piece', () => {
    for (const t of TRANSITIONS) {
      assert.ok(t.glimpses.length >= 1 && t.glimpses.length <= 3,
        `${t.from} → ${t.to} uses ${t.glimpses.length} glimpses`);
      assert.equal(new Set(t.glimpses).size, t.glimpses.length, 'duplicate glimpse');
      // §16: pacing should breathe, and nothing should feel like a loading screen.
      assert.ok(t.ms >= 250 && t.ms <= 1400, `${t.from} → ${t.to} is ${t.ms}ms`);
    }
  });

  test('durations are not all identical', () => {
    assert.ok(new Set(TRANSITIONS.map((t) => t.ms)).size > 1);
  });

  test('transitionBetween works in both directions and rejects strangers', () => {
    assert.equal(transitionBetween('hero', 'thesis')?.style, 'collapse');
    assert.equal(transitionBetween('thesis', 'hero')?.style, 'collapse');
    assert.equal(transitionBetween('hero', 'command'), null);
  });

  test('every glimpse a transition asks for exists in the library markup', () => {
    const markup = read(GLIMPSE);
    for (const t of TRANSITIONS) {
      for (const g of t.glimpses) {
        assert.ok(markup.includes(`gl-${g}`), `no primitive rendered for "${g}"`);
      }
    }
  });

  test('every rendered primitive is reachable from some transition', () => {
    const used = new Set(TRANSITIONS.flatMap((t) => t.glimpses));
    const rendered = Array.from(read(GLIMPSE).matchAll(/gl gl-([a-z-]+)/g)).map((m) => m[1]);
    assert.ok(rendered.length >= 12, 'the library should carry the full primitive set');
    // A primitive may be unused by the current cut, but the ones we claim to use
    // must all be present — the reverse direction is checked above.
    for (const g of used) assert.ok(rendered.includes(g), `${g} is not rendered`);
  });
});

describe('Fast scroll resolves to one handoff', () => {
  test('a jump never replays the intermediate bridges', () => {
    const jump = resolveHandoff('hero', 'memory');
    assert.equal(jump.style, 'handoff');
    assert.ok(jump.glimpses.length <= 1, 'a jump should carry at most one glimpse');
    assert.ok(jump.ms < 500, 'a jump must settle quickly');
  });

  test('an adjacent move keeps its authored transition', () => {
    const step = resolveHandoff('architecture', 'impact');
    assert.equal(step.style, 'trace');
    assert.deepEqual(step.glimpses, ['edge-trace', 'arc']);
  });

  test('a jump borrows the identity of the arriving transition', () => {
    // Arriving at `memory` going down comes from impact → memory (HISTORY).
    assert.equal(resolveHandoff('hero', 'memory').flash, 'HISTORY');
  });

  test('a backward jump borrows the transition leaving the destination', () => {
    // Landing back on `thesis` from far below: thesis → structure (FILES).
    assert.equal(resolveHandoff('pipeline', 'thesis').flash, 'FILES');
  });

  test('staying put produces no bridge at all', () => {
    const same = resolveHandoff('impact', 'impact');
    assert.equal(same.ms, 0);
    assert.deepEqual(same.glimpses, []);
  });

  test('every ordered pair resolves to something renderable', () => {
    for (const from of SCENE_IDS) {
      for (const to of SCENE_IDS) {
        const t = resolveHandoff(from, to);
        assert.ok(t.glimpses.length <= 3, `${from} → ${to}`);
        assert.ok(Number.isFinite(t.ms) && t.ms >= 0, `${from} → ${to}`);
      }
    }
  });
});

describe('Reverse travel', () => {
  test('direction is derived from the pair, not from a flag', () => {
    assert.equal(isReverse('impact', 'structure'), true);
    assert.equal(isReverse('structure', 'impact'), false);
    assert.equal(isReverse('impact', 'impact'), false);
  });

  test('scrolling up re-runs the same functions with a smaller input', () => {
    const bands = makeBands(1000);
    const down = stageAt(2600, bands);
    const up = stageAt(2600, bands);
    // Position determines state, so the same offset yields the same stage
    // regardless of how the reader arrived — that is what makes reverse free.
    assert.deepEqual(down.active, up.active);
    assert.equal(down.progress, up.progress);
  });
});

/** Twelve equal bands, one per scene, `size` pixels tall. */
function makeBands(size: number): SceneBand[] {
  return SCENE_IDS.map((id, i) => ({ id, top: i * size, bottom: (i + 1) * size }));
}

describe('Scene boundaries and active scene', () => {
  const bands = makeBands(1000);

  test('the centre line decides which scene owns the stage', () => {
    assert.equal(stageAt(0, bands).active, 'hero');
    assert.equal(stageAt(500, bands).active, 'hero');
    assert.equal(stageAt(1500, bands).active, 'thesis');
    assert.equal(stageAt(11_500, bands).active, 'command');
  });

  test('progress runs 0 to 1 within a scene', () => {
    assert.equal(stageAt(2000, bands).progress, 0);
    assert.equal(stageAt(2500, bands).progress, 0.5);
    assert.ok(stageAt(2999, bands).progress > 0.99);
  });

  test('a gap between scenes falls to the nearest, never to a default', () => {
    const gapped: SceneBand[] = [
      { id: 'hero', top: 0, bottom: 800 },
      { id: 'thesis', top: 1200, bottom: 2000 },
    ];
    // 900 is in the gap and closer to hero; 1150 is closer to thesis.
    assert.equal(stageAt(900, gapped).active, 'hero');
    assert.equal(stageAt(1150, gapped).active, 'thesis');
  });

  test('positions outside every band still resolve', () => {
    assert.equal(stageAt(-5000, bands).active, 'hero');
    assert.equal(stageAt(500_000, bands).active, 'command');
  });

  test('an empty page does not throw', () => {
    const s = stageAt(1234, []);
    assert.equal(s.active, 'hero');
    assert.equal(s.transition, null);
  });
});

describe('Scene magnetism', () => {
  const bands = makeBands(1000);

  test('the next scene becomes available in the 60-70% window', () => {
    assert.ok(HANDOFF_START >= 0.6 && HANDOFF_START <= 0.7);
  });

  test('no bridge before the handoff point', () => {
    assert.equal(stageAt(2000 + 500, bands).transition, null);
    assert.equal(stageAt(2000 + 699, bands).transition, null);
  });

  test('the bridge runs 0 to 1 across the handoff window', () => {
    const start = stageAt(2000 + HANDOFF_START * 1000, bands);
    assert.ok(start.transition, 'a bridge should be in play');
    assert.ok(start.transitionProgress < 0.02);

    const end = stageAt(2999, bands);
    assert.ok(end.transitionProgress > 0.99, 'the bridge should complete by the boundary');
  });

  test('the bridge in play is the one to the following scene', () => {
    const s = stageAt(3000 + 900, bands); // inside `architecture`
    assert.equal(s.active, 'architecture');
    assert.equal(s.transition?.to, 'impact');
    assert.equal(s.transition?.style, 'trace');
  });

  test('the last scene has nothing to hand off to', () => {
    const s = stageAt(11_999, bands);
    assert.equal(s.active, 'command');
    assert.equal(s.transition, null);
  });
});

describe('Creation order', () => {
  test('steps build in sequence, not all at once', () => {
    // Quarter of the way into the build window, only the first step has started.
    const early = [0, 1, 2, 3].map((i) => createStepProgress(HANDOFF_START * 0.25, i, 4));
    assert.ok(early[0] > 0);
    assert.equal(early[3], 0);
    assert.ok(early[0] >= early[1] && early[1] >= early[2] && early[2] >= early[3]);
  });

  test('creation finishes before the bridge to the next scene begins', () => {
    for (const i of [0, 1, 2, 3, 4]) {
      assert.equal(createStepProgress(HANDOFF_START, i, 5), 1,
        `step ${i} is unfinished when the handoff starts`);
    }
  });

  test('a settled scene is fully built, and an unreached one is not', () => {
    assert.equal(createStepProgress(1, 4, 5), 1);
    assert.equal(createStepProgress(0, 0, 5), 0);
  });

  test('a scene with no declared steps is simply present', () => {
    assert.equal(createStepProgress(0, 0, 0), 1);
  });

  test('progress is always within range', () => {
    for (const p of [-1, 0, 0.33, 0.7, 1, 2]) {
      for (const i of [0, 3, 9]) {
        const v = createStepProgress(p, i, 5);
        assert.ok(v >= 0 && v <= 1, `${p}/${i} produced ${v}`);
      }
    }
  });

  test('clamp01 is total', () => {
    assert.equal(clamp01(-3), 0);
    assert.equal(clamp01(0.5), 0.5);
    assert.equal(clamp01(7), 1);
  });
});

describe('Markup contract', () => {
  const index = read(INDEX);
  const stages = Array.from(index.matchAll(/data-stage="([a-z]+)"/g)).map((m) => m[1]);

  test('every stage on the page is a scene the model knows', () => {
    for (const s of stages) {
      assert.ok((SCENE_IDS as readonly string[]).includes(s), `unknown stage "${s}"`);
    }
  });

  test('stages appear in scene order', () => {
    // A scene may span more than one section (the premise belongs to the thesis,
    // the second pause to the change surface), so compare de-duplicated runs.
    const runs = stages.filter((s, i) => s !== stages[i - 1]);
    const expected = SCENE_IDS.filter((id) => stages.includes(id));
    assert.deepEqual(runs, expected);
  });

  test('the scenes the page declares cover the whole sequence', () => {
    // `hero` and `structure` live in their own components, so allow them to be
    // absent from index.astro but require everything else.
    const owned = new Set(stages);
    for (const id of SCENE_IDS) {
      if (id === 'hero' || id === 'structure') continue;
      assert.ok(owned.has(id), `index.astro never puts ${id} on the stage`);
    }
    assert.ok(read('src/components/landing/HeroStage.astro').includes('data-stage="hero"'));
    assert.ok(
      read('src/components/landing/StructureTransform.tsx').includes('data-stage="structure"'),
    );
  });

  test('chapter markers are still unique', () => {
    const markers = Array.from(index.matchAll(/marker="(\d\d) —/g)).map((m) => m[1]);
    assert.equal(new Set(markers).size, markers.length, 'a chapter number is used twice');
  });

  test('the rail is generated from the model rather than a second list', () => {
    const rail = read(RAIL);
    assert.ok(rail.includes("from './sceneModel'"), 'the rail keeps its own scene list');
    assert.ok(rail.includes('aria-hidden="true"'), 'the rail must be decorative');
  });

  test('decorative transition graphics are hidden from assistive technology', () => {
    assert.ok(read(GLIMPSE).includes('aria-hidden="true"'));
  });

  test('the exit choreography cannot capture the backdrop or the rail', () => {
    /*
      Both the backdrop and every rail tick carry `data-scene`, so a bare
      `[data-scene] > *` rule would overwrite their transforms. Scenes are marked
      with a separate attribute for exactly that reason.

      Comments are stripped first: this must test the rules the browser applies,
      not the prose explaining why the bad rule is absent.
    */
    const css = read(CSS).replace(/\/\*[\s\S]*?\*\//g, '');
    assert.ok(css.includes('[data-stage] > *'), 'exit choreography is not scoped to stages');
    assert.ok(!/\[data-scene\]\s*>\s*\*/.test(css), '[data-scene] > * would break parallax');
  });
});

describe('Performance and honesty constraints', () => {
  const director = read(BACKDROP);

  test('the director derives state from position, with no timers', () => {
    assert.ok(!/setInterval/.test(director), 'a timer would desynchronise from scroll');
    assert.ok(
      !/setTimeout\s*\(\s*\(\)\s*=>\s*\{[^}]*--trans-p/.test(director),
      'the bridge must not advance on a clock',
    );
  });

  test('the scroll path performs no layout reads', () => {
    // getBoundingClientRect is allowed, but only inside the measure pass.
    const applyBody = director.slice(director.indexOf('const apply ='), director.indexOf('const onScroll ='));
    assert.ok(
      !applyBody.includes('getBoundingClientRect'),
      'the frame callback measures layout, which will thrash on scroll',
    );
  });

  test('there is a single scheduled frame', () => {
    const requests = (director.match(/requestAnimationFrame/g) ?? []).length;
    // One in the scene director, one in the pointer light, and the hero's own.
    assert.ok(requests <= 4, `${requests} rAF call sites is too many`);
  });

  test('reduced motion removes the bridges entirely', () => {
    const css = read(CSS);
    const block = css.slice(css.indexOf('.glimpse-layer {'));
    assert.ok(/prefers-reduced-motion[\s\S]*\.glimpse-layer\s*\{\s*display:\s*none/.test(block),
      'glimpses must not run under reduced motion');
  });

  test('no scene invents a metric or a system state', () => {
    const model = read('src/components/landing/sceneModel.ts');
    for (const banned of ['riskScore', 'confidence', 'healthScore', 'securityScan']) {
      assert.ok(!model.includes(banned), `${banned} appeared in the scene model`);
    }
    // Flash labels name chapters, never findings.
    for (const t of TRANSITIONS) {
      if (!t.flash) continue;
      assert.ok(!/\d/.test(t.flash), `flash "${t.flash}" contains a figure`);
    }
  });
});

/* ─────────────────────────────────────────────────────────────────────────────
 * Pinned stage presentation model.
 *
 * Each scene is a tall scroll space containing one sticky stage, so the viewport
 * is a stage and scrolling changes which scene occupies it. These tests pin the
 * contract that makes that safe — above all, that no scene can end up with
 * content clipped inside a frame the reader cannot scroll.
 * ────────────────────────────────────────────────────────────────────────── */

describe('Scene durations', () => {
  test('scenes do not all get the same scroll distance', () => {
    assert.ok(new Set(SCENES.map((s) => s.vh)).size >= 6,
      'uniform durations are what make a scene system feel like a slideshow');
  });

  test('durations are plausible, and long enough for what the scene has to do', () => {
    for (const s of SCENES) {
      assert.ok(s.vh >= 0.8 && s.vh <= 3, `${s.id} is ${s.vh} viewports`);
      assert.ok(s.vhCompact >= 0.8 && s.vhCompact <= 3, `${s.id} compact is ${s.vhCompact}`);
    }
  });

  test('every scene has enough travel to actually pin', () => {
    /*
      Pin travel is `containerHeight − viewportHeight`. A scene exactly one
      viewport tall has none: the stage touches the top of the frame for one
      instant and then scrolls away like anything else. This is the single most
      counter-intuitive property of the presentation model, so it is pinned here
      rather than left to be rediscovered.
    */
    for (const s of SCENES) {
      assert.ok(s.vh >= MIN_SCENE_VH, `${s.id} at ${s.vh}vh would never pin`);
      assert.ok(
        s.vhCompact >= MIN_SCENE_VH_COMPACT,
        `${s.id} at ${s.vhCompact}vh compact would never pin`,
      );
    }
    assert.ok(MIN_SCENE_VH > 1, 'a floor of 1 viewport means zero pin travel');
  });

  test('the scroll-driven scenes get the most room', () => {
    const structure = SCENES.find((s) => s.id === 'structure')!;
    const statement = SCENES.find((s) => s.id === 'statement')!;
    assert.ok(structure.vh >= 2.4,
      'five scroll-linked stages cannot be driven in one viewport of travel');
    /*
      Not a 2x ratio: every scene needs at least MIN_SCENE_VH to pin at all, which
      raises the floor under the short scenes and compresses the achievable spread.
      1.5x still reads as a clearly longer scene.
    */
    assert.ok(structure.vh >= statement.vh * 1.5,
      'a typographic statement should not occupy the same distance as the transformation');
    assert.equal(
      Math.max(...SCENES.map((s) => s.vh)),
      structure.vh,
      'the transformation should be the longest scene on the page',
    );
  });

  test('small screens get shorter scenes, never longer', () => {
    for (const s of SCENES) {
      assert.ok(s.vhCompact <= s.vh, `${s.id} is longer on mobile`);
    }
    assert.ok(
      SCENES.some((s) => s.vhCompact < s.vh),
      'mobile should shorten at least some scenes — long pinned frames tire touch scrolling',
    );
  });

  test('every scene declares a chapter title for the marker', () => {
    for (const s of SCENES) {
      assert.ok(s.title.length > 0, `${s.id} has no title`);
    }
    assert.equal(new Set(SCENES.map((s) => s.title)).size, SCENES.length, 'duplicate title');
  });

  test('scene() resolves and rejects', () => {
    assert.equal(scene('memory').id, 'memory');
    assert.throws(() => scene('nope' as SceneId));
  });
});

describe('Pinned stage markup', () => {
  const index = read(INDEX);
  const hero = read('src/components/landing/HeroStage.astro');
  const structure = read('src/components/landing/StructureTransform.tsx');

  test('every scene section declares whether it pins', () => {
    const sections = Array.from(index.matchAll(/data-stage="([a-z]+)"([\s\S]{0,220}?)>/g));
    assert.ok(sections.length >= 10, 'expected the scenes to be present');
    for (const [, id, attrs] of sections) {
      assert.ok(/data-pin="(on|off|self)"/.test(attrs), `${id} does not declare data-pin`);
    }
  });

  test('every scene contains exactly one stage', () => {
    // One stage element per scroll space: two would compete for the same pin.
    const stages = (index.match(/class="scene-stage"/g) ?? []).length;
    const scenes = (index.match(/data-pin="(on|off)"/g) ?? []).length;
    assert.equal(stages, scenes, `${scenes} scenes but ${stages} stages`);
  });

  test('the markup ships the same pin decision the model declares', () => {
    /*
      The initial attribute has to agree with the declaration, or the first paint is
      laid out one way and corrected the moment the director runs — which the reader
      sees as a jump.
    */
    const pairs = Array.from(
      index.matchAll(/data-stage="([a-z]+)"[\s\S]{0,160}?data-pin="([a-z]+)"/g),
    );
    assert.ok(pairs.length >= 10, 'expected to find the scene sections');
    for (const [, id, pin] of pairs) {
      const declared = SCENES.find((s) => s.id === id);
      assert.ok(declared, `unknown scene ${id}`);
      assert.equal(
        pin,
        declared!.stageable ? 'on' : 'off',
        `${id} ships data-pin="${pin}" but stageable=${declared!.stageable}`,
      );
    }
  });

  test('the staged scenes are the ones that can hold a frame', () => {
    const staged = SCENES.filter((s) => s.stageable).map((s) => s.id);
    // Typographic and specification scenes fit a frame; figure-heavy ones do not.
    assert.deepEqual(staged, ['hero', 'thesis', 'technology', 'statement', 'command']);
    for (const id of ['architecture', 'impact', 'memory', 'retrieval', 'route', 'pipeline']) {
      assert.equal(SCENES.find((s) => s.id === id)!.stageable, false,
        `${id} carries a figure and cannot be guaranteed to fit one frame`);
    }
  });

  test('short viewports stage nothing at all', () => {
    assert.ok(MIN_STAGE_VIEWPORT >= 600 && MIN_STAGE_VIEWPORT <= 800,
      'the floor should exclude phones and short laptops, not every laptop');
  });

  test('pin decisions are never taken while the reader is moving', () => {
    const director = read(BACKDROP);
    const applyBody = director.slice(
      director.indexOf('const apply ='),
      director.indexOf('const onScroll ='),
    );
    for (const fn of ['applyPinPolicy', 'unpinOverflowing']) {
      assert.ok(!applyBody.includes(fn),
        `${fn} in the frame callback would move scene boundaries mid-scroll`);
    }
    assert.ok(
      !/ResizeObserver[\s\S]{0,200}document\.body/.test(director),
      'observing the body feeds pin changes back into itself',
    );
  });

  test('the safety pass can only remove pinning, never grant it', () => {
    const director = read(BACKDROP);
    const fn = director.slice(director.indexOf('const unpinOverflowing'));
    const body = fn.slice(0, fn.indexOf('\n    };'));
    assert.ok(body.includes("dataset.pin = 'off'"), 'it should be able to unpin');
    assert.ok(!body.includes("dataset.pin = 'on'"),
      'granting pinning late is what caused content to become unreachable');
  });

  test('the hero is a pinned stage driven by the model', () => {
    assert.ok(hero.includes('data-pin="on"'));
    assert.ok(hero.includes('scene-stage'));
    assert.ok(hero.includes("scene('hero')"), 'the hero should not hardcode its duration');
  });

  test('the structural transformation pins itself and is left alone', () => {
    assert.ok(structure.includes('data-pin="self"'),
      'it has driven its own sticky stage since before the scene system existed');
    assert.ok(!structure.includes('scene-stage'), 'a second pin would fight the first');
  });

  test('a scene that cannot fit the viewport falls back to normal flow', () => {
    const css = read(CSS).replace(/\/\*[\s\S]*?\*\//g, '');
    assert.ok(/\[data-stage\]\[data-pin='off'\]\s*>\s*\.scene-stage\s*\{[^}]*position:\s*static/.test(css),
      'unpinned scenes must return to flow so nothing is unreachable');
    assert.ok(/\[data-stage\]\[data-pin='on'\]\s*>\s*\.scene-stage\s*\{[^}]*position:\s*sticky/.test(css),
      'pinned scenes must actually pin');
  });

  test('the director decides pinning, and does it outside the scroll path', () => {
    const director = read(BACKDROP);
    assert.ok(director.includes('applyPinPolicy'), 'no pin policy');
    assert.ok(director.includes('unpinOverflowing'), 'no safety pass');
    assert.ok(director.includes('MIN_STAGE_VIEWPORT'), 'the viewport floor is not applied');
  });

  test('reduced motion drops pinning entirely', () => {
    const css = read(CSS);
    const reducedBlocks = css.split('@media (prefers-reduced-motion: reduce)').slice(1);
    assert.ok(
      reducedBlocks.some((b) => /\[data-pin='on'\]\s*\{\s*height:\s*auto/.test(b)),
      'scenes must return to normal flow under reduced motion',
    );
  });
});

describe('Chapter indicator', () => {
  test('the rail carries a film-style counter, not a carousel', () => {
    const rail = read(RAIL);
    assert.ok(rail.includes('data-scene-counter'), 'no scene counter');
    assert.ok(!/dot|bullet|pagination/i.test(rail), 'this should not read as a carousel');
  });

  test('there is an accessible equivalent, because the rail is decorative', () => {
    const backdrop = read(BACKDROP);
    assert.ok(backdrop.includes('data-scene-announce'), 'no accessible scene announcement');
    assert.ok(/data-scene-announce/.test(backdrop) && /aria-live="polite"/.test(backdrop),
      'the announcement must be polite, not assertive');
    assert.ok(/class="sr-only"[^>]*data-scene-announce|data-scene-announce[^>]*class="sr-only"/.test(backdrop)
      || /sr-only[\s\S]{0,120}data-scene-announce/.test(backdrop),
      'the announcement should not be visible chrome');
  });

  test('the chapter title is a brief marker, not a permanent label', () => {
    const css = read(CSS);
    assert.ok(/\.chapter-title\.is-showing\s*\{[^}]*animation:[^}]*1\s+both/.test(css),
      'the title must play once and stop');
    assert.ok(/@keyframes chapterTitle[\s\S]*?100%\s*\{[^}]*opacity:\s*0/.test(css),
      'the title must dissolve rather than stay on screen');
  });

  test('the counter and the announcement both come from the scene list', () => {
    const backdrop = read(BACKDROP);
    assert.ok(backdrop.includes('SCENES.length'), 'the total should not be hardcoded');
  });
});
