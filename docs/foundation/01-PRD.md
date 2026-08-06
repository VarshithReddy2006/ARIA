# Product Requirements Document

**Product:** Repository Intelligence Agent
**Document status:** Foundation — normative
**Version:** 2.0 (greenfield redesign)
**Supersedes:** all positioning and scope statements in `README.md`, `ARCHITECTURE.md`, `AUDIT_REPORT.md`
**Companion documents:** `02-SDD.md` (system design), `03-DIGITAL-TWIN-SPEC.md` (core data model)

> **Normative language.** MUST / MUST NOT / SHOULD / MAY are used in the RFC 2119 sense. A statement marked MUST is a requirement that any implementation is measured against, not an aspiration.

---

## 1. Executive Summary

### 1.1 What we are building

A **commit-addressed, precision-resolved, incrementally-maintained index of software repositories, exposed as a query API that AI agents and developer tools consume instead of building their own retrieval.**

Not a chat product. Not an IDE. Not a code generator. An index — in the same sense that Elasticsearch is an index, dbt is a semantic layer, and OpenTelemetry is an instrumentation substrate. The applications (chat, reports, PR intelligence, impact analysis) exist to prove the index is correct and to make it adoptable. They are not the product.

### 1.2 The bet, stated so it can be falsified

> Autonomous and semi-autonomous coding systems will originate the majority of code changes in mature engineering organizations within five years. Those systems are stateless: every session rediscovers the codebase from zero using `grep`, embeddings, and speculative file reads. The organizations running them will not tolerate that cost, latency, or error rate indefinitely. A shared, precise, persistent structural index of the codebase becomes infrastructure — and infrastructure positions are winner-take-most.

Falsification conditions, stated honestly because a bet without them is a slogan:

| The bet is wrong if… | Leading indicator to watch |
|---|---|
| Context windows and inference cost improve fast enough that brute-force file reading dominates on repositories of all sizes | Frontier window ≥10M tokens at <$0.10/Mtok, with reliable needle-retrieval at that length |
| Agent vendors decide retrieval *is* their differentiator and build it in-house | Cursor/Anthropic/OpenAI shipping a precise multi-language symbol index as a product surface |
| Precision turns out not to matter — heuristic retrieval scores as well as resolved retrieval on real tasks | Our own benchmark (§11.2) shows <15% recall@10 delta between heuristic and resolved indexes |

We MUST re-examine this PRD if any indicator fires.

### 1.3 Strategic posture

| Dimension | Position |
|---|---|
| Category | **Code Semantic Layer** (new category, defined in §7) |
| Positioning | **AI Software Engineering Infrastructure** |
| Primary user | **Autonomous coding agents and the vendors who build them** |
| Primary economic buyer | Developer-tool vendors; platform/architecture organizations |
| Primary interface | **Query API + MCP server.** Not a UI |
| Core asset | Precision at scale, plus accumulated repository history |
| Explicit non-goal | Writing code |

### 1.4 Why the previous architecture cannot get there

Stated once, plainly, because the redesign is a response to it: the prior system grew 25 feature domains on a 575-line parsing-and-chunking foundation, served retrieval from character-window chunks while claiming structural superiority, resolved symbols by name matching, stored graphs as pickled in-memory objects, orchestrated ingestion inside an HTTP handler, and never measured whether any of it beat plain embedding search. Every requirement in this document exists to make one of those things impossible to repeat.

---

## 2. Vision

> **Every codebase maintains an accurate, queryable model of itself — at every commit, in every language, for every consumer.**

Ten-year end state: asking "what breaks if I change this" is as fast, precise, and unremarkable as asking a database for a row. Software comprehension stops being an act of archaeology performed by individuals and becomes a resolved query against shared infrastructure.

---

## 3. Mission

**Build the index that makes software structure a first-class, queryable, versioned asset — and make it precise enough that an autonomous agent can act on its answers without verification.**

Three load-bearing words:

- **Index** — durable, maintained, queried many times per build. Not analysis-on-demand.
- **Versioned** — every answer is scoped to a commit. An unversioned answer about code is a guess about which code.
- **Precise enough to act on** — the acceptance bar is not "helpful to a human reading it." It is "an agent can mutate a codebase based on this without a human checking." That bar is roughly two orders of magnitude higher and it drives nearly every requirement here.

---

## 4. Product Philosophy

### 4.1 Determinism first, probability last

Most questions about code have exact answers. Where is this defined? Who calls it? What imports this module? Is this reachable from an entry point? These are graph and resolution queries with correct answers, computable without a language model.

We MUST answer every question that has an exact answer exactly. Language models are permitted only for the residue: synthesis, explanation, ranking under genuine ambiguity, and natural-language interpretation of intent. A system that asks an LLM "who calls this function" has an architecture defect, not a prompt-tuning opportunity.

Consequence: **a large fraction of our value MUST be deliverable with zero model calls.** This yields determinism, testability, sub-100ms latency, near-zero marginal cost, and offline capability — none of which are achievable if the model sits on the critical path.

### 4.2 Facts and interpretations are different substances and MUST NOT share a store

| | Facts | Interpretations |
|---|---|---|
| Examples | `f` is defined at `a.py:42`; module A imports B; commit c touched 4 files | "This module is over-coupled"; "read these files first"; "this is a repository pattern" |
| Truth condition | Verifiable against source | Depends on a model, threshold, or heuristic |
| Lifetime | Permanent for that commit | Invalidated by any change to our own logic |
| Regeneration | Expensive (requires reparse) | Cheap (recompute from facts) |
| Store | Durable, append-only, immutable | Derived, versioned by *our* algorithm version, freely discardable |

