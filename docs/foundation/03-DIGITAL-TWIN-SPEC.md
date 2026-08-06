# Repository Digital Twin — Specification

**Product:** Repository Intelligence Agent
**Document status:** Foundation — normative. This is the most important document in the set.
**Version:** 2.0 (greenfield design)
**Companion documents:** `01-PRD.md`, `02-SDD.md`

> Every other document describes what we build and how we build it. This document defines *the thing itself*. If the Twin is wrong, everything downstream is wrong. The PRD can be revised on market feedback; the SDD can be revised on operational evidence; this specification changes only with strong cause, because every feature, API, and storage decision derives from it.

---

## 0. A necessary correction to the name

The brief asks for a "Repository Digital Twin" and asserts it should be the core of the platform. I am adopting the name and the centrality, and rejecting two things the name implies. Recording this explicitly, because unexamined metaphors become architecture.

**Rejection 1 — it is not a simulation.** In engineering, a digital twin is a live, bidirectionally-coupled model that *simulates* physical behavior and *predicts* it under hypothetical conditions. Our artifact does not simulate execution and cannot predict runtime behavior from structure alone. Adopting the full metaphor sets an expectation we will fail: the first sophisticated user will say "simulate this change and tell me the runtime effect," and the honest answer is no. What we build is a **materialized, versioned, multi-facet index** — closer to a data warehouse of a codebase than to a wind-tunnel model.

**Rejection 2 — structure is not the whole twin.** The brief's entity list is entirely structural. But structural facts are the *most* replicable part of this product: a funded competitor reproduces them in 18 months. The facets that cannot be replicated on demand — history, runtime behavior, recorded intent, human ownership — are absent from the brief's model. If the Twin is defined as "structure," the architecture will make every non-structural facet a second-class extension, and the durable advantage will never be built. **Structure is therefore one facet of five, and the Twin is the join across them.**

**What is retained.** The core instinct of the brief is correct and is the foundation of this design: *build a durable model once, query it many times, rather than re-deriving understanding per question.* Everything below follows from that.

| Term | Meaning in this specification |
|---|---|
| **Twin** | The multi-facet, commit-scoped, materialized model of one repository at one commit |
| **Facet** | One coherent domain of knowledge about the repository (structure, history, runtime, intent, social) |
| **Timeline** | The ordered sequence of Twins for a repository. **The Timeline is the primary object; a Twin is a projection of it at an instant** |

---

## 1. What Is the Repository Digital Twin

### 1.1 Definition

> **The Repository Digital Twin is the complete, queryable, machine-readable model of one repository at one commit: every file, symbol, and resolved relationship in its structure; every relevant fact from its history; every available signal about its runtime behavior; every recorded decision that constrains it; and every human relationship to it — assembled into a single identifier space, addressable by commit, and served through one query contract.**

### 1.2 The five defining properties

Each is a hard requirement. Removing any one produces something that already exists and is not valuable.

| Property | Requirement | Without it, we are… |
|---|---|---|
| **Resolved** | Relationships are name-bound, not name-matched, and carry method and confidence | …a heuristic. Advisory only. Not actionable by an agent |
| **Commit-scoped** | Every fact is keyed to exactly one commit | …a HEAD-only snapshot. Useless for branches, PRs, and history — i.e. useless for agents |
| **Multi-facet** | Five facets in one identifier space, jointly queryable | …a dependency visualizer. Prior art since the 1990s |
| **Materialized** | Precomputed and persisted, not derived per question | …an on-demand analyzer. Cannot meet latency or cost targets |
| **Unified identity** | One moniker space across facets, commits, and repositories | …five disconnected datasets. Joins are the product; without shared identity there are no joins |

### 1.3 What the Twin is not

| Not | Because |
|---|---|
| A simulation | We model structure and record behavior; we do not execute or predict execution |
| A copy of the code | Git holds the code. We hold the model *of* the code. We never become a system of record for source |
| A single stored object | It is a lazy composition over facet stores with structural sharing (§6) |
| An opinion | The Twin holds facts. Interpretations — health scores, reading orders, recommendations — are *derived views over* the Twin, stored separately, and freely discardable |
| Complete | It has known blind spots: reflection, dynamic dispatch, config-driven wiring, and unrecorded intent. **The Twin MUST report its own coverage gaps** (§9) |

---

## 2. Why It Exists

### 2.1 The first-principles argument

Consider the cost structure of answering repository questions.

```
DERIVE-PER-QUESTION                      MATERIALIZE-ONCE
question arrives                          commit arrives
  → read files                              → parse + resolve + graph  [expensive]
  → parse                                   → persist
  → guess relationships                   question arrives
  → answer (approximate)                    → indexed lookup          [cheap]
                                            → answer (exact)

cost = O(questions × repo_size)           cost = O(commits × change_size)
                                                 + O(questions × log n)
precision: bounded by what fits           precision: bounded by the resolver
           in one pass                               (improvable independently)
```

Two consequences make materialization strictly correct rather than merely preferable:

**Consequence 1 — the economics invert with query volume.** For a human asking three questions a week, deriving per question is fine. For a fleet of agents issuing thousands of queries per day against the same commits, deriving per question is absurd. **The arrival of high-volume machine consumers is precisely what converts materialization from an optimization into a requirement**, and it is why this product is viable now and was not in 2015.

**Consequence 2 — precision becomes an independent axis.** When understanding is derived per question, precision is capped by what one pass can afford. When it is materialized, resolution quality can be improved once, offline, and every past and future query benefits. Precision stops competing with latency. This is the structural reason a materialized index can reach agent-actionable accuracy and an on-demand analyzer cannot.

### 2.2 Why it must be the platform's core

Because the alternative has a known failure mode, and this project has already experienced it.

```
WITHOUT A SHARED TWIN                    WITH A SHARED TWIN

chat ──── own retrieval                  chat ─────┐
impact ── own graph walk                 impact ───┤
report ── own metrics                    report ───┼──▶ TWIN ──▶ facts
PR ────── own diff analysis              PR ───────┤            (one truth)
agent ─── own context assembly           agent ────┤
dead code own reachability               deadcode ─┘

N implementations of the same            One implementation.
concepts. They diverge. They             Improving resolution improves
disagree. Improving one improves         every feature simultaneously.
one. Each is separately wrong.
```

