import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

/**
 * Cross-surface invariants for the Analysis ecosystem.
 *
 * These lock the properties that make thirteen surfaces read as one instrument.
 * They are deliberately source-text assertions rather than rendering tests: they
 * are cheap, they cannot flake, and every one of them corresponds to a defect
 * that actually occurred during the polish passes.
 *
 * They are NOT a substitute for looking at the pages. They only guarantee that
 * fixes already made cannot silently regress.
 */

const INTERACTIVE = 'src/components/interactive';
const DASHBOARD = join(INTERACTIVE, 'AnalysisDashboard.tsx');

function read(path: string): string {
  return readFileSync(path, 'utf8');
}

/** Every .tsx under src/components/interactive, recursively. */
function analysisComponents(): string[] {
  const out: string[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = join(dir, entry.name);
      if (entry.isDirectory()) walk(full);
      else if (entry.name.endsWith('.tsx')) out.push(full);
    }
  };
  walk(INTERACTIVE);
  return out;
}

/** Strips block and line comments so assertions test rendered code, not prose. */
function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1');
}

// ── §29 URL contract ────────────────────────────────────────────────────────

const REQUIRED_TAB_IDS = [
  'analysis',
  'reading_path',
  'chat',
  'graph',
  'call_graph',
  'api_surface',
  'report',
  'dead_code',
  'issues',
  'git_history',
  'pr_intelligence',
  'architecture_drift',
  'impact_analysis',
];

