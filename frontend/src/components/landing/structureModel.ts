/**
 * Geometry for the structural transformation stage (landing chapter 02).
 *
 * Kept out of the component so the five-stage choreography can be reasoned about
 * — and unit tested — separately from the DOM writes that apply it.
 *
 * Everything here is illustrative composition, not measured data. The module
 * names are real ARIA directories so the example is recognisable, but no count,
 * edge or position is derived from an actual analysis.
 */

export interface Pt {
  x: number;
  y: number;
}

export interface FileNode {
  /** Stage 01: where the file sits when the repository is just a list. */
  scatter: Pt;
  /** Stage 02+: where it sits once it has been grouped into a module. */
  clustered: Pt;
  /** Index into `modules`. */
  module: number;
}

export interface SymbolNode {
  at: Pt;
  module: number;
}

export interface StructureModel {
  modules: { label: string; at: Pt }[];
  files: FileNode[];
  symbols: SymbolNode[];
  /** Index into `symbols` — the symbol the caller/dependency story centres on. */
  focus: number;
  /** Module anchor → each of its files. Drawn from stage 02. */
  moduleEdges: [number, number][];
  /** Symbol → focus. Inbound. Drawn from stage 04. */
  callerEdges: number[];
  /** Focus → symbol. Outbound. Drawn from stage 05. */
  dependencyEdges: number[];
}

/** Desktop composition: three modules spread across the stage. */
export const MODEL_WIDE: StructureModel = {
  modules: [
    { label: 'services/', at: { x: 24, y: 30 } },
    { label: 'core/', at: { x: 70, y: 24 } },
    { label: 'mcp/tools/', at: { x: 50, y: 74 } },
  ],
  files: [
    // Scattered positions are deliberately even and alphabetical-feeling: a list.
    { scatter: { x: 12, y: 12 }, clustered: { x: 14, y: 22 }, module: 0 },
    { scatter: { x: 12, y: 30 }, clustered: { x: 15, y: 40 }, module: 0 },
    { scatter: { x: 12, y: 48 }, clustered: { x: 32, y: 16 }, module: 0 },
    { scatter: { x: 12, y: 66 }, clustered: { x: 62, y: 12 }, module: 1 },
    { scatter: { x: 12, y: 84 }, clustered: { x: 82, y: 18 }, module: 1 },
    { scatter: { x: 40, y: 12 }, clustered: { x: 80, y: 34 }, module: 1 },
    { scatter: { x: 40, y: 30 }, clustered: { x: 38, y: 82 }, module: 2 },
    { scatter: { x: 40, y: 48 }, clustered: { x: 58, y: 86 }, module: 2 },
    { scatter: { x: 40, y: 66 }, clustered: { x: 64, y: 64 }, module: 2 },
  ],
  symbols: [
    { at: { x: 30, y: 38 }, module: 0 }, // focus
    { at: { x: 18, y: 32 }, module: 0 },
    { at: { x: 26, y: 20 }, module: 0 },
    { at: { x: 64, y: 30 }, module: 1 },
    { at: { x: 74, y: 16 }, module: 1 },
    { at: { x: 78, y: 28 }, module: 1 },
    { at: { x: 44, y: 70 }, module: 2 },
    { at: { x: 56, y: 78 }, module: 2 },
    { at: { x: 46, y: 86 }, module: 2 },
  ],
  focus: 0,
  moduleEdges: [
    [0, 0], [0, 1], [0, 2],
    [1, 3], [1, 4], [1, 5],
    [2, 6], [2, 7], [2, 8],
  ],
  callerEdges: [3, 6, 4],
  dependencyEdges: [5, 7, 8, 1],
};

/**
 * Mobile composition. Fewer nodes on purpose: the point is to communicate the
 * transformation, not to reproduce desktop density on a 375px screen.
 */
export const MODEL_COMPACT: StructureModel = {
  modules: [
    { label: 'services/', at: { x: 26, y: 24 } },
    { label: 'core/', at: { x: 72, y: 40 } },
    { label: 'mcp/tools/', at: { x: 40, y: 76 } },
  ],
  files: [
    { scatter: { x: 18, y: 14 }, clustered: { x: 14, y: 16 }, module: 0 },
    { scatter: { x: 18, y: 34 }, clustered: { x: 34, y: 12 }, module: 0 },
    { scatter: { x: 18, y: 54 }, clustered: { x: 84, y: 30 }, module: 1 },
    { scatter: { x: 18, y: 74 }, clustered: { x: 82, y: 52 }, module: 1 },
    { scatter: { x: 18, y: 92 }, clustered: { x: 26, y: 88 }, module: 2 },
    { scatter: { x: 48, y: 14 }, clustered: { x: 54, y: 84 }, module: 2 },
  ],
  symbols: [
    { at: { x: 34, y: 32 }, module: 0 }, // focus
    { at: { x: 18, y: 28 }, module: 0 },
    { at: { x: 66, y: 32 }, module: 1 },
    { at: { x: 78, y: 44 }, module: 1 },
    { at: { x: 36, y: 68 }, module: 2 },
    { at: { x: 50, y: 74 }, module: 2 },
  ],
  focus: 0,
  moduleEdges: [
    [0, 0], [0, 1],
    [1, 2], [1, 3],
    [2, 4], [2, 5],
  ],
  callerEdges: [2, 4],
  dependencyEdges: [3, 5, 1],
};

/**
 * The five stages, as fractions of the section's scroll progress.
 *
 * Ranges are contiguous and each stage's visuals persist once reached, so the
 * reader accumulates structure rather than watching it get replaced. The
 * SYMBOLS → CALLERS boundary is where direction first appears, which is the
 * conceptual turn the section exists to deliver.
 */
export const STAGE_RANGES: [number, number][] = [
  [0.0, 0.18], // 01 FILES
  [0.18, 0.38], // 02 MODULES
  [0.38, 0.58], // 03 SYMBOLS
  [0.58, 0.78], // 04 CALLERS
  [0.78, 1.0], // 05 DEPENDENCIES
];

/** Which stage index a progress value falls in. */
export function stageAt(p: number): number {
  for (let i = STAGE_RANGES.length - 1; i >= 0; i--) {
    if (p >= STAGE_RANGES[i][0]) return i;
  }
  return 0;
}

export const STRUCTURE_STAGES = [
  { label: 'FILES', detail: 'what you can list' },
  { label: 'MODULES', detail: 'what groups together' },
  { label: 'SYMBOLS', detail: 'what is declared' },
  { label: 'CALLERS', detail: 'what depends on it' },
  { label: 'DEPENDENCIES', detail: 'what it reaches' },
] as const;
