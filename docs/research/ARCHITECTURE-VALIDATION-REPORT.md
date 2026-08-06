# Repository Intelligence Agent — Independent Architecture Validation

**Report type:** External architecture research and validation review
**Perspective:** Reviewed as if designed by a third party. No deference to existing decisions.
**Date:** 2026-07-25
**Audience:** Staff Engineer / Principal Engineer / CTO making a build-or-abandon decision
**Scope reviewed:** `docs/foundation/{01-PRD,02-SDD,03-DIGITAL-TWIN-SPEC}.md`, `docs/foundation/milestones/M1–M12`, `ria/` (29.9k LOC), `backend/`+`services/`+`core/` (legacy, ~31k LOC), CI, Docker, tests

---

## 0. Evidence basis and epistemic labels

This report separates three kinds of statement. Every significant claim carries one.

| Label | Meaning |
|---|---|
| **[REPO]** | Verified by reading this repository's files. Path cited. |
| **[DOC]** | Documented publicly by the vendor or in a peer-reviewed/arXiv paper. URL cited. |
| **[INFER]** | Informed inference from public behaviour, third-party analysis, or engineering first principles. Explicitly not a documented fact. |

**On proprietary systems.** Cursor, Devin, Windsurf, Copilot, Codex and Jules do not publish full internal architectures. Where this report describes them, it uses only vendor engineering posts, vendor docs, or clearly-labelled third-party analysis. No internal architecture is invented. Where public information is absent, this report says so rather than guessing.

**Third-party sources of variable reliability.** Several search results came from SEO content farms (`markaicode.com`, `fast.io/resources`, `skywork.ai`). Claims sourced only from those sites are **not** used as evidence in this report. Where they were the only source for a topic, the topic is marked *no reliable public information*.

---

## 1. Executive Summary

### 1.1 The one-paragraph verdict

RIA's foundation documents are the strongest artefact in the repository — the layering, the hard determinism boundary, the commit-addressed identity model, and the executable architecture fitness tests are genuinely at or above industry practice, and the reasoning quality in `02-SDD.md` exceeds what most Series-A engineering orgs produce. But the *architecture as specified* and the *architecture as built* are two different systems, and the *architecture as shipped* is a third. The 12-milestone plan is a waterfall of horizontal layers with no delivery surface, no evaluation harness, and no measurement of its central precision claim; the top five milestones (M8–M12) duplicate exactly the part of the stack that every agent vendor already owns and defends, while contradicting the PRD's own stated non-goals; and the storage substrate (single-file SQLite, whole-graph-in-memory traversal) contradicts the SDD's own load-bearing constraint. The bottom half is worth building. The top half is worth deleting.

### 1.2 Top ten findings, ranked by decision impact

| # | Finding | Severity | Evidence |
|---|---|---|---|
| 1 | **The product has no delivery layer.** `ria/` has no REST, MCP, GraphQL or CLI surface, is imported by nothing outside its own tests, and is not copied into the Docker image. 29.9k LOC of unreachable code. | **Critical** | [REPO] `Dockerfile` copies `backend core services models storage agents memory` only; no `ria` |
| 2 | **The central differentiation claim is unmeasured.** PRD §12.3 / SDD §8.3 make ≥0.95 precision / ≥0.90 recall blocking gates. CI runs `ruff check`, `ruff format --check`, `pytest`. No benchmark, no coverage gate, no type checker. | **Critical** | [REPO] `.github/workflows/ci.yml`; no `[tool.mypy]`/`[tool.coverage]` in `pyproject.toml` |
| 3 | **Graph layer violates the SDD's own constraint.** SDD §1.3 constraint 2: "no design may require loading a whole-repository graph into a process… eliminates the in-memory graph-object approach categorically." `GraphTraversalService.breadth_first(graph: Graph, …)` takes the whole graph object; `SqliteGraphCacheStore.put` serialises the entire snapshot to one JSON column. | **Critical** | [REPO] `ria/application/graph_traversal_service.py`, `ria/infrastructure/storage/sqlite/graph_store.py` |
| 4 | **M11/M12 fabricate verification evidence.** `ToolExecutionService.execute_action` returns hardcoded strings including "All tests passed successfully" and "Build artifacts compiled cleanly" without running anything. In a system whose entire value proposition is grounded, provenance-carrying answers, this is worse than absent. | **Critical** | [REPO] `ria/application/tool_execution.py` |
| 5 | **M8–M12 contradict the PRD.** PRD §1.3 lists "Writing code" as explicit non-goal and "Query API + MCP server. Not a UI" as the primary interface. M10 (9 agent roles, conflict resolution), M11 (workflow execution), M12 (patch/commit/PR generation) build a competing agent platform instead. | **High** | [REPO] `01-PRD.md` §1.3 vs milestones M10–M12 |
| 6 | **No retrieval mechanism of any competitive kind.** No embeddings (banned package-wide by architecture test), no lexical/trigram index, no ripgrep path. Symbol lookup is exact-name only over SQLite. Every named competitor has at least one of: embeddings, trigram index, or agentic grep. | **High** | [REPO] `tests/ria/integration/test_architecture_rules.py::TestNoModelCallsBelowReasoning` |
| 7 | **Language breadth is 3 (Python, JS, TS), Tier A only.** PRD P10 "buy language breadth" via SCIP/LSP is specified in SDD §2.1 and entirely unimplemented — no `ScipIndexerPort` exists. Sourcegraph and Serena reach 30–40+ languages precisely by consuming LSP/SCIP. | **High** | [REPO] `ria/ports/` has no SCIP/LSP port; [DOC] Serena is LSP-over-MCP across 40+ languages |
| 8 | **Specified infrastructure is entirely absent.** SDD §6.2 names PostgreSQL (facts spine), S3-compatible blob store, Redis (cache/queue/rate-limit/session), vector DB. Implementation: one SQLite file carries facts, derived data, all caches, and the job queue. | **High** | [REPO] `ria/infrastructure/storage/sqlite/` (20 modules); no Postgres/Redis/S3 adapter |
| 9 | **Model providers are echo stubs.** `OpenAIModelProvider`, `AnthropicModelProvider`, `GeminiModelProvider` all delegate to `LocalModelProvider`, which returns the prompt text back and estimates tokens as `len(text)//4`. M9 "grounded LLM reasoning" performs no inference. | **High** | [REPO] `ria/infrastructure/models/provider_registry.py` |
| 10 | **The app that actually serves traffic is the one the docs supersede.** `backend.api:app` runs migrations and loads a sentence-transformer at import time, mounts 25 routers on three prefixes each (two of them 3-line stubs), and gates auth behind an opt-in hardcoded path-prefix list with a loopback rate-limit bypass. | **High** | [REPO] `backend/api.py`, `backend/security_middleware.py` |

### 1.3 Scores

| Dimension | Score | Basis |
|---|---:|---|
| Architecture design quality (as documented) | **8.0 / 10** | Explicit constraints, stated rejections, quantified gates, executable fitness functions, honest open questions |
| Architecture quality (as implemented) | **4.0 / 10** | Layer discipline real and enforced; storage substrate, graph model, and delivery absent or contradictory |
| Industry readiness / competitive position | **3.0 / 10** | 3 languages, no retrieval, no MCP surface, no published precision numbers |
| Production readiness | **2.0 / 10** | Shipping app is the legacy stack; `ria` is unreachable; no tenancy, tracing, real queue, or sandbox |
| Enterprise readiness | **1.5 / 10** | Opt-in path-prefix auth, no RBAC, no tenancy, no audit spine, no SSO, no compliance posture |
| Cloud readiness | **2.0 / 10** | Single container, single process, root user, no healthcheck, no k8s/Helm/Terraform, in-process rate limiting |
| Scalability headroom vs stated targets | **3.0 / 10** | SQLite single-writer + whole-graph-in-memory vs stated 10M LOC / 10⁷ symbols / 10⁸ edges |
| Security posture | **3.0 / 10** | Good: no credentials in `ria`, argv-based git, no LLM below L7. Bad: auth bypass by default, no sandbox, no dependency pinning |
| Developer experience (internal) | **6.0 / 10** | Excellent docs and fitness tests; no type checker, no pre-commit, unpinned deps, `requires-python>=3.9` vs CI 3.12 vs Docker 3.11 |
| Test quality signal | **3.5 / 10** | 1034 tests but +~15 per upper milestone; no coverage measurement; no mypy; two `.md` files named `test_*` |

**Composite: build-worthiness of the bottom half (M1–M7 reduced) — recommend proceed. Build-worthiness of the top half (M8–M12 as specified) — recommend stop.**

### 1.4 Engineering complexity estimate

| Scope | Estimate | Comparable |
|---|---|---|
| The full 12-milestone vision as documented (10M LOC, multi-tenant, N languages, agent platform, execution) | **40–70 engineer-years** | Sourcegraph's code-intelligence stack and Meta's Glean are each multi-team, multi-year efforts [DOC] |
| Reduced 6-core scope to a credible, measured v1 (see §12) | **6–10 engineer-years** (4–6 engineers × ~18 months) | [INFER] |
| Current `ria/` → first external user (MCP surface + eval harness + Postgres path + one real provider) | **8–14 engineer-months** (2 engineers × 4–7 months) | [INFER] |
| M10–M12 as specified, done properly (real sandbox, real tool loop, real patch validation) | **+15–25 engineer-years**, and it competes with Cognition, OpenAI, Anthropic, Google | [INFER] |

---

## 2. Ground truth: what RIA is today

Three disjoint systems occupy one repository. This is the single most important fact for any decision.

| Stack | LOC | Reachable? | Evidence |
|---|---:|---|---|
| **Legacy v1** (`backend/ services/ core/ agents/ memory/ models/ storage/`) | ~31.2k | **Yes — this is the product** | [REPO] `Dockerfile` stage 3 copies exactly these; `CMD uvicorn backend.api:app` |
| **Greenfield `ria/`** (L0–L9 rebuild, clean architecture) | ~29.9k / 243 files | **No** | [REPO] zero imports of `ria` outside `tests/ria`; not in Docker image; no HTTP/CLI/MCP entry point |
| **Docs** (`docs/foundation/`) | 1,854 lines normative + 12 milestone docs | Normative for neither | [REPO] |

Structural profile of `ria/` [REPO]:
- 19 ports (`typing.Protocol`, zero third-party imports), 85 domain model modules, 91 application services, 12 SQL migrations.
- M1–M2 are deep: `ingestion_service.py` 646 lines, `subprocess_git_client.py` 785, `file_enumerator.py` 545, durable lease-based job queue, content-hash change detection.
- M9–M12 are shallow: `agent_lifecycle.py` 25 lines, `verification_pipeline.py` 30, `patch_validator.py` 33, `citation_builder.py` 36, `tool_execution.py` 39.
- Test counts per milestone: M8 972 → M9 987 → M10 1002 → M11 1018 → M12 1034. **~15 tests per entire layer.** The test count is a surface-area metric, not a behaviour metric.

Milestone docs mirror this: M1–M2 are 264–308 lines of design reasoning; M3–M12 are uniform 45–63-line tables. **The document quality degrades at exactly the point the implementation depth does.** That correlation is the most reliable signal in the repository about where the real engineering stopped.

---

## 3. How modern AI software-engineering systems are actually built

Research findings, organised as the four architectural schools that exist in production today.

### School A — Agentic search, no index

**Claude Code.** Anthropic removed vector search from Claude Code and standardised on `ripgrep` plus structured tool calls and precise file reads; Claude Code's creator is quoted saying agentic search "outperformed everything. By a lot." and that this was surprising [DOC: [zerofilter/Medium quoting Boris Cherny](https://zerofilter.medium.com/why-claude-code-is-special-for-not-doing-rag-vector-search-agent-search-tool-calling-versus-41b9a6c0f4d9), [rust-trends](https://rust-trends.com/posts/ripgrep-claude-code/)]. Third-party analysis frames it as "search, don't index": trading latency and tokens for the elimination of index-sync and third-party-embedding liabilities [INFER, [claude-code-ultimate-guide](https://github.com/FlorianBruniaux/claude-code-ultimate-guide/blob/main/guide/core/architecture.md)]. Anthropic has not published the full retrieval design.

