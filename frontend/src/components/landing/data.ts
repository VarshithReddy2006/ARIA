/**
 * Story data for the landing experience.
 *
 * These are illustrative fixtures describing ARIA's own repository — they let
 * the story show real shapes of output (module graph, blast radius, reading
 * path) before the visitor has given us a repository to analyse. Nothing here
 * is fetched from or written to the backend.
 */

export interface GraphNode {
  id: string;
  path: string;
  /** Rendered label — the file name only. */
  label: string;
  group: 'service' | 'core' | 'router' | 'mcp' | 'model';
  x: number;
  y: number;
  /** Included in the curated subset shown on small screens. */
  compact?: boolean;
  /** Position used when the curated subset is shown. */
  cx?: number;
  cy?: number;
  callers: number;
  imports: number;
  /** PageRank centrality, 0–1. */
  rank: number;
  role: string;
  /** Why the module matters — answers "why should I care about this node?". */
  why: string;
  summary: string;
}

export interface GraphEdge {
  from: string;
  to: string;
  kind: 'imports' | 'calls' | 'orchestrates';
}

/** Layout is authored on a 1000 × 560 canvas and scaled by the SVG viewBox. */
export const GRAPH_NODES: GraphNode[] = [
  {
    id: 'orchestrator',
    path: 'services/analysis_orchestrator.py',
    label: 'analysis_orchestrator.py',
    group: 'service',
    x: 500,
    y: 268,
    compact: true,
    cx: 500,
    cy: 150,
    callers: 48,
    imports: 12,
    rank: 0.94,
    role: 'Root orchestration hub',
    why: 'Nothing runs without it — every analysis stage is sequenced here.',
    summary:
      'Central orchestration engine managing AST detection, graph indexing, and SSE streaming pipeline.',
  },
  {
    id: 'ast',
    path: 'core/ast_parser.py',
    label: 'ast_parser.py',
    group: 'core',
    x: 232,
    y: 148,
    compact: true,
    cx: 210,
    cy: 430,
    callers: 34,
    imports: 4,
    rank: 0.82,
    role: 'Symbol extraction core',
    why: 'Every symbol the rest of the system reasons about originates here.',
    summary:
      'Tree-sitter parser extracting classes, methods, imports and full symbol hierarchies per file.',
  },
  {
    id: 'depgraph',
    path: 'core/dependency_graph.py',
    label: 'dependency_graph.py',
    group: 'core',
    x: 268,
    y: 404,
    compact: true,
    cx: 790,
    cy: 430,
    callers: 29,
    imports: 6,
    rank: 0.76,
    role: 'Topological engine',
    why: 'Turns symbols into a graph you can rank, sort and traverse.',
    summary:
      'NetworkX representation computing topological order, cycle detection and PageRank centrality.',
  },
  {
    id: 'repositories',
    path: 'backend/routers/repositories.py',
    label: 'repositories.py',
    group: 'router',
    x: 764,
    y: 128,
    callers: 21,
    imports: 8,
    rank: 0.68,
    role: 'HTTP entry surface',
    why: 'The only way in — changes here are visible to every client.',
    summary:
      'FastAPI router exposing analysis endpoints, repository registration and status probes.',
  },
  {
    id: 'github',
    path: 'services/github_service.py',
    label: 'github_service.py',
    group: 'service',
    x: 848,
    y: 236,
    callers: 16,
    imports: 3,
    rank: 0.58,
    role: 'Remote acquisition',
    why: 'The boundary with the outside world, and the first thing to fail.',
    summary: 'GitHub API client performing shallow clone and tree diff resolution.',
  },
  {
    id: 'search',
    path: 'mcp/tools/search_tools.py',
    label: 'search_tools.py',
    group: 'mcp',
    x: 148,
    y: 292,
    callers: 18,
    imports: 5,
    rank: 0.62,
    role: 'Retrieval bindings',
    why: 'Where a question becomes a graph traversal.',
    summary: 'MCP tool bindings for symbol lookup and ChromaDB vector retrieval.',
  },
  {
    id: 'schemas',
    path: 'models/schemas.py',
    label: 'schemas.py',
    group: 'model',
    x: 556,
    y: 486,
    compact: true,
    cx: 500,
    cy: 730,
    callers: 42,
    imports: 1,
    rank: 0.72,
    role: 'Contract layer',
    why: 'Widely imported, so its shape constrains everything downstream.',
    summary: 'Pydantic models defining analysis contracts and graph serialisation shapes.',
  },
];