The left-hand diagram is not hypothetical: it is a description of the system this design replaces, which accumulated two independent retrieval stacks, two independent incremental-build pipelines, and separate "knowledge graph" and "dependency graph" subsystems that could not be joined. **The Twin's centrality is not an aesthetic preference; it is the only known defense against that outcome.** Hence PRD principle P1, and hence the architectural rule that no feature may compute structure for itself.

### 2.3 The leverage property

Every improvement to the Twin multiplies across every consumer:

```
add precise resolution for Java
  ⟹ chat, impact, PR review, dead code, agents, reports  ALL improve for Java
     with zero feature work

add the runtime facet
  ⟹ dead code becomes accurate, hotspots become real, blast radius becomes
     execution-weighted, agent context becomes behavior-aware
     with zero feature work

add one commit to the timeline
  ⟹ every trend, forecast, and evolution query gains a data point
     forever, and cannot be back-filled by a competitor
```

This is the entire investment thesis for the architecture: **depth in the Twin compounds; breadth in features does not.**

---

## 3. Entity Model

### 3.1 Identity — the foundation of everything

Nothing in this specification matters more than identity. Every join, every historical trace, every cross-repository edge depends on it.

**Rule 1 — Structural entities are identified by moniker, never by path.**

```
scheme:package:descriptor

python:mypkg:module/Class#method().
typescript:@scope/pkg:src/mod/Class#method().
java:com.example:pkg/Class#method(String).
file:.:src/handlers/auth.py
module:.:src/handlers
repo:github.com:owner/name
```

Monikers are stable across renames, comparable across commits, and comparable across repositories. Path-based identity breaks on every file move, which makes lifetime tracking impossible and cross-repository topology unrepresentable. **Choosing monikers is what makes the History facet feasible at all** — you cannot track a symbol's lifetime if its identity changes when someone moves a file.

**Rule 2 — Every fact is keyed by `(repo_id, commit_id, moniker)`.** There are no unversioned facts.

**Rule 3 — Content identity is separate from logical identity.**

```
moniker       — logical:  "this is Class#method"        stable across edits
content_hash  — physical: "these exact bytes"           stable across commits/branches
```
Monikers enable historical continuity. Content hashes enable computational reuse. Conflating them loses one capability or the other.

### 3.2 Entity catalogue

Notation: `PK` primary key · `→` reference · `[]` collection · **F** fact (durable, immutable) · **D** derived (disposable) · **M** mutable configuration.

---

#### Repository — **M**

| Field | Type | Notes |
|---|---|---|
| `repo_id` PK | uuid | Internal stable id |
| `moniker` | string | `repo:host:owner/name` |
| `origin_url` | string | Upstream |
| `default_branch` | string | |
| `tenant_id` | → Tenant | Isolation boundary |
| `languages` | [{lang, loc, pct, tier, precision}] | **Per-language precision is part of the entity** |
| `frameworks` | [string] | Drives entry-point descriptors |
| `index_policy` | object | Snapshot cadence, retention, facet selection |
| `status` | enum | `active · indexing · degraded · paused · archived` |
| `size_metrics` | object | files, LOC, symbols, edges at HEAD |

**Relationships.** `1—N Branch` · `1—N Commit` · `1—N Twin` · `N—N Repository` (cross-repo dependency, Phase 6) · `N—1 Tenant`.
**Lifecycle.** `registered → first_index → active ⇄ degraded ⇄ paused → archived → purged`.
**Persistence.** Relational, mutable. The only entity in the structural core that is not immutable.

---

#### Workspace — **M**

A consumer-scoped view. Not part of the Twin; it *selects* a Twin.

| Field | Type | Notes |
|---|---|---|
| `workspace_id` PK | uuid | |
| `owner` | → User \| AgentIdentity | **Agents are first-class owners** |
| `repos` | [→ Repository] | Multi-repo scope |
| `pinned_commit` | → Commit \| null | Null = follow branch head |
| `active_branch` | string | |
| `confidence_floor` | float | Default filter for this consumer |
| `facet_selection` | [facet] | Which facets to include by default |

**Design note.** `confidence_floor` on the workspace is what lets one Twin serve an agent that requires `method=exact` and a human who wants leads, without maintaining two indexes. An agent workspace sets the floor at 1.0 for mutation-relevant queries; a human's exploratory workspace sets it at 0.4.

**Lifecycle.** `created → active ⇄ idle → deleted`. Session-scoped state only; a workspace never holds index data.
**Persistence.** Relational, mutable, TTL on idle.

---

#### Commit — **F**

| Field | Type | Notes |
|---|---|---|
| `commit_id` PK | (repo_id, sha) | |
| `sha` | string | |
| `parents` | [sha] | Multiple ⇒ merge commit |
| `author`, `committer` | → Person | |
| `authored_at`, `committed_at` | timestamp | |
| `message` | text | Mined for issue refs, conventional-commit type |
| `tree_hash` | string | |
| `change_stats` | object | files/insertions/deletions |
| `index_state` | enum | `pending · indexing · queryable · failed · orphaned` |
| `coverage` | object | **% of files parsed, resolved, by tier — the Twin's self-report** |

**Relationships.** `N—1 Repository` · `N—N Commit` (parent) · `1—1 Twin` · `1—N FileUnit` · `N—N Branch`.
**Lifecycle.** `discovered → pending → indexing → queryable` (terminal, immutable) or `failed`. `queryable → orphaned` on upstream history rewrite. **Orphaned commits retain their facts** — deleting them would silently rewrite our own history and invalidate past answers we have already given.
**Persistence.** Relational, immutable, partition key. Never updated after reaching `queryable`.

---

#### Branch — **M**

| Field | Type | Notes |
|---|---|---|
| `branch_id` PK | (repo_id, name) | |
| `head_commit` | → Commit | **The only mutable field. Branches are pointers** |
| `merge_base_cache` | {other_branch: sha} | Optimization for diff queries |
| `is_default`, `is_protected` | bool | |
| `index_policy_override` | object \| null | e.g. merge commits only |

**Design note.** Branch mutability is confined to a single pointer field. All facts hang off immutable commits. This is what makes branch support nearly free: a branch query resolves the pointer, then executes an ordinary commit-scoped query. Systems that key facts to branches instead of commits require full reindexing on every branch operation.

---

#### FileUnit — **F**

| Field | Type | Notes |
|---|---|---|
| `unit_id` PK | (repo_id, commit_id, path) | |
| `path` | string | Repo-relative, normalized |
| `content_hash` | string | **Global dedup + cache key** |
| `blob_sha` | string | Git object |
| `language`, `language_tier` | enum | Tier A / B / unknown |
| `size_bytes`, `line_count` | int | |
| `classification` | enum | `source · test · config · doc · generated · vendored · binary` |
| `parse_status` | enum | `parsed · partial · unparseable · skipped` + reason |
| `module` | → Module | |

