import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import {
  MODEL_WIDE,
  MODEL_COMPACT,
  STAGE_RANGES,
  STRUCTURE_STAGES,
  stageAt,
  type StructureModel,
} from '../src/components/landing/structureModel.ts';

/**
 * The five-stage structural transformation on the landing page.
 *
 * The section previously ran three coarse steps with a single list→graph morph,
 * so the graph did not visibly change when the label did. These tests pin the
 * properties that make the five stages distinct and cumulative.
 */

const MODELS: [string, StructureModel][] = [
  ['wide', MODEL_WIDE],
  ['compact', MODEL_COMPACT],
];

describe('stage ranges', () => {
  test('there are exactly five stages, matching the copy', () => {
    assert.equal(STAGE_RANGES.length, 5);
    assert.equal(STRUCTURE_STAGES.length, 5);
    assert.deepEqual(
      STRUCTURE_STAGES.map((s) => s.label),
      ['FILES', 'MODULES', 'SYMBOLS', 'CALLERS', 'DEPENDENCIES'],
    );
  });

  test('ranges are contiguous and cover the whole scroll', () => {
    assert.equal(STAGE_RANGES[0][0], 0);
    assert.equal(STAGE_RANGES[STAGE_RANGES.length - 1][1], 1);
    for (let i = 1; i < STAGE_RANGES.length; i++) {
      assert.equal(
        STAGE_RANGES[i][0],
        STAGE_RANGES[i - 1][1],
        `gap or overlap between stage ${i} and ${i + 1}`,
      );
    }
  });

  test('every range advances', () => {
    for (const [from, to] of STAGE_RANGES) {
      assert.ok(to > from, `range ${from}-${to} does not advance`);
    }
  });

  test('stageAt maps progress onto the right stage', () => {
    assert.equal(stageAt(0), 0);
    assert.equal(stageAt(0.1), 0);
    assert.equal(stageAt(0.25), 1);
    assert.equal(stageAt(0.45), 2);
    assert.equal(stageAt(0.65), 3);
    assert.equal(stageAt(0.85), 4);
    assert.equal(stageAt(1), 4);
  });

  test('the SYMBOLS to CALLERS boundary is where direction appears', () => {
    // Stage 3 (index 3) is CALLERS — the conceptual turn of the section.
    assert.equal(STRUCTURE_STAGES[2].label, 'SYMBOLS');
    assert.equal(STRUCTURE_STAGES[3].label, 'CALLERS');
    const boundary = STAGE_RANGES[3][0];
    assert.ok(boundary > 0.4 && boundary < 0.75, 'the turn should land mid-section');
  });
});

for (const [name, model] of MODELS) {
  describe(`structure model — ${name}`, () => {
    test('has three modules and every file belongs to one', () => {
      assert.equal(model.modules.length, 3);
      assert.ok(model.files.length > 0);
      for (const f of model.files) {
        assert.ok(
          f.module >= 0 && f.module < model.modules.length,
          `file references module ${f.module}, which does not exist`,
        );
      }
    });

    test('every symbol belongs to a real module', () => {
      assert.ok(model.symbols.length > 0);
      for (const s of model.symbols) {
        assert.ok(s.module >= 0 && s.module < model.modules.length);
      }
    });

    test('files actually move between stage 01 and stage 02', () => {
      // If scatter equalled clustered, MODULES would look identical to FILES.
      let moved = 0;
      for (const f of model.files) {
        if (f.scatter.x !== f.clustered.x || f.scatter.y !== f.clustered.y) moved++;
      }
      assert.equal(moved, model.files.length, 'every file must migrate into its cluster');
    });

    test('all coordinates stay inside the stage box', () => {
      const pts = [
        ...model.modules.map((m) => m.at),
        ...model.symbols.map((s) => s.at),
        ...model.files.flatMap((f) => [f.scatter, f.clustered]),
      ];
      for (const p of pts) {
        assert.ok(p.x >= 0 && p.x <= 100, `x=${p.x} outside 0-100`);
        assert.ok(p.y >= 0 && p.y <= 100, `y=${p.y} outside 0-100`);
      }
    });

    test('the focus symbol exists', () => {
      assert.ok(model.focus >= 0 && model.focus < model.symbols.length);
    });

    test('grouping edges connect a real module to a real file', () => {
      assert.ok(model.moduleEdges.length > 0);
      for (const [m, f] of model.moduleEdges) {
        assert.ok(m >= 0 && m < model.modules.length, `bad module index ${m}`);
        assert.ok(f >= 0 && f < model.files.length, `bad file index ${f}`);
      }
    });

    test('caller and dependency edges reference real symbols', () => {
      assert.ok(model.callerEdges.length > 0, 'CALLERS needs inbound edges to show');
      assert.ok(model.dependencyEdges.length > 0, 'DEPENDENCIES needs outbound edges');
      for (const i of [...model.callerEdges, ...model.dependencyEdges]) {
        assert.ok(i >= 0 && i < model.symbols.length, `bad symbol index ${i}`);
      }
    });

    test('the focus symbol is never its own caller or dependency', () => {
      assert.ok(!model.callerEdges.includes(model.focus), 'focus cannot call itself here');
      assert.ok(!model.dependencyEdges.includes(model.focus));
    });

    test('inbound and outbound sets are disjoint, so direction reads cleanly', () => {
      for (const i of model.callerEdges) {
        assert.ok(
          !model.dependencyEdges.includes(i),
          `symbol ${i} is drawn as both a caller and a dependency`,
        );
      }
    });

    test('the graph stays legible rather than becoming a mesh', () => {
      // §9: more edges must still read as more understandable.
      const totalEdges =
        model.moduleEdges.length + model.callerEdges.length + model.dependencyEdges.length;
      assert.ok(totalEdges <= 24, `${totalEdges} edges is too dense for an illustration`);
    });
  });
}

describe('mobile simplification', () => {
  test('the compact model carries fewer nodes than the wide one', () => {
    assert.ok(
      MODEL_COMPACT.files.length < MODEL_WIDE.files.length,
      'mobile should reduce node count, not shrink the desktop graph',
    );
    assert.ok(MODEL_COMPACT.symbols.length < MODEL_WIDE.symbols.length);
  });

  test('the compact model still tells the whole story', () => {
    assert.equal(MODEL_COMPACT.modules.length, 3, 'grouping must survive on mobile');
    assert.ok(MODEL_COMPACT.callerEdges.length > 0, 'direction must survive on mobile');
    assert.ok(MODEL_COMPACT.dependencyEdges.length > 0, 'reach must survive on mobile');
  });
});