Conflating these is why prior-generation tools rot: an opinion computed in 2024 with 2024 thresholds sits in the same table as a fact, indistinguishable, and nobody dares delete it. We MUST keep two stores with a one-way dependency: interpretations read facts; facts never read interpretations.

### 4.3 Every assertion carries provenance and confidence

Precision varies irreducibly by language, construct, and method. A call edge resolved by a type-aware indexer is not the same object as one guessed by name matching, and an agent MUST be able to tell them apart before acting.

Therefore every edge and every attribute in the index MUST carry:

```
provenance : which extractor produced this, at what version
method     : exact | inferred | heuristic
confidence : [0.0, 1.0]
commit     : the commit this holds for
```

This is the single most important design decision in the product. It converts "our call graph is approximate" from a hidden liability into a typed, filterable, honest property that consumers reason about. It also makes precision improvements measurable rather than anecdotal.

### 4.4 The API is the product; the UI is the proof

Machines will outnumber human consumers of this index by orders of magnitude. We MUST design for the machine consumer first: stable schemas, cheap pagination, deterministic ordering, explicit confidence, versioned contracts, latency budgets. Human interfaces are clients of the same API with no privileged access path. If a UI feature cannot be expressed as public API calls, the API is incomplete — we fix the API, not the UI.

### 4.5 No capability claim without a measurement

Any statement of the form "our X is better than Y" MUST be accompanied by a reproducible benchmark result, committed to the repository, with the dataset and harness available. Marketing copy is generated from benchmark output, not written by hand.

This principle is a direct correction of a prior failure mode: a self-graded quality audit that assessed files which did not exist. The remedy is structural — claims are derived from measurements or they are not made.

### 4.6 Subtraction is a feature

Capability breadth without depth is negative value: it multiplies maintenance, dilutes positioning, and hides the foundation's weakness. A feature that is not consumed, not benchmarked, and not on the critical path MUST be deleted rather than carried. We MUST maintain fewer capabilities at higher precision than the reverse.

### 4.7 Language breadth is bought, not built

We MUST NOT write symbol resolvers. Compiler-grade resolution exists as an ecosystem (SCIP indexers, LSP servers, native compiler front-ends). Our contribution is normalization, persistence, versioning, cross-language joining, and query — not re-implementing name binding for the twentieth language. This is the difference between a two-year roadmap and a ten-year one.

---

## 5. Core Problem

### 5.1 The problem statement

**Software systems exceed the working memory of any individual by three to six orders of magnitude, and no durable, queryable, machine-readable model of their structure exists — so every consumer, human or machine, reconstructs understanding from raw text, repeatedly, incompletely, and at high cost.**

### 5.2 Why it exists — four causal layers

**L1 — Source code is text.** Structure is implicit and recoverable only by parsing plus name resolution. Nothing on disk records that `handler` at line 40 is the same entity as `handler` imported three files away.

**L2 — Structure is not persisted.** IDEs resolve precisely, then discard on close. CI parses, then discards. Every tool re-derives from zero. The industry computes the same graph millions of times per day and stores it approximately never.

**L3 — Relevant information is scattered across systems that never join.** Intent lives in issues. Rationale lives in PR review threads. Constraints live in config and infra. Behavior lives in traces. Ownership lives in org charts. Each is separately queryable; none is joined to the code it concerns.

**L4 — A hard floor: some necessary information was never recorded anywhere.** Why is this timeout 30s? Because in 2019 someone tried 10 and a since-decommissioned service fell over. No parser recovers that.

L1 and L2 are fully solvable and are our Phase 1–3 scope. L3 is solvable with integration work and is where durable differentiation lives. **L4 is not solvable by analysis, only by capture** — recording decisions at decision time and binding them to the code they constrain. We MUST be honest that L4 is a ceiling on any comprehension claim, and we MUST begin capturing at L4 early, because capture value compounds only with elapsed time.

### 5.3 Why it is difficult

| Difficulty | Nature |
|---|---|
| Resolution requires near-compiler semantics | Types, generics, overloads, dynamic dispatch, macros, reflection, DI containers, monkey-patching |
| Correctness is per-language and non-transferable | Each language family is a separate multi-month investment |
| Scale is adversarial | 10M LOC ⇒ ~10⁷ symbols, ~10⁸ edges. Any in-memory design dies here |
| Everything is versioned | The index must be correct for *every* commit and branch, not just HEAD |
| Freshness competes with cost | Full reindex is correct and unaffordable; incremental is affordable and easy to get subtly wrong |
| Static analysis has a truth ceiling | Reflection, DI, config-driven wiring, and codegen are invisible to parsers |
| Precision is invisible until it is catastrophic | A 5%-wrong call graph looks fine in a demo and destroys trust the first time an agent deletes live code |

### 5.4 Why current tools fail

| Class | Approach | Structural failure |
|---|---|---|
| IDE / LSP | Precise, local, in-memory | Session-scoped, single-machine, no whole-repo synthesis, no persistence, no API |
| Code search | Text + precise refs at HEAD | Answers *where*, never *what breaks* or *why*. Requires the user to already know the query. HEAD-only |
| Static analyzers | Rule matching | Encode known-bad patterns. Cannot describe architecture or answer novel questions |
| Architecture tools | Snapshot visualization | Point-in-time artifacts, outside the workflow, no API, no history |
| Embedding RAG | Chunk → embed → similarity | Structurally blind. Cannot compute transitive closure. **Lexical similarity is not a dependency relation** |
| Long-context agents | Read files until understood | Currently effective and improving. Fails on scale, transitive closure, cross-repo, history, latency, and cost |
| Enterprise code intel | Precise, multi-language, indexed | The closest prior art. Built for human search UX; not commit-addressed as a queryable time series; not designed as an agent substrate; the strongest occupant redirected toward agent authoring |

