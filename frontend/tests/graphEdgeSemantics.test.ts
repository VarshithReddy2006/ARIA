import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  buildMutualPairSet,
  isMutual,
  resolveDependencyEdgeStyle,
  resolveCallEdgeStyle,
  resolveFocusChoreography,
  edgeFocusRole,
  edgeTransition,
  EDGE_TONE,
  EDGE_DASH,
  type DependencyEdgeFlags,
  type CallEdgeFlags,
} from '../src/components/interactive/graph/edgeSemantics.ts';

/**
 * Edge semantics for the two graph surfaces.
 *
 * The rule these tests exist to protect: no relationship may be distinguished by
 * colour alone. Both graphs previously separated incoming from outgoing purely by
 * emerald vs indigo, and neither had any treatment for a dependency cycle or for
 * mutual recursion.
 */

const depBase: DependencyEdgeFlags = {
  isPath: false,
  isOutgoing: false,
  isIncoming: false,
  isCyclic: false,
  hasActive: false,
};

const callBase: CallEdgeFlags = {
  isSelfCall: false,
  isMutualRecursion: false,
  isOutgoing: false,
  isIncoming: false,
  isAmbiguous: false,
  hasActive: false,
};

/** A visual "channel" fingerprint, ignoring colour. */
function nonColourSignature(v: { strokeWidth: number; dash?: string; bothEnds: boolean }) {
  return `${v.strokeWidth}|${v.dash ?? 'solid'}|${v.bothEnds}`;
}

describe('buildMutualPairSet', () => {
  test('detects a two-node cycle in both directions', () => {
    const pairs = buildMutualPairSet([
      { source: 'a.ts', target: 'b.ts' },
      { source: 'b.ts', target: 'a.ts' },
    ]);
    assert.ok(isMutual(pairs, 'a.ts', 'b.ts'));
    assert.ok(isMutual(pairs, 'b.ts', 'a.ts'));
  });

  test('does not flag a one-way dependency', () => {
    const pairs = buildMutualPairSet([
      { source: 'a.ts', target: 'b.ts' },
      { source: 'b.ts', target: 'c.ts' },
    ]);
    assert.equal(isMutual(pairs, 'a.ts', 'b.ts'), false);
    assert.equal(isMutual(pairs, 'b.ts', 'c.ts'), false);
  });

  test('a self-loop is not a mutual pair', () => {
    const pairs = buildMutualPairSet([{ source: 'a.ts', target: 'a.ts' }]);
    assert.equal(isMutual(pairs, 'a.ts', 'a.ts'), false);
  });

  test('handles an empty edge list', () => {
    assert.equal(buildMutualPairSet([]).size, 0);
  });

  test('does not mutate or require sorted input', () => {
    const edges = [
      { source: 'z.ts', target: 'a.ts' },
      { source: 'm.ts', target: 'n.ts' },
      { source: 'a.ts', target: 'z.ts' },
    ];
    const snapshot = JSON.stringify(edges);
    const pairs = buildMutualPairSet(edges);
    assert.equal(JSON.stringify(edges), snapshot);
    assert.ok(isMutual(pairs, 'z.ts', 'a.ts'));
    assert.equal(isMutual(pairs, 'm.ts', 'n.ts'), false);
  });
});

