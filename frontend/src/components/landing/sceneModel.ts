/**
 * The ARIA scene model — the landing page as a sequence of cinematic scenes.
 *
 * This module is the single source of truth for what the scenes are, how they
 * hand off to each other, and what the viewport should be showing at any scroll
 * position. It is deliberately pure: no DOM, no React, no timers. The DOM
 * controller in StoryBackdrop reads from here and writes custom properties.
 *
 * ── Why position-derived rather than timeline-driven ────────────────────────
 *
 * Every value below is computed *from the scroll offset*, never from a clock.
 * That single decision satisfies most of the hard requirements for free:
 *
 *   fast scroll   there is no animation queue to drain, so jumping from scene 01
 *                 to scene 06 cannot play six transitions — the state is simply
 *                 evaluated at the new position.
 *   paused scroll the scroll *is* the narrative clock. Stop moving and creation
 *                 stops with you, because progress is a function of position.
 *   reverse       scrolling up runs the same functions with a decreasing input,
 *                 so the visual logic reverses naturally instead of needing a
 *                 second, mirrored set of animations.
 *   cancellation  nothing to cancel. There are no stale timers by construction.
 *
 * The only animations allowed to run on their own clock are short one-shot
 * entrances (under ~600ms), which are cheap to finish and never leave the page
 * in a stale state.
 */

/* ── Scenes ────────────────────────────────────────────────────────────────── */

export type SceneId =
  | 'hero'
  | 'thesis'
  | 'structure'
  | 'architecture'
  | 'impact'
  | 'memory'
  | 'retrieval'
  | 'route'
  | 'pipeline'
  | 'technology'
  | 'statement'
  | 'command';

export interface Scene {
  id: SceneId;
  /** Shown in the edge rail. */
  label: string;
  /** Chapter title, briefly shown as the scene takes the stage. */
  title: string;
  /**
   * How many creation steps this scene is built from. Elements carrying
   * `data-create` reveal in order as the scene's progress advances, so the reader
   * watches the scene come into existence rather than meeting it finished.
   */
  createSteps: number;
  /**
   * Scroll distance the scene occupies, in viewport heights.
   *
   * Deliberately uneven. A typographic statement needs only enough travel to be
   * read; the five-stage structural transformation needs room for all five stages
   * to be driven by scroll. Giving every scene the same distance is what makes a
   * scene system feel like a slideshow.
   */
  vh: number;
  /** Shorter on small screens, where long pinned scenes make touch scrolling tiring. */
  vhCompact: number;
  /**
   * Whether this scene's content fits a single frame and can therefore be pinned.
   *
   * Declared rather than measured, and that is a deliberate correction. Measuring
   * content height at runtime and flipping pinning on the result changes the
   * document height, which moves every scene boundary below it — while the reader
   * is scrolling through them. The active scene then oscillates (…memory → impact →
   * retrieval → memory…) because the offsets shift underneath the walk.
   *
   * So: the typographic and specification scenes are staged, the figure-heavy
   * chapters scroll. A one-off safety pass may still *remove* pinning from a scene
   * that turns out not to fit, but nothing ever adds it back, and no decision is
   * taken once the reader is moving.
   */
  stageable: boolean;
}

/**
 * The sequence. Order here is the order on the page, and the DOM controller
 * asserts that the sections it finds match it — so a section reordered in the
 * markup without updating this list is caught rather than silently mis-lit.
 */
/**
 * Shortest scene, in viewport heights.
 *
 * A sticky stage's pin travel is `containerHeight − viewportHeight`. A scene
 * exactly one viewport tall therefore has *zero* travel: the stage touches the top
 * of the frame for a single instant and then scrolls away like any other element.
 * Every scene needs meaningful headroom above one viewport or it does not stage at
 * all — which is a genuinely counter-intuitive property of `position: sticky`, and
 * the reason this floor exists.
 */
export const MIN_SCENE_VH = 1.4;

