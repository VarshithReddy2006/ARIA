# System Design Document

**Product:** ARIA (Repository Intelligence Agent)
**Document status:** Foundation — normative
**Version:** 2.0 (greenfield design)
**Companion documents:** `01-PRD.md`, `03-DIGITAL-TWIN-SPEC.md`

> This document designs the ideal architecture without reference to the existing implementation. Migration is not in scope here. Where the design contradicts current code, the design wins.

---

## 1. Design Goals and Non-Goals

### 1.1 Goals, with quantified targets

| # | Goal | Target |
|:--:|---|---|
| G1 | **Precision** — resolved, not matched | ≥0.95 precision / ≥0.90 recall on symbol resolution for supported languages; ≥80% of edges `method=exact` |
| G2 | **Commit-addressed** — every answer scoped to a commit | 100% of fact queries accept and honor a `commit` parameter |
| G3 | **Incremental** — cost proportional to change, not repository size | p95 <2s for ≤10 changed files, independent of repository size |
| G4 | **Query latency** — machine-consumer grade | p95 <200ms for graph and resolution queries at 1M LOC |
| G5 | **Scale** — enterprise monorepo | 10M LOC, ~10⁷ symbols, ~10⁸ edges per repository |
| G6 | **Determinism** — no model in the fact path | ≥80% of queries served with zero LLM calls |
| G7 | **Extensibility** — new language or facet without core change | New language = one plugin, zero core edits |
| G8 | **Honest degradation** — never silently weaken | 100% of results carry `method` and `confidence` |

### 1.2 Explicit non-goals

Not designed for: real-time sub-second reaction to every keystroke (IDEs own that); code generation; being a general graph database; storing source code as a system of record (git is); replacing language servers for in-editor local resolution.

### 1.3 The four constraints that shape everything

1. **Facts are expensive to produce and cheap to keep. Interpretations are the reverse.** ⇒ two stores, one-way dependency.
2. **Structure at scale exceeds memory by orders of magnitude.** ⇒ no design may require loading a whole-repository graph into a process. This single constraint eliminates the in-memory graph-object approach categorically.
3. **Every fact is a function of a commit.** ⇒ commit is not metadata, it is part of every primary key.
4. **The dominant consumer is a machine issuing many small queries, not a human issuing few large ones.** ⇒ optimize for p95 of small point/neighborhood queries, not throughput of full-graph scans.

---

## 2. Layered Architecture

### 2.1 The stack

```
╔══════════════════════════════════════════════════════════════════════════╗
║ L9  APPLICATIONS        MCP · REST · GraphQL · CLI · IDE · CI · Web      ║
║                         (all are equal clients of L8. no back doors)     ║
╠══════════════════════════════════════════════════════════════════════════╣
║ L8  QUERY GATEWAY       contract · authz · quota · cache · pagination    ║
║                         deterministic ordering · latency budget          ║
╠══════════════════════════════════════════════════════════════════════════╣
║ L7  REASONING           tool-calling loop · retrieval planner            ║
║     (probabilistic)     context assembler · prompt orchestration         ║
║                         citation verifier · answer evaluator             ║
╟──────────────────────────────────────────────────────────────────────────╢
║     ═══════ HARD BOUNDARY: nothing below this line calls an LLM ═══════  ║
╟──────────────────────────────────────────────────────────────────────────╢
║ L6  ENGINEERING MEMORY  cross-commit timeline · evolution · trends       ║
║                         decisions · outcomes · agent working memory      ║
╠══════════════════════════════════════════════════════════════════════════╣
║ L5  DIGITAL TWIN        materialized multi-facet view @commit            ║
║                         assembly · diffing · projection                  ║
╠══════════════════════════════════════════════════════════════════════════╣
║ L4  KNOWLEDGE GRAPH     unified entity + relation model                  ║
║                         dependency · call · module · architecture graphs ║
╠══════════════════════════════════════════════════════════════════════════╣
║ L3  SEMANTIC RESOLUTION name binding · monikers · types · imports        ║
║     ★ the precision layer — the product's floor and its moat ★           ║
╠══════════════════════════════════════════════════════════════════════════╣
║ L2  PARSER              tree-sitter queries (breadth)                    ║
║                         SCIP / LSP indexers (precision)                  ║
╠══════════════════════════════════════════════════════════════════════════╣
║ L1  INGESTION           clone/fetch · commit resolution · change detect  ║
║                         file unit content-addressing                     ║
╠══════════════════════════════════════════════════════════════════════════╣
║ L0  REPOSITORY          git (system of record — we never own the truth)  ║
╚══════════════════════════════════════════════════════════════════════════╝

CROSS-CUTTING (every layer):
  ORCHESTRATION  durable queue · workers · idempotency · retry · cancel
  STORAGE        facts (durable, immutable) │ derived (disposable)
  OBSERVABILITY  metrics · traces · structured logs · audit
  CONTROL PLANE  tenancy · authz · quota · policy · billing
  EVALUATION     benchmarks · regression gates · precision reporting
```

### 2.2 Deviations from the layering proposed in the brief

| Change | Reason |
|---|---|
| **Added L8 Query Gateway** | The brief's "Applications" sat directly on Reasoning. Without a gateway there is no single place for contract versioning, authorization, quota, cache, or latency enforcement — and P7 ("API is the product") becomes unenforceable |
| **Added Orchestration as cross-cutting** | The brief has no job layer. Without one, ingestion runs inside request handlers, which pins the system to a single process. This was the prior architecture's hardest ceiling |
| **Added Control Plane** | Multi-tenancy, authz, and quota cannot be retrofitted. They are load-bearing from day one even when there is one tenant |
| **Added Evaluation as cross-cutting** | Precision claims are a first-class deliverable (P8). Evaluation is infrastructure, not a test folder |
| **Memory placed above Twin, not beside it** | Memory is *cross-commit*; the twin is *at-commit*. Memory must read many twins, so it depends on the twin, not the reverse |
| **Hard LLM boundary drawn between L6 and L7** | Makes P2 (determinism first) structurally enforceable rather than a convention. Any LLM call below L7 is a build failure |

### 2.3 Dependency direction — non-negotiable

```
L9 Applications
     │ depends on
     ▼
L8 Query Gateway
     │
     ▼
L7 Reasoning ──────┐
     │             │
     ▼             ▼
L6 Memory ───▶ L5 Twin ───▶ L4 Graph ───▶ L3 Resolution ───▶ L2 Parser ───▶ L1 Ingest
                                                                                │
                                                                                ▼
                                                                            L0 Git

RULE: dependencies point downward only. Cycles are a build failure.
RULE: no layer imports from the delivery layer (L8/L9). Domain never knows about HTTP.
RULE: enforced in CI by static import analysis — by our own product, once it can.
```

The last rule is deliberate: **the system's first serious customer is itself.** An architecture fitness function that fails our build if a domain module imports a delivery module is both a dogfooding mechanism and the highest-fidelity test of the CI-gate product.

---

## 3. Layer Specifications

Each layer specified as: responsibilities · inputs · outputs · interfaces · storage · scalability · failure modes · extensibility.

---

### L1 — Repository Ingestion