describe('File Graph edge semantics', () => {
  test('incoming and outgoing differ by more than colour', () => {
    const out = resolveDependencyEdgeStyle({ ...depBase, hasActive: true, isOutgoing: true });
    const inc = resolveDependencyEdgeStyle({ ...depBase, hasActive: true, isIncoming: true });

    assert.notEqual(out.stroke, inc.stroke, 'tones should still differ');
    assert.notEqual(
      nonColourSignature(out),
      nonColourSignature(inc),
      'direction must also be carried by dash or width, not colour alone',
    );
    assert.equal(out.dash, EDGE_DASH.solid, 'a dependency reads as a solid line');
    assert.equal(inc.dash, EDGE_DASH.incoming, 'a dependent reads as a dashed line');
  });

  test('a cycle is marked at both ends and dashed', () => {
    const cyc = resolveDependencyEdgeStyle({
      ...depBase, hasActive: true, isOutgoing: true, isCyclic: true,
    });
    assert.equal(cyc.bothEnds, true, 'a cycle needs an arrowhead at both ends');
    assert.equal(cyc.dash, EDGE_DASH.cyclic);
    assert.equal(cyc.stroke, EDGE_TONE.cyclic);
  });

  test('a cycle outside the current focus is not promoted', () => {
    const idleCycle = resolveDependencyEdgeStyle({ ...depBase, isCyclic: true, hasActive: true });
    assert.equal(idleCycle.bothEnds, false, 'only cycles touching the focus are emphasised');
    assert.equal(idleCycle.opacity, 0.1);
  });

  test('a traced path outranks every other relationship', () => {
    const path = resolveDependencyEdgeStyle({
      ...depBase, hasActive: true, isPath: true, isCyclic: true, isIncoming: true,
    });
    assert.equal(path.stroke, EDGE_TONE.path);
    assert.ok(path.strokeWidth > 2.25, 'the traced path must be the heaviest stroke');
    assert.equal(path.opacity, 1);
  });

  test('unrelated topology recedes but stays present', () => {
    const inactive = resolveDependencyEdgeStyle({ ...depBase, hasActive: true });
    assert.ok(inactive.opacity > 0, 'background edges must not vanish entirely');
    assert.ok(inactive.opacity <= 0.12, 'background edges must clearly recede');
  });

  test('the resting state honours the category tone when nothing is focused', () => {
    const idle = resolveDependencyEdgeStyle({ ...depBase, idleTone: '#2563eb' });
    assert.equal(idle.stroke, '#2563eb');
    assert.ok(idle.opacity > 0.3, 'the resting topology should be readable');
    const fallback = resolveDependencyEdgeStyle({ ...depBase });
    assert.equal(fallback.stroke, EDGE_TONE.idle);
  });

  test('focused relationships always outrank the resting state', () => {
    const idle = resolveDependencyEdgeStyle({ ...depBase });
    for (const flags of [
      { ...depBase, hasActive: true, isOutgoing: true },
      { ...depBase, hasActive: true, isIncoming: true },
      { ...depBase, hasActive: true, isPath: true },
    ]) {
      const v = resolveDependencyEdgeStyle(flags);
      assert.ok(v.strokeWidth > idle.strokeWidth, 'active edges must be heavier');
      assert.ok(v.opacity > idle.opacity, 'active edges must be more opaque');
    }
  });
});

describe('Call Graph edge semantics', () => {
  test('callers and callees differ by more than colour', () => {
    const out = resolveCallEdgeStyle({ ...callBase, hasActive: true, isOutgoing: true });
    const inc = resolveCallEdgeStyle({ ...callBase, hasActive: true, isIncoming: true });

    assert.notEqual(out.stroke, inc.stroke);
    assert.notEqual(
      nonColourSignature(out),
      nonColourSignature(inc),
      'call direction must also be carried by dash or width',
    );
  });

  test('a self-call is dotted and distinct from an ambiguous call', () => {
    const self = resolveCallEdgeStyle({ ...callBase, isSelfCall: true });
    const amb = resolveCallEdgeStyle({ ...callBase, isAmbiguous: true });

    assert.equal(self.dash, EDGE_DASH.recursive);
    assert.equal(amb.dash, EDGE_DASH.ambiguous);
    assert.notEqual(
      nonColourSignature(self),
      nonColourSignature(amb),
      'recursion and ambiguity must not look alike',
    );
  });

  test('mutual recursion is marked at both ends', () => {
    const mutual = resolveCallEdgeStyle({ ...callBase, isMutualRecursion: true });
    assert.equal(mutual.bothEnds, true);
    assert.equal(mutual.dash, EDGE_DASH.recursive);
  });

  test('recursion outranks plain direction', () => {
    const v = resolveCallEdgeStyle({
      ...callBase, hasActive: true, isOutgoing: true, isSelfCall: true,
    });
    assert.equal(v.dash, EDGE_DASH.recursive, 'recursion must win over direction');
  });

  test('an ambiguous call keeps its uncertainty inside the focus', () => {
    const focused = resolveCallEdgeStyle({
      ...callBase, hasActive: true, isOutgoing: true, isAmbiguous: true,
    });
    const resolved = resolveCallEdgeStyle({ ...callBase, hasActive: true, isOutgoing: true });

    assert.equal(focused.dash, EDGE_DASH.ambiguous, 'an unresolved call stays dashed');
    assert.ok(
      focused.strokeWidth < resolved.strokeWidth,
      'a guess must never look as strong as a resolved call',
    );
    assert.ok(focused.opacity > 0.5, 'but it must still be visible when in focus');
  });

  test('unrelated call chains recede but stay present', () => {
    const inactive = resolveCallEdgeStyle({ ...callBase, hasActive: true });
    assert.ok(inactive.opacity > 0);
    assert.ok(inactive.opacity <= 0.12);
  });

  test('every relationship kind yields a finite, renderable style', () => {
    const kinds: CallEdgeFlags[] = [
      { ...callBase },
      { ...callBase, hasActive: true },
      { ...callBase, hasActive: true, isIncoming: true },
      { ...callBase, hasActive: true, isOutgoing: true },
      { ...callBase, isSelfCall: true },
      { ...callBase, isMutualRecursion: true },
      { ...callBase, isAmbiguous: true },
    ];

    for (const k of kinds) {
      const v = resolveCallEdgeStyle(k);
      assert.ok(Number.isFinite(v.strokeWidth) && v.strokeWidth > 0, 'width must be positive');
      assert.ok(v.opacity > 0 && v.opacity <= 1, 'opacity must be in range');
      assert.ok(typeof v.stroke === 'string' && v.stroke.startsWith('#'), 'stroke must be a colour');
    }
  });
});