describe('Analysis ecosystem — URL and tab contract', () => {
  test('every documented tab id is still declared', () => {
    const src = read(DASHBOARD);
    for (const id of REQUIRED_TAB_IDS) {
      assert.ok(
        src.includes(`'${id}'`),
        `tab id '${id}' is missing — direct URLs ?tab=${id} would break`,
      );
    }
  });

  test('the tab list declares exactly the documented surfaces', () => {
    const src = read(DASHBOARD);
    const block = src.slice(src.indexOf('const TABS'), src.indexOf('function countFiles'));
    const ids = [...block.matchAll(/\{\s*id:\s*'([a-z_]+)'/g)].map((m) => m[1]);

    assert.equal(
      ids.length,
      REQUIRED_TAB_IDS.length,
      `expected ${REQUIRED_TAB_IDS.length} tabs, found ${ids.length}: ${ids.join(', ')}`,
    );
    assert.deepEqual([...ids].sort(), [...REQUIRED_TAB_IDS].sort());
  });

  test('tab state is still synchronised to the URL', () => {
    const src = read(DASHBOARD);
    assert.ok(src.includes('syncTabToUrl'), 'URL synchronisation helper is gone');
    assert.ok(src.includes("searchParams.set('tab'"), 'tab param is no longer written');
    assert.ok(src.includes('resolveInitialTab'), 'initial tab is no longer read from the URL');
  });

  test('deep-link params are still read', () => {
    const src = read(DASHBOARD);
    assert.ok(src.includes("params.get('file')"), 'file= deep link no longer read');
    assert.ok(src.includes("params.get('focus')"), 'focus= deep link no longer read');
  });
});

// ── §31 event contracts ─────────────────────────────────────────────────────

describe('Analysis ecosystem — shared event contracts', () => {
  test('the dashboard listens for every shared navigation event', () => {
    const src = read(DASHBOARD);
    for (const evt of [
      'aria-open-graph',
      'aria-open-chat',
      'aria-open-impact',
      'aria-open-issues',
      'aria-workspace-file-select',
    ]) {
      assert.ok(
        src.includes(`addEventListener('${evt}'`),
        `dashboard no longer listens for ${evt}`,
      );
    }
  });

  test('surfaces dispatch only the shared contracts, never a parallel system', () => {
    /*
      The complete set of ARIA cross-surface contracts. `aria-workspace-file-select`
      keeps the workspace explorer in step with graph selection — it is dispatched
      by the file graph and consumed by the dashboard shell.
    */
    const allowed = new Set([
      'aria-open-graph',
      'aria-open-chat',
      'aria-open-impact',
      'aria-open-issues',
      'aria-workspace-file-select',
      'aria-analysis-started',
      'aria-analysis-completed',
      'active-repo-changed',
      'active-repo-cleared',
    ]);

    for (const file of analysisComponents()) {
      const src = stripComments(read(file));
      for (const m of src.matchAll(/new CustomEvent\(\s*'([^']+)'/g)) {
        assert.ok(
          allowed.has(m[1]),
          `${file} dispatches '${m[1]}', which is not a shared ARIA contract`,
        );
      }
    }
  });
});

// ── §24 single completion indicator ─────────────────────────────────────────

describe('Analysis ecosystem — one authoritative completion indicator', () => {
  test('only the dashboard shell renders ANALYSIS COMPLETE', () => {
    const offenders: string[] = [];

    for (const file of analysisComponents()) {
      if (file === DASHBOARD) continue;
      if (stripComments(read(file)).includes('ANALYSIS COMPLETE')) offenders.push(file);
    }

    assert.deepEqual(
      offenders,
      [],
      `these panels render a competing completion badge: ${offenders.join(', ')}`,
    );
  });

  test('the shell still renders it exactly once', () => {
    const src = stripComments(read(DASHBOARD));
    assert.equal(
      [...src.matchAll(/ANALYSIS COMPLETE/g)].length,
      1,
      'the shell completion indicator must appear exactly once',
    );
  });

  test('panel footers do not reintroduce a green READY badge', () => {
    /*
      Panel summaries are neutral mono lines. A green "<X> READY" label reads as a
      second completion verdict beside the shell's, which is what §24 forbids.
    */
    const offenders: string[] = [];
    for (const file of analysisComponents()) {
      if (file === DASHBOARD) continue;
      const src = stripComments(read(file));
      if (/mono-label[^>]*var\(--success\)[^>]*>\s*[A-Z ]*READY/.test(src)) {
        offenders.push(file);
      }
    }
    assert.deepEqual(offenders, [], `green READY badges found in: ${offenders.join(', ')}`);
  });
});

// ── §32 data honesty ────────────────────────────────────────────────────────

describe('Analysis ecosystem — data honesty', () => {
  test('no surface asserts an unmeasured security or performance verdict', () => {
    const banned = [
      /\bvalue="PASS"/,
      /\bvalue="OPTIMAL"/,
      /0\s*CVE/i,
      /Grade\s+A\b/,
      /98\.4/,
      /no\s+bottlenecks/i,
    ];

    for (const file of analysisComponents()) {
      const src = stripComments(read(file));
      for (const pattern of banned) {
        assert.ok(
          !pattern.test(src),
          `${file} contains a fabricated verdict matching ${pattern}`,
        );
      }
    }
  });

  test('absent data uses the shared vocabulary rather than an invented positive', () => {
    const approved = ['NOT AVAILABLE', 'NOT MEASURED', 'UNAVAILABLE', 'NO DATA', 'not measured'];
    // At least one surface must actually use the vocabulary, or the rule is dead.
    const users = analysisComponents().filter((f) =>
      approved.some((word) => read(f).includes(word)),
    );
    assert.ok(users.length >= 3, 'the absent-data vocabulary is barely used — check for regressions');
  });
});

// ── §36 performance guards ──────────────────────────────────────────────────

describe('Analysis ecosystem — performance guards', () => {
  test('graph surfaces are still statically imported', () => {
    const src = read(DASHBOARD);
    assert.ok(
      src.includes("import { InteractiveDependencyGraph } from './graph/InteractiveDependencyGraph'"),
      'the file graph must stay a static import — React.lazy caused a load regression',
    );
    assert.ok(
      !/lazy\(\s*\(\)\s*=>\s*import\([^)]*InteractiveDependencyGraph/.test(src),
      'React.lazy was reintroduced for InteractiveDependencyGraph',
    );
  });

  /*
    `animate-pulse` is permitted only as an indeterminate progress bar while a
    build is running, and only in these two surfaces. Everywhere else it was
    decoration: pulsing header icons, a forever-pulsing hint dot, an arrow between
    reading-path steps, and high-coupling graph nodes that throbbed permanently.
  */
  const PULSE_ALLOWED = ['APISurfaceAnalyzer.tsx', 'GitHistoryAnalyzer.tsx'];

  test('animate-pulse is confined to indeterminate progress bars', () => {
    const offenders: string[] = [];

    for (const file of analysisComponents()) {
      const src = stripComments(read(file));
      if (!src.includes('animate-pulse')) continue;

      if (!PULSE_ALLOWED.some((name) => file.endsWith(name))) {
        offenders.push(file);
        continue;
      }
      // Even where allowed, it must be announced as a status region.
      assert.ok(
        src.includes('role="status"'),
        `${file} pulses without an accompanying role="status" region`,
      );
    }

    assert.deepEqual(
      offenders,
      [],
      `decorative pulse animation in: ${offenders.join(', ')}`,
    );
  });

  test('graph edges are never continuously animated', () => {
    for (const file of analysisComponents()) {
      const src = stripComments(read(file));
      assert.ok(
        !/animated:\s*true/.test(src),
        `${file} sets animated:true on graph edges — §25 forbids animated edge flow`,
      );
    }
  });
});

// ── §17 shared path language ────────────────────────────────────────────────

describe('Analysis ecosystem — shared path language', () => {
  test('the FilePath primitive is adopted across the polished surfaces', () => {
    const expected = [
      'DeadCodeAnalyzer.tsx',
      'IssueMapper.tsx',
      'PRIntelligence.tsx',
      'ArchitectureDrift.tsx',
      'ImpactAnalysisGraph.tsx',
      'ReportPanel.tsx',
    ];

    for (const name of expected) {
      const file = analysisComponents().find((f) => f.endsWith(name));
      assert.ok(file, `${name} not found`);
      assert.ok(
        read(file).includes("from '../ui/FilePath'"),
        `${name} no longer uses the shared FilePath component`,
      );
    }
  });
});

// ── §6 shared tab rail ──────────────────────────────────────────────────────

describe('Analysis ecosystem — shared tab rail', () => {
  const TABS_FILE = join(INTERACTIVE, 'Tabs.tsx');

  test('the rail scrolls internally and cannot overflow the document', () => {
    const src = read(TABS_FILE);
    assert.ok(src.includes('inner-scroll-x'), 'the rail lost its internal scroll region');
    assert.ok(src.includes('tab-rail'), 'the rail lost its edge-cue hook');
  });

  test('a tab can never rest half-visible at the rail edge', () => {
    const src = read(TABS_FILE);
    assert.ok(src.includes('snap-x'), 'scroll snapping removed');
    assert.ok(src.includes('snap-start'), 'per-tab snap alignment removed');
    assert.ok(src.includes('EDGE_CLEARANCE'), 'edge clearance constant removed');
  });

  test('keyboard navigation and ARIA roles are intact', () => {
    const src = read(TABS_FILE);
    for (const token of ['role="tablist"', 'role="tab"', 'aria-selected', 'aria-controls',
                         'ArrowRight', 'ArrowLeft', 'Home', 'End']) {
      assert.ok(src.includes(token), `tab rail lost ${token}`);
    }
  });

  test('every tab icon is rendered at one size', () => {
    const src = read(TABS_FILE);
    assert.ok(
      src.includes('h-3.5 w-3.5'),
      'tab icons no longer share a single size',
    );
  });
});

// ── §22 / §30 the two graphs must stay distinguishable ─────────────────────

describe('Graph surfaces — architecture vs execution vocabulary', () => {
  const FILE_GRAPH = join(INTERACTIVE, 'graph/InteractiveDependencyGraph.tsx');
  const CALL_GRAPH = join(INTERACTIVE, 'CallGraphAnalyzer.tsx');

  test('the File Graph identifies itself as repository topology', () => {
    const src = read(FILE_GRAPH);
    assert.ok(src.includes('FILE GRAPH'), 'File Graph lost its title');
    assert.ok(src.includes('REPOSITORY TOPOLOGY'), 'File Graph lost its architectural subtitle');
  });

  test('the File Graph header telemetry comes from the payload, not constants', () => {
    const src = read(FILE_GRAPH);
    assert.ok(src.includes('apiNodes.length'), 'node count is no longer derived from the payload');
    assert.ok(src.includes('apiEdges.length'), 'edge count is no longer derived from the payload');
    assert.ok(src.includes('stats.components'), 'component count is no longer derived');
    assert.ok(src.includes('NODES') && src.includes('EDGES'), 'header telemetry labels missing');
  });

  test('the Call Graph identifies itself as execution topology', () => {
    const src = read(CALL_GRAPH);
    assert.ok(src.includes('FUNCTION CALL GRAPH'), 'Call Graph lost its title');
    assert.ok(
      src.includes('INTER-FUNCTION TOPOLOGY'),
      'Call Graph lost its execution subtitle',
    );
  });

  test('the Call Graph speaks in execution terms', () => {
    const src = read(CALL_GRAPH);
    for (const term of ['fan_in', 'fan_out', 'is_recursive', 'CALL EDGES', 'ENTRY POINTS']) {
      assert.ok(src.includes(term), `Call Graph no longer references ${term}`);
    }
  });

  test('each inspector names the dimension it reports', () => {
    assert.ok(
      read(join(INTERACTIVE, 'graph/NodeDetailsPanel.tsx')).includes('Architecture Inspector'),
      'the file-graph inspector lost its identity',
    );
    assert.ok(
      read(CALL_GRAPH).includes('Function Inspector'),
      'the call-graph inspector lost its identity',
    );
  });

  test('no internal version tag leaks into an inspector title', () => {
    for (const file of analysisComponents()) {
      const src = stripComments(read(file));
      assert.ok(
        !/Inspector v\d/.test(src),
        `${file} exposes an internal version tag in an inspector title`,
      );
    }
  });
});

// ── §28 graph data integrity ────────────────────────────────────────────────

describe('Graph surfaces — data integrity', () => {
  test('no graph surface asserts a risk severity the backend never measured', () => {
    /*
      The Call Graph inspector used to badge functions HIGH / MEDIUM / LOW RISK
      from invented thresholds on degree and fan-in. The payload carries no risk
      score, so the reading is now a coupling band and is labelled as derived.
    */
    for (const name of ['CallGraphAnalyzer.tsx', 'graph/NodeDetailsPanel.tsx',
                        'graph/InteractiveDependencyGraph.tsx', 'graph/GraphCanvas.tsx']) {
      const src = stripComments(read(join(INTERACTIVE, name)));
      for (const banned of [/'HIGH RISK'/, /'MEDIUM RISK'/, /'LOW RISK'/]) {
        assert.ok(
          !banned.test(src),
          `${name} still asserts an unmeasured risk verdict matching ${banned}`,
        );
      }
    }
  });

  test('the coupling band is present and disclosed as derived', () => {
    const src = read(join(INTERACTIVE, 'CallGraphAnalyzer.tsx'));
    assert.ok(src.includes('couplingBand'), 'the coupling band was removed');
    assert.ok(
      src.includes('COUPLING'),
      'the coupling reading lost its label',
    );
    assert.ok(
      /Derived from fan-in/.test(src),
      'the coupling band no longer discloses what it is derived from',
    );
  });
});

// ── §21 / §30 graph deep-link and cross-navigation contracts ───────────────

describe('Graph surfaces — navigation contracts', () => {
  test('the file graph still synchronises selection into the URL', () => {
    const src = read(join(INTERACTIVE, 'graph/InteractiveDependencyGraph.tsx'));
    assert.ok(src.includes("searchParams.delete('focus')"), 'focus param cleanup removed');
    assert.ok(src.includes('history.replaceState'), 'URL synchronisation removed');
    assert.ok(
      src.includes('aria-workspace-file-select'),
      'workspace synchronisation event removed',
    );
  });

  test('the call graph can still hand a file to the file graph', () => {
    const src = read(join(INTERACTIVE, 'CallGraphAnalyzer.tsx'));
    assert.ok(
      src.includes('aria-open-graph'),
      'the call graph lost its route into the file graph',
    );
  });

  test('graph surfaces reach chat through the shared contract only', () => {
    for (const name of ['CallGraphAnalyzer.tsx', 'graph/NodeDetailsPanel.tsx']) {
      const src = read(join(INTERACTIVE, name));
      if (src.includes('Ask ARIA')) {
        assert.ok(
          src.includes('aria-open-chat'),
          `${name} offers Ask ARIA without using the shared chat contract`,
        );
      }
    }
  });
});