**Responsibilities.** Acquire repository content at a specified commit. Resolve refs to commit SHAs. Enumerate and classify files. Compute content-addressed identity for every file unit. Detect changes between commits. Emit ingestion events. **It does not parse.**

**Inputs.** Repository URL or path; ref (branch/tag/SHA); credentials; optional webhook event.
**Outputs.** `CommitManifest { repo_id, commit_sha, parent_shas, tree: [FileUnit{path, blob_sha, content_hash, language, size, mode}] }`; `ChangeSet { added, modified, deleted, renamed }` relative to a base commit; `FileContent` addressable by `content_hash`.

**Interfaces**
```
resolve_ref(repo, ref)                 -> CommitRef
fetch_commit(repo, sha)                -> CommitManifest
diff(repo, base_sha, head_sha)         -> ChangeSet
read_unit(content_hash)                -> bytes
list_commits(repo, range)              -> [CommitRef]
```

**Storage.** Bare git mirrors on a shared volume or object store (the working copy is a cache, never a source of truth). File content in a content-addressed blob store keyed by `content_hash` — deduplicated globally, so a file unchanged across 500 commits is stored once. Manifests in relational storage.

**Design decision: content-addressing at the file-unit level.** The unit of index reuse is `(content_hash, language, extractor_version)`. Consequences: a file identical in two branches is parsed once; a file unchanged across commits is never reparsed; a renamed file is not reparsed. Rename detection becomes a manifest concern only. **This one decision is what makes G3 (incrementality) achievable rather than aspirational** — incrementality falls out of the identity scheme instead of being bolted on as change-tracking logic.

**Scalability.** Shard by repository. Shallow and partial clones; blob filtering for large binaries. Object-store blob backend scales independently of compute. Concurrency limits per upstream host to avoid rate limits.

**Failure modes**

| Failure | Handling |
|---|---|
| Upstream unreachable | Retry with backoff; serve last-known-good index; mark freshness lag |
| Auth expired | Fail fast, actionable error, mark repo `degraded`, notify |
| Repository too large | Reject at admission with a stated limit — never partially ingest silently |
| Force-push / history rewrite | Old commits remain valid and immutable; branch head repointed; orphaned commits eligible for eviction |
| Corrupt or binary-as-text file | Classify `unparseable`, record reason, continue. **Never fail a build for one bad file** |
| Submodules | Ingest as separate repositories, link via cross-repo edge. Never inline |

**Extensibility.** VCS provider plugin (git first; Mercurial/Perforce possible). Language classification is table-driven. Webhook adapters per forge.

---

### L2 — Parser Layer

**Responsibilities.** Convert file content into syntactic facts. Two tiers, deliberately separated.

```
TIER A — BREADTH (tree-sitter)          TIER B — PRECISION (SCIP / LSP / compiler)
  every supported language                a subset of languages
  syntax only                             resolved semantics
  no cross-file knowledge                 cross-file monikers, types
  fast, incremental, error-tolerant       slower, needs build context
  ⇒ method: heuristic                     ⇒ method: exact
```

**Rationale for two tiers.** Tier A gives immediate, cheap, universal coverage; Tier B gives the precision that makes results actionable. They are complementary, not sequential alternatives, and a file may have both. The resolution layer (L3) merges them with Tier B always winning. **We MUST NOT let Tier A results masquerade as Tier B** — that is the exact failure the confidence model exists to prevent.

**Inputs.** `FileUnit` + content; language; optional build context (dependency manifests, lockfiles, compiler config) for Tier B.
**Outputs.** `ParseResult { unit_id, extractor, extractor_version, symbols[], import_stmts[], call_sites[], spans[], errors[] }` — all positions as byte offsets plus line/column; all symbols with local scope paths.

**Interfaces**
```
parse(unit, language)                  -> ParseResult          # Tier A
index_project(repo, commit, language)  -> [ScipDocument]       # Tier B
capabilities()                         -> {language: {tier, relations, precision}}
```

**Storage.** `ParseResult` keyed by `(content_hash, extractor, extractor_version)` in the derived store — disposable and fully reconstructible. Tier B outputs stored as normalized documents keyed by `(repo, commit, language, indexer_version)`.

**Design decision: tree-sitter queries, never manual tree walks.** Queries are declarative, versionable, testable against fixtures, and reviewable by language experts. Hand-rolled child traversal cannot see nested, conditional, or decorated constructs without ad-hoc special cases and silently under-extracts — a defect class that is invisible until precision is measured.

**Scalability.** Embarrassingly parallel across file units. Cache hit rate on `content_hash` is the dominant performance lever; expect >95% on incremental builds. Tier B is per-project and expensive — scheduled less frequently, on merge commits and release tags rather than every push.

**Failure modes**

| Failure | Handling |
|---|---|
| Syntax error | Tree-sitter is error-tolerant: extract what parses, record error spans, label affected symbols lower confidence |
| Unsupported language | Emit `FileUnit` with `language=unknown`; still available for text search; excluded from structural claims |
| Tier B indexer fails (no build, missing deps) | Fall back to Tier A **with explicit `method` downgrade** (P11). Record and surface the reason |
| Extractor version bump | Cache key changes ⇒ automatic reparse. No manual invalidation, ever |
| Grammar crash / pathological input | Sandbox with timeout and memory cap; mark unit `unparseable`; continue |

**Extensibility.** A language is a plugin declaring: grammar, query set, extension mapping, optional Tier B indexer command, and a **precision claim that MUST be backed by a committed fixture-based test suite**. No language ships without a measured precision claim (P8).

---

### L3 — Semantic Resolution Layer

★ **The most important layer in the system.** It is the difference between advisory and actionable, and it is the layer the previous architecture omitted entirely.

**Responsibilities.** Turn syntactic references into bound references. Assign globally stable identity to symbols (monikers). Resolve imports to definitions. Resolve call sites to callees, using type information where available. Merge Tier A and Tier B, preferring exact. Attach `method` and `confidence` to every produced relation. Detect and record ambiguity explicitly rather than picking arbitrarily.

**Inputs.** `ParseResult` set for a commit; Tier B indexer output; dependency manifests; language-specific resolution rules; framework descriptors (for entry-point and DI-aware resolution).
**Outputs.**
```
Symbol   { moniker, kind, name, container, file_unit, span, signature,
           visibility, language, provenance, confidence }
Relation { src_moniker, dst_moniker, kind, span,
           method: exact|inferred|heuristic, confidence, provenance }
Ambiguity{ src, candidates[], reason }        # first-class, never silently collapsed
```

**Interfaces**
```
resolve_commit(repo, commit)                     -> ResolutionSet
resolve_symbol(repo, commit, name|moniker, ctx)  -> [Symbol] + confidence
resolve_reference(repo, commit, span)            -> Symbol | Ambiguity
moniker_for(symbol)                              -> stable global id
precision_report(language)                       -> measured P/R by relation kind
```

**Storage.** Symbols and relations as normalized rows in the facts store, keyed by `(repo, commit, moniker)`. Immutable once written. Ambiguities stored alongside, never discarded.