describe('Shared semantics — cross-graph consistency', () => {
  test('both graphs use the same tone for the same direction', () => {
    const depOut = resolveDependencyEdgeStyle({ ...depBase, hasActive: true, isOutgoing: true });
    const callOut = resolveCallEdgeStyle({ ...callBase, hasActive: true, isOutgoing: true });
    assert.equal(depOut.stroke, callOut.stroke, 'outgoing must read the same on both surfaces');

    const depIn = resolveDependencyEdgeStyle({ ...depBase, hasActive: true, isIncoming: true });
    const callIn = resolveCallEdgeStyle({ ...callBase, hasActive: true, isIncoming: true });
    assert.equal(depIn.stroke, callIn.stroke, 'incoming must read the same on both surfaces');
    assert.equal(depIn.dash, callIn.dash, 'incoming must dash the same on both surfaces');
  });

  test('both graphs subdue unrelated topology identically', () => {
    const dep = resolveDependencyEdgeStyle({ ...depBase, hasActive: true });
    const call = resolveCallEdgeStyle({ ...callBase, hasActive: true });
    assert.equal(dep.opacity, call.opacity);
    assert.equal(dep.stroke, call.stroke);
  });
});

// ── The landing page must speak the product's direction language ───────────

describe('Landing topology — shares the product edge vocabulary', () => {
  const LANDING_GRAPH = 'src/components/landing/CodebaseGraph.tsx';

  function readLanding(): string {
    // Imported lazily so the pure-semantics tests above stay filesystem-free.
    return readFileSync(LANDING_GRAPH, 'utf8');
  }

  test('imports the shared tones instead of hardcoding its own', () => {
    const src = readLanding();
    assert.ok(
      src.includes("from '../interactive/graph/edgeSemantics'"),
      'the landing graph must reuse the product edge semantics module',
    );
    assert.ok(src.includes('EDGE_TONE.incoming'), 'inbound tone is not the shared one');
    assert.ok(src.includes('EDGE_TONE.outgoing'), 'outbound tone is not the shared one');
    assert.ok(src.includes('EDGE_DASH.incoming'), 'inbound dash is not the shared one');
  });

  test('does not reintroduce a private landing colour for direction', () => {
    const src = readLanding();
    // The old implementation used a gradient that carried no direction at all.
    assert.ok(!src.includes('cg-edge'), 'the directionless edge gradient is back');
    for (const literal of ['#34d399', '#818cf8']) {
      assert.ok(
        !src.includes(literal),
        `direction tone ${literal} is hardcoded — it must come from EDGE_TONE`,
      );
    }
  });

  test('direction is carried by an arrowhead, not colour alone', () => {
    const src = readLanding();
    assert.ok(src.includes('cg-head-in'), 'inbound arrowhead marker missing');
    assert.ok(src.includes('cg-head-out'), 'outbound arrowhead marker missing');
    assert.ok(src.includes('markerEnd'), 'edges no longer attach an arrowhead');
    assert.ok(
      src.includes('edge.to === activeId') && src.includes('edge.from === activeId'),
      'inbound/outbound are no longer distinguished',
    );
  });

  test('carries no perpetual motion', () => {
    const src = readLanding();
    assert.ok(
      !src.includes('repeatCount="indefinite"'),
      'travelling packets are back — perpetual motion implies live traffic',
    );
    assert.ok(!src.includes('animateMotion'), 'animateMotion is back on the landing graph');
    assert.ok(!src.includes('svg-pulse'), 'the perpetual pulse ring is back');
  });

  test('the illustrative disclosure is never hidden at a breakpoint', () => {
    const src = readLanding();
    assert.ok(src.includes('ILLUSTRATIVE'), 'the illustrative marker is gone');
    assert.ok(
      !/hidden\s+(sm|md|lg):block[^>]*>\s*\n?\s*ILLUSTRATIVE/.test(src),
      'the illustrative disclosure must not be hidden on small screens',
    );
  });
});

/**
 * Focus choreography.
 *
 * The two surfaces report different dimensions, so they must not respond to a
 * selection in the same rhythm. Architecture is a topology: direction is
 * structural, so both directions resolve together. Execution is a flow: what runs
 * before the selected function illuminates first, what it calls follows.
 *
 * These are the assertions that keep the Call Graph from collapsing back into a
 * differently-coloured File Graph.
 */