**Relationships.** `N—1 Commit` · `N—1 Module` · `1—N Symbol` · `N—N FileUnit` (imports, derived).
**Lifecycle.** Immutable per commit. Across commits, the same logical file is a *sequence* of FileUnits linked by path continuity and rename detection.
**Persistence.** Metadata relational; content in the content-addressed blob store, deduplicated globally. A file unchanged across 500 commits is stored once and parsed once.

**Design note.** `classification` is load-bearing, not cosmetic. Generated and vendored code must be excluded from health metrics, hotspot analysis, and agent context, and included in dependency resolution. A single flag drives dozens of downstream correctness behaviors — and its absence is why naive tools report vendored dependencies as the largest source of technical debt.

---

#### Module / Package / Directory — **F** (structural) + **M** (declared)

Deliberately one entity with a `kind` discriminator, because the distinction between "directory," "package," and "module" is language-specific and modeling them separately produces three near-identical tables that must be joined constantly.

| Field | Type | Notes |
|---|---|---|
| `module_id` PK | (repo_id, commit_id, moniker) | |
| `kind` | enum | `directory · package · module · namespace · service` |
| `parent` | → Module | Hierarchy |
| `declared_layer` | string \| null | **From config, not inferred** |
| `inferred_layer` | string \| null | **D** — from graph position |
| `public_api` | [→ Symbol] | Exported surface |
| `metrics` | object | **D** — fan-in/out, instability, cohesion |

**Design note — declared vs. inferred layer.** Both are stored, separately. The *declared* layer is intent (a fact about what humans decided). The *inferred* layer is observation. **Architecture drift is precisely the disagreement between the two**, which means drift detection is a comparison of two stored fields rather than a bespoke analysis subsystem. This is an example of the general pattern: model intent and observation as separate first-class data, and the interesting products fall out as joins.

---

#### Symbol — **F**

The central entity of the Structure facet.

| Field | Type | Notes |
|---|---|---|
| `symbol_id` PK | (repo_id, commit_id, moniker) | |
| `moniker` | string | Stable logical identity |
| `kind` | enum | `function · method · class · interface · struct · enum · trait · variable · constant · type_alias · module · property · parameter · field` |
| `name`, `qualified_name` | string | |
| `container` | → Symbol \| Module | Enclosing scope |
| `file_unit` | → FileUnit | |
| `span` | {start_byte, end_byte, start_line, start_col, end_line, end_col} | Byte offsets are authoritative |
| `signature` | string | Normalized, language-specific |
| `type_ref` | → TypeRef \| null | Present when Tier B available |
| `visibility` | enum | `public · protected · private · internal · package` |
| `modifiers` | [string] | `static · async · abstract · generator · deprecated · override` |
| `docstring` | text \| null | |
| `decorators` | [string] | Drives framework entry-point detection |
| `provenance` | {extractor, version, tier} | **Mandatory** |
| `confidence` | float | **Mandatory** |
| `is_entry_point` | bool + reason | From framework descriptor or heuristic |
| `is_exported` | bool | Part of the module's public API |

**Relationships.** `N—1 FileUnit` · `N—1 Symbol` (containment) · `1—N Relation` (out) · `1—N Relation` (in) · `1—N SymbolVersion` (across commits) · `N—1 TypeRef`.
**Lifecycle within a commit.** Immutable.
**Lifecycle across commits.** `introduced → stable → signature_changed → moved → renamed → removed`. Tracked by moniker continuity with rename heuristics; emitted as History facet lifetime events.
**Persistence.** Relational rows in the facts store, partitioned by `(repo, commit)`. Indexed on `moniker`, `(file_unit)`, `(kind, visibility)`.

**Design note — Function, Class, Method, Variable are `kind` values, not separate entities.** The brief lists them as distinct entities. Modeling them as separate tables would produce five near-identical schemas, five sets of indexes, and a union query for every traversal — for no benefit, since all five participate in identical relationships. One entity with a discriminator and a language-specific attribute bag is strictly better. This is where DDD-style rich entity modeling actively hurts: the domain objects here are uniform fact records, not behavior-bearing objects with distinct invariants.

---

#### Relation — **F**

The single most important entity in the system, because relations are what the product sells.

| Field | Type | Notes |
|---|---|---|
| `relation_id` PK | (repo_id, commit_id, src, dst, kind, span) | Span included: multiple call sites are distinct relations |
| `src`, `dst` | → Symbol \| Module \| FileUnit | Moniker refs |
| `kind` | enum | see below |
| `span` | Span \| null | Where the relation is expressed in source |
| **`method`** | enum | **`exact · inferred · heuristic`** |
| **`confidence`** | float | **[0,1]** |
| **`provenance`** | {extractor, version, tier, rule} | |
| `ambiguity_group` | uuid \| null | Non-null ⇒ one of N candidates |
| `attrs` | object | kind-specific (e.g. `is_conditional`, `is_dynamic`) |

**Relation kinds**
```
STRUCTURAL     calls · imports · exports · inherits · implements · instantiates
               references · defines · contains · overrides · type_of · returns
               throws · reads · writes · decorates · annotates
DERIVED        depends_on (transitive) · coupled_with · layer_violation
CROSS-FACET    tested_by · executed_by · owned_by · constrained_by · changed_with
```

**The `method` + `confidence` + `ambiguity_group` triple is the design centerpiece.** It converts irreducible imprecision from a hidden liability into typed, filterable, honest data:

```
"who calls process()?"

  method=exact                       3 call sites, certain
  method=inferred     (type-based)   2 call sites, confidence 0.85
  method=heuristic    (name match)  14 call sites, confidence 0.30,
                                     ambiguity_group=g7 (14 candidates)

  agent performing a mutation  →  filters to exact           → acts safely
  human exploring              →  sees all, sorted           → follows leads
  blast radius (default)       →  exact + inferred            → useful and honest
  dead code analysis           →  exact only, and reports the excluded set
```

Without this, a system must choose between over-reporting (noise, distrust) and under-reporting (dangerous omissions), and it must make that choice once, globally, at write time. With it, the choice moves to the consumer at query time, which is the only place where the right answer is knowable.