/**
 * Faint ambient topology sitting behind the real graph — depth only, carrying
 * no meaning. Authored on the same 1000 × 620 canvas.
 */
export const AMBIENT_NODES = [
  { x: 62, y: 84 }, { x: 176, y: 40 }, { x: 344, y: 66 }, { x: 646, y: 44 },
  { x: 906, y: 92 }, { x: 60, y: 200 }, { x: 946, y: 168 }, { x: 40, y: 470 },
  { x: 154, y: 556 }, { x: 388, y: 588 }, { x: 700, y: 590 }, { x: 900, y: 520 },
  { x: 968, y: 420 }, { x: 420, y: 236 }, { x: 660, y: 340 }, { x: 300, y: 300 },
];

export const AMBIENT_EDGES: Array<[number, number]> = [
  [0, 1], [1, 2], [2, 13], [3, 4], [5, 0], [6, 12], [7, 8], [8, 9],
  [9, 10], [10, 11], [11, 12], [15, 13], [13, 14],
];

export const GRAPH_EDGES: GraphEdge[] = [
  { from: 'repositories', to: 'orchestrator', kind: 'orchestrates' },
  { from: 'orchestrator', to: 'ast', kind: 'calls' },
  { from: 'orchestrator', to: 'depgraph', kind: 'calls' },
  { from: 'orchestrator', to: 'github', kind: 'calls' },
  { from: 'ast', to: 'depgraph', kind: 'imports' },
  { from: 'search', to: 'orchestrator', kind: 'calls' },
  { from: 'search', to: 'ast', kind: 'imports' },
  { from: 'depgraph', to: 'schemas', kind: 'imports' },
  { from: 'orchestrator', to: 'schemas', kind: 'imports' },
  { from: 'github', to: 'schemas', kind: 'imports' },
  { from: 'repositories', to: 'schemas', kind: 'imports' },
];

/*
 * Chapter 02's five layers now live in `structureModel.ts` alongside the stage
 * geometry that animates them, so the copy and the choreography cannot drift.
 */

/* ── Chapter 04: change propagation ───────────────────────────────────────── */
export interface PropagationStep {
  stage: string;
  target: string;
  detail: string;
}

export interface ChangeScenario {
  id: string;
  symbol: string;
  file: string;
  depth: number;
  files: number;
  symbols: number;
  chain: PropagationStep[];
}

export const CHANGE_SCENARIOS: ChangeScenario[] = [
  {
    id: 'parser',
    symbol: 'ASTParser.extract_call_hierarchy()',
    file: 'core/ast_parser.py',
    depth: 4,
    files: 7,
    symbols: 28,
    chain: [
      {
        stage: 'CHANGED SYMBOL',
        target: 'ASTParser.extract_call_hierarchy()',
        detail: 'Signature gains an optional AST scope parameter.',
      },
      {
        stage: 'DIRECT CALLER',
        target: 'DependencyGraph.build_call_graph()',
        detail: 'Consumes the node relationship tuple it returns.',
      },
      {
        stage: 'ORCHESTRATOR',
        target: 'AnalysisOrchestrator.run_pipeline()',
        detail: 'Parallel worker payload structure shifts with it.',
      },
      {
        stage: 'ENTRY POINT',
        target: 'GET /api/v1/analysis/{owner}/{repo}',
        detail: 'Client SSE stream response contract is affected.',
      },
    ],
  },
  {
    id: 'clone',
    symbol: 'GitHubService.shallow_clone()',
    file: 'services/github_service.py',
    depth: 3,
    files: 3,
    symbols: 9,
    chain: [
      {
        stage: 'CHANGED SYMBOL',
        target: 'GitHubService.shallow_clone()',
        detail: 'Adds retry backoff for upstream rate limits.',
      },
      {
        stage: 'DIRECT CALLER',
        target: 'AnalysisOrchestrator.clone_step()',
        detail: 'Must now catch a longer clone timeout window.',
      },
      {
        stage: 'ENTRY POINT',
        target: 'POST /api/v1/analyze',
        detail: 'Returns 202 Accepted earlier in the sequence.',
      },
    ],
  },
  {
    id: 'schema',
    symbol: 'RepositoryHealthSummary.score',
    file: 'models/schemas.py',
    depth: 2,
    files: 2,
    symbols: 4,
    chain: [
      {
        stage: 'CHANGED SYMBOL',
        target: 'RepositoryHealthSummary.score',
        detail: 'Field validation clamps the value between 0 and 100.',
      },
      {
        stage: 'ENTRY POINT',
        target: 'GET /api/v1/report/{owner}/{repo}',
        detail: 'Serialised report payload narrows its range.',
      },
    ],
  },
];