/** The same floor for small screens, where scenes are shortened. */
export const MIN_SCENE_VH_COMPACT = 1.25;

export const SCENES: readonly Scene[] = [
  { id: 'hero', label: 'Hero', title: 'Understand any codebase', createSteps: 4, vh: 1.6, vhCompact: 1.3, stageable: true },
  { id: 'thesis', label: '01 Premise', title: '01 — The premise', createSteps: 3, vh: 1.5, vhCompact: 1.3, stageable: true },
  { id: 'structure', label: '02 Structure', title: '02 — Structural transformation', createSteps: 5, vh: 2.8, vhCompact: 2.3, stageable: false },
  { id: 'architecture', label: '03 Architecture', title: '03 — Structural intelligence', createSteps: 6, vh: 2.3, vhCompact: 1.7, stageable: false },
  { id: 'impact', label: '04 Change', title: '04 — Change surface', createSteps: 5, vh: 2.1, vhCompact: 1.6, stageable: false },
  { id: 'memory', label: '05 Memory', title: '05 — Repository memory', createSteps: 5, vh: 1.9, vhCompact: 1.5, stageable: false },
  { id: 'retrieval', label: '06 Retrieval', title: '06 — Grounded retrieval', createSteps: 5, vh: 1.9, vhCompact: 1.5, stageable: false },
  { id: 'route', label: '07 Reading path', title: '07 — Onboarding', createSteps: 4, vh: 1.7, vhCompact: 1.4, stageable: false },
  { id: 'pipeline', label: '08 Pipeline', title: '08 — Pipeline architecture', createSteps: 5, vh: 1.7, vhCompact: 1.4, stageable: false },
  { id: 'technology', label: '09 Technology', title: '09 — Technology', createSteps: 4, vh: 1.6, vhCompact: 1.3, stageable: true },
  { id: 'statement', label: '10 Statement', title: 'Stop reading the codebase blind', createSteps: 3, vh: 1.6, vhCompact: 1.3, stageable: true },
  { id: 'command', label: '11 Enter', title: '10 — Enter the system', createSteps: 6, vh: 1.7, vhCompact: 1.3, stageable: true },
] as const;

/**
 * Viewport height below which nothing is staged.
 *
 * A pinned frame on a short viewport leaves almost no room for the content it is
 * supposed to hold, and long pinned scenes make touch scrolling tiring (§26). Below
 * this the experience keeps its scenes, bridges and creation order but scrolls
 * normally.
 */
export const MIN_STAGE_VIEWPORT = 680;

/** Scene lookup by id, for the markup and the director. */
export function scene(id: SceneId): Scene {
  const found = SCENES.find((s) => s.id === id);
  if (!found) throw new Error(`unknown scene: ${id}`);
  return found;
}

export const SCENE_IDS: readonly SceneId[] = SCENES.map((s) => s.id);

export function sceneIndex(id: SceneId): number {
  return SCENE_IDS.indexOf(id);
}

export function sceneAt(index: number): Scene {
  const clamped = Math.min(SCENES.length - 1, Math.max(0, index));
  return SCENES[clamped];
}

/* ── Transition vocabulary ─────────────────────────────────────────────────── */

/**
 * Eight styles, chosen to express the *relationship* between two chapters rather
 * than for variety's sake. A morph says "the same thing, re-read"; a trace says
 * "this caused that"; a collapse says "all of that reduces to this".
 */
export type TransitionStyle =
  | 'dissolve'
  | 'morph'
  | 'trace'
  | 'collapse'
  | 'expand'
  | 'wipe'
  | 'luminance'
  | 'handoff';

/** The glimpse primitives. Small, composable, CSS/SVG only. */
export type Glimpse =
  | 'node-field'
  | 'edge-trace'
  | 'collapse'
  | 'expand'
  | 'scan'
  | 'grid'
  | 'blueprint'
  | 'bracket'
  | 'arc'
  | 'horizon'
  | 'trace-memory'
  | 'lumen';