**Lifecycle.** Immutable per commit. Across commits: `added → persisted → removed`, emitting `EdgeAdded` / `EdgeRemoved` domain events.
**Persistence.** The largest table in the system (~10⁸ rows for a 10M LOC repository). Partitioned by `(repo, commit)`. Two covering indexes: `(repo, commit, src, kind)` and `(repo, commit, dst, kind)` — forward and reverse traversal respectively. Reverse traversal is not an afterthought: "who calls this" is the highest-value query in the product and it is a reverse walk.

---

#### TypeRef — **F**

| Field | Type | Notes |
|---|---|---|
| `type_id` PK | (repo, commit, moniker) | |
| `kind` | enum | `primitive · named · generic · union · intersection · function · unknown` |
| `resolved_to` | → Symbol \| null | Null for primitives and externals |
| `type_args` | [→ TypeRef] | Generics |
| `nullable` | bool | |
| `confidence` | float | Inference confidence |

Present only where Tier B indexing is available. Its presence is what elevates call resolution from `heuristic` to `exact` for dynamic dispatch — which makes TypeRef availability, not language "support," the real determinant of precision per language.

---

#### Import / Dependency / ExternalPackage — **F**

Import statements are `Relation(kind=imports)`; this entity models *external* dependencies, which are a different kind of thing (unindexed, versioned, third-party).

| Field | Type | Notes |
|---|---|---|
| `dep_id` PK | (repo, commit, coordinate) | |
| `coordinate` | string | `pypi:fastapi@0.110.0` |
| `ecosystem` | enum | pypi, npm, maven, go, cargo… |
| `version_spec`, `resolved_version` | string | Declared vs. locked |
| `scope` | enum | `runtime · dev · test · build · optional` |
| `is_direct` | bool | Direct or transitive |
| `used_by` | [→ FileUnit] | **Actual usage, not just declaration** |
| `symbols_used` | [→ Symbol] | External symbols actually referenced |

**Design note.** `used_by` and `symbols_used` are what make this entity worth having. "Declared but never imported" and "used in one file only" are immediately actionable, and neither is answerable from a manifest file alone. This is a small example of the general principle: value comes from joining declaration (intent) with structure (observation).

---

#### CallEdge

Not a separate entity. `Relation(kind=calls)`. Recorded here explicitly because the brief lists it separately and because introducing a parallel call-edge table would immediately violate the one-graph rule of §5.

---

#### APISurface — **D**

| Field | Type | Notes |
|---|---|---|
| `api_id` PK | (repo, commit, module) | |
| `public_symbols` | [→ Symbol] | |
| `classification` | {symbol: `public·internal·deprecated·experimental`} | |
| `instability` | float | Martin's I = fan-out / (fan-in + fan-out) |
| `breaking_changes_vs` | {base_commit: [Change]} | Signature/removal diffs |

Derived, because classification depends on our heuristics and thresholds. Recomputable from facts. Storing it as a fact would freeze a 2026 opinion into permanent record — exactly the rot mechanism PRD §4.2 exists to prevent.

---

#### KnowledgeNode / KnowledgeEdge

Not separate entities. **Rejected from the model.** A "knowledge graph" distinct from the structural graph guarantees two identifier spaces, two update paths, and eventual divergence — the exact defect the previous architecture exhibited when its knowledge graph and dependency graph could not be joined. Symbols, Modules, FileUnits, Commits, Persons, and Decisions *are* the nodes; Relations are the edges. There is one graph (§5).

---

#### ArchitectureLayer — **M** (declared) + **D** (inferred)

| Field | Type | Notes |
|---|---|---|
| `layer_id` PK | (repo, name) | Not commit-scoped: layers are declared intent |
| `name`, `order` | string, int | e.g. delivery(3) → domain(2) → infra(1) |
| `member_patterns` | [glob] | Path or moniker patterns |
| `allowed_dependencies` | [layer] | The rule |
| `violations` | [→ Relation] | **D**, per commit |

Sourced from `.repo-intel.yml`. **This is the first entry point of the Intent facet, and it is deliberately the simplest one:** a layering rule is machine-checkable intent, cheap to declare, and immediately enforceable at merge. Starting the Intent facet with ADR prose would produce something unenforceable; starting with layering produces a merge gate.

---

#### DesignPattern — **D**

| Field | Type | Notes |
|---|---|---|
| `pattern_id` PK | (repo, commit, pattern, scope) | |
| `pattern` | enum | repository · factory · observer · singleton · adapter · middleware-chain · CQRS… |
| `participants` | [→ Symbol] | |
| `confidence` | float | |
| `detection_rule` | string | Which rule fired |

Derived and explicitly low-priority. Pattern detection is high-noise and low-actionability. Included in the model for completeness; scheduled no earlier than Phase 5; **shipped only if it reaches ≥0.8 precision on a labelled corpus** (P8). If it does not, it is deleted rather than shipped with a disclaimer.

---

#### Person / Team / Ownership — **F** (facts) + **D** (expertise)

| Field | Type | Notes |
|---|---|---|
| `person_id` PK | uuid | Identity-resolved across emails and accounts |
| `identities` | [{email, vcs_login, sso_id}] | |
| `team` | → Team \| null | |
| `expertise` | {module: score} | **D** — from authorship × recency × structure |
| `is_active` | bool | Departure is a risk signal |

`Ownership { module → [person], confidence, source: codeowners \| blame \| declared }`.

**Design note.** Ownership from CODEOWNERS is *declared*; from blame it is *observed*. Storing the source makes "the declared owner has not touched this in two years" a queryable fact — one of the highest-value organizational signals available and again a declaration-versus-observation join.

---

#### RuntimeObservation — **F** (Phase 4+)

| Field | Type | Notes |
|---|---|---|
| `obs_id` PK | uuid | |
| `target` | → Symbol \| FileUnit | |
| `commit_range` | (sha, sha) | Deployment window the data covers |
| `kind` | enum | `coverage · invocation_count · latency · error_rate · trace_edge` |
| `value`, `unit` | number, string | |
| `source` | enum | `test_coverage · apm · profiler · logs` |
| `window` | (from, to) | |

**Why this facet matters disproportionately.** It resolves the truth ceiling of static analysis. `Relation(kind=calls, method=heuristic)` plus a runtime trace edge between the same endpoints upgrades the relation's effective confidence. Statically-reachable-but-never-executed code is *demonstrably* dead in a way no reachability sweep can establish. **Nobody in the competitive set fuses static structure with runtime observation, and it is the single largest available precision improvement that does not require better parsing.**

---

#### Decision / ADR — **F** (Phase 5+)