/* ── Chapter 05: repository memory (time) ─────────────────────────────────────
 *
 * The temporal dimension of the same repository. ARIA reads git history, so this
 * chapter shows the shape of that output: when a module was being changed, how
 * much of it was rewritten, and where change concentrated.
 *
 * Illustrative, exactly like the graph and blast-radius fixtures above, and
 * disclosed as such wherever it is rendered. `from` and `to` are positions on a
 * normalised 0→1 timeline, not dates, so the axis labels and the spans can never
 * disagree. Nothing here animates as though commits were arriving live.
 */
export interface HistorySpan {
  path: string;
  role: string;
  /** First recorded change, as a position on the 0→1 window. */
  from: number;
  /** Most recent change, as a position on the 0→1 window. */
  to: number;
  /** Commits touching the file across the window. */
  commits: number;
  /** Share of the module rewritten across the window, 0→1. */
  churn: number;
  /** Change concentrating in a structurally central module. */
  hotspot?: boolean;
  /** What the shape of this span means. */
  note: string;
  /** Included in the curated subset shown on small screens. */
  compact?: boolean;
}

/** Axis labels. Evenly spaced, so they describe the window without implying dates. */
export const HISTORY_ERAS = ['2024', '2025', '2026'] as const;

export const REPOSITORY_HISTORY: HistorySpan[] = [
  {
    path: 'services/analysis_orchestrator.py',
    role: 'ROOT ORCHESTRATION HUB',
    from: 0.04,
    to: 1.0,
    commits: 214,
    churn: 0.92,
    hotspot: true,
    note: 'Touched in every phase of the project, and still changing.',
    compact: true,
  },
  {
    path: 'core/ast_parser.py',
    role: 'SYMBOL EXTRACTION CORE',
    from: 0.06,
    to: 0.86,
    commits: 168,
    churn: 0.74,
    hotspot: true,
    note: 'Heavy early churn as language support widened, quieter since.',
    compact: true,
  },
  {
    path: 'core/dependency_graph.py',
    role: 'TOPOLOGICAL ENGINE',
    from: 0.18,
    to: 0.94,
    commits: 131,
    churn: 0.63,
    note: 'Rewritten once when centrality replaced simple import counting.',
    compact: true,
  },
  {
    path: 'models/schemas.py',
    role: 'CONTRACT LAYER',
    from: 0.0,
    to: 0.98,
    commits: 97,
    churn: 0.41,
    note: 'Small, constant edits — the cost of being imported everywhere.',
    compact: true,
  },
  {
    path: 'backend/routers/repositories.py',
    role: 'HTTP ENTRY SURFACE',
    from: 0.22,
    to: 0.72,
    commits: 64,
    churn: 0.35,
    note: 'Settled once the endpoint contract stabilised.',
  },
  {
    path: 'mcp/tools/search_tools.py',
    role: 'RETRIEVAL BINDINGS',
    from: 0.48,
    to: 1.0,
    commits: 58,
    churn: 0.56,
    note: 'The newest subsystem, and the most active relative to its age.',
  },
  {
    path: 'services/github_service.py',
    role: 'REMOTE ACQUISITION',
    from: 0.02,
    to: 0.44,
    commits: 39,
    churn: 0.18,
    note: 'Effectively finished — a boundary that stopped moving.',
  },
];

/** Read-outs derived from the spans above, so the two can never drift apart. */
export const HISTORY_SUMMARY = {
  commits: REPOSITORY_HISTORY.reduce((sum, s) => sum + s.commits, 0),
  files: REPOSITORY_HISTORY.length,
  hotspots: REPOSITORY_HISTORY.filter((s) => s.hotspot).length,
};

/* ── Chapter 06: grounded retrieval ───────────────────────────────────────── */
export const MEMORY_QUESTION =
  'How does ARIA detect circular dependencies across modules?';

export const MEMORY_SYMBOLS = [
  { symbol: 'DependencyGraph.find_cycles()', path: 'core/dependency_graph.py', lines: 'L182–L219' },
  { symbol: 'simple_cycles()', path: 'networkx/algorithms/cycles.py', lines: 'L98–L164' },
  { symbol: 'AnalysisOrchestrator.audit_graph()', path: 'services/analysis_orchestrator.py', lines: 'L412–L448' },
];