export interface Transition {
  from: SceneId;
  to: SceneId;
  style: TransitionStyle;
  /** At most three: a glimpse is a bridge, not a set piece. */
  glimpses: Glimpse[];
  /** Nominal duration, used only to size the scroll window the bridge occupies. */
  ms: number;
  /** A brief system label, shown at the luminance peak of the bridge. */
  flash?: string;
}

/**
 * One entry per adjacent pair. The reasoning behind each choice:
 *
 *   hero → thesis          the field collapses to nothing, so the claim lands in
 *                          an empty frame.
 *   thesis → structure     from nothing, files appear: an expansion.
 *   structure → architecture the resolved topology is re-read as a graph — same
 *                          material, new meaning, so: morph.
 *   architecture → impact  one relationship detaches and travels: a trace.
 *   impact → memory        propagation endpoints stretch into time: morph.
 *   memory → retrieval     all that history reduces to a few cited symbols.
 *   retrieval → route      evidence aligns into an ordered path: a handoff.
 *   route → pipeline       the route straightens into a rail: morph.
 *   pipeline → technology  the rail subdivides into specification columns: wipe.
 *   technology → statement everything leaves except one block of type.
 *   statement → command    the prompt emerges from darkness: luminance.
 */
export const TRANSITIONS: readonly Transition[] = [
  { from: 'hero', to: 'thesis', style: 'collapse', glimpses: ['collapse', 'lumen'], ms: 900, flash: 'STRUCTURE' },
  { from: 'thesis', to: 'structure', style: 'expand', glimpses: ['node-field', 'grid'], ms: 800, flash: 'FILES' },
  { from: 'structure', to: 'architecture', style: 'morph', glimpses: ['trace-memory', 'edge-trace'], ms: 900, flash: 'TOPOLOGY' },
  { from: 'architecture', to: 'impact', style: 'trace', glimpses: ['edge-trace', 'arc'], ms: 800, flash: 'IMPACT' },
  { from: 'impact', to: 'memory', style: 'morph', glimpses: ['horizon', 'scan'], ms: 900, flash: 'HISTORY' },
  { from: 'memory', to: 'retrieval', style: 'collapse', glimpses: ['collapse', 'lumen'], ms: 800, flash: 'EVIDENCE' },
  { from: 'retrieval', to: 'route', style: 'handoff', glimpses: ['bracket', 'horizon'], ms: 700, flash: 'READING PATH' },
  { from: 'route', to: 'pipeline', style: 'morph', glimpses: ['horizon', 'scan'], ms: 700, flash: 'PIPELINE' },
  { from: 'pipeline', to: 'technology', style: 'wipe', glimpses: ['grid', 'blueprint'], ms: 800, flash: 'SPECIFICATION' },
  { from: 'technology', to: 'statement', style: 'dissolve', glimpses: ['trace-memory'], ms: 1000 },
  { from: 'statement', to: 'command', style: 'luminance', glimpses: ['lumen', 'horizon'], ms: 1000, flash: 'ENTER' },
] as const;

/** The adjacent transition between two scenes, in either direction. */
export function transitionBetween(from: SceneId, to: SceneId): Transition | null {
  return (
    TRANSITIONS.find((t) => t.from === from && t.to === to) ??
    TRANSITIONS.find((t) => t.from === to && t.to === from) ??
    null
  );
}

/**
 * The bridge to play for *any* pair of scenes, including a jump.
 *
 * A fast scroll from scene 01 to scene 06 must not replay five bridges. It gets a
 * single, shorter handoff instead: the current world leaves, one glimpse marks
 * the crossing, and the target world is created. The glimpse borrows from the
 * transition that *arrives* at the destination, so the bridge still says
 * something true about where the reader has landed.
 */