**Design decision: monikers, not file-path-plus-name.** A moniker is a stable, scheme-qualified identity (`python:mypkg.module.Class#method`) that survives file moves and is comparable across commits and — critically — across repositories. Path-based identity breaks on every rename and makes cross-repo joins impossible. Monikers are what make evolution tracking and cross-repo topology feasible at all.

**Design decision: ambiguity is data, not an error.** When `x.process()` has 14 candidate callees, the system records 14 candidates with distributed confidence rather than choosing one. Consumers then decide: an agent performing a mutation filters to `method=exact`; a human exploring accepts candidates. **Arbitrary disambiguation is the single largest hidden source of wrong answers in code-intelligence systems**, and it is invisible precisely because it looks like an answer.

**Scalability.** Resolution is per-commit but incremental: only symbols in changed units, plus units whose resolution *depended on* changed units, need recomputation. This requires a **reverse dependency index** (`unit → units whose resolution consumed it`), maintained as a first-class artifact. Without it, any change forces whole-repo re-resolution and G3 is unreachable.

**Failure modes**

| Failure | Handling |
|---|---|
| Dynamic dispatch unresolvable | Emit candidate set with confidence; never guess |
| Reflection / metaprogramming | Structurally invisible. Record a coverage gap; framework descriptors mitigate common cases |
| Missing external dependency | Resolve to an `external` symbol stub with a package coordinate; do not fail |
| Circular imports | Fixed-point iteration with a bounded iteration cap |
| Conflicting Tier A / Tier B results | Tier B wins; conflict logged as a precision signal and fed to the eval harness |
| Resolution timeout at scale | Degrade to Tier A for the remainder, label everything affected, surface partial-resolution status |

**Extensibility.** Per-language resolution plugins. Framework descriptors as declarative data (`framework: fastapi` ⇒ decorated functions are entry points; `framework: spring` ⇒ annotated beans are DI-wired). Framework descriptors are the highest-leverage extensibility point in the system: they convert a whole class of static-analysis blindness into a data-file contribution.

---

### L4 — Knowledge Graph

**Responsibilities.** Maintain one unified entity-relation model over resolved symbols, files, modules, and packages. Serve traversal: neighbors, paths, reachability, transitive closure, cycles, centrality. Project specialized views (dependency, call, module, architecture) from the single underlying graph.

**Design decision: one graph, many projections.** Not seven separate graph objects. A "call graph" is `edges WHERE kind='calls'`; a "dependency graph" is `edges WHERE kind='imports'` lifted to file granularity; an "architecture graph" is the module graph aggregated by declared layer. Maintaining seven independent structures guarantees divergence, multiplies update cost by seven, and violates P1. The prior architecture built a "knowledge graph" and a "dependency graph" as separate subsystems and they could not be joined — a direct consequence of this mistake.

**Inputs.** `ResolutionSet` per commit; module/package declarations; architecture rules from configuration.
**Outputs.** Node and edge sets; traversal results (paths, reachable sets, cycles); computed metrics (centrality, fan-in/out, instability, cycle depth) — metrics stored as *derived*, never as facts.

**Interfaces**
```
neighbors(node, direction, kinds, depth, min_confidence)  -> [Node]
paths(src, dst, max_depth)                                -> [Path]
reachable(roots, direction, kinds, limit)                 -> ReachableSet
cycles(scope)                                             -> [Cycle]
subgraph(seeds, depth, kinds)                             -> Subgraph
metrics(scope)                                            -> MetricSet
```

Note `min_confidence` on traversal. **Confidence filtering must be available at query time, not fixed at write time** — the same graph serves an agent needing certainty and a human wanting leads.

**Storage.** Adjacency in relational tables, not an in-memory graph library and not (initially) a dedicated graph database:

```
nodes(repo_id, commit_id, node_id PK, kind, moniker, file_unit, span, attrs)
edges(repo_id, commit_id, src_id, dst_id, kind, method, confidence, span, provenance)
  INDEX (repo, commit, src_id, kind)      -- forward traversal
  INDEX (repo, commit, dst_id, kind)      -- reverse traversal
  INDEX (repo, commit, moniker)           -- symbol lookup
```

Justification for relational over a graph database, stated as a trade-off: our workload is dominated by bounded-depth neighborhood queries (depth 1–4) and reachability with early termination, not by deep unbounded pattern matching. Two covering indexes serve bounded traversal at target latency. In exchange we get transactions, mature operations, straightforward multi-tenancy, cheap joins to non-graph facets — the multi-facet joins of PRD §6.2 are *ordinary SQL joins* in this model and would be federation problems in a graph DB — and no additional system to run. **Revisit if measured p95 for depth ≥5 traversal exceeds budget; the query interface is deliberately storage-agnostic so this remains a swap, not a rewrite.**

**Scalability.** Partition by `(repo_id, commit_id)`. Bounded-depth traversal with hard limits and early termination — every traversal API takes a `limit` and MUST return `truncated: true` rather than running long. Precomputed transitive closure for the small set of hot roots (entry points, public API symbols). Never load a full graph into a process; all traversal is index-driven and streaming.

**Failure modes**

| Failure | Handling |
|---|---|
| Traversal explosion (hub node, 10⁵ edges) | Hard `limit` + `truncated` flag. **Truncation MUST be reported, never silent** |
| Cycle in a "DAG" assumption | All traversal is cycle-safe by construction (visited set) |
| Missing node referenced by an edge | Referential integrity enforced at write; dangling edges rejected at ingest |
| Confidence-filtered graph becomes disconnected | Return partial result with an explicit coverage statement |

**Extensibility.** New edge kinds are additive rows — no schema migration. New metrics are derived computations. New projections are query definitions, not new stores.

---

### L5 — Repository Digital Twin

Fully specified in `03-DIGITAL-TWIN-SPEC.md`. Summarized here for layer completeness.

**Responsibilities.** Assemble the multi-facet, commit-scoped view. Provide twin-level operations: `get`, `diff`, `project`. Own materialization and cache policy. Guarantee internal consistency — every component of a returned twin describes the same commit.

**Inputs.** Graph + resolution facts, history facet, runtime facet, intent facet, social facet, all at one commit.
**Outputs.** `Twin@commit` (assembled, possibly partial with explicit facet availability); `TwinDiff(c1, c2)`.

**Interfaces**
```
get_twin(repo, commit, facets[], depth)  -> Twin
diff_twins(repo, c1, c2, facets[])       -> TwinDiff
project(twin, view)                      -> ProjectedView
facet_status(repo, commit)               -> {facet: available|stale|absent}
```

**Storage.** Twins are **not** stored as monolithic blobs. A twin is a *lazy, cached composition over facet stores*, materialized per-facet-per-commit with structural sharing. Storing whole-twin snapshots would multiply storage by commit count and make partial invalidation impossible.

**Failure modes.** Facet unavailable ⇒ return twin with `facet_status` marking absence; **never fabricate and never silently omit**. Requested commit not indexed ⇒ return nearest indexed ancestor with an explicit `staleness` field, or reject if the caller requires exactness. Partial materialization ⇒ complete on demand, or serve partial with a coverage statement.

**Extensibility.** A new facet registers with the twin assembler; existing consumers are unaffected because facet selection is explicit in every request.

---

### L6 — Engineering Memory