| Field | Type | Notes |
|---|---|---|
| `decision_id` PK | uuid | |
| `title`, `status` | string, enum | `proposed · accepted · superseded · deprecated` |
| `context`, `decision`, `consequences` | text | ADR structure |
| `constrains` | [→ Symbol \| Module \| Layer] | **The binding — the essential field** |
| `invariants` | [MachineCheckableRule] | The subset that can be enforced |
| `decided_at`, `deciders` | timestamp, [→ Person] | |
| `supersedes` | → Decision | |
| `outcome` | {evaluated_at, assessment, evidence} | **Did it work?** |

**Why this is the ten-year moat.** PRD §5.2 identifies L4 — information that was never recorded — as a hard ceiling on any comprehension claim. Analysis cannot break that ceiling; only *capture* can. A system that records decisions at decision time, binds them to the code they constrain, checks the machine-checkable subset continuously, and later records whether the decision worked, accumulates something no parser recovers and no competitor can backfill. `outcome` is the field that eventually makes this a learning system rather than a filing cabinet.

**Sequencing.** This facet must start early even though it matures late, because its value is a function of elapsed calendar time. Beginning with `ArchitectureLayer` rules (already machine-checkable) is the pragmatic on-ramp.

---

#### EngineeringMemory entities — **F**

| Entity | Fields | Notes |
|---|---|---|
| `LifetimeEvent` | `entity_moniker, kind(introduced·modified·moved·renamed·signature_changed·removed), commit, prev, next` | Append-only. **Never deleted, even on orphaned commits** |
| `EvolutionMetric` | `repo, scope, metric, commit, timestamp, value` | **D** — downsampled with age |
| `Trend` | `metric, window, slope, volatility, r², confidence` | **D** |
| `AgentMemoryEntry` | `repo, namespace, key, value, created_by, ttl, confidence` | Agent working memory across sessions |

**`AgentMemoryEntry` is strategically significant and easy to overlook.** It makes the platform the durable memory of otherwise stateless agents: "I already determined that the auth flow works like X," "this test is flaky," "the owner said not to touch this module." Once an agent's accumulated repository knowledge lives here, switching away costs the agent its memory — the strongest form of integration lock-in available (PRD §10.3, moat 2), and it is cheap to build.

---

#### Twin — the composition

| Field | Type | Notes |
|---|---|---|
| `twin_id` PK | (repo_id, commit_id) | |
| `facet_status` | {facet: `available · partial · stale · absent` + reason} | **Mandatory self-report** |
| `coverage` | {files_parsed%, symbols_resolved%, exact_edge%} | Per language |
| `materialization` | {facet: `materialized · lazy · evicted`} | |
| `schema_version` | int | Twin schema version |
| `built_at`, `build_duration` | timestamp, ms | |

**The Twin has almost no fields of its own, and that is the correct design.** It is a composition handle plus a self-description. All content lives in facet stores. The two things it genuinely owns — `facet_status` and `coverage` — are what make it trustworthy: **a Twin that cannot state what it does not know is not usable by an autonomous agent.** Every response derived from a Twin carries its coverage, so a consumer can decide whether to act, verify, or ask a human.

---

## 4. Entity Relationship Overview

```
                            ┌──────────┐
                            │  Tenant  │
                            └────┬─────┘
                                 │ 1—N
                            ┌────▼─────────┐         ┌───────────┐
              ┌─────────────│  Repository  │────────▶│ Workspace │
              │             └────┬─────────┘  N—N    └───────────┘
              │ 1—N              │ 1—N                 (selects)
        ┌─────▼─────┐      ┌─────▼─────┐
        │  Branch   │─────▶│  Commit   │◀──── parents (N—N, DAG)
        └───────────┘ head └─────┬─────┘
                                 │ 1—1
                          ┌──────▼──────┐
                          │    TWIN     │  facet_status · coverage
                          └──────┬──────┘
      ┌───────────┬──────────────┼──────────────┬───────────────┐
      ▼           ▼              ▼              ▼               ▼
 STRUCTURE     HISTORY        RUNTIME        INTENT          SOCIAL
      │           │              │              │               │
 ┌────▼─────┐┌────▼──────┐ ┌─────▼──────┐ ┌────▼─────┐  ┌──────▼─────┐
 │ Module   ││LifetimeEvt│ │RuntimeObs  │ │ Decision │  │  Person    │
 │ FileUnit ││EvolMetric │ │  coverage  │ │ ArchLayer│  │  Team      │
 │ Symbol   ││ Trend     │ │  traces    │ │Invariant │  │  Ownership │
 │ TypeRef  ││AgentMemory│ │  incidents │ │          │  │  Expertise │
 │ ExtDep   │└───────────┘ └────────────┘ └──────────┘  └────────────┘
 └────┬─────┘
      │ 1—N                     ALL FACETS SHARE ONE MONIKER SPACE
 ┌────▼──────────────────────────────────────────────────────────┐
 │ RELATION   src ─kind─▶ dst   + method + confidence + provenance│
 │            ↑ the edges of the single unified graph             │
 └───────────────────────────────────────────────────────────────┘
```

The shared moniker space across the bottom is the whole design. It is what turns five datasets into one queryable model, and it is why identity (§3.1) is specified before anything else.

---

## 5. Graphs — One Graph, Many Projections

### 5.1 The core decision

The brief asks for seven graphs: Knowledge, Dependency, Call, Architecture, Module, History, Engineering Memory. **We build one graph and project seven views from it.**

```
REJECTED                                 ADOPTED
7 stores, 7 update paths                 1 store: nodes + edges
                                         7 query definitions
knowledge ─┐                             ┌─────────────────────────────┐
dependency─┤                             │  nodes(moniker, kind, …)    │
call ──────┤  each maintained            │  edges(src, dst, kind,      │
module ────┤  independently               │        method, confidence)  │
arch ──────┤  ⇒ divergence guaranteed    └──────────┬──────────────────┘
history ───┤  ⇒ 7× update cost                     │ projections
memory ────┘  ⇒ cannot be joined         ┌──────────┴──────────┐
                                          ▼                     ▼
                                    filter by kind        aggregate by scope
```