**Breadth of the pattern.** Independent analysis observes that Claude Code, Codex CLI, OpenCode, Cursor, Continue and Aider all default to grep/ripgrep as primary search despite LSP being ubiquitous IDE infrastructure [DOC: [grapeot.me](https://grapeot.me/share/why-coding-agents-still-use-grep-en-20260327.html)]. There is an open Claude Code feature request arguing the cost: 50–200 searches per session returning raw lines with no structural context, forcing full-file reads [DOC: [anthropics/claude-code#40702](https://github.com/anthropics/claude-code/issues/40702)].

**Why this matters to RIA:** this is the strongest competitive threat to the entire premise, and it comes from the vendor RIA would sell to. RIA's PRD §1.2 lists exactly this falsification condition. It has not been tested.

### School B — Structural map, cheap and deterministic

**Aider.** Parses the repo with tree-sitter, extracts symbol definitions, builds a symbol graph, and runs (personalised) PageRank to select which files and definitions enter a token-budgeted map [DOC: [aider repomap](https://aider.chat/2023/10/22/repomap.html), [aider docs](https://aider.chat/docs/repomap.html); ranking mechanism corroborated by [independent write-up](https://anishgandhi.com/aider-pagerank-codebase-ranking) and reimplementations].

**Why this matters:** Aider gets ~70% of RIA's M3–M5 value in a few thousand lines, with no database, no graph store, and no snapshot layer. Any RIA layer that cannot beat a PageRanked tree-sitter map on a measured task is not earning its complexity.

### School C — Precise, persistent, indexed code intelligence

This is RIA's actual category, and it has serious incumbents.

**Meta Glean.** Open-source code indexing system storing typed, schema-defined *facts* (definitions, references, types, call relations, inheritance, imports) queried with Angle, a Datalog-style language [DOC: [glean.software](https://glean.software/), [engineering.fb.com](https://engineering.fb.com/2024/12/19/developer-tools/glean-open-source-code-indexing/)]. Incrementality is achieved by **stacking immutable databases**: a new DB layers over an old one, the stack is invisible to queries, the old DB remains readable, and multiple versions can coexist — including several different "new" layers each replacing a different portion of "old" [DOC: [glean.software/blog/incremental](https://glean.software/blog/incremental/), [Glean blog feed](https://glean.software/blog/atom.xml)].

**Google Kythe.** Language-agnostic interchange: indexers emit directed graph data as a stream of node/edge entries; compilation extractors capture build invocations into a compilation database so indexing is build-accurate [DOC: [kythe.io overview](https://www.kythe.io/docs/kythe-overview.html), [writing an indexer](https://www.kythe.io/docs/schema/writing-an-indexer.html), [KCD spec](https://kythe.io/docs/kythe-compilation-database.html)].

**Sourcegraph.** Two complementary engines: **Zoekt** (trigram inverted index — postings lists per three-character sequence, index ~2–3× corpus size, trigram metadata in RAM, whole repos skippable when a required trigram is absent) [DOC: [zoekt design](https://github.com/sourcegraph/zoekt/blob/main/doc/design.md), [Sourcegraph memory-optimisation post](https://about.sourcegraph.com/blog/zoekt-memory-optimizations-for-sourcegraph-cloud/) — that post's test corpus was 19,000 repos / 2.6B lines / 166GB on disk] and **SCIP** (successor indexing format to LSIF, powering go-to-definition and find-references; precise navigation requires uploading per-repo indexes) [DOC: [announcing SCIP](https://sourcegraph.com/blog/announcing-scip), [precise code navigation docs](https://docs.sourcegraph.com/code_intelligence/explanations/precise_code_intelligence)]. Sourcegraph now positions itself explicitly as the intelligence layer where humans and agents are both first-class users of the same system, delivered over MCP [DOC: [Sourcegraph new era post](https://sourcegraph.com/blog/a-new-era-for-sourcegraph-the-intelligence-layer-for-ai-coding-agents-and-developers), [sourcegraph.com/mcp](https://sourcegraph.com/mcp)].

**GitHub.** Two published pieces of infrastructure. **Stack graphs** encode name-binding as a graph where paths represent valid bindings, are incremental (unlike scope graphs as originally published), and require *no repository configuration and no CI/build participation* [DOC: [Introducing stack graphs](https://github.blog/2021-12-09-introducing-stack-graphs/), [stack graphs paper arXiv 2211.01224](https://arxiv.org/pdf/2211.01224v2), [Python precise nav](https://github.blog/news-insights/product-news/precise-code-navigation-python-code-navigation-pull-requests/)]. **Blackbird** is a purpose-built code search engine written in Rust [DOC: [The technology behind GitHub's new code search](https://github.blog/engineering/architecture-optimization/the-technology-behind-githubs-new-code-search/)].

**rust-analyzer / Salsa.** The reference design for incremental semantic analysis: the program is expressed as queries `K -> V` over inputs, with **early cutoff** so that a changed input does not force re-execution of every transitive dependent when intermediate results are unchanged [DOC: [Salsa](https://github.com/salsa-rs/salsa), [Durable Incrementality](https://rust-analyzer.github.io/blog/2023/07/24/durable-incrementality.html), [rustc dev guide](https://rust-lang.github.io/rustc-dev-guide/queries/salsa.html)].

**Serena.** LSP-over-MCP: language servers back semantic tools (`find_symbol`, `find_referencing_symbols`, `replace_symbol_body`) so agents navigate and edit by symbol rather than by line or grep, across 40+ languages, consumed by Claude Code, Codex, Cursor, Copilot and others [DOC: [oraios/serena](https://github.com/oraios/serena), [gh-aw reference](http://github.github.com/gh-aw/reference/serena/), [independent profile](https://rywalker.com/research/serena)].

### School D — Hybrid embedding retrieval at product scale

**Cursor.** Builds its first view of a codebase as a **Merkle tree** — cryptographic hash per file, folder hashes derived from children — so changed files and directories are identified without reprocessing everything [DOC: [Cursor: securely indexing large codebases](https://cursor.com/blog/secure-codebase-indexing)]. Chunks are embedded server-side and stored in Turbopuffer with encrypted path information and line ranges; plaintext used for embedding does not outlive the request under privacy mode, and embeddings plus obfuscated paths are what persist [DOC: [Cursor data-use page](https://cursor.com/data-use); corroborating third-party analyses [aiexpjourney](https://aiexpjourney.substack.com/p/ai-innovations-and-trends-09-cursor), [simonwillison.net notes](http://www.simonwillison.net/random/vector-search/)].

**GitHub Copilot.** Repositories are indexed to improve context-grounded answers; the cloud agent uses semantic code search for when exact names or patterns are unknown [DOC: [Indexing repositories for Copilot](https://docs.github.com/en/copilot/using-github-copilot/indexing-repositories-for-copilot-chat)]. A new embedding model was reported to deliver a 37.6% retrieval-quality lift, ~2× throughput, and an 8× smaller index [DOC: [GitHub blog](https://github.blog/news-insights/product-news/copilot-new-embedding-model-vs-code/)].

**Windsurf / Codeium.** Published the remote-indexing and multi-repo context-awareness rationale — personalising an LLM system to private code either by fine-tuning or by precomputing an index and retrieving into the context window [DOC: [Codeium remote indexing announcement](https://codeium.com/blog/remote-indexing-multirepo-announcement)]. Note: Cognition acquired the Windsurf team and folded the editor into the Devin family [DOC-adjacent, third-party: [vibecoding.app](https://vibecoding.app/blog/building-ai-agents-with-windsurf)]. Detailed Cascade/"Riptide" internals are **not publicly documented**; claims found in SEO content about Windsurf building "a graph of file relationships" are unsourced and are not treated as evidence here.

**Continue.dev.** Publishes guidance for building a custom code RAG so a codebase can be indexed once across all users rather than per-developer [DOC: [Continue custom code RAG guide](https://continue-docs.mintlify.app/guides/custom-code-rag)].

### School E — Execution environments (the part RIA has none of)

Every system that mutates code isolates execution. This is universal.

| System | Isolation | Evidence |
|---|---|---|
| **OpenHands** | Client-server runtime in Docker containers; event-stream architecture where all agent-environment interaction flows as typed events (`User Message → Agent → LLM → Action → Runtime → Observation → Agent`); the `(action, observation)` log *is* the State object, enabling multi-turn reasoning and delegation | [DOC] [Runtime Architecture](https://docs.all-hands.dev/usage/architecture/runtime), [OpenHands SDK paper arXiv 2511.03690](https://arxiv.org/pdf/2511.03690), [original paper arXiv 2407.16741](https://arxiv.org/pdf/2407.16741) |
| **OpenAI Codex** | OS-enforced sandbox limiting writes to the workspace, **network off by default**, plus an approval policy for actions outside the sandbox; constraints propagate down the whole process tree | [DOC] [Agent approvals & security](https://developers.openai.com/codex/agent-approvals-security/), [Running Codex safely](https://openai.com/index/running-codex-safely/), [Windows sandbox post](https://openai.com/index/building-codex-windows-sandbox/) |
| **OpenAI Agents platform** | Sandbox = isolated Unix-like environment with filesystem, shell, packages, mounted data, ports, **snapshots**, controlled external access | [DOC] [Sandbox Agents guide](https://platform.openai.com/docs/guides/agents/sandboxes) |
| **Devin** | Per-session isolated VM with its own terminal, browser and dev environment; managed Devins each get their own VM and verify their own changes before reporting back; Outposts run sessions inside customer-controlled infrastructure | [DOC] [Devin can now manage Devins](https://old.cognition.ai/blog/devin-can-now-manage-devins), [Outposts](https://docs.devin.ai/cloud/outposts/overview) |
| **Google Jules** | Clones the repo into a secure Google Cloud VM, works asynchronously, returns plan + reasoning + diff | [DOC] [blog.google](https://blog.google/technology/google-labs/jules/) |
| **Factory** | Enterprise platform with hierarchical model allow/deny, LLM gateways, BYOK, MCP servers; coordinator dispatches to role-specialised droids | [DOC] [Factory enterprise docs](https://docs.factory.ai/enterprise/index), [GA announcement](https://www.factory.ai/news/ga) |
| **RIA** | **None.** Zero matches for `sandbox`. M11 tool execution returns hardcoded success strings. | [REPO] `ria/application/tool_execution.py` |

### School F — Agent topology: the settled question

This is directly relevant to M10, and the industry answer is nuanced but clear.

- **Cognition (Devin) argued against multi-agent for coding.** Their position: context management is the fundamental issue; splitting a task across agents loses critical information in transmission; the discipline that matters is context engineering — building the right context dynamically [DOC: [Don't Build Multi-Agents](https://cognition.ai/blog/dont-build-multi-agents)].
- **Anthropic argued for multi-agent — for research.** Their Research feature has a lead agent that plans and spawns parallel subagents, each with its own context window, and reported ~90.2% improvement over a single-agent Opus 4 baseline on an internal eval, at roughly 15× the tokens of a normal chat [DOC: [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system); token multiple corroborated by third-party summary]. Anthropic's own later framing is conditional: multi-agent protects context, enables parallelism and specialisation — when the slices are genuinely independent [DOC: [When to use multi-agent systems](https://claude.com/blog/building-multi-agent-systems-when-and-how-to-use-them)].
- **The reconciliation.** Parallel *read-only search* fans out well. Parallel *code mutation* does not, because subagents make conflicting decisions on shared state [DOC: Cognition's argument; [LangChain's how-and-when post](https://www.langchain.com/blog/how-and-when-to-build-multi-agent-systems)]. Reported analysis attributes ~80% of BrowseComp variance to token usage alone — i.e. much of the multi-agent win is fresh context windows, not agent specialisation [DOC-adjacent, third-party summarising Anthropic's post].
- **The simplicity result.** *Agentless* — a three-phase localise → repair → validate pipeline with no agent deciding future actions and no complex tools — achieved the best performance and lowest cost among open-source approaches on SWE-bench Lite at time of submission (27.33% at $0.34/issue in the original; 32.00% at $0.70 in the updated version) [DOC: [arXiv 2407.01489](https://ar5iv.labs.arxiv.org/html/2407.01489), [NSF record of updated figures](https://par.nsf.gov/biblio/10682640-demystifying-llm-based-software-engineering-agents)].

**Implication for M10:** nine agent roles with a task-planner DAG, communication bus, and conflict resolution is a bet against the published evidence, on the axis (code mutation) where the evidence is least favourable, built by a team that has not yet shipped one working retrieval query.

### School G — Is "Digital Twin" a real abstraction?

Answered honestly: **yes in research, no in production.**

- The **Code Digital Twin** is a published research proposal: a persistent, evolving knowledge infrastructure over a codebase modelling both a physical layer (source, artefacts, history, runtime) and a conceptual layer (domain concepts, functionality, design rationale), explicitly separating long-term knowledge engineering from task-time context engineering and serving as a backend "context engine" for AI coding assistants [DOC: [arXiv 2503.07967](https://arxiv.org/abs/2503.07967), [arXiv 2510.16395](https://arxiv.org/html/2510.16395v1)]. RIA's `03-DIGITAL-TWIN-SPEC.md` is closely aligned with this line of work.
- **No production system ships a "twin" as a distinct architectural layer.** Glean has facts + derived predicates. Kythe has a node/edge graph + serving. Sourcegraph has Zoekt + SCIP. rust-analyzer has Salsa queries. GitHub has stack graphs. None interpose a materialised multi-facet composite object between the graph and the query API.

**Verdict on M6 is in §6.6.** Summary: the *concept* is defensible and is RIA's most interesting intellectual contribution; the *layer* is not, and the persisted snapshot store is actively harmful.

### School H — Graph store choice

Evidence is genuinely mixed and workload-dependent, which supports RIA's AD5 (relational, not Neo4j) more than it undermines it.

- Vendor position (interested party): pre-materialised relationships give graph databases order-of-magnitude advantages on join-heavy traversal [DOC: [Neo4j](https://neo4j.com/blog/developer/rdbms-vs-graph-data-modeling/)].
- Independent benchmarking is split. One peer-reviewed comparison found Neo4j strong on complex relationships but weaker under concurrent access, where SQL Server was markedly more stable [DOC: [Applied Sciences 14(21):9867](https://mdpi.com/2076-3417/14/21/9867)]. Another found Neo4j faster on simple queries but a relational engine more efficient as query complexity rose [DOC: [ResearchGate 361607172](https://www.researchgate.net/publication/361607172)]. A recent practitioner benchmark reported Postgres recursive CTEs beating Neo4j ~4× on neighbourhood reachability while Neo4j beat Postgres 85–135× on point-to-point shortest path, with the gap widening with distance [DOC-adjacent, single-author benchmark: [pedroalonso.net](https://www.pedroalonso.net/blog/graphrag-vs-vector-postgres/)].
- On retrieval topology for code specifically: a benchmark of three pipelines on Java codebases found deterministic AST-derived knowledge graphs gave more reliable coverage and multi-hop grounding than LLM-extracted graphs at substantially lower indexing cost, with vector-only RAG failing on multi-hop architectural chains [DOC: [arXiv 2601.08773](https://arxiv.org/abs/2601.08773)]. A broader study found agentic search substantially narrows the dense-RAG-to-GraphRAG gap, with GraphRAG retaining an advantage on complex multi-hop reasoning once its offline cost is amortised [DOC: [arXiv 2604.09666](https://arxiv.org/html/2604.09666v1)].

**Implication:** RIA's relational-graph decision is defensible *and* its dominant query profile (p95 of small neighbourhood queries, per SDD §1.3 constraint 4) is precisely where recursive CTEs are competitive. The problem is not the engine choice. It is that RIA does not actually implement adjacency queries — it materialises whole graphs (§6.5).

---

## 4. Architecture review — the pipeline as a whole

### 4.1 The shape problem

The stated pipeline is a strictly sequential chain of twelve horizontal layers:

```
Repository → Foundation → Ingestion → Parser → Semantic → Graph → Twin
          → Query → Context → Reasoning → Multi-Agent → Workflow → Execution
```

Three structural criticisms.

**(a) It is a waterfall wearing layer-cake clothing.** Each milestone is completed before the next begins, and nothing is user-facing until milestone twelve. The evidence of what this costs is in the repository: M1–M7 are deep and defensible; M8–M12 are 25–40-line services that satisfy a port signature. The plan produced twelve "complete" milestones and zero validated hypotheses. Every system in §3 was built as a thin vertical slice first — Aider shipped a repo map before it had a graph; Sourcegraph shipped Zoekt search before SCIP precision; OpenHands shipped an event stream and a Docker runtime before it had multi-agent delegation.

**(b) The layer count exceeds the number of independent lifecycle boundaries.** A layer earns its existence when it can be deployed, scaled, versioned, or replaced independently. By that test: Foundation+Ingestion share one lifecycle (both are git-driven, both scale with repo size, both are batch). Graph+Twin share one lifecycle (both are derived, disposable, rebuilt from resolution). Query+Context share one (both are read-path, latency-bound, cache-friendly). Multi-Agent+Workflow+Execution share one (all are session-scoped mutation orchestration). Twelve milestones map onto roughly **six** real boundaries. §12 proposes that collapse.

**(c) The chain has no feedback edge.** A real code-intelligence system has a loop: query results feed relevance signals, relevance signals feed ranking, failures feed the evaluation set, evaluation gates the index. RIA's chain is one-directional from git to execution, with "continuous learning" bolted on at M12 as a 47-line milestone. Learning at the end of a one-way pipe cannot influence the resolution quality that determines everything upstream of it.

### 4.2 What the architecture gets genuinely right

Objective credit, stated plainly because a critique without it is not calibrated.

1. **Commit as part of every primary key** [REPO `03-DIGITAL-TWIN-SPEC.md`]. Every fact keyed `(repo_id, commit_id, moniker)`. This is correct and most competitors do not do it — Cursor's Merkle-tree approach detects change but the index is a moving present-tense view, not a commit-addressed history [DOC: Cursor indexing post]. RIA's choice matches Glean's stacked-DB model, where multiple versions coexist and are simultaneously queryable [DOC: Glean incremental].
2. **The hard determinism boundary** [REPO `02-SDD.md` §2.1]. "Nothing below L7 calls an LLM," enforced as a build failure. This is a real architectural fitness function and it is rarer than it should be. It is also currently over-broad (§6.9).
3. **Facts/derived split with one-way dependency** [REPO SDD §1.3 constraint 1]. Matches Glean's facts + derived predicates model [DOC].
4. **Executable architecture rules.** `tests/ria/integration/test_architecture_rules.py` (384 lines) enforces legacy isolation, domain purity, port purity, layer direction, validation-library containment, and bans dead implementations — with a discovery guard so the suite cannot pass vacuously. This is the single best asset in the repository and most teams at this stage have nothing equivalent.
5. **Provenance envelope on every result** [REPO twin spec §7.2: mandatory `coverage`/`provenance`/`confidence`]. Correct instinct for an agent-consumer product, and it is what separates "index" from "search box."
6. **Explicitly stated rejections and open questions** [REPO SDD §7, twin spec T1–T7]. Documenting that relational adjacency at 10⁸ edges is unvalidated is more useful than a confident claim. The problem is not that T2 is open; it is that nothing has been done to close it.

### 4.3 The doc-implementation gap, tabulated

| Specified in `02-SDD.md` §6.2 / §2.1 | Implemented | Evidence |
|---|---|---|
| PostgreSQL as facts spine, partitioned by repo/commit | ❌ single-file SQLite | [REPO] `ria/infrastructure/storage/sqlite/` |
| S3-compatible blob store | ❌ local filesystem CAS | [REPO] `filesystem_blob_store.py` |
| Redis for cache / queue / rate limit / sessions | ❌ SQLite tables | [REPO] `job_repository.py`, `*_cache_store.py` |
| Vector DB / pgvector | ❌ none in `ria` (banned by test) | [REPO] `TestNoModelCallsBelowReasoning` |
| SCIP / LSP indexers for Tier-B precision | ❌ no port, no adapter | [REPO] `ria/ports/` |
| L6 Engineering Memory (timeline, evolution, trends, decisions, agent working memory) | ❌ layer absent entirely | [REPO] no timeline/evolution/twin_at services |
| L8 Query Gateway (contract, authz, quota, cache, pagination, latency budget) | ❌ absent | [REPO] no delivery code in `ria` |
| L9 Applications (MCP, REST, GraphQL, CLI, IDE, CI, Web) | ❌ absent from `ria` | [REPO] `Dockerfile` excludes `ria` |
| Cross-cutting orchestration: durable queue, workers, idempotency, retry, cancel | ⚠️ partial — real lease-based SQLite queue, single-process runner | [REPO] `ria/application/job_runner.py`, `0002_ingestion.sql` |
| Cross-cutting control plane: tenancy, authz, quota, policy, billing | ❌ absent | [REPO] |
| Cross-cutting evaluation: benchmarks, regression gates, precision reporting | ❌ absent (one 52-line perf test) | [REPO] `tests/ria/performance/` |
| Domain events (SDD §5.4) | ❌ no event bus anywhere | [REPO] zero `EventBus` matches |
| Graph stored relationally, not as in-memory objects (AD5, §1.3 c2) | ❌ contradicted — whole-graph objects and whole-snapshot JSON blobs | [REPO] §6.5 below |

**Eleven of thirteen specified cross-cutting or infrastructure commitments are unimplemented.** The layered design is not the risk. The gap between the design and the substrate is.

---

## 5. Critical-questions matrix

For every layer: why it exists, whether it is necessary, whether it scales, and the redesign call.

| Layer | Why it exists | Necessary? | Scalable as built? | Merge / Split | Industry does it differently? | Redesign call |
|---|---|---|---|---|---|---|
| **M1 Foundation** | Repo identity, commit resolution, CAS, config, observability | **Yes** | Yes (git is the SoR) | Merge into M2 | No — matches everyone | **Keep, merge** |
| **M2 Ingestion** | Clone/fetch, commit+branch discovery, change detection, file units, durable queue | **Yes** | Partly — single-process worker, SQLite queue | Merge M1 | Cursor uses Merkle trees; RIA uses content hashes + git — equivalent or better | **Keep, merge; add Merkle/tree-hash fast path** |
| **M3 Parser** | tree-sitter per-language extraction, parse cache | **Yes** | Yes | Keep | Universal (Aider, Cursor, Continue, GitCortex) | **Keep; add SCIP ingestion** |
| **M4 Semantic Resolution** | Scopes, symbols, imports, references, inheritance | **Yes — this is the moat** | Unproven; no cross-file dependency tracking | Keep, split Tier A / Tier B | Stack graphs, SCIP, Salsa are the references — all more sophisticated | **Keep and invest; the only layer that should get *more* budget** |
| **M5 Knowledge Graph** | Node/edge model, 9 projections, traversal | **Yes as a query surface, No as a materialised artefact** | **No — whole-graph in memory** | Merge into store + query | Kythe/Glean store facts and derive; nobody materialises a graph object | **Redesign: delete `Graph` object, adjacency-only** |
| **M6 Digital Twin** | Materialised multi-facet view @commit | **Concept yes, layer no** | No — snapshot store is a whole-graph blob | Merge into M5+M7 as a read model | Research-only construct; no production analogue | **Demote to read model; delete `twin_store`** |
| **M7 Query Engine** | 23 primitives, dependency/impact/architecture analysis | **Yes — this is the product** | Untested at scale | Merge M8's planning in | Sourcegraph/Glean/Kythe all expose this as *the* API | **Promote to first deliverable, not seventh** |
| **M8 Context Engine** | Intent, planning, retrieval, ranking, compression, citations, budget | **Partly** | Cannot rank without signals; no lexical or vector retrieval | Merge with M7 | Every agent vendor owns this; it is their differentiator | **Reduce to: token-budgeted result shaping + citations. Delete intent classification.** |
| **M9 Reasoning Engine** | LLM abstraction, grounding, verification, streaming | **Thin yes** | N/A — providers are stubs | Keep thin | Vendors use provider SDKs + gateways; not a hand-rolled layer | **Reduce to one real provider + citation verifier; use a gateway** |
| **M10 Multi-Agent Platform** | 9 roles, DAG planner, orchestrator, bus, conflict resolution | **No** | N/A | **Delete** | Cognition argues against for coding; Anthropic's win was read-only research | **Delete. Expose tools; let host agents orchestrate.** |
| **M11 Workflow Engine** | Planner, state machine, tool exec, approvals, verification, rollback, audit | **No, as specified** | N/A — fabricates results | **Delete; keep audit** | OpenHands event stream + Docker runtime is the real shape | **Delete. Keep the audit log as a cross-cutting concern.** |
| **M12 Execution + Learning** | Patch gen/validate, git ops, branch, commit, PR, learning | **No** | N/A | **Delete** | Codex/Devin/Jules own this with per-session VM isolation | **Delete. Ship a CI gate instead (already prototyped).** |

**Answering "what would Google / OpenAI / Anthropic do?" without hand-waving:**

- **Google (evidenced by Kythe + Glean):** define a language-agnostic fact schema, make indexers pluggable and build-accurate, invest heavily in incrementality and a real query language, and *never* materialise a whole-repo graph object. They would build M1–M5 and M7 and would treat M6 and M8–M12 as consumers, not layers. [DOC: kythe.io, glean.software]
- **OpenAI (evidenced by Codex):** would not build the index at all initially. They would give the model a sandbox with a shell, turn the network off, and let agentic search find things — then add indexes only where measurement showed grep losing. [DOC: Codex sandbox docs]
- **Anthropic (evidenced by Claude Code):** the same, more aggressively — they removed vector search after measuring that agentic search beat it. They would demand RIA's benchmark before RIA's architecture. [DOC: Claude Code retrieval reporting]
- **Sourcegraph:** would adopt SCIP as the ingestion format on day one to get language breadth for free, pair it with a trigram index for the fuzzy path, and expose everything over MCP. [DOC: SCIP announcement, sourcegraph.com/mcp]

---

## 6. Per-layer deep analysis

### 6.1 M1 Repository Foundation — sound, keep

**What exists** [REPO]: `RepositoryManager` (517 lines), `CommitResolver` (293), `SubprocessGitClient` (785, argv-based with timeouts, `-z` tree parsing, ref peeling, unit/record separators), `FilesystemBlobStore` (344, sharded, atomic writes), `SystemClock`, migration `0001`.

**Assessment.** This is the highest-quality code in `ria/`. The git client in particular is disciplined: argv arrays rather than shell strings, explicit timeouts, `-z` for path safety. Treating git as the system of record and never claiming to own truth is exactly right and matches every system in §3.

**Weaknesses.** (a) `FilesystemBlobStore` is the only CAS; the SDD's S3 target means the storage port will need range reads, multipart writes, and presigned access it does not currently model. (b) No shallow/partial-clone or sparse-checkout strategy is evident, which matters for monorepos. (c) `count_lines` on the git client suggests scanning work that should be derived from parse output.

**Verdict: keep, merge into M2. Do not spend more here.**

### 6.2 M2 Repository Ingestion — sound, with one real gap

**What exists** [REPO]: `IngestionService` (646), `FileEnumerator` (545), `CommitDiscovery` (335), `MirrorManager` (208), content-hash change detection, atomic visibility, and a **durable lease-based job queue** (`0002_ingestion.sql`, `JobStore.lease_next/requeue_expired`, `JobRunner` with retry/backoff/dead-letter, 369 lines).

**Assessment.** The queue is the most important thing here and it is real. SDD §2.2 correctly identifies "ingestion runs inside request handlers" as the prior architecture's hardest ceiling; that ceiling has been removed. Lease-based work claiming with expiry requeue is the right primitive.

**Comparison.** Cursor's Merkle tree gives change detection at *directory* granularity, so an unchanged subtree is skipped by one hash comparison [DOC: Cursor indexing post]. RIA's content-hash-per-file approach must enumerate every file to know nothing changed. Since RIA already has git, it should use `git diff-tree` between commits, which is strictly better than both — O(changed files) with no enumeration at all. Whether `CommitDiscovery`/`ChangeSet` does this is worth confirming; if the enumerate-then-hash path is the primary one, that is the single cheapest performance win available.

**Gaps.** (a) Single-process worker; no distributed execution, no worker container in `docker-compose.prod.yml` [REPO]. (b) No cancellation propagation into running parse work is evident. (c) No repository-level concurrency control, so two ingestions of the same repo contend on SQLite's single writer.

**Verdict: keep. Add git-diff-driven change detection. Extract the worker into its own process before anything else.**

### 6.3 M3 Parser Layer — correct choice, insufficient breadth

**What exists** [REPO]: `TreeSitterAdapter` (211), `PythonExtractor` (323), `JsTsExtractor` (244), parser and capability registries, parse cache (`0003`), incremental parser. Tree-sitter pinned `>=0.21,<0.22`.

**Assessment.** tree-sitter is the correct and universal choice — Aider, Cursor, Continue, GitCortex and RIA all land there [DOC]. The capability registry (`capabilities_for_language`, `max_tier_for_language`) is a good abstraction that most competitors lack: it makes coverage machine-readable, which is a prerequisite for the honest `coverage` envelope the twin spec demands.

**Weaknesses.** (a) **Three languages.** Enterprise buyers have Java, Go, C#, Kotlin, Ruby, PHP, C++, Terraform, SQL. Sourcegraph and Serena solve this by consuming LSP/SCIP rather than writing extractors [DOC]. (b) tree-sitter cannot do type inference or cross-module resolution; it is a syntax layer, and RIA's precision claims live one layer up. (c) `<0.22` pin means the ecosystem's newer grammars are unavailable.

**Verdict: keep. Add a SCIP ingestion adapter as the highest-leverage single change in the entire architecture (§12.2).**

### 6.4 M4 Semantic Resolution — the moat, and the least-defended layer

**What exists** [REPO]: nine resolver ports (`ScopeResolverPort`, `SymbolResolverPort`, `NamespaceResolverPort`, `ImportResolverPort`, `ReferenceResolverPort`, `InheritanceResolverPort`, plus cache/registry/facade), semantic cache `0004`, 901 tests at that milestone.

**Assessment.** The PRD is right that this is the moat: "a system that asks an LLM 'who calls this function' has an architecture defect" [REPO PRD §4.1] is the correct instinct, and it is the one claim that would genuinely differentiate RIA from School A and School D competitors.

**Critical weaknesses.**

1. **The 0.95/0.90 claim is unmeasured.** No labelled corpus, no benchmark harness, no CI gate [REPO]. This is not a documentation gap; it means the product's only differentiator is currently a hypothesis. GitHub published a paper on stack graphs [DOC arXiv 2211.01224]; Sourcegraph publishes per-language SCIP indexer maturity [DOC]. RIA publishes a number in a PRD.
2. **No dependency-tracked incrementality.** The caches are keyed by reuse-key and fingerprint and, per the twin spec, "never invalidate, only evict" [REPO §6.5 of twin spec]. That is a defensible design for *at-commit* caching, but cross-file resolution results depend on other files' symbol tables, and without a dependency graph between query results there is no way to selectively recompute. Salsa's early-cutoff model exists precisely for this and is the published reference [DOC: rust-analyzer durable incrementality]. Glean solves the same problem with stacked immutable DBs where a new layer replaces a portion of the old [DOC]. RIA has neither mechanism, so incremental correctness at the 2-second p95 target is unsubstantiated.
3. **No Tier-B path.** PRD P10 says buy breadth. Nothing was bought.

**Verdict: keep, and redirect budget here from M8–M12. Specifically: build the labelled corpus first, then the CI gate, then Salsa-style dependency tracking, then SCIP ingestion.**

### 6.5 M5 Knowledge Graph — redesign required

**What exists** [REPO]: node/edge builders, 9 projections, `GraphTraversalService` (BFS/DFS/shortest-path/reachability/ancestors/descendants), `SqliteGraphStore`, `SqliteGraphCacheStore`, migration `0005`.

**The defect, stated precisely.** SDD §1.3 constraint 2 reads: *"Structure at scale exceeds memory by orders of magnitude ⇒ no design may require loading a whole-repository graph into a process. This single constraint eliminates the in-memory graph-object approach categorically."*

Verified implementation [REPO]:
```python
# ria/application/graph_traversal_service.py
def breadth_first(self, graph: Graph, start_id: GraphNodeId, max_depth=None) -> TraversalResult:
    ...
    for edge in graph.outgoing_edges(node.node_id):
```
Every traversal method takes a whole `Graph` object. `TraversalPort` is defined that way in `ria/ports/graph.py`. And:
```python
# ria/infrastructure/storage/sqlite/graph_store.py
def put(self, key: GraphCacheKey, snapshot: GraphSnapshot) -> None:
    snapshot_json = json.dumps(_serialize_snapshot(snapshot), default=str)
    # -> single ria_graph_cache.snapshot_json column
```
The graph cache stores **the entire node and edge set of a commit as one JSON string in one column**. `get_snapshot` reads all node rows and all edge rows for a commit and materialises tuples of every node and edge.

At the SDD's stated target of 10⁷ symbols and 10⁸ edges, one snapshot JSON would be in the hundreds of gigabytes. The design the SDD "eliminates categorically" is the design that shipped. This is not a small inconsistency — it invalidates the p95 <200ms-at-1M-LOC goal, because the current shape's cost is O(graph), not O(neighbourhood).

**What the redesign looks like.**

1. Delete `Graph` from every port signature. `TraversalPort` should accept `(repository_id, commit_sha, start_id, edge_kinds, max_depth, limit)` and return a bounded frontier.
2. Push traversal into the store as recursive CTEs over `ria_graph_edge (repository_id, commit_sha, source_id, kind)` with a covering index. This is the workload where relational engines are competitive on neighbourhood reachability [DOC: independent benchmarks in §3 School H].
3. Delete `SqliteGraphCacheStore` entirely. Caching a whole graph is caching the thing you must never materialise. Cache *query results* keyed by `(repo, commit, primitive, args)` instead.
4. Enforce it: add an architecture test asserting no port signature accepts `Graph`, and a performance test that fails if a traversal reads more rows than `O(frontier × fanout)`.
5. Keep the relational choice. AD5 is correct; the implementation is not.

**Verdict: redesign, and merge the storage concern into the fact store. The node/edge *model* is fine; the materialisation is not.**

### 6.6 M6 Digital Twin — the abstraction question, answered

**Does the abstraction exist in industry?** No production system ships it (§3 School G). It exists as an active research proposal — the Code Digital Twin, an evolving knowledge infrastructure over physical and conceptual layers acting as a backend context engine for coding assistants [DOC: arXiv 2503.07967, arXiv 2510.16395]. RIA's spec is a stronger engineering treatment of that idea than the papers are, particularly the moniker identity scheme and the coverage/provenance/confidence envelope.

**What equivalent systems exist?** Glean's derived predicates over stacked fact DBs; Kythe's serving layer over the node/edge graph; Salsa's query graph with early cutoff; Sourcegraph's SCIP upload per repo/commit [all DOC]. All four are *query-time derivations*, not *stored composites*.

**Should it be redesigned or removed?** **Redesigned, not removed — and demoted from a layer to a read model.**

The keep-worthy parts:
- **Commit-scoped multi-facet composition** as an API concept. "Give me the twin at commit X, projected to the structure and history facets" is a genuinely good query contract and is more useful to an agent than five separate calls.
- **Unified identity via monikers** `scheme:package:descriptor`. This is essentially SCIP's symbol-string design and is the right call — it is also the interoperability hook that makes SCIP ingestion cheap.
- **Structural sharing** (~600× saving claimed in twin spec §6.4). Correct instinct; matches Glean's stacked-DB reuse.
- **Lazy composition** — the spec says lazy; the implementation stores snapshots, which is eager. Resolve in favour of the spec.

The delete-worthy parts:
- `TwinStorePort.save_snapshot` / `twin_store.py` (287 lines) and `TwinCacheStore`. A stored snapshot of a composite whose components are already commit-immutable is pure duplication with an invalidation surface.
- `SnapshotManagerPort`, `SynchronizationPort`, `ConsistencyValidatorPort`, `TwinLifecyclePort` — four ports whose existence is a consequence of storing the snapshot. Remove the snapshot and three of the four evaporate. `ConsistencyValidatorPort` should survive as an *evaluation* tool, not a runtime port.
- `RepositoryMetricsPort` belongs in M7 analysis, not in the twin.

**Verdict: keep the concept and the query contract; delete the persistence; fold the remainder into M5's fact store and M7's query surface. This removes one entire layer and roughly ten ports.**

### 6.7 M7 Query & Analysis Engine — should have been milestone three

**What exists** [REPO]: `QueryEnginePort`, `SymbolQueryPort` (8 methods), `GraphQueryPort` (7), plus dependency, impact, architecture, pattern-matching and cross-reference analysis ports, `query_optimizer.py` (39 lines), migration `0007`.

**Assessment.** This is the product. PRD §1.3 says the primary interface is "Query API + MCP server. Not a UI." The twin spec defines 23 primitives, 20 deterministic, with `ask` as 1 of 23 [REPO]. That ratio is the most commercially interesting claim in the whole document set, and it is exactly what Sourcegraph is now selling — deterministic navigation and search exposed to agents over MCP [DOC].

**The sequencing error.** Building this seventh, with no delivery surface, means no consumer has ever exercised a primitive. Query APIs are shaped by their callers; designing 23 primitives before any caller exists guarantees rework. Evidence that this already happened: `query_optimizer.py` is 39 lines — an optimiser with nothing to optimise.

**Weaknesses.** (a) Analysis ports (impact, architecture, pattern matching) are five separate concerns bundled with the read path; they are *derived analytics* and belong above the query gateway, not inside it. (b) No pagination, no deterministic ordering contract, no latency budget enforcement — all specified for L8, which does not exist. (c) `find_references` correctness is unverified (§6.4).

**Verdict: promote. This plus a delivery surface plus an eval harness is the minimum viable product. Split the five analysis ports out into a separate "analytics" module above the gateway.**

### 6.8 M8 AI Context & Retrieval Engine — over-scoped, and missing the actual retrieval

**What exists** [REPO]: `IntentClassifierPort`, `ContextPlannerPort`, `RepositoryRetrieverPort`, `RankingEnginePort`, `CompressionEnginePort`, `CitationBuilderPort`, `PromptBuilderPort`, `TokenBudgetPort`, cache, registry. Explicitly no LLM calls and no embeddings [REPO M8 doc].

**The functional hole.** RIA has **no retrieval mechanism that competes**:

| Approach | Who uses it | RIA |
|---|---|---|
| Agentic grep / ripgrep | Claude Code, Codex CLI, and by report most CLI agents [DOC] | ❌ |
| Trigram inverted index | Sourcegraph (Zoekt), GitHub (Blackbird) [DOC] | ❌ |
| Embeddings + vector store | Cursor (Turbopuffer), Copilot, Continue, Windsurf [DOC] | ❌ banned by architecture test |
| Precise symbol index | Sourcegraph (SCIP), GitHub (stack graphs), Serena (LSP) | ⚠️ exact-name only, 3 languages |

An agent asking "where is authentication handled?" — the canonical query in Copilot's own docs [DOC: VS Code workspace context] — cannot be served by exact-name symbol lookup. RIA's own PRD falsification test requires comparing resolved retrieval against a heuristic/embedding baseline and finding a >15% recall@10 delta. **There is no baseline to compare against, so the bet cannot currently be won or lost.**

**Over-scoped parts.** `IntentClassifierPort` is a deterministic classifier trying to guess what an LLM caller wants — the caller already knows, and every agent vendor treats intent as their own concern. `ContextPlannerPort` and `PromptBuilderPort` assume RIA constructs prompts for someone else's model, which conflicts with being an index. Anthropic's own guidance frames context curation as the harness's job, with compaction, tool-result clearing and memory as the levers [DOC: [Effective context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents), [context-engineering cookbook](https://platform.claude.com/cookbook/tool-use-context-engineering-context-engineering-tools)]. A shared index that also owns prompt construction will be bypassed by every serious harness.

**What to keep.** Token-budgeted result shaping (real and valuable — agents need "give me this under 8k tokens"), citation building (core to the provenance promise), and result ranking *once there are signals to rank on*. Relevant industry datapoint: task-scoped thin MCP tool surfaces were benchmarked as cutting token consumption ~75% versus broad-surface designs without hurting first-answer accuracy [DOC: [Cyclr benchmark](https://uk.finance.yahoo.com/news/cyclr-benchmark-finds-mcp-server-140000716.html)] — which argues for a small, sharp tool surface rather than a context-planning engine.

**Verdict: cut roughly 60%. Keep budget shaping + citations + ranking. Delete intent classification, context planning, prompt building. Add a lexical index (trigram or SQLite FTS5) and an *optional, measured* embedding path behind a port so the PRD's own falsification test can actually run.**

### 6.9 M9 AI Reasoning Engine — currently non-functional, and blocked by its own guardrail

**What exists** [REPO]: `ReasoningEnginePort`, `ModelProviderPort`, `PromptExecutorPort`, `EvidenceValidatorPort`, `CitationAttachmentPort`, `StreamingPort`, `PromptTemplatePort`, migration `0009`. `ModelProviderRegistry` maps `openai`/`anthropic`/`google` to adapters that all delegate to `LocalModelProvider`, which echoes the prompt back and estimates tokens as `len(text)//4`.

**The self-inflicted block.** `TestNoModelCallsBelowReasoning` forbids importing `openai`, `anthropic`, `google`, or `sentence_transformers` **anywhere in `ria`** [REPO]. The rule was correct when the determinism boundary was the risk; it is now the reason M9 cannot work. The fix is small and should have been part of M9: scope the rule by package, permitting model clients only in `ria.infrastructure.models` (and an embedding adapter only in `ria.infrastructure.embeddings`), and forbidding them in `ria.domain`, `ria.ports`, and every `ria.application` module below the reasoning services. That preserves the architectural guarantee and unblocks the product.

**Over-engineering.** Ten ports for a layer whose job is: render a template, call a model, verify that every claim carries a citation that resolves, stream the result. Hand-rolling provider abstraction is also the wrong build/buy call in 2026 — OpenHands ships model-agnostic multi-LLM routing as framework infrastructure [DOC: [OpenHands SDK paper](https://arxiv.org/html/2511.03690v2)], and Factory exposes LLM gateways and BYOK as platform features [DOC: Factory enterprise docs]. Use a gateway.

**What is genuinely valuable and under-built.** `EvidenceValidatorPort` + `CitationAttachmentPort`. A verifier that rejects any generated claim not backed by a resolvable `(repo, commit, moniker, span)` is the one place where RIA's determinism investment pays off in the probabilistic layer. It is currently a ~36-line service.

**Missing.** No prompt registry, so prompt version cannot appear in provenance as SDD §4 requires [REPO]. No cost accounting. No token budgeting against a real tokenizer. No fallback/routing policy. No caching of model responses.

**Verdict: shrink to four ports. Fix the architecture rule to be layer-scoped. Wire exactly one real provider. Invest the recovered effort in the citation verifier — it is the differentiator.**

### 6.10 M10 Multi-Agent Developer Platform — delete

**What exists** [REPO]: ten ports (`TaskPlannerPort`, `AgentRegistryPort`, `AgentFactoryPort`, `AgentLifecyclePort`, `AgentOrchestratorPort`, `SharedContextPort`, `CommunicationBusPort`, `ResultAggregatorPort`, `ConflictResolutionPort`, `ExecutionPlannerPort`), 9 agent roles, migration `0010`. Implementation depth: `agent_lifecycle.py` is 25 lines wrapping a `Dict[str, AgentState]`; `communication_bus.py` is 26 lines.

**Why delete, on evidence.**

1. **It contradicts the PRD.** §1.3: primary interface is a Query API + MCP server; explicit non-goal is writing code. A nine-role agent platform with conflict resolution is a different product.
2. **The published evidence is against it for code mutation.** Cognition's position is that multi-agent systems fragment context and produce conflicting decisions [DOC: Don't Build Multi-Agents]. Anthropic's 90.2% multi-agent win was on *research* — parallel read-only search with independent threads — and cost ~15× the tokens [DOC: Anthropic multi-agent post]. Anthropic's own later guidance conditions the pattern on genuinely independent slices [DOC: claude.com]. Code editing on a shared working tree is the opposite of independent.
3. **The simplest thing measured best.** Agentless, with no agent deciding future actions and no complex tooling, topped open-source SWE-bench Lite results at the lowest cost [DOC: arXiv 2407.01489].
4. **The market position is hopeless.** Competitors here are Cognition (per-session VMs, managed Devins), OpenAI (Codex sandboxes), Google (Jules cloud VMs), Factory (coordinator + droids), OpenHands (event stream + Docker runtime) [all DOC]. RIA would enter with 25-line services and no execution isolation.
5. **The strategic error is inverted.** Every one of those competitors is a potential *customer* of RIA's index. Building M10 converts every customer into a competitor. Sourcegraph explicitly chose the opposite: be the intelligence layer that agents consume [DOC].

**What to build instead:** an MCP server exposing the 20 deterministic primitives, so Claude Code, Codex, Cursor and OpenHands become distribution channels. Serena demonstrates the model — an MCP server providing symbol-level tools, consumed by essentially every agent surface [DOC].

**Verdict: delete all ten ports, the nine roles, and migration 0010. Recovered budget: substantial.**

### 6.11 M11 Autonomous Workflow Engine — delete, with one exception

**What exists** [REPO]: ten ports including `WorkflowPlannerPort`, `ExecutionStateMachinePort`, `ToolExecutionPort`, `ApprovalManagerPort`, `VerificationPipelinePort`, `RollbackPlannerPort`, `AuditLogPort`, migration `0011`.

**The most serious finding in the report.** `ToolExecutionService.execute_action` [REPO `ria/application/tool_execution.py`]:

```python
elif a_type == "test":
    return f"Invoked automated test suite for '{target}'. All tests passed successfully."
elif a_type == "build":
    return f"Simulated build invocation for '{target}'. Build artifacts compiled cleanly."
```

And `VerificationPipelineService.verify_execution` [REPO] returns `tool_success=True, evidence_consistent=True` unconditionally, checking only that the output string is non-empty and the workflow has ≥1 step.

Nothing is executed. Strings asserting that tests passed and builds compiled are returned as observations, and the verification pipeline hardcodes success. In a system whose entire thesis is grounded, provenance-carrying, agent-actionable answers, a component that manufactures verification evidence is a correctness hazard of the highest order. If any downstream consumer ever treated these as observations, the system would confidently report green on code it never ran. The milestone doc describes this as "read-only/simulated by design," which is honest, but the strings do not say "simulated" for the test case — they say tests passed.

**Immediate action, independent of any roadmap decision:** delete `ToolExecutionService` and `VerificationPipelineService`, or make every return value explicitly `NOT_EXECUTED`. This is not a design debate; it is a defect.

**Comparison.** The real shape of this layer, if it were built, is OpenHands': typed events flowing `Action → Runtime (sandbox) → Observation`, with the `(action, observation)` log serving as the state object [DOC: OpenHands runtime docs and SDK paper]. Approvals are Codex's approval policy layered on an OS-enforced sandbox with network off [DOC]. RIA has neither the event stream nor the sandbox.

**The exception.** `AuditLogPort` is legitimately needed — but as a cross-cutting concern (SDD §2.1 already lists audit under observability), not as a workflow port.

**Verdict: delete nine ports and migration 0011. Promote audit to cross-cutting. Delete the two fabricating services today.**

### 6.12 M12 Repository Execution & Continuous Learning — delete; ship the CI gate instead

**What exists** [REPO]: `RepositoryEditPort`, `PatchGenerationPort`, `PatchValidationPort`, `GitRepositoryPort`, `BranchManagerPort`, `CommitPlannerPort`, `PullRequestBuilderPort`, `LearningEnginePort`, `ExecutionHistoryPort`, `ExecutionStorePort`, migration `0012`. Depth: `patch_validator.py` 33 lines, `commit_planner.py` 31, `pull_request_builder.py` 39.

**Why delete.** Patch generation, validation, branch management, commit authoring and PR creation are precisely what Codex, Jules, Devin and Copilot's coding agent do, each behind isolated execution [DOC]. Patch validation without a sandbox that can build and test is not validation. Without execution isolation, this layer can produce diffs but cannot know whether they work — and a diff of unknown correctness is what a plain LLM already produces for free.

**The "continuous learning" problem.** A learning engine at the terminus of a one-way pipeline cannot improve resolution, ranking or retrieval — the things that determine quality. Genuine learning loops in this domain look like: outcome signals feeding an evaluation corpus, which gates the index. That is the evaluation harness, not a 47-line milestone.

**What to ship instead — and it is already prototyped.** `.github/actions/repo-intelligence/` is a composite action taking `github-token`/`api-url`/`api-token`/`check-name` and emitting `risk-score`/`risk-level`/`comment-url` [REPO]. That is a real product wedge: a CI gate that answers "what does this PR break, precisely, with citations" using the index — no mutation, no sandbox, no competition with Cognition. It currently calls a remote backend rather than the local index, which is the thing to fix.

**Comparison for that wedge.** Greptile builds a codebase graph to reason about how changes affect other parts of the system [DOC: [Greptile graph-based context](https://www.greptile.com/docs/how-greptile-works/graph-based-codebase-context)]. CodeRabbit runs review as part of the merge/CI process [DOC: [CodeRabbit deep dive](https://www.coderabbit.ai/blog/coderabbit-deep-dive)]. Both are validated markets, and both are *read-only* — reachable without an execution platform. RIA's precise call graph is a genuine advantage in exactly this niche.

**Verdict: delete all ten ports and migration 0012. Reinvest in the CI gate backed by the real index.**

---

## 7. Comparison with every major system

### 7.1 Master comparison matrix

Confidence key: **D** = vendor-documented, **T** = third-party analysis, **N** = not publicly documented.

| System | Retrieval / index | Execution isolation | Agent topology | Commit-scoped? | Languages | Conf. |
|---|---|---|---|---|---|---|
| **Claude Code** | ripgrep + structured tool calls + precise reads; vector search deliberately removed | Local, permission-gated tool use | Single agent + spawnable subagents with own context windows | No | Language-agnostic (text) | D/T |
| **OpenAI Codex** | Agentic shell search; AGENTS.md for project conventions | OS-enforced sandbox, network off by default, approval policy; cloud sandboxes with snapshots | Single agent loop running terminal commands | No | Language-agnostic | D |
| **Cursor** | Merkle-tree change detection → AST-aware chunking → embeddings in Turbopuffer with encrypted paths; plaintext not retained under privacy mode | Local editor + agent mode | Single agent (Composer/Agent) | No (present-tense index) | Language-agnostic chunking | D/T |
| **OpenHands** | Agent tools over sandbox filesystem | **Docker client-server runtime** | Event stream `(action, observation)`; delegation supported | No | Language-agnostic | D |
| **Aider** | tree-sitter symbol graph + PageRank, token-budgeted repo map | Local git working tree, auto-commits | Single agent | Per-commit via git, not indexed | tree-sitter grammar set | D |
| **Continue.dev** | Local-first index; documented path to shared/custom code RAG | Local IDE | Single agent | No | Multi | D |
| **GitHub Copilot** | Repo indexing + semantic code search; new embedding model reported +37.6% retrieval quality, 8× smaller index; Blackbird for code search | Cloud coding agent; VS Code local | Single agent + coding agent | Repo-indexed, not commit-addressed | Multi | D |
| **Sourcegraph / Cody** | **Zoekt trigram index + SCIP precise indexes**, cross-repo, MCP surface | None (read/navigate; agents act elsewhere) | N/A — intelligence layer | **Yes** (SCIP uploads per repo/commit) | 30+ via indexer ecosystem | D |
| **Devin (Cognition)** | Not publicly detailed | **Per-session isolated VM**; Outposts run in customer infra | Single agent; "managed Devins" each in own VM | N | N | D (infra) / N (retrieval) |
| **Windsurf** | Remote indexing + multi-repo context awareness (RAG-based) | Local IDE | Cascade agent | No | Multi | D (index rationale) / N (Cascade internals) |
| **Factory** | "Engineering system indexing" + native integrations + MCP; BYOK, LLM gateways | Enterprise deployment; details limited | Coordinator dispatching role-specialised droids | N | Multi | D (platform) / N (index) |
| **Google Jules** | Not publicly detailed | **Secure Google Cloud VM per task** | Single async agent; plan → diff → PR | N | Multi | D (workflow) / N (retrieval) |
| **Serena** | **LSP-over-MCP**: `find_symbol`, `find_referencing_symbols`, `replace_symbol_body` | None (tool server) | N/A — tool provider | Working-tree | **40+** | D |
| **Glean (Meta)** | Typed schema facts, Angle/Datalog queries, **stacked immutable DBs** for incrementality | N/A | N/A | Yes (versioned DBs) | Multi via indexers | D |
| **Kythe (Google)** | Node/edge entry streams from build-accurate compilation extraction | N/A | N/A | Per-compilation | C++, Go, Java + others | D |
| **RIA (current)** | Exact-name symbol lookup over SQLite; **no lexical, no vector, no grep** | **None** | 9 roles specified, 25-line implementations | **Yes — best in class** | **3 (Py/JS/TS)** | REPO |

### 7.2 Per-system: similarities, differences, and what RIA should take

**vs Claude Code** — *The competitor that could make RIA unnecessary.*
Similar: nothing. Different: everything. Claude Code's thesis is that no index is needed; RIA's is that a precise index is infrastructure. Anthropic tested theirs by measurement and removed the index [DOC]. RIA has not tested its own. **Take:** run the head-to-head immediately — RIA's PRD already specifies it (arms A–F including a long-context baseline, SDD §8). Also take the honest cost framing: RIA's real pitch is not "better answers" but "fewer tokens and lower latency for the same answer," which is a measurable, defensible claim that agentic grep genuinely loses on at scale (50–200 searches per session, per the Claude Code issue thread [DOC]).

**vs OpenAI Codex** — *The reason M11/M12 should not exist.*
Similar: nothing today. Different: Codex has an OS-enforced sandbox with network disabled and an approval policy propagating down the process tree [DOC]. RIA's tool executor returns strings. **Take:** if execution is ever built, buy or adopt an isolation primitive; do not hand-roll. Also take AGENTS.md as a design lesson — a cheap, file-based convention layer beat a sophisticated config system.

**vs Cursor** — *The closest thing to a real indexing peer.*
Similar: both index; both care about change detection. Different: Cursor's index is present-tense and embedding-based; RIA's is commit-addressed and symbol-based. Cursor's privacy design (embeddings + obfuscated/encrypted paths persisted, plaintext not retained beyond the request) is a shipped answer to the objection RIA will hit on its first enterprise call [DOC]. **Take:** (1) the Merkle/tree-hash change-detection pattern, adapted to git trees, which RIA can do better because it already has commit trees; (2) the privacy architecture, near-verbatim, as a design requirement — RIA currently stores full source in a local CAS with no encryption story.

**vs OpenHands** — *The reference architecture RIA's M11 should have copied.*
Similar: both have a layered, port-based, model-agnostic design. Different: OpenHands' central abstraction is a typed event stream where the `(action, observation)` log *is* the state, and the runtime is a Docker client-server [DOC]. That single abstraction replaces RIA's `WorkflowExecutorPort` + `ExecutionStateMachinePort` + `ToolExecutionPort` + `AgentOrchestratorPort` + `CommunicationBusPort` + `SharedContextPort`. **Take:** if any agent layer survives, use one event log, not six ports. Also note OpenHands ships native sandboxed execution, lifecycle control, multi-LLM routing and security analysis as *framework* features [DOC: SDK paper] — that is the build/buy line RIA is currently on the wrong side of.

**vs Aider** — *The benchmark RIA must beat to justify itself.*
Similar: tree-sitter symbol extraction, graph over symbols, token-budgeted output. Different: Aider does it with no database, no persistence, no snapshots, and ranks with PageRank [DOC]. **Take:** PageRank/centrality as a ranking signal — RIA's M8 has a `RankingEnginePort` with no signals, and graph centrality is a free, deterministic, defensible one that RIA is uniquely positioned to compute well. Also take the humility: Aider is the control group. Any RIA layer that cannot beat a PageRanked tree-sitter map on a measured task is unjustified complexity.

**vs Continue.dev** — *The "index once for the team" thesis.*
Similar: both see per-developer indexing as wasteful. Continue documents building a custom code RAG so the codebase is indexed once for all users [DOC]. That is RIA's commercial thesis, already validated by someone else's docs. **Take:** this is a positioning gift — cite it. It also implies the deliverable is a *server*, which RIA does not have.

**vs GitHub Copilot** — *The scale reference for embeddings.*
Different: Copilot invests in embedding quality (reported +37.6% retrieval quality, ~2× throughput, 8× smaller index) and uses semantic search precisely when exact names are unknown [DOC]. **Take:** the framing "semantic search for when you don't know the name; precise search for when you do" is the correct division of labour, and it is an argument for RIA adding a fuzzy path rather than banning it.

**vs Sourcegraph / Cody** — *The direct incumbent. Read this row twice.*
Similar: commit/revision-scoped precise indexes, deterministic navigation, agents and humans as co-equal consumers, MCP delivery. Sourcegraph has explicitly repositioned as "the intelligence layer for AI coding agents and developers" [DOC] — that is RIA's PRD §1.1 as a shipped product. Different: they have Zoekt (trigram, ~2–3× corpus index size, battle-tested at 19k repos / 2.6B lines), SCIP with a multi-language indexer ecosystem, cross-repo search, and an MCP server [DOC]. They also publish a build-vs-buy argument aimed squarely at teams considering RIA's project [DOC: [what it takes to run code intelligence in-house](https://sourcegraph.com/blog/what-it-actually-takes-to-run-code-intelligence-in-house)]. **Take:** adopt SCIP as an ingestion format (§12.2). This converts Sourcegraph's ecosystem from a moat into a supply chain. RIA's genuine differentiators against them are (a) commit-addressed history as a first-class query axis and (b) the coverage/provenance/confidence envelope. Those are narrow but real. Everything else is a losing fight.

**vs Devin** — *The topology lesson and the isolation lesson.*
Documented: per-session isolated VMs, managed Devins each in their own VM verifying their own changes, Outposts for customer-controlled infra [DOC]. Retrieval internals are **not public**. Cognition also authored the strongest published argument against multi-agent for coding [DOC]. **Take:** the isolation model if execution is ever built; the topology argument as grounds to delete M10.

**vs Windsurf** — *Limited public information.*
Documented: remote indexing and multi-repo context awareness, with the fine-tuning-vs-context-awareness framing [DOC]. Cascade/Riptide internals are **not publicly documented**; SEO content claiming specific graph architectures is not credible evidence. **Take:** multi-repo context as a first-class requirement — RIA has no cross-repo identity story and its own twin spec lists this as open question T4.

**vs Factory** — *The enterprise-control reference.*
Documented: hierarchical model allow/deny, LLM gateways, BYOK, MCP servers, and a coordinator dispatching to role-specialised droids [DOC]. **Take:** the enterprise control surface (model allow/deny, BYOK, gateway) is what an enterprise buyer asks for in the first meeting, and RIA has none of it. Note also that Factory *does* use role-specialised agents — which is a fair counterpoint to §6.10. The distinction that holds: Factory's roles map to distinct SDLC artefacts (review, docs, test) with separate outputs, not to nine collaborators editing one tree.

**vs Google Jules** — *The async-PR product shape.*
Documented: clones into a secure Google Cloud VM, works asynchronously, returns plan + reasoning + diff [DOC]. **Take:** the async, PR-shaped delivery model is the right UX for RIA's CI-gate wedge — post findings on the PR, do not hold a session open.

**vs Serena** — *The competitor RIA most resembles, and the cheapest path to breadth.*
Similar: symbol-level retrieval as a service to agents, MCP delivery. Different: Serena gets 40+ languages by delegating to language servers, is MIT-licensed, has ~25k stars, and is already consumed by Claude Code, Codex, Cursor, Copilot and JetBrains assistants [DOC]. **This is the most important competitive fact in the report and it does not appear anywhere in RIA's foundation documents.** RIA's PRD §1.2 falsification condition ("agent vendors decide retrieval is their differentiator and build it in-house") has a sibling that already fired: *an open-source project already gave every agent symbol-level retrieval for free.* **Take:** RIA's answer must be what Serena structurally cannot do — persistent cross-commit history, cross-repo identity, and confidence/coverage reporting. LSP is working-tree-scoped and stateless; that is the gap. If RIA does not build to that gap specifically, it is building a slower Serena with three languages.

**vs Glean / Kythe** — *The architectural elders.*
Similar: typed facts, schema-defined, pluggable indexers, derived layers. Different: Glean's stacked immutable DBs give real incrementality with multi-version coexistence [DOC]; Kythe's build-accurate compilation extraction gives resolution accuracy tree-sitter cannot reach [DOC]. **Take:** (1) stacked-DB incrementality instead of RIA's evict-only caches; (2) a Datalog-ish query surface is the mature shape for 23 primitives — it generalises where 23 hand-written methods do not; (3) build-integration as the Tier-B accuracy ceiling, which is what SCIP indexers effectively provide.

### 7.3 Over- and under-engineering, itemised

**Over-engineered relative to every system above** [all REPO]:
- 19 ports, 85 domain model modules, 91 application services, 12 SQL migrations — for a system with zero users and zero benchmark runs.
- 10 ports each for M10, M11, M12 (30 ports for three deleted layers).
- Twin persistence: 5 ports and a 287-line store for a composite of immutable parts.
- Registry ports (`ParserRegistryPort`, `SemanticRegistryPort`, `GraphRegistryPort`, `TwinRegistryPort`, `QueryRegistryPort`, `ContextRegistryPort`, `ReasoningRegistryPort`, `WorkflowRegistryPort`) — eight registries whose combined job is version strings and capability lists. One `CapabilityRegistry` suffices.
- Three router prefixes per router in the legacy backend, tripling the OpenAPI surface, with two 3-line stub routers mounted three times each.

**Under-engineered relative to every system above**:
- No evaluation harness (Glean, GitHub, Sourcegraph, Agentless all measure).
- No delivery surface (Serena, Sourcegraph, Factory all ship MCP).
- No lexical index (Sourcegraph/GitHub), no embeddings (Cursor/Copilot/Continue), no grep (Claude Code/Codex).
- No execution isolation while claiming execution (OpenHands/Codex/Devin/Jules).
- No dependency-tracked incrementality (Salsa/Glean).
- No cross-repo identity (Sourcegraph/Windsurf).
- No tracing, no cost accounting, no model gateway (OpenHands/Factory).
- No language breadth mechanism (Serena/Sourcegraph via LSP/SCIP).

---

## 8. Scalability analysis

Stated targets [REPO SDD §1.1 G1–G8]: 10M LOC, ~10⁷ symbols, ~10⁸ edges, p95 <200ms graph queries at 1M LOC, p95 <2s incremental for ≤10 files, ≥80% zero-LLM queries.

| Constraint | Ceiling as built | Analysis |
|---|---|---|
| **Storage engine** | ~10⁵–10⁶ symbols, single tenant, single writer | SQLite has a single-writer lock per database file; WAL lets readers proceed but writes serialise [DOC: [tenthousandmeters](https://tenthousandmeters.com/blog/sqlite-concurrent-writes-and-database-is-locked-errors/), [Turso explainer](https://betterstack.com/community/guides/databases/turso-explained/)]. Practical dataset ceilings around 1TB and no native replication are widely reported [DOC: [sesamedisk](https://sesamedisk.com/sqlite-in-production-2026/)]. Facts + derived + all caches + the job queue share one file [REPO], so ingestion writes block cache writes block queue leases. |
| **Graph traversal** | Fails at ~10⁶ edges | Whole-graph materialisation (§6.5). At 10⁸ edges this is not a tuning problem. |
| **Graph cache** | Fails earlier than traversal | Entire snapshot as one JSON column [REPO]. |
| **Workers** | 1 | Single-process `JobRunner`; no worker container in compose [REPO]. |
| **Rate limiting** | Incorrect above 1 process | In-process sliding window per client IP, with a `127.0.0.1`/`::1` bypass [REPO `backend/security_middleware.py`]. |
| **Multi-repo / multi-tenant** | Not designed | No tenancy column strategy visible; twin spec T4 (cross-repo identity) open [REPO]. |
| **Language breadth** | 3 | Linear engineering cost per language without SCIP. |

**What the industry's numbers imply for RIA's targets.** Zoekt's index runs ~2–3× corpus size with trigram metadata resident in memory, and Sourcegraph's own guidance was to size nodes to hold the text of default branches [DOC]. A corpus of 19k repos / 2.6B lines occupied 166GB on disk [DOC]. RIA's 10M-LOC target is far smaller than that, which is encouraging — but it means the index must be **on-disk, paged, and sharded**, exactly what a single SQLite file with whole-snapshot blobs is not.

**Horizontal scaling path (currently absent, in dependency order):**
1. Extract the ingest worker into its own process; queue stays as-is initially.
2. Move facts to PostgreSQL, partitioned by `(repo_id, commit_id)` as SDD §6.2 already specifies. This alone removes the single-writer ceiling and enables read replicas.
3. Move the queue off the facts DB (Redis, SQS, or a dedicated Postgres schema with `SKIP LOCKED`).
4. Convert graph traversal to bounded recursive CTEs with covering indexes; delete the graph cache.
5. Shard by repository. Repository-level sharding is natural because no query crosses repos until cross-repo identity exists.
6. Blob store to S3-compatible; keep the CAS interface.

**Verdict: the design can scale; the implementation cannot, and the gap is roughly one quarter of focused infrastructure work — not a rewrite.**

---

## 9. Performance analysis

**Known bottlenecks, ordered by expected impact** [all REPO unless noted]:

1. **Whole-graph materialisation** (§6.5). Every graph query pays O(nodes + edges) deserialisation. This makes the p95 <200ms goal unreachable at any interesting size.
2. **JSON round-tripping as the storage format.** `node_json`, `edge_json`, `snapshot_json`, and `mappers.py` (785 lines) indicate JSON columns are pervasive. Every read pays `json.loads` plus object construction. Typed columns with covering indexes are 10–100× cheaper for point/neighbourhood queries — which SDD §1.3 constraint 4 identifies as the dominant profile.
3. **Import-time work in the shipped app.** `backend/api.py` runs `configure_logging`, `run_migrations()`, `_load_analysis_store()`, and `_warmup_services()` (eagerly loading a BGE sentence-transformer and a tree-sitter parser) **at module import**. This makes cold start slow, breaks liveness semantics, and makes the module unimportable in constrained environments.
4. **Module-level mutable state.** `ANALYSIS_STORE` is a process-global hydrated at import — the exact pattern SDD §7 lists as rejected. It also prevents multi-worker correctness.
5. **Recursive DFS.** `GraphTraversalService.depth_first` uses Python recursion, so deep graphs hit the recursion limit before they hit a performance limit.
6. **No pagination or result limits** in the query ports. `find_references` on a widely-used symbol returns everything.
7. **No tokenizer-accurate budgeting.** `LocalModelProvider` estimates tokens as `len(text)//4`, which is a placeholder, not a budget.
8. **File enumeration for change detection** rather than `git diff-tree` (§6.2).
9. **No response caching at the edge.** SDD specifies cache at L8; L8 does not exist.

**Missing performance infrastructure:** no benchmark harness, no load generator, no latency SLO assertions in CI, no tracing (the observability package is logging + metrics only, by deliberate choice per M1 §2.9 [REPO]), no flame-graph or profiling workflow, no index-size accounting. The only performance test is 52 lines.

**The measurement gap is the real finding.** Every number in SDD §1.1 is an assertion. A p95 target with no harness is a wish. Building the harness is ~2 engineer-weeks and would change design decisions immediately — which is precisely what happened to Anthropic when they measured agentic search against RAG [DOC] and to the Agentless authors when they measured simplicity against agents [DOC].

---

## 10. Security analysis

### 10.1 Findings

| # | Finding | Severity | Evidence |
|---|---|---|---|
| S1 | **Auth is off by default.** `APIKeyMiddleware` returns `call_next(request)` immediately when `settings.api_key` is unset. A deployment that forgets one env var is fully open. | **Critical** | [REPO] `backend/security_middleware.py` |
| S2 | **Auth is allowlist-by-path, not deny-by-default.** Only a hardcoded prefix list (`/api/analyze`, `/api/index`, `/api/chat`, `/api/retrieve`, `/api/issues/map`, their `/api/v1` twins, and any path containing `/report`) is protected. Repositories, graph, twin, execution, workspace, memory, symbols and PR routers are unauthenticated. | **Critical** | [REPO] same file |
| S3 | **Rate limiting bypassed from loopback** and incorrect across workers (per-process sliding window). Behind any reverse proxy that presents `127.0.0.1`, the bypass is global. | **High** | [REPO] `RateLimitMiddleware` |
| S4 | **No sandbox, while M11/M12 model repository mutation.** Codex, OpenHands, Devin and Jules all isolate [DOC]. | **High** | [REPO] zero `sandbox` matches |
| S5 | **No dependency pinning.** All deps are lower-bound ranges (`fastapi>=0.110`, `chromadb>=0.4`, …); `uv.lock` exists but CI installs from `requirements.txt`. Supply-chain exposure with no SBOM, no `pip-audit`, no Dependabot evidence. | **High** | [REPO] `pyproject.toml`, `ci.yml` |
| S6 | **Container runs as root**, no `HEALTHCHECK`, no read-only filesystem, no dropped capabilities. Release workflow pushes to GHCR with no image scan, no SBOM, no provenance attestation, and does not re-run tests before publishing. | **High** | [REPO] `Dockerfile`, `release.yml` |
| S7 | **`.env` present in the working tree.** Secrets management is `.env` + pydantic-settings; no vault/KMS, no rotation. Credit: `ria/config/settings.py` holds no credentials at all, which is the right design. | **Medium** | [REPO] |
| S8 | **Source code stored unencrypted in a local CAS**, with no privacy mode, no path obfuscation, no retention policy. Cursor's shipped answer (embeddings + encrypted paths persisted; plaintext not retained beyond the request) is the bar enterprise buyers will apply [DOC]. | **Medium** | [REPO] `filesystem_blob_store.py` |
| S9 | **CORS with `allow_credentials=True`** plus dev-origin injection into the production origin list when `frontend_url` differs. | **Medium** | [REPO] `backend/api.py` |
| S10 | **No authorization model at all** — no RBAC, no per-key scoping, no tenancy isolation, no repository-level ACLs. Any authenticated caller reaches every repository. | **High** (blocks enterprise) | [REPO] |
| S11 | **Prompt-injection surface unaddressed.** M9 will feed repository content (including untrusted PR content in the CI-gate wedge) into model prompts with no provenance-based trust separation. | **Medium→High** once M9 is real | [REPO] |

### 10.2 Security credit where due

- `SubprocessGitClient` uses argv arrays with explicit timeouts and `-z` parsing — no shell interpolation, no path-splitting bugs [REPO].
- `ria.domain` and `ria.ports` are provably free of third-party and credential-bearing code, enforced by test [REPO].
- The determinism boundary means untrusted content cannot reach a model below L7 — a genuinely useful injection containment property, currently over-enforced but architecturally correct.
- `gemini_provider.py` handles keys without logging them [REPO].

### 10.3 Minimum viable security posture before any external user

Deny-by-default auth · per-key repository scoping · tenancy column on every fact table · rate limiting in shared storage · pinned dependencies + `pip-audit` in CI · non-root container with healthcheck · image scan + SBOM in release · encrypted-at-rest blob store with a documented retention policy · audit log for every query with principal and repo.

---

## 11. Developer experience, enterprise readiness, cloud readiness

### 11.1 Developer experience — 6.0/10

**Strong** [REPO]: the foundation docs are unusually good and genuinely decision-useful; the architecture fitness tests give fast, specific feedback; ports are clean `Protocol`s with real docstrings; `tests/ria/fakes.py` (758 lines) is a proper test double library; milestone docs for M1–M2 record defects found and deviations taken, which is professional practice most teams skip.

**Weak** [REPO]: **no type checker anywhere** despite a fully annotated codebase — that is a large amount of annotation effort producing zero verification; **no coverage measurement**, so 1034 tests have unknown reach; ruff runs on defaults (E/F only) with no configured ruleset; no pre-commit hooks; Python version is inconsistent three ways (`requires-python>=3.9`, CI 3.12, Docker 3.11) which means `3.9` compatibility is claimed and never tested; two `.md` files in `tests/` named `test_*`; onboarding requires understanding two parallel architectures with no `CONTRIBUTING` guidance on which to touch.

**Highest-leverage DX fixes, in order:** add `mypy --strict` on `ria/` to CI (the annotations are already there — this is nearly free verification); add coverage with a floor on `ria/`; configure ruff properly; align Python versions; delete or archive the legacy stack.

### 11.2 Enterprise readiness — 1.5/10

Present: structured JSON logging with ambient context, metrics behind a port, request IDs.

Absent: SSO/OIDC · RBAC · multi-tenancy · per-repo ACLs · audit trail of queries · quota/billing metering · data residency · encryption at rest · key rotation · retention/deletion (GDPR/DSAR) · SOC 2 / ISO posture · BYOK or model allow/deny (which Factory ships as a baseline enterprise feature [DOC]) · self-hosted deployment story beyond one container · SLA/uptime instrumentation · support/on-call runbooks (there is `docs/production.md`, 269 lines, which is a start).

The SDD is right that "multi-tenancy, authz, and quota cannot be retrofitted… load-bearing from day one even when there is one tenant" [REPO §2.2]. That statement is correct and was not acted on. Adding a `tenant_id` to every fact table now costs hours; adding it after external users costs a migration project.

### 11.3 Cloud readiness — 2.0/10

Present: multi-stage Dockerfile, GHCR release pipeline with QEMU/Buildx and gha caching, dev and prod compose files.

Absent: any Kubernetes manifest, Helm chart, Terraform, or CloudFormation (verified: no `infra/`, `deploy/`, or `k8s/` outside `.venv`/`node_modules`) · no separate worker container · no Postgres or Redis service in compose · no reverse proxy · no horizontal pod autoscaling story · no readiness/liveness endpoints wired to real dependency checks · no graceful shutdown or in-flight job draining · no blue/green or canary path · no backup/restore procedure for the SQLite file that holds all state · no disaster recovery plan · no multi-region consideration.

`ria/` cannot run in the published image at all [REPO `Dockerfile`].

---

## 12. Suggested redesign

### 12.1 Collapse twelve milestones into six cores

| New core | Absorbs | Rationale |
|---|---|---|
| **C1 Index Core** | M1 + M2 + M3 | One lifecycle: git-driven, batch, scales with repo size. Add git-diff change detection and SCIP ingestion. |
| **C2 Resolution** | M4 (+ new Tier-B) | The moat. Split Tier A (tree-sitter, breadth) from Tier B (SCIP/LSP, precision) behind one `ResolutionPort`. Add Salsa-style dependency tracking. |
| **C3 Fact Store & Graph** | M5 + M6 persistence | Facts and adjacency in one relational store. Delete the `Graph` object, the graph cache, and the twin snapshot store. Postgres-first. |
| **C4 Query API & Delivery** | M7 + SDD L8 + L9 | The product. 20 deterministic primitives + MCP server + REST + CLI. Contract, authz, quota, pagination, deterministic ordering, latency budget. Twin becomes a *read model* here. |
| **C5 Retrieval** | reduced M8 + new lexical/vector | Symbol + trigram/FTS5 + optional embeddings behind a port. Ranking on graph centrality and recency. Token-budgeted shaping. Citations. |
| **C6 Grounded Answers** | reduced M9 | One real provider via a gateway, prompt registry with versioned provenance, citation verifier that rejects unresolvable claims. |
| **Cross-cutting** | new | **Evaluation harness (first-class)**, orchestration/workers, control plane (tenancy/authz/quota), observability incl. tracing, audit. |
| **Deleted** | M10, M11, M12 | Contradict the PRD, contradict published evidence, and compete with better-funded incumbents. |

### 12.2 The single highest-leverage change: adopt SCIP as an ingestion format

Rationale: RIA's moniker scheme (`scheme:package:descriptor`) is already essentially SCIP's symbol design [REPO twin spec §identity]. SCIP is an open format with a multi-language indexer ecosystem, explicitly built as an improvement over LSIF for exactly this purpose [DOC: [announcing SCIP](https://sourcegraph.com/blog/announcing-scip)]. Consequences of adopting it:

- Language breadth goes from 3 to the size of the SCIP indexer ecosystem, without RIA writing extractors.
- PRD P10 ("buy language breadth") becomes true instead of aspirational.
- Tier B precision arrives via build-accurate indexers, which is how Kythe reaches accuracy tree-sitter cannot [DOC].
- Interop: RIA can *consume* existing customer SCIP uploads, which is a shorter sales cycle than "re-index everything with us."
- Cost: one `ScipIndexerPort` + a SCIP protobuf reader + moniker mapping. Weeks, not quarters.

### 12.3 Mergers

- M1 → M2 (one ingestion lifecycle).
- M6 persistence → C3; M6 query contract → C4 as a read model.
- M8's planning/prompt concerns → C6; M8's retrieval/ranking → C5; M8's intent classification → deleted.
- Eight registry ports → one `CapabilityRegistry`.
- M11's `AuditLogPort` → cross-cutting observability.

### 12.4 Splits

- **M4 → Tier A / Tier B** behind one port. Different accuracy, different cost, different confidence; they must be separately measurable because the confidence envelope depends on knowing which produced a result.
- **M7 → query primitives vs derived analytics.** Impact, architecture, pattern-matching and cross-reference analysis are consumers of the primitives, not peers of them, and they belong above the gateway so they can be versioned and rate-limited separately.
- **Ingest worker → separate process/deployable.** The first real scaling seam.
- **Evaluation → its own top-level package with its own CI job.** SDD §2.1 already calls it cross-cutting infrastructure; it should not live in `tests/`.

### 12.5 Fix the architecture rule that blocks the product

`TestNoModelCallsBelowReasoning` currently bans model and embedding clients package-wide, which is why M9's providers are echo stubs [REPO]. Replace with a layer-scoped rule:

- `openai` / `anthropic` / `google-genai` importable **only** from `ria.infrastructure.models`.
- `sentence_transformers` / embedding clients importable **only** from `ria.infrastructure.embeddings`.
- Forbidden in `ria.domain`, `ria.ports`, `ria.observability`, and in every `ria.application` module except the reasoning services.
- Add the inverse rule: no `ria.application.{ingestion,parser,semantic,graph,query}*` module may import `ria.infrastructure.models`.

This preserves the guarantee that made the rule valuable while allowing the product to exist.

### 12.6 Also fix, immediately

1. Delete `ToolExecutionService` and `VerificationPipelineService`, or make them return explicit `NOT_EXECUTED` (§6.11). This is a correctness defect, not a roadmap item.
2. Remove the `Graph` parameter from `TraversalPort` and delete `SqliteGraphCacheStore` (§6.5).
3. Make `backend` auth deny-by-default, or take the legacy app off any public network.
4. Add `mypy --strict` on `ria/` to CI.
5. Pin dependencies and add `pip-audit`.
6. Unmount the two 3-line stub routers and collapse the triple prefix mounting.

---

## 13. Missing systems — the full checklist

Every item the brief asked about, with a verdict on whether RIA actually needs it. "Needed" is judged against the reduced C1–C6 scope, not the current twelve.

### 13.1 Needed and missing — build these

| System | Why needed | Priority |
|---|---|---|
| **Delivery layer (MCP + REST + CLI)** | Without it there is no product. MCP is the 2026 distribution channel [DOC: Serena, Sourcegraph MCP] | **P0** |
| **Evaluation harness** (labelled corpus, precision/recall gates, latency SLOs, issue→PR benchmark) | The only differentiator is currently unmeasured. SDD §8 already specifies it | **P0** |
| **PostgreSQL facts spine** | Removes the single-writer ceiling; already the specified choice | **P0** |
| **Bounded graph adjacency queries** | Current design contradicts SDD §1.3 c2 and cannot hit p95 targets | **P0** |
| **Lexical index** (trigram or SQLite FTS5 → Zoekt-class later) | The fuzzy path every competitor has and RIA lacks | **P1** |
| **Authentication / authorization / tenancy** | Cannot be retrofitted (SDD §2.2 says so); blocks every enterprise conversation | **P1** |
| **Model gateway + prompt registry + cost accounting** | Provenance requires prompt version; economics require cost per query | **P1** |
| **Distributed worker process** | First real scaling seam; queue primitive already exists | **P1** |
| **Tracing** (OpenTelemetry) | Multi-layer latency attribution is impossible without it | **P1** |
| **Embedding service behind a port** | Required to run RIA's own falsification test; keep optional | **P1** |
| **Dependency-tracked incrementality** (Salsa-style early cutoff or Glean-style stacked DBs) | The p95 <2s incremental goal is unsubstantiated without it | **P2** |
| **Cross-repo identity + multi-repo support** | Twin spec T4; enterprise buyers are multi-repo; Sourcegraph's core differentiator | **P2** |
| **Object storage adapter (S3-compatible)** | Specified; needed for horizontal scale and durability | **P2** |
| **Secrets management** (vault/KMS, rotation) | `.env` is not an enterprise answer | **P2** |
| **Query result cache at the gateway** | Specified at L8; cheap latency win | **P2** |
| **Artifact storage** (index artefacts, SCIP uploads, eval snapshots) | Needed once indexes are shared across a team | **P2** |
| **Configuration management + feature flags** | Needed to ship risky index changes safely | **P3** |
| **Rate limiting in shared storage** | Current implementation is incorrect above one process | **P1** |
| **Backup/restore + DR runbook** | All state currently lives in one unbacked-up file | **P2** |
| **Encryption at rest + retention policy for source blobs** | Buyer requirement; Cursor's model is the reference [DOC] | **P2** |

### 13.2 Needed only if execution is ever built — deliberately deferred

Sandbox / container execution · terminal executor · workspace manager · workspace snapshots · rollback engine · patch validation with real build+test · GPU scheduling. All of these are table stakes for an execution product (§3 School E) and none of them are worth starting while the index is unmeasured. Recommendation: never build them; integrate with OpenHands/Codex/Devin instead, which is also the go-to-market.

### 13.3 Not needed — do not build

| System | Why not |
|---|---|
| **Event bus / message broker** | SDD §7 already rejected event sourcing. A durable job queue covers the real need. Domain events add a distributed-debugging tax for no current consumer. |
| **Microservices** | The modular monolith with named extraction seams (SDD §6.1) is the correct call for a team this size. Keep it. Extract the worker; extract nothing else. |
| **Multi-agent orchestration / shared agent memory / conflict resolution** | §6.10. Delete. |
| **Marketplace / plugin architecture / extension API** | Premature by years. The language-plugin registry already covers the one extensibility axis that matters. |
| **GPU scheduling** | No owned models. Use hosted inference. |
| **Distributed execution framework** | Repository-level sharding plus a queue covers the workload; Ray-class infrastructure is unjustified. |
| **Tool registry** | Only meaningful if RIA hosts an agent loop. It should not. MCP's own tool listing is the registry. |
| **Policy engine** | Deny-by-default authz plus repo scoping is sufficient until there is a second tenant with different rules. |

### 13.4 Architectural style verdict

Modular monolith, as chosen [REPO SDD §6.1] — correct, and the four named extraction seams are the right hedge. The only extraction to perform now is the ingest worker. Microservices at this stage would multiply the operational surface of a system that has not yet served one query.

---

## 14. Risk analysis

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | **Agentic search is good enough and the index is unnecessary.** Anthropic measured this and removed their index [DOC]. RIA's PRD lists it as a falsification condition and has not tested it. | **High** | **Fatal** | Run the head-to-head benchmark (SDD §8 arms A–F) before any further layer work. Reframe the pitch around tokens and latency, which is where grep genuinely loses. |
| R2 | **Serena already occupies the position.** LSP-over-MCP, 40+ languages, MIT, ~25k stars, consumed by every major agent [DOC]. Not mentioned anywhere in RIA's foundation docs. | **High** | **Severe** | Differentiate on what LSP structurally cannot do: cross-commit history, cross-repo identity, coverage/confidence reporting. If RIA cannot articulate that in one sentence, stop. |
| R3 | **Sourcegraph is the incumbent and has repositioned onto RIA's exact thesis** [DOC]. | **High** | **Severe** | Adopt SCIP (§12.2) to convert their ecosystem into supply. Compete on history + provenance, not on breadth. |
| R4 | **The precision claim fails when measured.** 0.95/0.90 on Python+TS with tree-sitter only, no build integration, no type inference. | **Medium-High** | **Severe** | Measure early on a small labelled corpus. If Tier A cannot reach it, that is the argument for SCIP, and it is better learned in week 3 than year 2. |
| R5 | **Storage rewrite discovered late.** Postgres migration after external users is a project, not a task. | **High** if deferred | **High** | Migrate before the first external user. Cost now: weeks. |
| R6 | **Graph model rewrite.** `Graph` appears in port signatures, so removing it touches every graph consumer. | **Certain** | **High** | Do it now while the only consumers are tests. |
| R7 | **Fabricated verification evidence reaches a consumer.** | Medium | **Severe** (trust-destroying) | Delete today (§12.6.1). |
| R8 | **Two parallel architectures diverge further.** 60k LOC of duplicated intent; the wrong one ships. | **High** | **High** | Pick one this quarter. Recommended: freeze the legacy stack behind a feature flag, give `ria` a delivery surface, cut over, delete. |
| R9 | **Scope collapse under maintenance load.** 19 ports / 91 services / 12 migrations with no users is already more surface than a small team can evolve. | **High** | **High** | Execute §12.1. Deleting M10–M12 removes 30 ports and 3 migrations. |
| R10 | **Unmeasured test suite gives false confidence.** 1034 tests, no coverage, no mypy, +15 tests per upper layer. | **Certain** | **Medium** | Coverage floor + mypy strict. Expect the numbers to be uncomfortable. |
| R11 | **Security incident from default-open auth.** | Medium | **Severe** | Deny-by-default now, or keep the legacy app off public networks. |
| R12 | **Context windows and cost improve past the threshold** (PRD's own indicator: ≥10M tokens at <$0.10/Mtok with reliable long-range retrieval). | Medium | **Fatal** | Track it explicitly. Note the counter-evidence: context-rot findings and the industry-wide move to compaction and memory suggest bigger windows are not a full substitute [DOC: [Anthropic context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents), [long-running harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)]. |
| R13 | **Supply-chain compromise** via unpinned dependencies with no audit or SBOM. | Medium | High | Pin, `pip-audit`, SBOM in release. |
| R14 | **Single-file state loss.** All facts, caches and the queue in one unbacked-up SQLite file. | Medium | High | Backup procedure now; Postgres later. |

---

## 15. Roadmap and priority improvements

Sequenced so that each phase produces something that can be falsified. No phase depends on a later one.

### Phase 0 — Stop the bleeding (1–2 weeks)

1. Delete `ToolExecutionService` + `VerificationPipelineService` (fabricated evidence).
2. Make legacy auth deny-by-default, or remove the legacy app from public exposure.
3. Pin dependencies; add `pip-audit`; non-root container; add `HEALTHCHECK`.
4. Add `mypy --strict` on `ria/` and a coverage floor to CI.
5. Unmount stub routers; collapse triple-prefix mounting.
6. Align Python versions across `pyproject.toml`, CI, and Docker.

**Exit criterion:** CI verifies types and coverage; no component can report success for work it did not do.

### Phase 1 — Prove or kill the thesis (3–5 weeks)

7. Build the evaluation harness: labelled resolution corpus for Python + TypeScript; precision/recall computation; latency measurement; CI gate wired to SDD §8.3 thresholds.
8. Run the head-to-head from SDD §8: RIA-resolved retrieval vs embedding baseline vs long-context baseline vs agentic grep, on the issue→PR benchmark.
9. Publish the numbers internally, including the failures.

**Exit criterion:** a defensible answer to "does precision measurably help an agent?" **This is the single most important gate in the entire programme. If the answer is no, stop — and stopping here costs 5 weeks instead of 5 years.**

### Phase 2 — Make it a product (6–10 weeks)

10. MCP server exposing the 20 deterministic primitives, thin and task-scoped (thin-MCP designs benchmarked ~75% cheaper in tokens than broad surfaces without accuracy loss [DOC]).
11. REST gateway with contract versioning, authz, quota, pagination, deterministic ordering, latency budget, and result caching (SDD L8).
12. Remove `Graph` from all port signatures; bounded recursive-CTE adjacency; delete the graph cache and twin snapshot store.
13. PostgreSQL facts spine, partitioned by `(repo_id, commit_id)`; `tenant_id` on every fact table from the first migration.
14. Extract the ingest worker into its own process.
15. Deny-by-default authz with per-key repository scoping; rate limiting in shared storage.

**Exit criterion:** an external agent (Claude Code or Codex via MCP) answers a real question against a real repository through RIA, authenticated, under an SLO.

### Phase 3 — Breadth and depth (10–16 weeks)

16. SCIP ingestion adapter + moniker mapping → language breadth (§12.2).
17. Tier A / Tier B split behind one resolution port, with per-tier confidence reporting.
18. Lexical index (FTS5 first, Zoekt-class if measurement justifies it).
19. Embedding path behind a port, enabled only where measurement shows a win.
20. Graph-centrality ranking (the Aider lesson).
21. Model gateway + versioned prompt registry + cost accounting; one real provider; citation verifier that rejects unresolvable claims.
22. OpenTelemetry tracing.

**Exit criterion:** ≥10 languages with published per-language coverage and confidence; measured recall improvement over Phase 1 baseline.

### Phase 4 — The wedge (8–12 weeks)

23. CI architecture gate backed by the real index: precise impact analysis on a PR with citations, no mutation, no sandbox. `.github/actions/repo-intelligence/` is the prototype; point it at the local index.
24. Cross-repo identity + multi-repo indexing.
25. Engineering memory (SDD L6): timeline, evolution, trends, `twin_at` — the cross-commit queries that LSP-based competitors structurally cannot answer. **This is the differentiation, and it is currently the only entirely missing specified layer.**

**Exit criterion:** a paying design partner using the CI gate.

### Never (recommended)

M10 multi-agent platform · M11 workflow execution · M12 patch/commit/PR generation · sandbox/container execution · marketplace · plugin/extension API · event bus · microservices.

---

## 16. Technical debt analysis

| Debt | Type | Interest rate | Principal | Action |
|---|---|---|---|---|
| Two parallel architectures (60k LOC) | Structural | **Very high** — every change requires deciding which system | Weeks to cut over + delete | Freeze legacy, deliver `ria`, delete legacy |
| `Graph` in port signatures | Design | High — grows with every consumer | Days now, months later | Fix in Phase 2 |
| SQLite as facts + derived + cache + queue | Substrate | High | 3–5 weeks to Postgres | Phase 2 |
| JSON columns as primary storage format | Performance | Medium-high | Per-table migrations | Phase 2, alongside Postgres |
| Echo-stub model providers | Correctness | Medium | Days once the rule is scoped | Phase 3 |
| Fabricated tool/verification results | **Correctness defect, not debt** | N/A | Hours | Phase 0 |
| No type checker on annotated code | Verification | Medium — annotations rot silently | Hours to enable, days to fix fallout | Phase 0 |
| No coverage measurement | Verification | Medium | Hours to enable | Phase 0 |
| Package-wide model-import ban | Design | Medium — blocks the product | Hours | Phase 0/3 |
| 30 ports for M10–M12 | Surface | Medium — maintenance with no value | Deletion | Phase 1 |
| 8 registry ports | Surface | Low-medium | Consolidation | Phase 3 |
| Import-time side effects + module-global `ANALYSIS_STORE` | Correctness/perf | High while legacy ships | Days | Phase 0 or delete with legacy |
| Triple-prefix router mounting + stub routers | API surface | Low-medium | Hours | Phase 0 |
| Unpinned dependencies | Supply chain | Medium | Hours | Phase 0 |
| Python version inconsistency | Build | Low-medium | Hours | Phase 0 |
| No tracing | Observability | Medium, growing with layers | ~1 week | Phase 3 |
| Missing L6 memory layer | Scope | Low today, **this is the differentiator** | Phase 4 | Phase 4 |
| 12 migrations before first query | Schema | Medium — every fix is now a migration | Consider squashing to `0001` while there are no users | Phase 2 |

**Aggregate assessment.** The debt is unusually *tractable* for its size, because there are no users and no data to migrate. Almost every item above is 10× cheaper to fix now than after a first external customer. That is the strongest argument for doing Phase 0–2 immediately rather than continuing to add layers.

---

## 17. Verdict

### 17.1 Should this architecture be built?

**Partially — and the partition is sharp.**

**Build (C1–C6, roughly M1–M7 reduced):** commit-addressed ingestion, tree-sitter + SCIP parsing, precise semantic resolution, a relational fact store with real adjacency queries, a query API delivered over MCP, hybrid retrieval, and a thin grounded-answer layer with a citation verifier. This is a real category with real incumbents, which is evidence the category exists. RIA's commit-addressed identity model and its coverage/provenance/confidence envelope are genuine differentiators that no competitor examined here matches.

**Do not build (M10–M12):** the multi-agent platform, the workflow engine, and the execution layer. They contradict the PRD's own non-goals, contradict the published evidence on agent topology for code mutation, require an execution-isolation platform RIA does not have and should not build, and convert every potential customer into a competitor.

### 17.2 The three things that decide this

1. **Measure before building anything else.** The entire thesis rests on an unmeasured precision claim, and the vendor RIA would sell to has already published a result pointing the other way. Phase 1 costs five weeks and either validates a multi-year programme or saves it.
2. **Ship a delivery surface or the work does not exist.** 29.9k LOC that nothing imports and no container includes is not an architecture, it is a design document written in Python. MCP is the cheapest path from code to consumer.
3. **Differentiate against Serena and Sourcegraph explicitly, in writing.** Neither appears in RIA's foundation documents. Both occupy adjacent-to-identical positions. The defensible gap is cross-commit history and calibrated confidence — the things a stateless, working-tree-scoped language server cannot provide. If that sentence cannot be made concrete, the programme has no wedge.

### 17.3 What a CTO should take from this

The document set suggests a team that can reason about architecture at a high level. The repository suggests a team that built the interesting half well, then generated the uninteresting half to completion criteria rather than to purpose — and never closed the loop with measurement or a consumer. Those are correctable failures of sequencing and scope, not of capability. The recommendation is not to abandon the architecture. It is to delete a third of it, measure the rest, and put it behind an MCP endpoint before writing another layer.

---

## 18. Sources

All URLs below were retrieved during this review. Content from these sources has been paraphrased and summarised rather than quoted, in compliance with licensing restrictions; no more than 30 consecutive words are reproduced from any single source. Substance and factual accuracy have been preserved.

**Agent architecture and topology**
- Cognition — Don't Build Multi-Agents: https://cognition.ai/blog/dont-build-multi-agents
- Anthropic — How we built our multi-agent research system: https://www.anthropic.com/engineering/multi-agent-research-system
- Anthropic/Claude — When to use multi-agent systems: https://claude.com/blog/building-multi-agent-systems-when-and-how-to-use-them
- LangChain — How and when to build multi-agent systems: https://www.langchain.com/blog/how-and-when-to-build-multi-agent-systems
- Agentless (arXiv 2407.01489): https://ar5iv.labs.arxiv.org/html/2407.01489 · updated figures: https://par.nsf.gov/biblio/10682640-demystifying-llm-based-software-engineering-agents

**Context engineering**
- Anthropic — Effective context engineering for AI agents: https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- Anthropic — Effective harnesses for long-running agents: https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
- Claude cookbook — memory, compaction, tool clearing: https://platform.claude.com/cookbook/tool-use-context-engineering-context-engineering-tools

**Retrieval and indexing**
- Cursor — Securely indexing large codebases: https://cursor.com/blog/secure-codebase-indexing
- Cursor — Data use & privacy: https://cursor.com/data-use
- GitHub — New Copilot embedding model: https://github.blog/news-insights/product-news/copilot-new-embedding-model-vs-code/
- GitHub — Indexing repositories for Copilot: https://docs.github.com/en/copilot/using-github-copilot/indexing-repositories-for-copilot-chat
- GitHub — The technology behind GitHub's new code search (Blackbird): https://github.blog/engineering/architecture-optimization/the-technology-behind-githubs-new-code-search/
- VS Code — How Copilot understands your workspace: https://code.visualstudio.com/docs/copilot/workspace-context
- Codeium — Remote indexing and multi-repo context awareness: https://codeium.com/blog/remote-indexing-multirepo-announcement
- Continue — How to build custom code RAG: https://continue-docs.mintlify.app/guides/custom-code-rag
- Aider — Building a better repository map with tree-sitter: https://aider.chat/2023/10/22/repomap.html · https://aider.chat/docs/repomap.html
- Claude Code retrieval reporting (third-party, quoting Boris Cherny): https://zerofilter.medium.com/why-claude-code-is-special-for-not-doing-rag-vector-search-agent-search-tool-calling-versus-41b9a6c0f4d9 · https://rust-trends.com/posts/ripgrep-claude-code/
- Why coding agents still use grep (third-party analysis): https://grapeot.me/share/why-coding-agents-still-use-grep-en-20260327.html
- Claude Code issue #40702 (indexed search request): https://github.com/anthropics/claude-code/issues/40702

**Code intelligence infrastructure**
- Sourcegraph — Announcing SCIP: https://sourcegraph.com/blog/announcing-scip
- Sourcegraph — Precise code navigation docs: https://docs.sourcegraph.com/code_intelligence/explanations/precise_code_intelligence
- Sourcegraph — The intelligence layer for AI coding agents: https://sourcegraph.com/blog/a-new-era-for-sourcegraph-the-intelligence-layer-for-ai-coding-agents-and-developers
- Sourcegraph — MCP: https://sourcegraph.com/mcp
- Sourcegraph — What it takes to run code intelligence in-house: https://sourcegraph.com/blog/what-it-actually-takes-to-run-code-intelligence-in-house
- Zoekt design: https://github.com/sourcegraph/zoekt/blob/main/doc/design.md · memory optimisations: https://about.sourcegraph.com/blog/zoekt-memory-optimizations-for-sourcegraph-cloud/
- GitHub — Introducing stack graphs: https://github.blog/2021-12-09-introducing-stack-graphs/ · paper: https://arxiv.org/pdf/2211.01224v2
- Meta — Indexing code at scale with Glean: https://engineering.fb.com/2024/12/19/developer-tools/glean-open-source-code-indexing/ · https://glean.software/
- Glean — Incremental indexing: https://glean.software/blog/incremental/ · DB representation: https://glean.software/docs/implementation/db/
- Kythe overview: https://www.kythe.io/docs/kythe-overview.html · writing an indexer: https://www.kythe.io/docs/schema/writing-an-indexer.html · compilation database: https://kythe.io/docs/kythe-compilation-database.html
- Salsa: https://github.com/salsa-rs/salsa · rust-analyzer durable incrementality: https://rust-analyzer.github.io/blog/2023/07/24/durable-incrementality.html
- Serena: https://github.com/oraios/serena · https://rywalker.com/research/serena

**Execution and sandboxing**
- OpenHands runtime architecture: https://docs.all-hands.dev/usage/architecture/runtime · SDK paper: https://arxiv.org/pdf/2511.03690 · original paper: https://arxiv.org/pdf/2407.16741
- OpenAI Codex — approvals & security: https://developers.openai.com/codex/agent-approvals-security/ · running Codex safely: https://openai.com/index/running-codex-safely/ · Windows sandbox: https://openai.com/index/building-codex-windows-sandbox/ · cloud environments: https://developers.openai.com/codex/cloud/environments/
- OpenAI — Sandbox Agents guide: https://platform.openai.com/docs/guides/agents/sandboxes
- Cognition — Devin can now manage Devins: https://old.cognition.ai/blog/devin-can-now-manage-devins · Outposts: https://docs.devin.ai/cloud/outposts/overview
- Google — Jules announcement: https://blog.google/technology/google-labs/jules/
- Factory — enterprise docs: https://docs.factory.ai/enterprise/index · GA announcement: https://www.factory.ai/news/ga

**Graph vs vector retrieval, storage**
- AST-derived vs LLM-extracted knowledge graphs for code (arXiv 2601.08773): https://arxiv.org/abs/2601.08773
- Do we still need GraphRAG? (arXiv 2604.09666): https://arxiv.org/html/2604.09666v1
- Code Digital Twin (arXiv 2503.07967): https://arxiv.org/abs/2503.07967 · (arXiv 2510.16395): https://arxiv.org/html/2510.16395v1
- Concurrent access: relational vs graph NoSQL (Applied Sciences 14(21):9867): https://mdpi.com/2076-3417/14/21/9867
- Performance of graph and relational databases in complex queries: https://www.researchgate.net/publication/361607172
- Postgres CTE vs Neo4j traversal benchmark (single-author): https://www.pedroalonso.net/blog/graphrag-vs-vector-postgres/
- SQLite concurrency: https://tenthousandmeters.com/blog/sqlite-concurrent-writes-and-database-is-locked-errors/ · https://betterstack.com/community/guides/databases/turso-explained/ · production limits: https://sesamedisk.com/sqlite-in-production-2026/

**Code review / MCP design**
- Greptile — graph-based codebase context: https://www.greptile.com/docs/how-greptile-works/graph-based-codebase-context
- CodeRabbit — deep dive: https://www.coderabbit.ai/blog/coderabbit-deep-dive
- Thin vs thick MCP token benchmark: https://uk.finance.yahoo.com/news/cyclr-benchmark-finds-mcp-server-140000716.html
- Cloudflare — Code Mode (MCP tool surface design): https://blog.cloudflare.com/code-mode-mcp/

**Sources consulted and rejected as unreliable:** `markaicode.com` (multiple "architecture" pages containing unsourced internal designs for Cursor and Copilot), `fast.io/resources` (Devin architecture pages), `skywork.ai` (Jules reviews), `lowcode.agency` (Windsurf indexing claims). These are SEO-generated content presenting inference as documented fact. No claim in this report rests on them.