export const MEMORY_CONTEXT = [
  { label: 'Topology depth', value: '12' },
  { label: 'Graph directed', value: 'DiGraph' },
  { label: 'Nodes evaluated', value: '1,284' },
  { label: 'Cycles found', value: '0' },
];

export const MEMORY_ANSWER = [
  'Cycle detection runs on the directed import graph, not on the file tree.',
  'DependencyGraph.find_cycles() delegates to networkx.simple_cycles() over the DiGraph built during indexing, then filters results to first-party modules so vendored packages never raise false positives.',
  'Every cycle is returned as an ordered path, which is what lets the report cite the exact import that closes the loop.',
];

/* ── Chapter 07: reading path ─────────────────────────────────────────────── */
export interface ReadingStep {
  index: string;
  path: string;
  role: string;
  rank: number;
  /** Illustrative reading-time estimate, in minutes. */
  minutes: number;
  note: string;
}

export const READING_PATH: ReadingStep[] = [
  {
    index: '01',
    path: 'services/analysis_orchestrator.py',
    role: 'ROOT ORCHESTRATION HUB',
    rank: 0.94,
    minutes: 12,
    note: 'Start here: every analysis stage is sequenced from this module.',
  },
  {
    index: '02',
    path: 'core/ast_parser.py',
    role: 'SYMBOL EXTRACTION CORE',
    rank: 0.82,
    minutes: 9,
    note: 'How raw source becomes classes, methods and import statements.',
  },
  {
    index: '03',
    path: 'core/dependency_graph.py',
    role: 'TOPOLOGICAL ENGINE',
    rank: 0.76,
    minutes: 8,
    note: 'Where symbols become a graph you can rank, sort and traverse.',
  },
  {
    index: '04',
    path: 'models/schemas.py',
    role: 'CONTRACT LAYER',
    rank: 0.72,
    minutes: 5,
    note: 'The shapes every analyzer agrees to speak in.',
  },
  {
    index: '05',
    path: 'backend/routers/repositories.py',
    role: 'HTTP ENTRY SURFACE',
    rank: 0.68,
    minutes: 6,
    note: 'Read last: the thin layer that exposes all of the above.',
  },
];

/* ── Chapter 08: pipeline ─────────────────────────────────────────────────── */
export const PIPELINE_STAGES = [
  {
    step: '01',
    title: 'CLONE',
    sub: 'Target repository',
    detail: 'Shallow clone into an ephemeral workspace. Nothing is written back.',
  },
  {
    step: '02',
    title: 'DETECT',
    sub: 'Ecosystem & stacks',
    detail: 'Languages, build manifests, package boundaries and entry points.',
  },
  {
    step: '03',
    title: 'INDEX',
    sub: 'Symbol extraction',
    detail: 'Tree-sitter parses each file into fine-grained symbol hierarchies.',
  },
  {
    step: '04',
    title: 'ANALYZE',
    sub: 'Graph computation',
    detail: 'Centrality, cycle detection and blast radius over the NetworkX graph.',
  },
  {
    step: '05',
    title: 'ANSWER',
    sub: 'Knowledge retrieval',
    detail: 'Graph-grounded retrieval that cites the files it reasoned over.',
  },
];

/* ── Chapter 09: technology ───────────────────────────────────────────────── */
export const TECHNOLOGY = [
  {
    column: 'CORE',
    items: ['Tree-sitter AST', 'NetworkX Topology', 'FastAPI', 'Python 3.12', 'ChromaDB'],
  },
  {
    column: 'INTELLIGENCE',
    items: ['Gemini 2.5 Flash', 'DeepSeek', 'Deterministic RAG', 'Incremental Caching'],
  },
  {
    column: 'INTERFACE',
    items: ['Astro', 'React', 'Tailwind CSS', 'TypeScript'],
  },
];

/** Shown until `/api/v1/repos/examples` responds, so the section never flashes empty. */
export const FALLBACK_SAMPLES = [
  {
    name: 'google/guava',
    url: 'https://github.com/google/guava',
    description: 'Google core libraries for Java.',
    tech_stack: ['Java', 'Maven'],
  },
  {
    name: 'fastapi/fastapi',
    url: 'https://github.com/fastapi/fastapi',
    description: 'High performance Python framework.',
    tech_stack: ['Python', 'Pydantic', 'Starlette'],
  },
  {
    name: 'vercel/next.js',
    url: 'https://github.com/vercel/next.js',
    description: 'The React Framework for the Web.',
    tech_stack: ['JavaScript', 'TypeScript', 'React'],
  },
];