| Projection | Definition | Nodes | Edge kinds |
|---|---|---|---|
| **Dependency** | file-level import topology | FileUnit | `imports`, `exports` |
| **Call** | function-level invocation | Symbol | `calls`, `overrides` |
| **Module** | dependency lifted to module scope | Module | aggregated `imports` |
| **Architecture** | module graph grouped by declared layer | Layer | aggregated, annotated with violations |
| **Type** | inheritance and implementation | Symbol | `inherits`, `implements`, `type_of` |
| **History** | commit DAG + lifetime events | Commit, LifetimeEvent | `parent`, `changed_with` |
| **Ownership** | people to code | Person, Module | `owns`, `authored`, `reviews` |
| **Knowledge** | everything, unfiltered | all | all |

The "knowledge graph" is not an eighth structure; it is the unprojected graph. Naming it separately in the previous architecture is precisely what caused it to be *built* separately.

### 5.2 How the projections interact

The interactions are where the product's unique capability lives, and in this model each one is an ordinary join:

```
Call × Dependency
  "does this call cross a module boundary that shouldn't be crossed?"
  → join call edges to module membership, evaluate layer rules

Call × History
  "this function's callers doubled in six months"
  → count call edges per commit over the timeline

Dependency × Architecture
  "which imports violate declared layering?"
  → import edges where declared_layer(src) ↛ declared_layer(dst)

Call × Runtime
  "statically reachable, never executed in production"
  → reachable(entry_points) MINUS observed_invocations

Call × Ownership
  "who should review a change to this function?"
  → owners of the modules containing its transitive callers

History × Runtime
  "changes to this module correlate with incidents"
  → churn series × incident series, per module

Structure × Intent
  "this change violates ADR-014"
  → new edges ∩ Decision.invariants

Ownership × History
  "the only person who understood this left"
  → expertise concentration × person.is_active
```

Eight capabilities. Zero new subsystems. All eight are unreachable from a context window, and all eight are unreachable from a design with seven separate graph stores. **This table is the concrete payoff of both the one-graph decision and the five-facet decision.**

### 5.3 Traversal semantics — mandatory rules

| Rule | Requirement |
|---|---|
| **Bounded** | Every traversal takes `max_depth` and `limit`. No unbounded traversal is exposed |
| **Truncation is reported** | `truncated: true` with the reason. **Silent truncation is forbidden** — it is indistinguishable from a complete answer |
| **Cycle-safe** | Visited set always. No traversal may assume acyclicity |
| **Confidence-filterable** | `min_confidence` and `methods[]` on every traversal |
| **Deterministic order** | Stable sort by (score, moniker). Same query ⇒ byte-identical result. Required for caching and for reproducible evaluation |
| **Commit-scoped** | Traversal never crosses commits unless explicitly querying the History projection |

---

## 6. Lifecycle: Building, Updating, Versioning, Storing

### 6.1 Construction

```
COLD BUILD (new repository)                 INCREMENTAL (subsequent commit)
1  register + admission check               1  webhook / poll → commit sha
2  clone; resolve commit                    2  manifest diff → ChangeSet
3  enumerate + classify FileUnits           3  affected = changed ∪ reverse_deps(changed)
4  parse all (Tier A) ─ parallel            4  parse affected  [~95% cache hits]
5  index project (Tier B) where possible    5  Tier B if manifests/config changed
6  resolve → symbols, relations, ambiguity  6  resolve affected + dependents
7  build graph nodes/edges                  7  copy-on-write graph; upsert deltas
8  facets: history · social (+runtime/intent)8  facet deltas
9  derived: metrics · projections · embeds  9  invalidate + recompute affected derived
10 mark commit QUERYABLE (atomic)           10 mark QUERYABLE (atomic)
11 emit CommitIndexed                       11 emit CommitIndexed + lifetime events

hours for 10M LOC                           target p95 < 2s for ≤10 files
```

**The reverse dependency index is the linchpin of step 3.** Changing `config.py` may require re-resolving 200 files that import it, while changing a leaf test file requires one. Without a maintained `unit → units whose resolution consumed it` index, correctness forces whole-repository re-resolution and the incrementality target is unreachable. This index is therefore a first-class artifact with its own tests and benchmarks — not an optimization detail.

### 6.2 Incremental update correctness

Three failure modes, each with a specific defense. All three are subtle, and all three produce answers that look correct.

| Failure | Defense |
|---|---|
| **Stale derived data** — a metric computed from pre-change facts | Every derived record stores the `algo_version` and the commit it derives from. Mismatch ⇒ recompute. Never trust derived data across a version boundary |
| **Missed fan-out** — a dependent file not re-resolved | Reverse dependency index is maintained transactionally with the forward index. A periodic full-rebuild audit compares incremental against cold results on sample commits and alerts on divergence. **This audit is the only real defense; incremental correctness cannot be proven, only continuously tested** |
| **Partial visibility** — a consumer observes a half-built index | Atomic visibility (§6.1 step 10). A commit is invisible until complete, then visible instantly. There is no intermediate observable state |

### 6.3 Versioning

```
Commit DAG (immutable)          Twin timeline (1:1 with indexed commits)

  c1 ── c2 ── c3 ──── c6         T1   T2   T3        T6      (main)
          ╲              ╱                  ╲        ╱
           c4 ── c5 ────                     T4  T5          (feature)

Queries:
  twin_at(c3)                  → exact commit
  twin_at(branch=main)         → resolve head → twin_at(sha)
  twin_at(timestamp)           → nearest indexed ancestor + staleness
  diff_twins(c3, c5)           → structural delta
  diff_twins(merge_base(main, feature), feature_head)   → the PR's true change
```

**Branch support is nearly free** because facts key to commits and a branch is a pointer (§3.2, Branch). **Merge support** is the `merge_base` query plus a three-way structural diff: `diff(base, ours)` and `diff(base, theirs)` reveal *semantic* conflicts — both branches changed the signature of the same symbol — that a textual merge cannot detect because the edits are in different files. That capability is a direct consequence of commit-addressed structure and is unavailable to any HEAD-only index.

**Snapshot cadence policy** — indexing every commit on every branch is neither affordable nor useful:

| Scope | Default policy |
|---|---|
| Default branch | Every commit |
| Active feature branches | Head only, refreshed on push |
| PR branches | Merge-base and head (enables the PR diff) |
| Tags / releases | Always, retained permanently |
| Stale branches | Not indexed |
| Retention | Full twins 90 days; merge commits 1 year; releases forever; **lifetime events forever** |

### 6.4 Storage strategy

```
FACTS (durable, immutable, irreplaceable)      DERIVED (disposable)
  commits · manifests · FileUnits                metrics · projections
  symbols · relations · TypeRefs                 embeddings · materialized facets
  lifetime events · decisions                    API classifications · patterns
  runtime observations                           health scores · reading orders
  ── continuously backed up ──                   ── never backed up ──
  ── loss is unrecoverable ──                    ── rebuild from facts ──
```