**The honest competitive read:** our real competitor is not embedding-RAG chat, which is already commoditized and dying. It is a two-million-token context window with agentic file navigation, and that competitor improves several-fold per year. We are only defensible where brute force structurally cannot go: very large repositories, transitive closure, cross-repository topology, historical questions, and sub-200ms high-volume querying. **Every requirement in this PRD MUST be justified against that list or dropped.**

---

## 6. Product Definition

### 6.1 Precise definition

> **Repository Intelligence Agent is a repository indexing system that maintains, for each indexed repository and at each indexed commit, a versioned multi-facet model of that repository — its structure, resolved symbol relationships, history, runtime behavior, recorded intent, and human ownership — and exposes that model through a deterministic query API, an MCP server for AI agents, and a set of reference applications built exclusively on that API.**

Decomposed into commitments:

| Clause | Commitment |
|---|---|
| *indexing system* | Precompute and persist. Not analysis-on-request |
| *for each indexed commit* | Commit-addressed. Every query is time-scoped; branches are first-class |
| *versioned multi-facet model* | Five facets (§6.2), independently extensible, jointly queryable |
| *resolved symbol relationships* | Name binding, not name matching. Provenance and confidence on every edge |
| *deterministic query API* | Same inputs ⇒ same outputs. No model in the fact path |
| *MCP server for AI agents* | Agents are a first-class client class, not an integration |
| *reference applications built exclusively on that API* | No privileged internal access. Dogfooding is architecturally enforced |

### 6.2 The five facets

```
                REPOSITORY DIGITAL TWIN  @commit
   ┌───────────┬───────────┬───────────┬───────────┬───────────┐
   │ STRUCTURE │  HISTORY  │  RUNTIME  │  INTENT   │  SOCIAL   │
   ├───────────┼───────────┼───────────┼───────────┼───────────┤
   │ files     │ commits   │ coverage  │ ADRs      │ ownership │
   │ symbols   │ churn     │ traces    │ issues    │ reviewers │
   │ imports   │ evolution │ profiles  │ PR ration.│ expertise │
   │ calls     │ authorship│ incidents │ specs     │ team map  │
   │ types     │ lifetimes │ perf      │ constraints│ bus factor│
   │ modules   │ hotspots  │ errors    │ invariants│           │
   ├───────────┴───────────┴───────────┴───────────┴───────────┤
   │            ONE QUERY SURFACE · ONE ID SPACE               │
   └───────────────────────────────────────────────────────────┘
     P1-P3          P3-P4        P4-P5       P5-P6      P4
```

Structure is **one facet of five**, not the whole model. This is a deliberate correction: the durable advantage lies in facets competitors do not maintain — history, runtime, intent — and in the *joins* between facets. Joins are the product's unique capability surface:

- structure × history → "this module's coupling has doubled in six months"
- structure × runtime → "this code is statically reachable but never executed in production"
- structure × intent → "this change violates a constraint recorded in ADR-014"
- structure × social → "the only person who understands this subsystem left"
- history × runtime → "changes to this module correlate with incidents at 4× base rate"

No competitor can answer any of those, and none of them is reachable from a context window.

### 6.3 What this product is NOT

Normative non-goals. Each MUST be refused, including when a customer asks.

| Non-goal | Reason |
|---|---|
| **Code generation / autocomplete** | Distribution-locked market against vastly better-resourced incumbents. We are the substrate they consume |
| **An IDE or IDE replacement** | We ship thin clients into IDEs; we do not compete with them |
| **A chat product** | Chat is a reference client that demonstrates the index. It is never the roadmap driver |
| **A security scanner** | Owned by mature specialists. We MAY expose structure to them via API |
| **A documentation generator** | Low trust, commodity, immediately stale |
| **A linter / style enforcer** | Solved. We enforce *architecture*, which is not solved |
| **Autonomous code modification (through Phase 6)** | Requires trust we have not earned. Revisit only after sustained precision evidence |

---

## 7. Product Positioning

### 7.1 Options evaluated

| Candidate | Verdict |
|---|---|
| AI Repository Chat | **Reject.** Commodity, dozens of implementations, no defensibility, no buyer |
| Repository Intelligence Platform | **Reject.** Accurate but inert. Names a feature bucket, not a budget line. No buyer has this in their org chart |
| AI Engineering Platform | **Reject.** Implies authoring and execution. We deliberately do not do those |
| Code Knowledge System | **Reject.** Adjacent to enterprise-search vendors; invites the wrong comparison and the wrong buyer |
| **AI Software Engineering Infrastructure** | **Adopt** |

### 7.2 Justification

**Infrastructure** is chosen because every structural property of the product is an infrastructure property:

1. **Consumed by other software, not primarily by people.** Machines are the majority client. That is the definition of infrastructure.
2. **Value scales with query volume, not seats.** A team of 20 with 5 agents generates more index load than 200 humans. Seat pricing mismodels the value; usage pricing fits it.
3. **Correctness is the product; UX is a wrapper.** Infrastructure competes on precision, latency, availability, and freshness — measurable properties, not taste.
4. **It becomes load-bearing and therefore hard to remove.** Once an agent's retrieval path or a team's merge gate depends on us, removal has a cost. That is how infrastructure businesses defend themselves.
5. **It survives application-layer churn.** Cursor, Devin, Copilot, and their successors will rise and fall. All of them need repository context. Infrastructure outlives its clients — the historically strongest position in developer tooling.

**The strategic cost, stated plainly:** infrastructure has a slower, harder go-to-market. No viral bottom-up adoption, no screenshot-driven growth, a small number of demanding integration partners, and a long proof cycle. We accept that cost in exchange for a defensible position, and we mitigate it with a free, open, aggressively distributed MCP server (§9.3).

---

## 8. Product Category

### 8.1 Definition