export function resolveHandoff(from: SceneId, to: SceneId): Transition {
  const a = sceneIndex(from);
  const b = sceneIndex(to);

  if (a === b) {
    return { from, to, style: 'dissolve', glimpses: [], ms: 0 };
  }

  const adjacent = transitionBetween(from, to);
  if (adjacent && Math.abs(a - b) === 1) return adjacent;

  // A jump. Borrow the arriving transition's identity, keep only its first
  // glimpse, and shorten it so the target settles quickly.
  const arriving =
    b > a
      ? TRANSITIONS.find((t) => t.to === to)
      : TRANSITIONS.find((t) => t.from === to);

  return {
    from,
    to,
    style: 'handoff',
    glimpses: arriving?.glimpses.slice(0, 1) ?? ['scan'],
    ms: 420,
    flash: arriving?.flash,
  };
}

/** True when the reader is moving back up through the system. */
export function isReverse(from: SceneId, to: SceneId): boolean {
  return sceneIndex(to) < sceneIndex(from);
}

/* ── Position → state ──────────────────────────────────────────────────────── */

export interface SceneBand {
  id: SceneId;
  /** Document offset of the scene's top edge, in pixels. */
  top: number;
  /** Document offset of the scene's bottom edge, in pixels. */
  bottom: number;
}

export interface StageState {
  active: SceneId;
  /** 0→1 through the active scene. */
  progress: number;
  /** The bridge currently in play, if the reader is inside a transition window. */
  transition: Transition | null;
  /** 0→1 through that bridge. */
  transitionProgress: number;
  /** Direction of travel. */
  reverse: boolean;
}

/**
 * Fraction of a scene's travel given over to handing off to the next one.
 *
 * §13: the next scene should start becoming available around 60–70% and settle by
 * 85–95%. So the bridge occupies the last 30% of a scene's band, and the incoming
 * scene's creation is already underway before the outgoing one has fully left.
 */
export const HANDOFF_START = 0.7;

/** Clamp helper, kept here so the DOM controller needs no maths of its own. */
export function clamp01(value: number): number {
  return value < 0 ? 0 : value > 1 ? 1 : value;
}

/**
 * Everything the stage needs, derived from one scroll offset.
 *
 * `mid` is the document offset of the viewport's centre line. A scene owns the
 * stage while the centre line is inside its band; between bands the nearest one
 * wins, so a seam never drops the stage back to a default scene.
 */
export function stageAt(
  mid: number,
  bands: readonly SceneBand[],
  previousActive?: SceneId,
): StageState {
  if (bands.length === 0) {
    return {
      active: 'hero',
      progress: 0,
      transition: null,
      transitionProgress: 0,
      reverse: false,
    };
  }

  let best = Infinity;
  let chosen = bands[0];
  for (const band of bands) {
    const distance = mid < band.top ? band.top - mid : mid >= band.bottom ? mid - band.bottom : 0;
    if (distance <= best) {
      best = distance;
      chosen = band;
    }
  }

  const span = chosen.bottom - chosen.top;
  const progress = span > 0 ? clamp01((mid - chosen.top) / span) : 1;

  const index = sceneIndex(chosen.id);
  const next = index + 1 < SCENES.length ? SCENES[index + 1].id : null;

  let transition: Transition | null = null;
  let transitionProgress = 0;
  if (next && progress >= HANDOFF_START) {
    transition = transitionBetween(chosen.id, next);
    transitionProgress = clamp01((progress - HANDOFF_START) / (1 - HANDOFF_START));
  }

  const reverse = previousActive ? isReverse(previousActive, chosen.id) : false;

  return { active: chosen.id, progress, transition, transitionProgress, reverse };
}

/* ── Creation order ────────────────────────────────────────────────────────── */

/**
 * Whether a creation step of `index` (0-based) has been built yet, given the
 * scene's progress. Creation is front-loaded into the first 70% of the scene so
 * it has finished assembling before the bridge to the next scene begins.
 */
export function createStepProgress(
  sceneProgress: number,
  index: number,
  total: number,
): number {
  if (total <= 0) return 1;
  const build = clamp01(sceneProgress / HANDOFF_START);
  return clamp01(build * total - index);
}