**Structural sharing is what makes per-commit twins affordable.** A commit that changes 3 of 100,000 files:

```
naive:    full copy of all nodes and edges           ~30 GB per commit
sharing:  new rows only for affected units;
          unchanged nodes referenced by
          (content_hash, resolver_version)           ~50 MB per commit

                                                     ≈600× reduction
```

Without this, commit-addressing is economically impossible and the entire versioning design collapses. It is not an optimization; it is the enabling mechanism.

**The five-tier storage split** (facts in relational, content in blob, derived in relational + vector, cache/queue ephemeral, git mirrors) is specified in `02-SDD.md` §6.2. The operational consequence worth restating: **derived storage may be dropped entirely at any time to reclaim space, and the system rebuilds it.** That is what makes algorithm iteration cheap and disaster recovery simple — restore facts, rebuild the rest.

### 6.5 Caching

Because facts about a commit are immutable, **cache entries never require invalidation; they expire only by eviction.** Every cache key includes the producing component's version, so a component upgrade invalidates exactly its own outputs and nothing else. This eliminates the hardest correctness problem such a system normally has, and it is a direct dividend of commit-addressing. Full tier table in `02-SDD.md` §5.5.

---

## 7. Query Interface

The Twin's public contract. Roughly twenty primitives, deliberately few and deliberately narrow. **This is simultaneously the REST API, the GraphQL schema, the MCP tool catalog, and the CLI surface** — one contract, several transports.

### 7.1 Universal parameters

Every primitive accepts:

```
repo            required
commit          required (accepts sha | branch | timestamp | "HEAD")
min_confidence  default 0.0
methods         default [exact, inferred, heuristic]
limit, cursor   pagination
facets          which facets to consult
```

Every primitive returns:

```
{ results: [...],
  truncated: bool,
  coverage:  { files_parsed%, symbols_resolved%, exact_edge% },
  provenance:{ commit, resolver_version, built_at },
  confidence: float }
```

**The uniform coverage and provenance envelope is a hard requirement, not a convenience.** An autonomous consumer must be able to decide whether to trust a result, and that decision requires knowing what the index does and does not cover. Returning bare results is what makes existing tools unusable by agents.

### 7.2 The primitives

| # | Primitive | Returns | Class |
|:--:|---|---|:--:|
| 1 | `resolve_symbol(name \| moniker, context)` | [Symbol] + confidence | D |
| 2 | `get_symbol(moniker)` | Symbol with full detail | D |
| 3 | `find_references(moniker, kinds, depth)` | [Relation] with spans | D |
| 4 | `callers(moniker, depth)` | [Symbol] + paths | D |
| 5 | `callees(moniker, depth)` | [Symbol] + paths | D |
| 6 | `blast_radius(seeds[])` | affected files, symbols, tests, API impact | D |
| 7 | `reachable(roots[], direction)` | ReachableSet + unreached remainder | D |
| 8 | `subgraph(seeds[], depth, kinds)` | Subgraph | D |
| 9 | `paths(src, dst, max_depth)` | [Path] | D |
| 10 | `cycles(scope)` | [Cycle] with depth | D |
| 11 | `module_graph(scope)` | Module projection + metrics | D |
| 12 | `layer_violations()` | [Relation] + rule violated | D |
| 13 | `api_surface(module)` | public/internal/deprecated + instability | D |
| 14 | `tests_for(targets[])` | [test symbols] + coverage if available | D |
| 15 | `owners(target)` | [Person] + source + confidence | D |
| 16 | `search_semantic(query, k)` | [Chunk] + resolved symbols | P |
| 17 | `find_precedents(description, k)` | [Symbol] — in-repo implementations of a pattern | P |
| 18 | `timeline(entity, range)` | [LifetimeEvent] | D |
| 19 | `evolution(metric, scope, range)` | TimeSeries + Trend | D |
| 20 | `diff_twins(c1, c2, facets)` | TwinDiff | D |
| 21 | `capabilities()` | languages, facets, **measured precision** | D |
| 22 | `index_status()` | freshness, coverage, degradation | D |
| 23 | `ask(question, budget)` | Answer + verified citations | **P** |

**D = deterministic (no LLM). P = probabilistic.** Twenty of twenty-three primitives are deterministic. **`ask` is one primitive of twenty-three**, and that ratio is the architecture of the product expressed as an API: the chat interface is a single entry point among many, not the system.

**On `capabilities()` and `index_status()` as first-class primitives:** no competitor exposes measured precision and index coverage as queryable API surface. Doing so is a direct expression of PRD principles P4 and P11, and it is the mechanism by which the Code Semantic Layer category requirement of "declared precision" is satisfied in software rather than in marketing copy.

### 7.3 Example: the agent flow, expressed in primitives

```
resolve_symbol("RateLimitMiddleware")            → moniker, span, confidence 1.0
find_references(moniker, kinds=[call, import])   → 7 exact sites
blast_radius(["backend/security_middleware.py"]) → 14 files, 6 tests,
                                                    public_api_affected: false,
                                                    confidence 0.94,
                                                    unresolved_edges: 3
find_precedents("rate limiting")                 → 3 in-repo implementations
tests_for([...])                                 → 6 test files, 11 tests
owners("backend/middleware")                     → 2 people, source: codeowners

⇒ agent writes the patch. ~4k tokens. No exploration. No hallucinated paths.
  Baseline (grep + embeddings): 30–60k tokens, 20–60s, unverified paths.
```

Note `unresolved_edges: 3` in the blast radius response. The Twin is telling the agent that three edges could not be resolved and the answer may therefore be incomplete. **An agent that receives that field can decide to escalate; an agent that receives a bare number cannot.** That single field is the difference between an advisory tool and infrastructure an autonomous system can build on.

---

## 8. Every Feature Consumes the Twin

The architectural commitment: **no feature computes structure for itself.** Every capability is a composition of §7 primitives. If a feature needs something the primitives cannot express, we add a primitive — we never add a private analysis path.