> ## The Code Semantic Layer
>
> A persistent, commit-addressed, precision-resolved model of a codebase that any tool or agent queries instead of re-deriving structure from source text.
>
> **A Code Semantic Layer MUST provide:**
> 1. **Resolution** — name binding, not name matching, with declared method and confidence
> 2. **Versioning** — queryable at any indexed commit or branch
> 3. **Multi-facet joins** — structure joined with history, runtime, intent, ownership
> 4. **A machine-first query contract** — stable, deterministic, paginated, versioned, latency-bounded
> 5. **Incremental maintenance** — freshness proportional to change size, not repository size
> 6. **Declared precision** — published, benchmarked accuracy per language and per relation type

Clause 6 is the one that makes the category real rather than rhetorical. Every prior generation of code-intelligence tooling shipped unquantified accuracy. A semantic layer that will not state its precision is not a semantic layer; it is a heuristic with a REST interface.

### 8.2 Why the category is real

Every data ecosystem develops a semantic layer once consumers multiply past the point where per-consumer extraction is tolerable. BI got dbt and Cube. Observability got OpenTelemetry. Search got Elasticsearch. Feature engineering got feature stores. The pattern is invariant: N consumers each build bespoke low-quality extraction over one substrate, until the extraction is factored out and standardized.

AI coding is exactly at that inflection. Every agent product independently implements repository context extraction. Every one does grep plus embeddings plus heuristics. Every one does it badly, because retrieval is not their differentiator and will never receive their best engineers. That is a factoring waiting to happen.

### 8.3 Category ownership requirements

| Requirement | Why it is the gate |
|---|---|
| Publish the benchmark and the harness | Defines the axis of competition on our terms |
| Open-source the client protocol (MCP server, SDKs) | No agent vendor adopts a closed retrieval dependency |
| Publish the index schema as a versioned spec | A category needs an interoperable contract |
| Be first to precise + versioned + multi-facet | Simultaneity is the claim; any one of the three alone is prior art |

---

## 9. Target Users

### 9.1 Ranking

Scored 1–10 per axis. Strategic value weighted ×2 because early-stage sequencing is about compounding, not immediate revenue.

| Rank | User | Pain | WTP | Reach | Strategic ×2 | **Total /50** |
|:--:|---|:--:|:--:|:--:|:--:|:--:|
| **1** | **AI coding agent / dev-tool vendor** | 9 | 9 | 6 | 10 | **44** |
| **2** | **Platform / Architecture organization** | 9 | 9 | 4 | 8 | **38** |
| **3** | **Staff / Principal engineer** | 8 | 4 | 8 | 8 | **36** |
| 4 | Enterprise modernization program | 9 | 9 | 4 | 5 | 32 |
| 5 | Engineering manager | 7 | 6 | 6 | 5 | 29 |
| 6 | Senior engineer | 6 | 4 | 8 | 5 | 28 |
| 7 | Open-source maintainer | 7 | 2 | 9 | 5 | 28 |
| 8 | Junior engineer | 9 | 1 | 8 | 3 | 24 |
| 9 | CTO / VP Engineering | 5 | 8 | 3 | 4 | 24 |

### 9.2 Rank 1 — AI coding agents and their vendors

**Identity.** The retrieval subsystem of every agentic coding product, plus every internal agent platform at organizations with 500+ engineers.

**Pain.** Asked to "add rate limiting to the payments endpoint," an agent must locate the endpoint, its middleware chain, existing rate-limit precedents, the config surface, the tests, and the blast radius. Today it burns 30–60k tokens and 20–60 seconds of speculative file reading to assemble what a resolved index returns in 50ms and 2k tokens — and it still hallucinates import paths.

**Workflow — this is the product shape.**

```
agent  ──▶ resolve_symbol("RateLimitMiddleware", commit=HEAD)
       ◀── {file, span, signature, kind, confidence: 1.0, method: exact}

agent  ──▶ find_references(sym, kind=[call, import], depth=2)
       ◀── 7 sites, each {file, span, method: exact}

agent  ──▶ blast_radius(files=["backend/security_middleware.py"])
       ◀── {files: 14, symbols: 31, tests: 6, public_api_affected: false,
            confidence: 0.94, unresolved_edges: 3}

agent  ──▶ find_precedents("rate limiting", k=3)
       ◀── 3 in-repo implementations with spans

agent  ──▶ tests_for(files=[...])
       ◀── 6 test files, 11 test functions

agent  ──▶ writes patch. ~4k tokens. No exploration. No hallucinated imports.
```

**Value proposition, expressed only in numbers because that is the only language this buyer accepts:**

| Metric | Target |
|---|---|
| Context tokens per task | −70% vs. grep + embeddings |
| Retrieval recall@10 on real issue→PR tasks | ≥0.70 (baseline ~0.40) |
| Hallucinated import/path rate | ≈0 (paths are index-verified) |
| Time to assemble context | <500ms p95 (vs. 20–60s) |
| First-pass patch acceptance | +10–20pp |

**Why they buy rather than build.** Precise multi-language resolution is 12–24 engineer-months per language family, is nobody's differentiator, and never wins the internal prioritization argument against model quality and product surface.

**Hard blockers we MUST clear before this user is addressable:** precise resolution (not heuristic), commit and branch scoping, <200ms p95, published benchmark, MCP-native interface, self-hosted option for code-egress-sensitive customers. Every one is a Phase 2–3 deliverable. This ranking is therefore a *forcing function on the roadmap*, not a market observation.

### 9.3 Rank 2 — Platform / Architecture organization

**Pain.** Custodian of a system nobody fully understands. Cannot answer: what breaks if we change this, which modules violate our layering, is coupling worsening, can we delete this, which services depend on the thing we are decommissioning.