**Responsibilities.** Everything cross-commit. Maintain the timeline of twins. Track entity lifetimes (when a symbol appeared, moved, changed signature, disappeared). Compute evolution metrics and trends. Store decisions and their outcomes. Provide durable per-repository working memory for agents across sessions and vendors.

**Design decision: memory is a peer of structure, not a child of it.** History is not an attribute of the current snapshot; the snapshot is one frame of the history. Modeling it as `Twin.history` makes the more valuable asset subordinate to the less valuable one and guarantees underinvestment. The correct model is `Timeline<Twin>` — the twin is a projection of the timeline at an instant.

**Inputs.** Commit sequence; twin at each indexed commit; git metadata; incident and deployment feeds; recorded decisions.
**Outputs.** `EntityLifetime`; `EvolutionMetric` time series; `Trend { slope, volatility, confidence }`; `DecisionRecord`; `AgentMemoryEntry`.

**Interfaces**
```
timeline(repo, entity, range)             -> [LifetimeEvent]
evolution(repo, metric, range, scope)     -> TimeSeries
trend(repo, metric, window)               -> Trend
twin_at(repo, timestamp|commit)           -> Twin
decisions_for(repo, scope)                -> [DecisionRecord]
agent_memory(repo, namespace)             -> [MemoryEntry]      # read/write
```

**Storage.** Append-only event log for lifetime events (immutable facts). Time-series storage for metrics (derived, recomputable). Relational for decisions. Retention differs sharply by kind: **lifetime events are kept forever because they are unrecoverable after upstream history rewrites; metric series are freely evictable because they are recomputable from facts.** This distinction is the retention policy.

**Scalability.** Metrics are downsampled at increasing age (daily → weekly → monthly). Lifetime events are compacted by entity, not deleted. Snapshot cadence is policy-driven: every commit on the default branch, merge commits only on other branches, with a configurable ceiling.

**Failure modes.** History rewrite upstream ⇒ affected commits marked orphaned; **derived series recomputed, lifetime events retained with an orphan marker** (deleting them would silently rewrite our own history). Gaps from unindexed periods ⇒ marked explicitly in the series; never interpolated. Trend computed on insufficient data ⇒ returned with low `confidence`, never suppressed silently.

**Extensibility.** New metrics register as derived computations over facts and backfill automatically. New event kinds are additive.

---

### L7 — Reasoning Engine

**The first layer permitted to call a language model.** Everything below is deterministic.

**Responsibilities.** Interpret natural-language intent. Plan retrieval. Drive a tool-calling loop against L8. Assemble context under a token budget. Orchestrate versioned prompts. **Verify every citation before emitting.** Produce answers with attribution. Feed evaluation.

**Inputs.** Natural-language question; repository and commit scope; conversation and agent memory; available tools (which are exactly the L8 query primitives).
**Outputs.** `Answer { text, citations[{moniker|file, span, commit}], confidence, tools_used[], tokens, latency }`.

**Interfaces**
```
answer(question, scope, budget, memory)  -> Answer          (streaming)
plan(question, scope)                    -> RetrievalPlan
assemble(refs, budget)                   -> Context
verify(answer, scope)                    -> VerificationResult
```

**Design decision: tool-calling loop, not fixed pre-fetch.**

```
REJECTED (pre-fetch)                    ADOPTED (tool loop)
question                                question
  ├─ classify intent                      ├─ model receives tool catalog
  ├─ retrieve everything up front         ├─ model queries what it needs
  ├─ pack a fixed blob                    ├─ follows leads iteratively
  └─ one LLM shot                         ├─ bounded iterations + budget
                                          └─ stops when sufficient
Failure: if retrieval missed the         Property: recoverable. The model
relevant file, the answer is wrong       can discover what no classifier
and nothing can recover it.              anticipated.
```

Pre-fetch was the prior architecture's shape and it has an unrecoverable failure mode. The tool loop costs latency and tokens; we buy those back with aggressive caching, deterministic fast paths for exact-answerable questions (P2 — many questions never reach the model at all), and hard iteration bounds.

**Design decision: hybrid seeding.** Graph traversal needs seeds. Rule-based entity extraction from the question produces excellent seeds for symbol-shaped questions and *nothing* for diffuse ones — at which point a graph-first retriever silently collapses to plain vector search, which is exactly the failure mode our thesis criticizes. Correct design: embed the question, retrieve candidate chunks, use *their resolved symbols* as seeds, expand via graph. **Vector search for seeding; graph for expansion.** Neither alone.

**Design decision: citation verification is mandatory and non-bypassable.** Before an answer is emitted, every cited span MUST be confirmed to exist at the queried commit. A citation to a nonexistent location is worse than no citation because it manufactures false confidence. This check is deterministic, cheap, and belongs in the emit path — not in a post-hoc evaluation job.