| Feature | Twin primitives used | Facets | New code required |
|---|---|---|---|
| **Repository Chat** | `ask` → tool loop over 1–20 | Structure, History | Prompt + orchestration only |
| **Issue Mapping** | `search_semantic` → `subgraph` → `blast_radius` → `tests_for` | Structure, History | Ranking heuristic only |
| **Impact Analysis** | `blast_radius`, `callers`, `reachable`, `tests_for` | Structure (+Runtime) | **None — it is primitive 6** |
| **Architecture Review** | `module_graph`, `layer_violations`, `cycles`, `api_surface` | Structure, Intent | Rule evaluation only |
| **Health Report** | `module_graph`, `api_surface`, `evolution`, `cycles`, `reachable` | Structure, History | Scoring + rendering only |
| **Reading Paths** | `module_graph` (centrality), `reachable(entry_points)`, `owners` | Structure, Social | Ordering heuristic only |
| **Dead Code Detection** | `reachable(entry_points)` complement, **minus runtime observations** | Structure, Runtime | Framework descriptors |
| **Dependency Analysis** | `module_graph`, external deps, `find_references` | Structure | **None** |
| **PR Intelligence** | `diff_twins(merge_base, head)`, `blast_radius`, `layer_violations`, `tests_for`, `owners` | All five | Diff presentation only |
| **CI Architecture Gate** | `layer_violations`, `cycles`, `api_surface` diff, `diff_twins` | Structure, Intent | Rule config + check protocol |
| **Drift Detection** | declared vs. inferred layer comparison | Structure, Intent | **None — it is a stored-field comparison** |
| **Evolution Analytics** | `evolution`, `timeline`, `trend` | History | Visualization only |
| **Ownership / Bus Factor** | `owners`, `expertise`, `timeline` | Social, History | Scoring only |
| **Autonomous Agents** | Full primitive set via MCP + `AgentMemoryEntry` | All five | **None — the API is the product** |
| **Cross-Repo Topology** | `subgraph` across repos via monikers | Structure | Cross-repo edge resolution |
| **Predictive Risk** | `evolution` × incident observations | History, Runtime | Model only |

Two observations from this table.

**First, four features require literally no new code** — they are already primitives or trivial field comparisons. Impact analysis, dependency analysis, drift detection, and the agent interface are pure consequences of the model. That is the leverage property of §2.3 made concrete.

**Second, "PR Intelligence" is the only feature touching all five facets, which is why it is the best commercial wedge.** It is the natural demonstration of the whole design: structural diff, blast radius, layering violation, affected tests, and the right reviewers — in one merge check, where a developer already is, at the moment a decision is being made. It cannot be replicated by a context window and it becomes politically unremovable once installed.

---

## 9. Known Limitations — Stated in the Model

The Twin MUST report its own blind spots. `coverage` and `facet_status` exist for this purpose, and the following are the specific classes they must expose.

| Limitation | Nature | Mitigation | Residual |
|---|---|---|---|
| Reflection, `eval`, metaprogramming | Structurally invisible | Framework descriptors; runtime facet | Permanent for arbitrary dynamism |
| Dynamic dispatch without types | Ambiguous | TypeRef where Tier B exists; candidate sets elsewhere | Reduced, never eliminated |
| Config-driven wiring (DI, YAML routing) | Not in code | Framework descriptors; config parsing | Partial |
| Generated code | Structure of the generator, not the intent | Classification + exclusion from metrics | Acceptable |
| Cross-language boundaries (FFI, RPC) | Two disjoint graphs | API-contract edges (Phase 6) | Partial |
| Unrecorded intent (PRD L4) | Never written down | Decision capture (§3.2) | **Permanent for the past. Solvable only forward** |
| Semantics of behavior | We model structure, not meaning | Runtime facet | Permanent |

**Three commitments follow, and they are what separate this design from every prior generation of code-intelligence tooling:**

1. Blind spots are **enumerated in the data model**, not discovered by users.
2. `coverage` is returned on **every response**, so consumers always know the basis of an answer.
3. Confidence is **never inflated to appear complete.** A low-confidence answer labelled low-confidence is useful. A low-confidence answer presented as certain is the failure mode that destroys trust in an entire product category — one wrong deletion recommendation acted upon costs more than fifty correct ones earn.

---

## 10. Schema Evolution

The Twin schema will change for a decade. Rules, in force from the first commit:

| Rule | Requirement |
|---|---|
| **Additive by default** | New entities, kinds, and fields are additive. Removals require a deprecation cycle |
| **`schema_version` on every Twin** | Consumers can detect and adapt |
| **Versioned extractors** | Every fact records the producing component and version. A bump invalidates exactly its own outputs |
| **Derived is free to change** | Only facts need care. Interpretations may be recomputed at will — the central benefit of the facts/derived split |
| **Query contract is versioned separately** | The API may remain stable across internal schema changes; that decoupling is the point of the gateway layer |
| **Relation kinds are open** | New edge kinds are data rows, never migrations. This is why the graph is one table |
| **Backfill via event replay** | New derived facets are backfilled by replaying the domain event log rather than reindexing history |

---

## 11. Open Design Questions

Recorded rather than resolved. Each is a genuine fork with material consequences, and each will be decided by measurement rather than argument.

| # | Question | Decide by | Consequence |
|:--:|---|---|---|
| T1 | Materialize every commit's twin, or materialize lazily on first query? | Phase 3 storage measurement | Cost vs. p95 latency. Current lean: lazy with eager materialization for default-branch heads and releases |
| T2 | Is relational adjacency sufficient at 10⁸ edges and depth ≥5? | Phase 3 load testing | May force a graph engine for the traversal path only. Query interface is deliberately storage-agnostic to keep this a swap |
| T3 | Should `confidence` be calibrated probability or ordinal score? | Phase 2, empirically | Calibrated is far more useful to agents and much harder to produce honestly. Lean: ordinal initially, calibrated per language once labelled data exists |
| T4 | How should cross-repository symbol identity work for private forks and vendored copies? | Phase 6 | Determines whether cross-repo topology is reliable or advisory |
| T5 | Should the runtime facet be a first-class facet or an enrichment of relation confidence? | Phase 4 | Affects whether "never executed" is a fact or a derived judgement |
| T6 | Can decision capture achieve enough adoption to matter, or does it fail like documentation always has? | Phase 5 pilot | This is the ten-year moat. If capture does not happen naturally at merge time, the moat does not exist and the roadmap changes |
| T7 | Do agents actually consume `coverage` and `confidence`, or ignore them? | Phase 4 pilots | If ignored, the entire honesty apparatus is cost without benefit and precision must instead be enforced by defaults |

T6 and T7 deserve emphasis: they are the two questions that could invalidate significant parts of this design, and both are answerable only with real users. Neither should be argued about internally past the point where a pilot could settle it.