**Workflow — the critical insight is that reporting is worthless and enforcement is not.**

```
1. Declare intended architecture     .repo-intel.yml (layers, allowed edges,
                                      public API contracts, cycle budget)
2. Every PR                          index the merge commit; diff structure;
                                      evaluate declared rules
3. Violation                         merge check fails with the exact edge,
                                      the rule it breaks, and the commit that
                                      introduced it
4. Weekly                            drift trend, coupling trajectory,
                                      hotspot movement, ownership risk
5. Quarterly                         evolution review from real history
```

A report is read once and filed. **A merge gate changes behavior permanently and becomes politically impossible to remove.** Architecture fitness functions in CI are the highest-retention capability available to this product, and they are a thin layer over structure + history + declared intent.

**Blockers:** their languages (Java, Go, Kotlin, C#), multi-repository topology, SSO/RBAC, self-hosted deployment, audit trail.

### 9.4 Rank 3 — Staff / Principal engineer

Our champion and our worst buyer: highest genuine enthusiasm, near-zero budget authority. Treat explicitly as the **distribution channel to Rank 2**, never as a revenue line. Give them free, excellent, individually useful tooling — CLI, IDE client, impact analysis — and design it to make an organizational case on their behalf.

### 9.5 Rank 8 — Junior engineer, deliberately deranked

Maximum pain, zero budget, and a genuine pedagogical hazard: struggling through a codebase is how structural intuition forms, and a tool that answers everything builds dependence rather than competence. We serve them (free tier, reading paths, explanations) but MUST NOT let their needs drive the roadmap. Leading with onboarding is a positioning error that anchors the product to the user with the least willingness to pay.

---

## 10. Value Proposition and Competitive Advantage

### 10.1 Against each named competitor

| Competitor | Their strength | Our relationship | Honest statement |
|---|---|---|---|
| **GitHub Copilot** | Authoring; distribution in every VS Code install | **Complement** | We do not compete. We are the structural index its agent mode lacks |
| **Cursor** | Best-in-class authoring loop and UX | **Complement, integration target** | Their retrieval is embeddings + grep. That is the gap we fill |
| **Claude Code** | Strongest reasoning; excellent agentic loop | **Complement, first MCP target** | It navigates files well and holds no persistent model. We are its memory |
| **Sourcegraph** | Precise navigation, 30+ languages, enterprise scale | **Closest prior art; primary technical benchmark** | They are ahead on precision and breadth. We differ on being commit-addressed, multi-facet, and agent-first. Their pivot toward agent authoring vacated this position — but the entry fee is the resolution layer they already built and we have not |
| **Devin** | Autonomous end-to-end task execution | **Complement** | It burns enormous context on exploration. We are the substrate that reduces it |
| **Continue** | Open, extensible, self-hostable | **Complement, easiest integration** | Open ecosystem, MCP-native. Best first partner |
| **OpenHands** | Open agent platform | **Complement** | Same shape as Continue |

**Note the pattern: six of seven are complements, not competitors.** That is the strongest available signal that the positioning is correct. A product whose "competitors" all want to consume it is infrastructure.

Our only genuine competitors: Sourcegraph's code-intel layer, in-house indexes at large agent vendors, and the improving economics of long-context brute force.

### 10.2 Why choose us instead of any of them

Because the question is malformed. Nobody chooses us *instead of* Cursor; they run Cursor *on top of* us. The correct framing:

| For | The alternative to us is | We win because |
|---|---|---|
| An agent vendor | Building your own index, badly | Precision you would not fund, on languages you would not staff, benchmarked publicly |
| A platform team | Manual review + architecture diagrams that lie | Continuous, enforced, versioned, historical — a merge gate rather than a slide |
| A staff engineer | Reading code for three days | Exact transitive answers in milliseconds |
| An enterprise | An unmodifiable legacy system | Precise blast radius and dependency truth before a migration commits budget |

### 10.3 Competitive advantage by time horizon

**Short-term (0–18 months) — execution advantages, all copyable in 3–6 months**

1. Commit-addressed index (nobody ships structural time-travel as a query parameter)
2. Provenance and confidence on every edge (nobody publishes precision honestly)
3. Published benchmark defining the competitive axis
4. MCP-native from day one
5. Deterministic-first architecture: near-zero marginal cost per query, offline-capable

**Long-term (18 months–10 years) — the four durable moats, ranked**

| Rank | Moat | Type | Why durable | Time to replicate |
|:--:|---|---|---|---|
| **1** | **Accumulated repository history corpus** | Data | Requires elapsed calendar time. Cannot be bought, scraped, or backfilled | = our age |
| **2** | **Embedded position in agent retrieval loops** | Integration | Removal degrades the client's own eval scores. Switching cost is their regression | 12–24 mo + displacement |
| **3** | **CI merge-gate installation** | Workflow | Gates accrete rules; rules encode institutional decisions; nobody removes a passing gate | 12–18 mo |
| **4** | **Multi-language precision at scale** | Technical | Genuinely hard, but publicly documented (SCIP/LSIF/stack-graphs). Entry fee, not a moat | 18–30 mo |

The ordering is the strategy. Most engineering instinct pushes toward moat 4 because it is the most technically interesting. **Moat 1 is worth more and requires only that we start indexing continuously, early, and never stop.** Every month of delay is a month of moat that cannot be recovered later at any price.

**Network effects.** Weak-to-moderate and we MUST NOT overclaim them. Real ones: (a) each new language indexer raises value for all polyglot users; (b) a larger indexed corpus improves cross-repo benchmarking percentiles for everyone; (c) MCP ecosystem adoption is a standards effect — each integration raises the cost of a competing protocol; (d) published benchmarks attract contributed evaluation datasets. Absent: no user-to-user effect. A second user on the same repository adds nothing directly.

**Research advantages.** Three genuinely publishable questions, each producing artifacts that double as marketing: (i) does resolved structural retrieval beat embedding retrieval on real repository tasks, and by how much, per language — with free labels from issue-linked merged PRs; (ii) can architectural degradation be forecast from structural time series; (iii) what is the token-precision Pareto frontier for agent context assembly. Owning the benchmark for (i) is a category-defining asset.

---

## 11. Product Principles

Each principle states what it forbids, because a principle that forbids nothing is a slogan.

| # | Principle | Forbids | Rationale |
|:--:|---|---|---|
| **P1** | **One index, one source of truth** | Any feature computing its own structure; any parallel retrieval stack | Divergence between subsystems is unresolvable and every duplicate is a permanent tax. Directly targets the prior system's two chat stacks and two build pipelines |
| **P2** | **Determinism before probability** | LLM calls for questions with exact answers | Determinism buys testability, latency, cost, and offline use. An LLM asked "who calls this" is an architecture defect |
| **P3** | **Resolution, not matching** | Name-equality-based edges presented as facts | The difference between advisory and actionable. The precision floor of the entire product |
| **P4** | **Every answer carries provenance, confidence, and a commit** | Bare unattributed results | Consumers must calibrate trust. Enables honest degradation instead of silent error |
| **P5** | **Commit-addressed or invalid** | HEAD-only answers | Agents work on branches; reviews concern diffs. An unversioned answer is a guess about which code |
| **P6** | **Facts and interpretations in separate stores** | Persisting opinions alongside facts | Opinions are invalidated by our own logic changes; facts are not. Prevents rot |
| **P7** | **The API is the product** | Privileged internal access paths for our own UIs | Guarantees the machine consumer is first-class and the API is complete |
| **P8** | **No claim without a benchmark** | Unmeasured capability assertions in any document or UI | The remedy for the prior credibility failure. Claims are generated from measurements |
| **P9** | **Incremental by construction** | Any design where update cost scales with repository size | Freshness is a hard requirement at scale; retrofitting incrementality is a rewrite |
| **P10** | **Buy language breadth, build the layer above it** | Hand-written resolvers | Ten-year roadmaps do not include reimplementing name binding twenty times |
| **P11** | **Degrade explicitly, never silently** | Falling back to a weaker method without saying so | Silent degradation is the most expensive failure mode in analysis tooling: it looks like success |
| **P12** | **Subtract before adding** | Carrying unconsumed, unbenchmarked capability | Breadth without depth is negative value |

### 11.1 Principle conflict resolution

Principles will conflict. Precedence order, highest first:

```
P3 Resolution  >  P4 Provenance  >  P5 Commit-addressed  >  P2 Determinism
>  P1 Single index  >  P9 Incremental  >  P8 Benchmark  >  everything else
```

Worked example: precise resolution for a language is unavailable, but a customer needs coverage now. P3 says do not ship name matching as fact; P4 says label everything. Resolution: ship it, labelled `method: heuristic` with measured confidence, excluded by default from `blast_radius` and any agent-actionable query, included in advisory queries when the caller explicitly opts in. **P3 and P4 together permit imprecision but forbid dishonesty about it.**

---

## 12. Success Metrics

### 12.1 North Star

> **Structural queries served per week against indexes that are fresh (< 1 commit stale), by consumers other than ourselves.**

Chosen because it is simultaneously falsifiable and captures every dimension of the thesis: *queries* means the index is used; *structural* means for what it is uniquely good at; *fresh* means incrementality works; *by consumers other than ourselves* forbids self-dealing through our own demo apps.

Anti-gaming: our own applications' queries are counted separately and never in the North Star.

### 12.2 Metric tree

```
NORTH STAR: fresh external structural queries / week
│
├── ADOPTION
│   ├── repositories under continuous indexing
│   ├── distinct external consumers (agents, tools, CI installs)
│   ├── MCP server installs (weekly active)
│   └── repos with ≥1 enforced CI gate          ◀ strongest retention signal
│
├── QUALITY  (gates release; regressions block merge)
│   ├── symbol resolution precision / recall, per language
│   ├── call-edge precision / recall, per language
│   ├── retrieval recall@10, MRR on issue→PR benchmark
│   ├── blast-radius precision / recall vs. actual PR file sets
│   ├── citation validity rate (cited span exists and is relevant)
│   └── % of index edges with method=exact       ◀ single best precision proxy
│
├── PERFORMANCE
│   ├── query latency p50 / p95 / p99, by query class
│   ├── incremental index p95 (target: <2s for ≤10 changed files)
│   ├── cold index throughput (kLOC / minute)
│   ├── freshness lag (commit → queryable), p95
│   └── index size / MLOC
│
├── EFFICIENCY
│   ├── tokens per agent task vs. baseline    ◀ the number that sells
│   ├── LLM cost per answered question
│   ├── % of queries answered with zero model calls  (target ≥80%)
│   └── infra cost per MLOC-month
│
└── BUSINESS
    ├── external-consumer retention (M3, M6, M12)
    ├── index API revenue / total revenue    ◀ proves infra positioning
    ├── net revenue retention
    └── enforced-rule count per installation (expansion proxy)
```

### 12.3 Phase gates — quantified, non-negotiable

No phase begins until the prior gate passes on committed, reproducible measurements.

| Gate | Criterion |
|---|---|
| **G1 → Phase 2** | Benchmark harness committed and runnable; baseline published for ≥10 repositories; ≥3 retrieval arms compared; CI fails on regression |
| **G2 → Phase 3** | Symbol resolution precision ≥0.95 / recall ≥0.90 on Python + TypeScript; ≥80% of call edges `method=exact` |
| **G3 → Phase 4** | Retrieval recall@10 ≥0.70 on issue→PR (baseline ≤0.45); ≥40% token reduction at equal or better recall |
| **G4 → Phase 5** | 1M+ LOC repository indexed; query p95 <200ms; incremental p95 <2s for ≤10 files |
| **G5 → Phase 6** | ≥2 external agent products in production on our MCP server; ≥50 repositories with an enforced CI gate |
| **G6 → Phase 7** | 12+ months of continuous history on ≥1,000 repositories; ≥1 predictive claim validated out-of-sample |

### 12.4 Metrics we explicitly refuse to optimize

| Refused | Why |
|---|---|
| Lines of code, service count, endpoint count | The prior architecture optimized these to its own detriment |
| Feature count | Directly opposed to P12 |
| GitHub stars | Vanity, weakly correlated with infrastructure adoption |
| Chat sessions | Chat is a demo. Growth here signals drift from the thesis |
| Dashboard MAU | Same |
| Languages "supported" | Meaningless without per-language precision. Report precision or say nothing |

---

## 13. Roadmap

Seven phases. Each carries objectives, deliverables, milestones, risks, and dependencies. Durations assume a small senior team and are ranges, not commitments.

### Phase 1 — Foundation (0–3 months)

**Objective.** Establish measurement, delete unearned surface, and build the ingestion and storage spine that everything else assumes.

**Deliverables**
- Evaluation harness: issue→PR retrieval benchmark generated from git history; ≥10 repositories; ≥4 retrieval arms; committed datasets; CI regression gate
- Baseline results published in the repository
- Commit-addressed storage spine: content-addressed file units, commit-keyed index sets, structural sharing
- Job orchestration: durable queue, worker pool, idempotent tasks, retry, cancellation
- Ingestion service extracted from any HTTP handler; clone/fetch/webhook driven
- Tree-sitter parse layer via **queries**, not hand-rolled child traversal
- AST-boundary chunking replacing character windows
- Facts store (durable, append-only) and derived store (disposable) physically separated
- Dependency inversion enforced: domain code MUST NOT import delivery code; CI-checked
- Subtraction: all stubs, placeholder routers, dead pipelines, duplicate stacks, and vendored artifacts removed; all documentation reconciled to measured reality

**Milestones.** M1.1 harness runs. M1.2 baseline published. M1.3 subtraction complete. M1.4 commit-addressed ingest end-to-end. M1.5 chunking delta measured and published.

**Risks.** Benchmark labels are noisy (mitigate: filter to single-issue PRs under 20 files, hand-audit a sample). Subtraction resistance (mitigate: gate — no Phase 2 work merges until complete).

**Dependencies.** None. This phase is the prerequisite for everything.

---

### Phase 2 — Repository Intelligence Core (3–8 months)

**Objective.** Replace heuristic structure with resolved structure. This is the phase that determines whether the product is advisory or actionable.

**Deliverables**
- SCIP ingestion pipeline: normalize `scip-python`, `scip-typescript` into the resolution store
- Resolution layer: monikers, name binding, import resolution, type-informed dispatch where available
- Provenance and confidence on every edge (P4), enforced by schema — an edge without them MUST NOT be storable
- Explicit degradation ladder: `exact` → `inferred` → `heuristic`, labelled and independently queryable
- Graph engines rebuilt on resolved input: dependency, call, module, architecture
- Framework-awareness for entry points (web routes, DI containers, task queues, test discovery, event handlers) to eliminate the dead-code false-positive class
- Precision benchmark per language, per relation type, published

**Milestones.** M2.1 SCIP ingest for Python. M2.2 TypeScript. M2.3 confidence model enforced in schema. M2.4 G2 gate met. M2.5 dead-code false-positive rate <2% on a framework-heavy corpus.

**Risks.** Indexer coverage gaps (mitigate: labelled heuristic fallback, never silent — P11). SCIP normalization is harder than expected (mitigate: timebox; fall back to LSP-driven extraction).

**Dependencies.** Phase 1 storage spine and harness.

---

### Phase 3 — Repository Digital Twin (8–14 months)

**Objective.** Make the multi-facet, versioned twin real and queryable as a unit.

**Deliverables**
- Twin assembly and materialization at commit granularity, with structural sharing between commits
- Branch and merge-base support; diff-of-twins as a first-class operation
- History facet: full commit/churn/authorship/lifetime model joined to structural identity
- Social facet: ownership, expertise, bus-factor derived from blame × structure
- Query API v1 frozen: ~20 primitives (see Twin Specification §7), versioned contract, deterministic ordering, pagination, latency budgets
- MCP server as the primary product surface, open-sourced
- Snapshot, retention, and eviction policy
- Scale target: 1M+ LOC repository within latency budget

**Milestones.** M3.1 twin materialized at arbitrary commit. M3.2 twin diff. M3.3 API v1 frozen. M3.4 MCP server published. M3.5 G4 gate met.

**Risks.** Storage growth from per-commit materialization (mitigate: structural sharing, aggressive eviction of derived data, facts-only durability). API v1 frozen too early (mitigate: explicit experimental namespace, and freeze only after two external consumers).

**Dependencies.** Phase 2 resolution.

---

### Phase 4 — AI Reasoning Engine (12–18 months, overlaps Phase 3)

**Objective.** Make the twin the substrate for tool-using reasoning, and make agents first-class clients.

**Deliverables**
- Tool-calling loop replacing fixed pre-fetch: the model queries the twin iteratively rather than receiving one pre-assembled blob
- Retrieval planner: hybrid seeding (vector for seeds, graph for expansion — fixing the seed-starvation failure where empty entity extraction silently collapses to plain vector search)
- Context assembler with real tokenization and knapsack packing under a declared budget
- Citation verification: every cited span MUST be verified to exist at the queried commit before the answer is emitted
- Runtime facet v1: coverage ingestion → execution-weighted graphs, dead-code precision, real hotspot ranking
- Prompt registry with versioning and A/B capability
- Answer-quality evaluation integrated into the same harness as retrieval

**Milestones.** M4.1 tool loop in production. M4.2 G3 gate met. M4.3 coverage-fused dead-code detection. M4.4 citation validity >0.98.

**Risks.** Tool loops increase latency and cost (mitigate: aggressive caching, deterministic fast paths, bounded iteration). Coverage data is unavailable in many repos (mitigate: treat as optional enrichment, never a dependency).

**Dependencies.** Phase 3 query API.

---

### Phase 5 — Developer Experience (16–24 months)

**Objective.** Make the index adoptable and its value visible, without letting the UI become the product.

**Deliverables**
- CI/CD integration: GitHub App and equivalents — PR blast radius, affected tests, drift violations, merge checks
- Architecture fitness functions: declarative rules in `.repo-intel.yml`, enforced at merge
- IDE clients (thin, API-only): hover, callers, blast radius, precedent search
- CLI parity with the API
- Reference web application: architecture, evolution, health, findings — as an API client with no privileged access
- Reports as the shareable artifact for non-users

**Milestones.** M5.1 merge gate blocking a real violation in a real repository. M5.2 IDE client shipped. M5.3 G5 gate met.

**Risks.** UI gravity pulls the roadmap (mitigate: P7 enforced architecturally — UIs cannot access internals). Gate false positives destroy trust (mitigate: warn-only mode by default, promote to blocking only after a measured clean period).

**Dependencies.** Phase 3 API, Phase 2 precision.

---

### Phase 6 — Enterprise Platform (22–36 months)

**Objective.** Make the platform deployable and purchasable inside large organizations.

**Deliverables**
- Multi-tenancy with hard isolation; RBAC; SSO/SAML/SCIM; audit log
- Self-hosted and VPC deployment; air-gapped option
- Multi-repository and service topology: cross-repo dependency resolution, API-contract-level edges between services
- Enterprise language families: Java, Go, C#, Kotlin
- Quotas, cost accounting, per-tenant SLOs
- Index API as a commercial product with published SLAs

**Milestones.** M6.1 self-hosted GA. M6.2 cross-repo topology. M6.3 Java + Go at G2 precision. M6.4 first enterprise deployment at ≥5M LOC.

**Risks.** Enterprise requirements consume all capacity (mitigate: ring-fence platform capacity separately from core index capacity). Per-language precision regresses under breadth pressure (mitigate: G2 precision gate applies per language, without exception).

**Dependencies.** Phases 2–5.

---

### Phase 7 — Autonomous Engineering Platform (36+ months)

**Objective.** Convert accumulated history into capabilities that require no competitor-reachable input.

**Deliverables**
- Intent facet: ADR capture bound to code, continuous conformance checking, constraint violation detection at merge
- Predictive engineering: incident-risk forecasting from structural time series, validated out-of-sample
- Cross-repository benchmarking: percentile position on coupling, cycles, hygiene, evolution rate
- Agent memory service: durable per-repository working knowledge shared across agent sessions and vendors
- Carefully bounded write actions: mechanical, verifiable refactors only, always PR-gated, never merged autonomously

**Milestones.** M7.1 intent conformance blocking a violating merge. M7.2 validated out-of-sample risk prediction. M7.3 G6 gate met.

**Risks.** Prediction claims outrun evidence (mitigate: P8 — out-of-sample validation or no claim). Write actions damage trust (mitigate: mechanical-only, reversible, PR-gated, opt-in).

**Dependencies.** Sustained history from Phase 3 onward. **This phase cannot be accelerated by funding or headcount; it is gated on elapsed calendar time, which is precisely why it is the strongest moat.**

---

### Roadmap dependency structure

```
P1 Foundation ─────┬──▶ P2 Core ──────┬──▶ P3 Twin ──┬──▶ P4 Reasoning ──┐
 measurement       │   resolution      │   versioned  │   tool loops      │
 storage spine     │   provenance      │   multi-facet│   runtime facet   │
 subtraction       │                   │   API v1     │                   │
                   │                   │   MCP        ├──▶ P5 DX ─────────┤
                   │                   │              │   CI gates        │
                   └───────────────────┴──────────────┴──▶ P6 Enterprise ─┤
                                                          tenancy, langs   │
                                                                           ▼
                                                              P7 Autonomous
                                                              (gated on TIME)

Critical path: P1 → P2 → P3 → P4.  P5 and P6 parallelize once P3 API is frozen.
```

---

## 14. Open Questions

Recorded rather than resolved, because a foundation document that pretends certainty is less useful than one that names its uncertainty.

| # | Question | Resolve by | Consequence if we get it wrong |
|:--:|---|---|---|
| Q1 | Does resolved structural retrieval materially beat embedding retrieval on real tasks? | Phase 1 benchmark | If no, the entire thesis fails and we should stop |
| Q2 | What is the true precision ceiling per language for dynamic languages? | Phase 2 | Determines which markets are addressable at all |
| Q3 | Do agent vendors adopt an external index, or insist on in-house? | Phase 3–4 pilots | Determines whether the primary user is reachable |
| Q4 | Is the buyer the vendor or the enterprise? | Phase 5–6 | Determines pricing model and GTM shape |
| Q5 | Will context economics erase the wedge before we reach scale? | Continuous | Existential. Watch the §1.2 indicators |
| Q6 | Does per-commit materialization stay economically viable at enterprise scale? | Phase 3 | May force lazy materialization and a latency renegotiation |
| Q7 | Can architectural degradation actually be forecast? | Phase 7 | Determines whether the history moat converts into product value |