describe('Focus choreography — execution reads as a traversal', () => {
  test('callers illuminate before callees', () => {
    const callers = resolveFocusChoreography('incoming', 'execution');
    const callees = resolveFocusChoreography('outgoing', 'execution');
    assert.ok(
      callers.delayMs < callees.delayMs,
      'what calls this must light before what this calls',
    );
  });

  test('the selected function never waits', () => {
    assert.equal(resolveFocusChoreography('focus', 'execution').delayMs, 0);
    assert.equal(resolveFocusChoreography('focus', 'architecture').delayMs, 0);
  });

  test('unrelated chains retreat last, so the eye follows the traversal', () => {
    const { delayMs } = resolveFocusChoreography('unrelated', 'execution');
    assert.ok(delayMs > resolveFocusChoreography('outgoing', 'execution').delayMs);
  });
});

describe('Focus choreography — architecture reads as a structure', () => {
  test('both directions resolve together', () => {
    const inbound = resolveFocusChoreography('incoming', 'architecture');
    const outbound = resolveFocusChoreography('outgoing', 'architecture');
    assert.deepEqual(
      inbound,
      outbound,
      'direction is structural here, not temporal — staggering it would imply execution order',
    );
  });

  test('the two surfaces are genuinely distinguishable', () => {
    const exec = resolveFocusChoreography('outgoing', 'execution');
    const arch = resolveFocusChoreography('outgoing', 'architecture');
    assert.notEqual(
      exec.delayMs,
      arch.delayMs,
      'the Call Graph must not share the File Graph cadence',
    );
  });
});

describe('Focus choreography — bounds and wiring', () => {
  test('nothing is left waiting, and nothing runs long enough to feel like a loop', () => {
    const roles = ['focus', 'incoming', 'outgoing', 'unrelated', 'idle'] as const;
    for (const surface of ['architecture', 'execution'] as const) {
      for (const role of roles) {
        const c = resolveFocusChoreography(role, surface);
        assert.ok(Number.isFinite(c.delayMs) && c.delayMs >= 0, `${role}/${surface} delay`);
        assert.ok(c.durationMs > 0 && c.durationMs <= 600, `${role}/${surface} duration`);
        assert.ok(c.delayMs + c.durationMs <= 900, `${role}/${surface} settles promptly`);
      }
    }
  });

  test('the resting state carries no delay', () => {
    for (const surface of ['architecture', 'execution'] as const) {
      assert.equal(resolveFocusChoreography('idle', surface).delayMs, 0);
    }
  });

  test('edgeFocusRole maps selection state onto a role', () => {
    assert.equal(edgeFocusRole({ isIncoming: false, isOutgoing: false, hasActive: false }), 'idle');
    assert.equal(edgeFocusRole({ isIncoming: true, isOutgoing: false, hasActive: true }), 'incoming');
    assert.equal(edgeFocusRole({ isIncoming: false, isOutgoing: true, hasActive: true }), 'outgoing');
    assert.equal(edgeFocusRole({ isIncoming: false, isOutgoing: false, hasActive: true }), 'unrelated');
  });

  test('the transition it emits is bounded and never repeats', () => {
    const css = edgeTransition(resolveFocusChoreography('outgoing', 'execution'));
    for (const prop of ['stroke', 'stroke-width', 'opacity']) {
      assert.ok(css.includes(prop), `${prop} is not transitioned`);
    }
    assert.ok(!/infinite|alternate/.test(css), 'a focus response must not loop');
    assert.ok(!/transform/.test(css), 'geometry must not move on a focus change');
  });
});

describe('Graph surfaces adopt the shared choreography', () => {
  const FILE_GRAPH = 'src/components/interactive/graph/GraphCanvas.tsx';
  const CALL_GRAPH = 'src/components/interactive/CallGraphAnalyzer.tsx';

  test('neither surface hardcodes its own timing', () => {
    for (const file of [FILE_GRAPH, CALL_GRAPH]) {
      const src = readFileSync(file, 'utf8');
      assert.ok(
        src.includes('resolveFocusChoreography'),
        `${file} does not use the shared choreography`,
      );
    }
  });

  test('each surface declares the dimension it reports', () => {
    assert.ok(
      readFileSync(FILE_GRAPH, 'utf8').includes("'architecture'"),
      'the File Graph must choreograph as a topology',
    );
    assert.ok(
      readFileSync(CALL_GRAPH, 'utf8').includes("'execution'"),
      'the Call Graph must choreograph as a flow',
    );
  });

  test('a focus change still never animates the edges themselves', () => {
    for (const file of [FILE_GRAPH, CALL_GRAPH]) {
      const src = readFileSync(file, 'utf8');
      assert.ok(src.includes('animated: false'), `${file} reintroduced marching dashes`);
    }
  });
});