**Storage.** Prompts in a versioned registry (prompt version is part of every answer's provenance). Conversation state ephemeral with TTL. Agent memory durable in L6. LLM response cache keyed by `(prompt_version, model, context_hash)` — absent from the prior system and a straightforward large cost win.

**Failure modes.** Provider unavailable ⇒ circuit breaker, failover with the streaming-safety invariant (retry only if zero tokens emitted; never after partial output). All providers unavailable ⇒ **deterministic structured response from the twin with no prose** — degraded but honest and still useful, because most of the value is deterministic anyway. Tool loop non-convergence ⇒ iteration cap, return best-effort with a partial marker. Citation verification failure ⇒ strip the citation and lower stated confidence; **never emit an unverified citation.** Budget exhaustion ⇒ return what fits with an explicit truncation notice.

**Extensibility.** Providers, prompts, and tools are all registries. Adding a query primitive to L8 automatically expands the tool catalog — the reasoning layer gains capability without modification.

---

### L8 — Query Gateway

**Responsibilities.** The single entry point to everything. Contract versioning. Authentication, authorization, tenancy scoping. Quota and rate limiting. Cache orchestration. Pagination and deterministic ordering. Latency budget enforcement. Audit logging. Response shaping per protocol (REST, GraphQL, MCP).

**Design decision: one gateway, many protocols.** MCP, REST, and GraphQL are transport adapters over one internal query contract. This guarantees agents and humans get identical semantics — and prevents the drift that occurs when an agent interface is added later as a separate path.

**Interfaces.** The ~20 query primitives of the Twin Specification §7, plus:
```
capabilities(repo)     -> supported languages, facets, measured precision
index_status(repo)     -> freshness, coverage, degradation, last commit
```
`capabilities` and `index_status` are first-class product surface, not diagnostics. A consumer MUST be able to ask "how much of this repository do you actually understand, and how well" before trusting an answer. No competitor exposes this; it is a direct expression of P4 and P11.

**Storage.** Stateless. Cache in a shared store keyed by `(tenant, repo, commit, query, params, schema_version)`. Because facts are immutable per commit, **cache entries never require invalidation — they expire only by eviction.** This is a significant simplification that falls directly out of commit-addressing.

**Scalability.** Fully stateless ⇒ horizontal scaling behind a load balancer. Read replicas for the facts store. Cache hit rates should be high for agent workloads (repeated queries against a stable commit).

**Failure modes.** Downstream layer failure ⇒ typed error identifying the failed layer and whether a retry is meaningful. Quota exceeded ⇒ 429 with reset time. Query too expensive ⇒ reject at admission with a cost estimate rather than accepting and timing out. Cache unavailable ⇒ serve from source, degraded latency, alert.

**Extensibility.** New protocol = new adapter. New primitive = one registration, available across all protocols simultaneously.

---

### L9 — Applications

**Responsibilities.** Consume L8. Nothing else. Every application — our MCP server, CLI, web UI, IDE clients, CI integrations, and reference chat — is an ordinary API client with no privileged path.

**Enforcement.** Applications live in separate modules that MUST NOT import from L1–L7. CI-checked. This is P7 made structural: if a UI feature cannot be built from public API calls, the API is incomplete and we fix the API.

---

## 4. Subsystem Catalogue

| Subsystem | Layer | Responsibility | Key decision |
|---|:--:|---|---|
| **Repository Manager** | L1 | Registration, credentials, refs, clone lifecycle, admission limits | Git is the system of record; working copies are caches |
| **Change Detector** | L1 | Content-hash diffing, rename detection, reverse-dependency fan-out | Fan-out via reverse dependency index, not whole-repo rescan |
| **Parser Engine** | L2 | Tier A/B extraction, versioned cache | Queries not tree walks; version in cache key |
| **Symbol Resolver** | L3 | Monikers, binding, ambiguity, confidence | Ambiguity is data; Tier B wins merges |
| **Dependency Engine** | L4 | Import/module edges, cycles, layering | Projection of the unified graph |
| **Call Graph Engine** | L4 | Call edges, closure, blast radius | Confidence-filterable at query time |
| **Knowledge Graph Builder** | L4 | Unified node/edge materialization | One graph, many projections |
| **Twin Builder** | L5 | Facet assembly, diffing, materialization policy | Lazy composition, not stored blobs |
| **Repository Memory** | L6 | Timeline, lifetimes, evolution, decisions, agent memory | Peer of structure, not child |
| **Retrieval Engine** | L7 | Hybrid seed + graph expansion, ranking | Vector seeds, graph expansion |
| **Context Builder** | L7 | Real tokenization, knapsack packing under budget | Greedy packing, never break-on-first-overflow |
| **Prompt Orchestrator** | L7 | Versioned prompts, A/B, provider routing | Prompt version in answer provenance |
| **Reasoning Engine** | L7 | Tool loop, citation verification | Verification non-bypassable |
| **Evaluation Engine** | X | Benchmarks, regression gates, precision reports | Blocks releases; not a test folder |
| **Job Orchestrator** | X | Durable queue, workers, idempotency, retry, cancel, priority | Every task idempotent and resumable |
| **Monitoring** | X | Metrics, traces, logs, alerts, SLOs | Per-query-class latency SLOs |
| **Workspace Manager** | L8/L9 | Per-user/agent scope, active repo, pinned commit, preferences | Session state only; never index state |
| **Control Plane** | X | Tenancy, authz, quota, policy, billing | Present from day one, even single-tenant |
| **Plugin Registry** | X | Languages, frameworks, facets, analyzers | Declarative manifests with mandatory precision tests |

---

## 5. Data Flow

### 5.1 Ingestion (write path)

```
webhook / schedule / manual
        │
        ▼
┌──────────────────┐   enqueue(IndexCommit{repo, sha})   ┌───────────────┐
│  Repository Mgr  │ ──────────────────────────────────▶ │  Job Queue    │
└──────────────────┘                                     └───────┬───────┘
                                                                 │
                        ┌────────────────────────────────────────┘
                        ▼
                 ┌─────────────┐
                 │   Worker    │
                 └──────┬──────┘
                        │
   1. fetch commit ─────┤──▶ CommitManifest + FileUnits (content-addressed)
   2. diff base ────────┤──▶ ChangeSet
   3. fan-out ──────────┤──▶ affected units = changed ∪ reverse_deps(changed)
   4. parse ────────────┤──▶ ParseResult      [cache: content_hash+extractor_ver]
   5. resolve ──────────┤──▶ Symbols, Relations, Ambiguities  (+method+confidence)
   6. graph upsert ─────┤──▶ nodes/edges @commit
   7. facets ───────────┤──▶ history · social · runtime · intent
   8. derived ──────────┤──▶ metrics, projections, embeddings
   9. commit txn ───────┤──▶ mark commit QUERYABLE   ◀── atomic visibility
  10. emit events ──────┴──▶ CommitIndexed{repo, sha, stats, coverage}
                        │
                        ▼
              ┌───────────────────┐
              │  Event Bus        │──▶ eval · monitoring · CI gate · webhooks
              └───────────────────┘
```

**Critical property — atomic visibility (step 9).** A commit is invisible to queries until fully indexed, then becomes visible atomically. There is no intermediate state in which a consumer observes a half-built index. Partial-visibility is the most insidious correctness bug available in this class of system: it produces answers that are wrong in ways indistinguishable from right.

### 5.2 Agent query (read path)

```
Agent ──MCP──▶ Query Gateway
                    │ authz · quota · cache lookup
                    │  ├── HIT  ──────────────────────────────────▶ response
                    │  └── MISS
                    ▼
              deterministic?
              ├── YES ──▶ Twin/Graph/Resolution ──▶ response   [no LLM · <200ms]
              └── NO  ──▶ Reasoning Engine
                              │
                              ├──▶ plan retrieval
                              ├──▶ tool loop ──┐
                              │   (bounded)    │ calls back through Gateway
                              │                │ ◀── same primitives, no bypass
                              ├──▶ assemble context under budget
                              ├──▶ LLM (streaming)
                              ├──▶ verify citations  ◀── mandatory
                              └──▶ response + provenance
```

Note that the reasoning layer's tool calls re-enter through the Gateway. This is deliberate: it means reasoning is subject to the same authorization, quota, caching, and audit as any external consumer, and it makes the tool catalog and the public API identical by construction.

### 5.3 Sequence — incremental index of a 3-file change

```
Webhook  Gateway  Queue   Worker   Blob   Parser  Resolver  Graph   Bus
   │        │       │        │       │       │       │        │      │
   │─push──▶│       │        │       │       │       │        │      │
   │        │─enq──▶│        │       │       │       │        │      │
   │        │       │──job──▶│       │       │       │        │      │
   │        │       │        │─fetch▶│       │       │        │      │
   │        │       │        │◀─3 changed units─────────────────────│
   │        │       │        │  reverse_deps(3) = 11 units          │
   │        │       │        │───parse 14──────▶│  (12 cache hits)  │
   │        │       │        │◀──ParseResult────│                   │
   │        │       │        │───resolve 14─────────────▶│          │
   │        │       │        │◀──symbols+relations+conf──│          │
   │        │       │        │───upsert @sha───────────────────────▶│
   │        │       │        │───copy-on-write unchanged nodes─────▶│
   │        │       │        │───mark QUERYABLE (atomic)───────────▶│
   │        │       │        │───CommitIndexed────────────────────────────▶│
   │        │       │        │                                            ├─▶ eval
   │        │       │        │                                            ├─▶ CI gate
   │        │       │        │                                            └─▶ metrics
   └────────┴───────┴────────┴──── target: p95 < 2s ─────────────────────────────┘
```

The 2-second target is achievable only because of three compounding decisions: content-addressed parse caching (12 of 14 units are cache hits), the reverse dependency index (11 affected units instead of the whole repository), and copy-on-write structural sharing (unchanged graph nodes are referenced, not rewritten).

### 5.4 Event flow

```
DOMAIN EVENTS (durable, ordered per repo, replayable)

RepositoryRegistered · CommitIndexed · IndexFailed · ResolutionDegraded
SymbolAdded/Moved/Removed/SignatureChanged · EdgeAdded/Removed
CycleIntroduced · LayerViolationDetected · PublicAPIBroken
TwinMaterialized · TrendThresholdCrossed · PrecisionRegressed

CONSUMERS
  Evaluation Engine ─── regression detection
  CI Gate ──────────── merge checks
  Memory ───────────── lifetime event log
  Monitoring ───────── SLO tracking
  Webhooks ─────────── customer integrations
  Cache ────────────── warm popular commits
```

Events are durable and replayable, which makes them the mechanism for adding new derived consumers retroactively: a facet or metric introduced in year three can be backfilled by replaying the log rather than reindexing history.

### 5.5 Caching strategy

| Tier | Contents | Key | Invalidation |
|:--:|---|---|---|
| L0 | Parse results | `content_hash + extractor_version` | Never (content-addressed) |
| L1 | Resolution sets | `repo + commit + resolver_version` | Never (commit-immutable) |
| L2 | Graph query results | `repo + commit + query + params` | Never — **eviction only** |
| L3 | Materialized twins/facets | `repo + commit + facet` | Eviction by LRU + age |
| L4 | Embeddings | `content_hash + model_version` | Never |
| L5 | LLM responses | `prompt_ver + model + context_hash` | TTL |
| L6 | Derived metrics | `repo + commit + metric + algo_version` | On algorithm version bump |

**The single most valuable consequence of commit-addressing:** because facts about a commit never change, almost nothing requires invalidation. Cache invalidation — normally the hardest correctness problem in a system like this — is reduced to an eviction policy. Every cache key includes the producing component's version, so upgrading a component invalidates exactly its own outputs automatically and nothing else.

---

## 6. Deployment Architecture

### 6.1 Modular monolith first — with predefined seams

**Decision: start as a modular monolith with strictly enforced internal boundaries; extract services only against measured pressure.**

Justification. At current scale, microservices would add network latency to the hot path (violating G4), distributed-transaction complexity around atomic visibility, operational burden disproportionate to team size, and — most importantly — they would freeze boundaries we do not yet understand well enough to freeze. The monolith gives in-process call latency, transactional consistency for the visibility guarantee, and cheap boundary refactoring. **The risk of a monolith is boundary erosion, and that risk is mitigated by CI-enforced import rules rather than by network calls.** Using process boundaries to enforce module discipline is paying a permanent latency and complexity tax for a problem that static analysis solves for free.

Predefined extraction seams, in priority order with explicit triggers:

```
┌─────────────────────────────────────────────────────────────┐
│                    MODULAR MONOLITH                         │
│                                                             │
│  ╔═══════════════════╗   ← SEAM 1: Indexing Workers        │
│  ║ ingest·parse·     ║     trigger: CPU-bound scaling       │
│  ║ resolve·graph     ║     needs differ from query serving  │
│  ╚═══════════════════╝                                      │
│  ╔═══════════════════╗   ← SEAM 2: Query Service            │
│  ║ twin·memory·      ║     trigger: read scaling; needs     │
│  ║ graph query·gw    ║     independent replicas             │
│  ╚═══════════════════╝                                      │
│  ╔═══════════════════╗   ← SEAM 3: Reasoning Service        │
│  ║ reasoning·LLM     ║     trigger: different failure       │
│  ╚═══════════════════╝     domain, latency, cost profile    │
│  ╔═══════════════════╗   ← SEAM 4: Control Plane            │
│  ║ tenancy·authz·    ║     trigger: multi-region or         │
│  ║ quota·billing     ║     compliance isolation             │
│  ╚═══════════════════╝                                      │
└─────────────────────────────────────────────────────────────┘

Extraction rule: extract when a measured scaling, failure-isolation, or
compliance need exists. Never because a diagram looks better.
```

Seam 1 (indexing workers) is the earliest extraction because indexing and querying have genuinely divergent resource profiles — CPU-heavy batch versus latency-sensitive reads — and because worker crashes must not affect query availability.

### 6.2 Storage architecture

```
┌───────────────────────────────────────────────────────────────┐
│ FACTS STORE (durable, immutable, append-only)                 │
│   PostgreSQL │ commits · manifests · symbols · relations       │
│              │ nodes · edges · lifetime events · decisions     │
│   partitioned by (repo_id, commit_id) · read replicas          │
│   ── the only store whose loss is unrecoverable ──             │
├───────────────────────────────────────────────────────────────┤
│ BLOB STORE (content-addressed, immutable)                      │
│   S3-compatible │ file contents · SCIP documents · artifacts    │
│   keyed by content_hash · globally deduplicated                │
├───────────────────────────────────────────────────────────────┤
│ DERIVED STORE (disposable, fully reconstructible)              │
│   PostgreSQL │ metrics · projections · materialized facets      │
│   Vector DB  │ embeddings (keyed by content_hash)               │
│   ── may be dropped entirely and rebuilt from facts ──         │
├───────────────────────────────────────────────────────────────┤
│ CACHE + QUEUE (ephemeral)                                      │
│   Redis │ query cache · job queue · rate limits · sessions      │
├───────────────────────────────────────────────────────────────┤
│ GIT MIRRORS (cache of upstream truth)                          │
│   shared volume │ bare repositories                             │
└───────────────────────────────────────────────────────────────┘
```

**The facts/derived split is an operational capability, not a taxonomy.** It means: derived storage can be dropped to recover disk without data loss; algorithm changes trigger a rebuild rather than a migration; backup policy differs by store (facts continuously, derived never); and disaster recovery has one clear objective — restore facts, rebuild the rest.

**Why PostgreSQL as the spine.** Transactions for atomic visibility; partitioning for repo/commit isolation; mature replication and operations; `pgvector` as a viable embedding store, removing a system; and — decisively — **the multi-facet joins that constitute our unique capability are ordinary SQL joins here, where in a polyglot or graph-native design they would be cross-system federation problems.** Trade-off accepted: less expressive deep graph traversal than a native graph database. Mitigated by our workload being bounded-depth, by covering indexes, and by the query interface being storage-agnostic so a targeted swap remains possible.

### 6.3 Scaling model

| Axis | Mechanism |
|---|---|
| Repositories | Shard by `repo_id`. No cross-repo transactions except explicit topology edges |
| Repository size | Partition by commit; bounded traversal; no whole-graph loads |
| Commits | Structural sharing; snapshot cadence policy; age-based eviction |
| Query volume | Stateless gateway + horizontal replicas + read replicas + cache |
| Index throughput | Worker pool, autoscaled by queue depth; per-file parallelism |
| Languages | Independent plugins; parallel per-language indexing |
| Tenants | Row-level isolation with `tenant_id`; separate databases for enterprise |

**Capacity model for a 10M LOC repository** (design sizing, to be validated in Phase 3):

```
files              ~100k          symbols        ~10M
edges              ~100M          nodes+edges    ~30 GB / commit (naive)
                                  with sharing   ~50 MB / incremental commit
cold index         ~2-4 h (parallel workers)
incremental        <2 s (≤10 files)
query p95          <200 ms (bounded depth, covering indexes)
```

The 600× gap between naive per-commit storage and incremental storage is the entire justification for structural sharing. Without it, per-commit materialization is economically impossible and the commit-addressing requirement collapses.

---

## 7. Architecture Principles — Evaluated

The brief asks whether each named paradigm is appropriate. Assessed individually; several are rejected.

| Paradigm | Verdict | Reasoning |
|---|:--:|---|
| **SOLID** | **Adopt** | SRP and DIP are the two the prior architecture violated most damagingly — a router that cloned, parsed, embedded, graphed, and persisted; domain modules importing delivery modules. DIP is enforced here by the CI-checked import rule of §2.3. ISP matters for the query contract: narrow, purpose-specific primitives beat one god-query |
| **Clean Architecture** | **Adopt, partially** | The dependency rule (inward only, domain independent of infrastructure) is exactly right and directly encoded in §2.3. Full ceremony — entities, use-cases, interactors, boundary DTOs at every crossing — is rejected: for a data-intensive system it produces mapping layers that add cost without insight. **Adopt the dependency rule; reject the ceremony** |
| **DDD** | **Adopt selectively** | Ubiquitous language is essential — *symbol*, *moniker*, *relation*, *facet*, *twin*, *commit* must mean one thing everywhere. Bounded contexts map naturally onto layers and the extraction seams. **Aggregates and rich domain entities are rejected**: our domain objects are large immutable fact sets, not behavior-bearing entities with invariants to protect. Forcing aggregates onto 10⁸ edges is a category error |
| **Hexagonal** | **Adopt** | The strongest fit in the list. Every external dependency is a port: VCS, language indexer, LLM provider, vector store, blob store, event bus. This is what makes P10 (buy language breadth) architecturally real — a new SCIP indexer is a new adapter, and swapping storage is an adapter change |
| **CQRS** | **Adopt** | Our read and write paths are already radically asymmetric: writes are batch, throughput-oriented, transactional, worker-driven; reads are latency-critical, high-volume, cacheable. They should scale, be modeled, and be deployed independently. **Event sourcing is rejected** — git is already the event log for source, and re-deriving current state from an event stream on every read is the wrong trade for our access pattern |
| **Event-driven** | **Adopt for integration; reject as the primary control flow** | Domain events (§5.4) are excellent for decoupling derived consumers, CI gates, evaluation, and customer webhooks, and they enable retroactive backfill via replay. But the ingestion pipeline itself MUST remain a synchronous, transactional pipeline per commit — the atomic visibility guarantee (§5.1) is not achievable if pipeline stages communicate only through eventual-consistency events |
| **Repository pattern** | **Adopt** | Data access behind interfaces per aggregate root. Enables the storage swap of §6.2 and makes layers testable without a database |
| **Pipeline architecture** | **Adopt — it is the core write-path shape** | Ingestion is genuinely a pipeline: clone → parse → resolve → graph → facets → derived. Explicit stages with declared inputs/outputs, resumability, and per-stage caching. The prior architecture had this correct in concept and implemented it twice, keeping the weaker one on the request path — the lesson is that **one pipeline implementation is mandatory** |
| **Plugin architecture** | **Adopt — critical** | Languages, frameworks, facets, analyzers. This is how the system reaches 20 languages without 20 core changes, and how framework-awareness becomes a community-contributable data file. Every plugin MUST ship a precision test suite (P8) |
| **Domain events** | **Adopt** | See event-driven. Note the discipline: `SymbolRemoved` is a domain event; `HTTP 200 returned` is not. Prior implementations emitted UI progress notifications and called them events — that conflation makes the event log useless for replay |
| **Bounded contexts** | **Adopt** | Contexts: Ingestion, Structure (parse/resolve/graph), Twin, Memory, Reasoning, Delivery, Control. Each owns its storage and publishes events. **These are exactly the microservice seams**, which is why the monolith can be split later without redesign |

### 7.1 Explicitly rejected patterns

| Rejected | Reason |
|---|---|
| Event sourcing as the primary store | Git is the source event log. Re-deriving state per read is wrong for our access pattern |
| Microservices from day one | Adds latency to the hot path, breaks atomic visibility, freezes boundaries prematurely |
| Full Clean Architecture ceremony | Mapping layers between identical shapes are cost without insight in a data-intensive system |
| DDD aggregates over graph data | Category error at 10⁸ edges |
| Graph database as the initial spine | Loses transactions and cheap cross-facet joins — which are our differentiator — to buy deep traversal we do not primarily need. Revisit on measured evidence |
| Shared mutable in-process state | The prior architecture's `ANALYSIS_STORE` singleton made multi-worker deployment incorrect: N workers, N divergent views, nondeterministic answers |
| LLM anywhere below L7 | Destroys determinism, testability, latency, and cost structure simultaneously |

---

## 8. Evaluation Framework

**Evaluation is a subsystem, not a test directory.** It gates releases. It produces the numbers that constitute our marketing. It is the mechanism by which P8 is enforceable rather than aspirational.

### 8.1 What is measured

| Dimension | Metric | Method | Target | Gate |
|---|---|---|---|:--:|
| **Symbol resolution** | precision / recall per language | Hand-labelled fixture corpora + LSP cross-validation | ≥0.95 / ≥0.90 | Blocking |
| **Call edges** | precision / recall; % `method=exact` | Fixtures + differential vs. Tier B indexers | ≥0.90 / ≥0.85; ≥80% exact | Blocking |
| **Import/dependency edges** | precision / recall | Fixtures; manifest cross-check | ≥0.98 / ≥0.95 | Blocking |
| **Retrieval** | recall@5/10/20, MRR, nDCG | **Issue→PR corpus (labels free from git)** | recall@10 ≥0.70 | Blocking |
| **Blast radius** | precision / recall vs. actual PR file sets | Historical PRs: predict from seed files, compare to merged reality | ≥0.75 / ≥0.80 | Blocking |
| **Architecture understanding** | agreement with expert-labelled module/layer assignment | Expert-labelled reference repositories | ≥0.80 agreement | Advisory |
| **Reasoning quality** | correctness, completeness, groundedness | LLM-as-judge with human-audited calibration subset | ≥0.85 | Advisory |
| **Citation validity** | % cited spans that exist and are relevant | Deterministic existence check + sampled relevance audit | ≥0.98 exists; ≥0.90 relevant | Blocking |
| **Latency** | p50/p95/p99 by query class | Continuous load test | p95 <200ms deterministic | Blocking |
| **Incrementality** | p95 index time by change size | Synthetic change replay over real history | <2s for ≤10 files | Blocking |
| **Cost** | $ per MLOC-month; $ per answered question | Infra + provider accounting | Tracked, budgeted | Advisory |
| **Token efficiency** | tokens per agent task vs. baseline | A/B against grep+embedding baseline | −70% | Blocking |
| **Memory** | RSS per worker; index bytes per MLOC | Profiling | No unbounded growth | Blocking |

### 8.2 The primary benchmark — issue→PR retrieval

The keystone insight of the entire evaluation framework:

> **For every merged pull request that closes an issue, the set of files that PR modified is ground truth for "which files are relevant to this issue."**

Labels are therefore free, abundant, in-domain, and continuously refreshed — no annotation budget, no synthetic tasks, no benchmark contamination. This corpus can be regenerated for any repository at any time.

```
Corpus construction
  for each repo in corpus_repos:
    for pr in merged_prs(repo) where pr closes exactly one issue:
      accept if 1 <= |pr.changed_files| <= 20        # excludes trivia and bulk churn
                and not pr.is_revert
                and not pr.is_dependency_bump
                and pr.diff is not purely formatting
      task = { query : issue.title + issue.body,
               commit: pr.base_sha,                  # index state BEFORE the fix
               truth : set(pr.changed_files) }

Arms compared (identical task set, identical budget)
  A  BM25 / lexical                      — floor
  B  embedding-only                       — the incumbent approach
  C  graph-only (seeds from entities)     — isolates the structural contribution
  D  hybrid: vector seeds + graph expand  — our design
  E  D + rerank                           — full system
  F  long-context: dump N files to model   — the real competitor

Reported per arm: recall@{5,10,20} · precision@10 · MRR · nDCG@10
                  context tokens · latency p95 · $ per task
```

Arm F is essential and uncomfortable: it measures us against the competitor that is actually improving. **A benchmark that omits the long-context baseline is a benchmark designed to flatter us.** Including F, and publishing when F wins on a repository class, is what makes the whole framework credible.

Corpus requirements: ≥15 repositories; ≥3 language families; sizes from 10k to 5M LOC; a mix of frameworks; at least 3 held out permanently as a test set never used for tuning.

### 8.3 Regression testing

```
Every commit to our code:
  unit + fixture precision tests (fast, <2 min)
  ↓
Every PR:
  full benchmark on a 3-repo subset
  BLOCK if any blocking metric regresses beyond noise threshold
  ↓
Nightly:
  full benchmark, all repos, all arms
  publish to a public dashboard
  ↓
Every release:
  all phase gates re-verified; precision report regenerated per language
  ↓
Continuous:
  shadow evaluation on live traffic; drift detection
```

**Noise threshold discipline.** Every metric has a measured run-to-run variance; regressions are flagged only beyond 2σ. Without this, blocking gates produce alert fatigue and are disabled within a month — which is how quality gates die everywhere.

### 8.4 Precision reporting as product surface

We publish, per language and per relation type, measured precision and recall — in the documentation, in the API (`capabilities()`), and in the UI. When precision for a language is poor, we say so and label its outputs accordingly.

The reasoning is strategic, not ethical. Every prior generation of code-intelligence tooling shipped unquantified accuracy, which trained the entire market to distrust the category. **Publishing measured precision — including where it is bad — is simultaneously the most differentiating and least copyable competitive move available, because copying it requires a competitor to disclose numbers they have never measured and may not like.** It also defines the axis of competition on our terms.

---

## 9. Architecture Decision Record

| # | Decision | Alternatives rejected | Trade-off accepted |
|:--:|---|---|---|
| **AD1** | Commit-addressed everything | HEAD-only index | Higher storage; mitigated by structural sharing. Buys branches, PR review, time-travel, and invalidation-free caching |
| **AD2** | Separate facts and derived stores | One store | Two backup/retention policies. Buys free algorithm iteration and disposable-derived recovery |
| **AD3** | Provenance + confidence on every relation | Bare edges | ~20% storage overhead. Buys honest degradation, agent-actionability, and measurable precision |
| **AD4** | Buy resolution via SCIP/LSP | Write our own resolvers | Dependency on external indexer quality and build context. Buys years of roadmap |
| **AD5** | Relational graph storage | Neo4j; in-memory NetworkX | Weaker deep traversal. Buys transactions, cheap cross-facet joins, operational simplicity |
| **AD6** | Modular monolith with enforced seams | Microservices | Boundary-erosion risk; mitigated by CI import rules. Buys latency and transactional visibility |
| **AD7** | Content-addressed file units | Path-based identity | Rename handling moves to manifests. Buys near-free incrementality and cross-branch dedup |
| **AD8** | Tool-calling loop over pre-fetch | Fixed retrieve-then-generate | Higher latency and token use. Buys recoverability from retrieval misses |
| **AD9** | Hard LLM boundary at L7 | LLM wherever convenient | Some features harder to build. Buys determinism, testability, cost, offline capability |
| **AD10** | One graph, many projections | Separate graph per view | Query-time projection cost. Buys consistency and 1/7 update cost |
| **AD11** | Ambiguity as first-class data | Pick best candidate | Consumers must handle candidate sets. Buys elimination of the largest silent-error class |
| **AD12** | Mandatory citation verification | Trust model output | Small latency cost on emit. Buys elimination of fabricated references |
| **AD13** | Atomic commit visibility | Incremental visibility | Slightly delayed freshness. Buys the absence of half-built-index answers |
| **AD14** | Publish measured precision | Marketing-safe vagueness | Public exposure of weaknesses. Buys credibility and control of the competitive axis |
| **AD15** | Plugin precision tests mandatory | Fast language additions | Slower breadth growth. Buys per-language precision that survives breadth pressure |

---

## 10. Risk Register

| # | Risk | L | I | Mitigation |
|:--:|---|:-:|:-:|---|
| R1 | Context economics erase the wedge | H | Sev | Own scale, transitive closure, cross-repo, history, latency. Include long-context arm F in every benchmark and watch it |
| R2 | External indexers insufficient for precision targets | M | Sev | Tiered fallback with honest labelling; contribute upstream; native indexers as last resort for top languages only |
| R3 | Per-commit storage economically unviable | M | H | Structural sharing; snapshot cadence policy; age eviction; derived-store disposability. Validate at Phase 3 |
| R4 | Query latency target unmet at 10M LOC | M | H | Bounded traversal; covering indexes; precomputed hot closures; storage-agnostic query interface preserves the swap option |
| R5 | Agent vendors build in-house instead of integrating | M | Sev | Open protocol; free tier; make our precision the thing they cannot match; publish benchmarks that make the build/buy math explicit |
| R6 | Complexity outruns capability (the prior failure, repeated) | M | H | P12; phase gates; every subsystem must be on a critical path or be deleted |
| R7 | Precision regresses under language-breadth pressure | H | H | Per-language blocking gates; AD15; no language ships without measured precision |
| R8 | Reverse dependency index becomes the bottleneck | M | M | Treat as a first-class artifact with its own benchmarks and incremental maintenance |
| R9 | Dead-code false positives destroy trust | H | H | Framework descriptors; runtime facet; **never present low-confidence reachability as actionable** |
| R10 | Evaluation gates become alert fatigue and get disabled | M | H | Noise thresholds at 2σ; gates on a small stable set; nightly for the rest |
