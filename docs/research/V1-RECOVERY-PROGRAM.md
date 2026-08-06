# Version 1 Recovery Program

**Repository Intelligence Platform → v0.9.0-beta**

**Document type:** Engineering recovery plan (execution-ready)
**Owner:** Principal Engineer
**Input:** `docs/research/ENGINEERING-DESIGN-REVIEW-V1.md` (EDR, score 31/100, v1.0 rejected)
**Status:** Proposed — awaiting go/no-go on Phase 1
**Date:** 2026-07-28

---

## Document conventions

Every recovery item is identified `R-NNN` and carries **Problem · Root Cause · Impact · Risk · Fix · Effort · Priority · Acceptance Criteria**.

One deliberate deviation from the requested format, stated because hiding it would violate the honesty principle this program exists to establish: the full eight-field template is applied to the **31 substantive recovery items**. A further **27 mechanical items** (delete a redundant array, move a dependency between sections, rename a file) are captured in compact tables in §5. Writing 400 words of ceremony around "delete 44 redundant `activationEvents` entries" produces a document nobody executes. Each mechanical item still carries an owner, effort, priority and a testable acceptance criterion.

Effort is in **engineer-days (ed)**, assuming an engineer already familiar with this codebase. Multiply by 1.6 for an onboarding engineer.

---

## 1. Executive Summary

### 1.1 Situation

The EDR rejected v1.0 on four independent blockers and scored the platform 31/100. The dominant finding was not incompleteness — it was **fabrication**: three advertised subsystems return hardcoded answers, invented metrics, invented rule identifiers, and invented confidence scores between 0.95 and 0.98, presented to users inside an "Evidence" block. A fourth blocker is that `pytest tests/` — the exact CI command — exits with code 2, meaning `main` was red when `v1.0.0` was tagged.

### 1.2 What this program is

A **subtraction program**. The platform contains approximately 71,000 lines implementing the same product twice, advertises 18 capabilities of which at least 6 do not work, and ships a fabricated Copilot alongside a real retrieval pipeline that already does the job properly. Recovery is achieved primarily by deleting things, not building them.

Quantified targets:

| Metric | Now | After recovery |
|---|---:|---:|
| Advertised capabilities | 18 | **6** (all real, all tested) |
| Fabricated output sites | 3 subsystems / ~1,500 LOC | **0** |
| Python LOC (shipping stack) | 41,535 | **≈36,000** |
| Parallel architectures | 2 (`legacy` ships, `ria/` unreachable + broken) | **1 shipping, 1 frozen and green** |
| Mounted route trees | ~75 (25 routers × 3 prefixes) | **≈18** (one prefix) |
| CI gates | ruff only (and the suite fails) | ruff · mypy · coverage floor · pip-audit · npm audit · image scan |
| Test collection | exit 2 | **exit 0** |
| Auth default | open | **deny-by-default, fails closed** |
| Deserialization RCE surface | `pickle.load` on primary path | **0** |
| Frontend tests | 0 | **≥30 component + 1 E2E** |

### 1.3 Recommended release scope

Ship **six capabilities** that are real, deterministic, and testable:

1. Repository Analysis (ingest, parse, symbol index)
2. Dependency Graph
3. Call Graph
4. Impact Analysis / Blast Radius
5. Architecture Drift + API Surface breaking-change detection
6. Repository Chat (the real `services/chat/` retrieval pipeline, with verified citations)

Excluded from v0.9.0-beta, with reasons stated publicly: Repository AI Copilot, Copilot Skills Framework, Learning Workspace, Repository Learning Intelligence, Metrics Engine, Quality Engine, Rules Engine, Dependency Story, Execution Flow, Unified Workspace, Context Intelligence, Repository Digital Twin.

### 1.4 Cost

The program is split into three tracks. The beta ships on Track A; the rest continues after release. Costs are derived item-by-item in §4 and reconciled in §6.

| Track | Scope | Effort | Calendar (2 engineers) | Ships |
|---|---|---:|---|---|
| **A — Minimum Honest Beta** | All fabrications removed · security P0/P1 · green CI · honesty envelope end-to-end · truthful docs | **52 ed** | **7 weeks** | **v0.9.0-beta.1** |
| B — Structural Recovery | Dependency inversion, singleton lifecycle, graph source of truth, symbol identity + measured recall, client consolidation | 51 ed | +6 weeks | 0.9.x |
| C — Quality Debt | God-file splits, UI primitives, accessibility baseline, tracing, prompt registry | 34 ed | +4 weeks | 1.0.0 candidate |

**Full program ≈122 ed / 17 weeks with two engineers.** Single engineer: Track A 11 weeks, full program 24 weeks.

Phase 1 alone — the honesty gate — is **8 ed / 1 week** and delivers the largest single reduction in reputational risk in the entire program. It should be authorised independently of everything else.

### 1.5 The one decision that must be made first

**Does the Copilot subsystem get rebuilt or deleted?** §4.6 recommends deletion with the good ideas merged into the existing retrieval pipeline. If leadership wants Copilot rebuilt instead, the program grows by ~20 ed and v0.9.0 slips 3 weeks — and it would be rebuilding a second assistant next to a working one. The recommendation is deletion.

---

## 2. Recovery Strategy

### 2.1 Strategic principles, in precedence order

1. **Honesty outranks capability.** A missing feature costs a user nothing. A fabricated feature costs them a wrong decision and costs the project its credibility permanently. Every conflict resolves toward removal.
2. **Deletion outranks refactoring.** Refactoring fabricated code produces well-structured fabrication. Delete first, then refactor what remains.
3. **Determinism outranks inference.** Where the platform already holds a symbol index and a call graph, a question with an exact answer must be answered exactly. Any LLM call substituting for a lookup is a defect.
4. **Explicit limitation outranks silent degradation.** `coverage: DEGRADED` is a feature. A silently empty edge list is a bug that looks like data.
5. **One of everything.** One backend, one graph store, one assistant, one UI, one API prefix, one canonical document per topic.
6. **No new features.** Enforced as a merge rule for the duration of the program (§10.3).

### 2.2 Sequencing rationale

The ten phases are ordered by dependency, not by severity. Two orderings were considered and rejected:

- *Security first.* Rejected: hardening code that is about to be deleted wastes 4–6 ed, and the largest security-adjacent risk (fabricated output driving engineering decisions) is a Phase 1 concern anyway.
- *CI first.* Rejected: fixing CI before deleting the fabrications means fixing tests (`tests/test_copilot_skills.py`, `tests/test_repository_copilot.py`, `tests/test_interactive_learning_workspace.py`) that exist to assert fabricated behaviour is correct. Those tests are deleted in Phase 1; repairing them first is pure waste.

The chosen order is: **remove falsehoods → remove duplication → make safe → make verifiable → make correct → consolidate → clean clients → align docs → release.** Phase 4 (Reliability/CI) lands early enough that every subsequent phase is guarded by a green gate.

### 2.3 Branch and merge strategy

- `main` stays deployable. Every phase merges through a `recovery/phase-N-*` integration branch.
- Phase 1 lands as a **single reviewable PR per subsystem removed**, not one giant deletion, so each removal is independently revertable.
- No feature PRs merge during the program. CI enforces this via a labelled-PR check (R-058).
- Tag `v0.9.0-beta.1` from `main` only when the §12 acceptance criteria pass in full.

### 2.4 What is explicitly NOT in scope

- Rewriting the platform. The legacy stack is repairable and repairs are cheaper than a rewrite.
- Resuming `ria/` development. It is frozen green and left alone (R-016).
- New languages, new engines, new agents, new dashboards, new VS Code commands, multi-repo, multi-tenancy, execution/sandboxing.
- Fixing the accessibility backlog to full WCAG AA conformance. Phase 7 establishes the tooling and fixes keyboard traps; conformance is a post-beta program (R-045).

---

## 3. Verified evidence base

New verification performed for this plan, beyond the EDR:

**E1 — CI break root cause identified.** `ria/config/settings.py` defines exactly two classes: `ObservabilitySettings` and `Settings`. `ria/infrastructure/git/subprocess_git_client.py:45` performs a module-level `from ria.config.settings import GitSettings`. `GitSettings` does not exist — a rename or removal was never propagated. Because the import is module-level, collection of the entire `tests/ria` tree (137 files) aborts, which aborts `pytest tests/`. Single-symbol fix.

**E2 — Dead module inventory (zero inbound imports across the whole repo).**

| LOC | Path | Note |
|---:|---|---|
| 58 | `agents/analyzer.py` | |
| 60 | `agents/explainer.py` | |
| 37 | `backend/main.py` | **Second FastAPI entry point.** `Dockerfile` uses `backend.api:app` |
| 60 | `memory/cache.py` | |
| 71 | `memory/sqlite_store.py` | |
| 91 | `services/chat/performance.py` | |
| 53 | `services/mcp_service.py` | `backend/mcp_server.py` (322 LOC) is the live one |
| 33 | `backend/copilot/copilot_memory.py` | Phase 1 deletes the package |
| 19 | `backend/copilot/copilot_response.py` | |
| 34 | `backend/copilot/copilot_stream.py` | |
| 90 | `backend/copilot/copilot_tools.py` | Reached only via a side-effect relative import (`tool_registry.py:47`); detector under-counts relative imports |

**463 LOC of confirmed dead code**, of which 176 is outside the Copilot package and survives Phase 1.

**E3 — Tests that pin the fabrications.** These assert that fabricated behaviour is correct and must be deleted with their subjects:
- `tests/test_copilot_skills.py` — `:41` asserts `len(skills) == 12`; `:163` is named `test_response_contract_and_evidence_first` and validates the shape of invented evidence.
- `tests/test_repository_copilot.py` — `:31` asserts `len(tools) >= 5`; hits `/api/copilot/{chat,commands,tools}`.
- `tests/test_interactive_learning_workspace.py` — `:121,130,139,147` hit reading-path endpoints with **the author's own repository hardcoded in the test URL**, which is why the tests pass despite `DEFAULT_REPO_FILES`.

**E4 — Skill count corrected.** 12 concrete skills plus `base_skill.py` (the ABC), not 13 concrete skills as stated in the EDR. Confirmed by `tests/test_copilot_skills.py:41`.

**E5 — A progress tracker exists.** `services/reading_path/progress_tracker.py` exposes `get_user_progress` (imported by `tests/test_interactive_learning_workspace.py:28`) despite there being no user identity in the product. Its persistence semantics are **unverified** and must be checked in R-013 before deletion or retention.

---

## 4. Phase-by-Phase Recovery Roadmap

---

## PHASE 1 — AI Integrity Recovery

**Goal:** zero fabricated outputs. **Effort: 6 ed.** **Gate: no user-visible value originates from a literal.**

### R-001 — Delete the `backend/copilot/` package
- **Problem.** 29 files / ~1,090 LOC return hardcoded answers with invented telemetry and confidence. `skills/performance_skill.py:66` → `{"latency_ms": 8.4, "cyclomatic_complexity": 6, "memory_mb": 14.2}`; `:79` → `"confidence": 0.97`. `skills/search_skill.py:56-58` returns this project's own file list as "search results" for any query. `skills/review_skill.py:66` → `{"maintainability_index": 88, "rule_violations": 0}` for a file never analysed. Invented rule IDs (`ARCH-003`, `SRCH-001`, `EDU-001`) are cited as authority; no rule registry exists. `tool_registry.py:4` claims 15 tools; `copilot_tools.py` registers 5, and those 5 pass fabricated arguments to real engines (`:44-47` evaluates rules against `models/domain.py` and `frontend/App.tsx`, which exist in no analysed repository). `copilot_context.py:14` defaults `repo_name` to the author's own repository.
- **Root cause.** The subsystem was scaffolded architecture-first (skill ABC, registry, selector, tool registry, controller, streamer — all structurally sound) and the analysis bodies were filled with fixtures to make the scaffold demonstrable. The fixtures were then mounted on a production router, wired to a 371-line frontend, documented as a shipped capability, and tagged v1.0.0. No feature flag existed to dark-launch it, so the only options were ship or delete, and ship was chosen.
- **Impact.** Users receive invented maintainability indices, latency figures and complexity scores with 97% stated confidence. Any engineer who opens one skill file discovers this in under a minute.
- **Risk if unfixed.** Terminal. For a product whose sole premise is grounded, cited, deterministic intelligence, this is unrecoverable on discovery. Plausible misrepresentation exposure if the platform is ever commercialised.
- **Fix.** Delete `backend/copilot/` entirely. Remove the import and both mounts (`backend/api.py:296`, `:301-302`). Delete `frontend/src/components/copilot/CopilotWorkstation.tsx` (371 LOC) and its route. Delete `tests/test_copilot_skills.py` and `tests/test_repository_copilot.py`. Preserve the two genuinely good ideas by recording them in an ADR for Phase 6: skill/slash-command routing, and a tool registry with schemas.
- **Effort.** 1 ed. **Priority.** P0 — release blocker.
- **Acceptance criteria.**
  1. `grep -ri "copilot" backend/ services/ frontend/src/ tests/` returns no matches outside `docs/` and ADRs.
  2. `GET /api/copilot/commands` returns 404.
  3. `pytest tests/` collects and passes with the two test files removed.
  4. No response field named `confidence` exists anywhere that is not computed from measured data.

### R-002 — Delete the three fabricating VS Code webview views
- **Problem.** `vscode-extension/src/views/KnowledgeGraphView.ts:17-18` renders `Entities: 142 | Relationships: 380 | Active Focus: current editor file` as literals in a static HTML template. No API call is made. `LearningView.ts` and `ArchitectureView.ts` follow the identical pattern.
- **Root cause.** Views were built as UI placeholders to populate the activity bar before backends existed, then never revisited.
- **Impact.** Users see specific, plausible, invented statistics presented as their repository's knowledge graph, inside their editor.
- **Risk.** Same class as R-001, with higher visibility — the activity bar is always on screen.
- **Fix.** Delete all three view files and their registrations. Do not replace with "coming soon" panels; remove the entries from the activity bar entirely.
- **Effort.** 0.5 ed. **Priority.** P0.
- **Acceptance criteria.** No webview in `vscode-extension/src/` contains a numeric literal presented as repository data; a test asserts this by scanning view templates for digit sequences adjacent to the words `Entities`/`Relationships`.

### R-003 — Remove the Learning Workspace surface
- **Problem.** `backend/routers/reading_path.py:25` carries the comment `# Dummy repository file list fallback` defining `DEFAULT_REPO_FILES`, which every endpoint then passes to `get_knowledge_graph(full_repo, DEFAULT_REPO_FILES)` (`:52`, `:76`) — so concepts and journeys are computed over a hardcoded file list, not the requested repository. `:158` accepts `owner` and `repo_name` and never uses them. `:164-167` returns `detect_knowledge_gaps(["backend/api.py"])` with hardcoded arguments, so every repository receives an identical answer.
- **Root cause.** The learning feature requires two things the platform does not have — per-repository concept extraction wired to real analysis, and a user identity to hang progression from. Both were stubbed to make the UI demonstrable.
- **Impact.** Learners are taught facts about a fixed file list while the UI claims they describe their repository. Educational value is negative.
- **Risk.** High. This is the capability most likely to be evaluated by a non-engineer, who cannot detect the substitution.
- **Fix.** Remove `backend/routers/reading_path.py` from `backend/api.py` mounting; remove `frontend/src/components/reading/LearningWorkspace.tsx`; delete `tests/test_interactive_learning_workspace.py`. **Retain** `services/reading_path/*` on disk — `journey_generator`, `concept_scorer`, `gap_detector`, `dependency_story`, `architecture_mentor`, `quiz_generator` are real algorithms worth rebuilding on in v1.2 — and add a package-level `README.md` stating the module is unmounted pending real repository wiring and user identity.
- **Effort.** 1 ed. **Priority.** P0.
- **Acceptance criteria.** `GET /api/reading-path/...` returns 404; no string literal `DEFAULT_REPO_FILES` is reachable from any mounted route; `services/reading_path/README.md` states the unmounted status and the two prerequisites.

### R-004 — Remove the three `type(None)` capabilities
- **Problem.** `backend/dependencies.py:246,251,256` register `Module Stability`, `Dependency Smells` and `Architecture Health` into the analysis DAG with `type(None)` as the builder class. `backend/routers/stability.py` and `backend/routers/dependency_smells.py` are 3 lines each and are mounted three times each. VS Code commands `repoIntelligence.showModuleStability` and `repoIntelligence.showArchitectureHealth` invoke them.
- **Root cause.** DAG nodes were registered to reserve the dependency edges before implementations existed; the routers and commands were added to complete the vertical slice.
- **Impact.** Three advertised capabilities, two mounted routers and two command-palette entries that do nothing.
- **Risk.** High for an OSS launch — invoking an advertised command and getting nothing is the first thing a new user does.
- **Fix.** Delete the three registry entries, both stub routers and their mounts, and both VS Code commands (`package.json` contributions plus their handlers in `commands.ts`). Record in the ADR that `Architecture Health` is genuinely wanted post-beta and that its DAG dependencies were `["Dependency Graph", "Call Graph"]`.
- **Effort.** 0.5 ed. **Priority.** P0.
- **Acceptance criteria.** `analysis_registry` contains no entry whose builder is `type(None)`; a unit test asserts this. No VS Code command resolves to a route returning 404.

### R-005 — Replace LLM-based citation validation with a deterministic verifier
- **Problem.** `agents/evaluator.py` validates citations by calling a model, then `:172` does `citations_valid = bool(data.get("citations_valid", True))` — if the evaluating model omits the field, citations are treated as valid. Fail-open.
- **Root cause.** Grounding was implemented as an LLM-judged quality check rather than as a lookup, despite the platform holding a symbol index and a file store that can answer the question exactly.
- **Impact.** The product's central claim — cited, verifiable answers — rests on a probabilistic check that defaults to "trust it". This is the single highest-value correctness gap.
- **Risk.** High. Every hallucinated file path currently passes validation silently.
- **Fix.** Add `services/chat/citation_verifier.py`: parse `**File:** <path>` and `**Lines:** X–Y` from the answer, resolve each path against the symbol index and the cloned tree, validate the line range against actual file length, and return `CitationReport{verified: list, unresolved: list}`. Mark unresolved citations inline in the response and set `citations_valid=False` by default. Keep the LLM evaluator strictly for subjective quality scoring, clearly labelled as such. Credit where due: `_fallback_eval` (`:208-211`) already fails closed on exception — only the malformed-response path is wrong.
- **Effort.** 3 ed. **Priority.** P0 — this is the one *build* item in Phase 1, and it is what makes the "evidence-first" claim true rather than aspirational.
- **Acceptance criteria.** A test injects an answer citing `nonexistent/file.py:1-5` and asserts the response reports it as unresolved and sets `citations_valid=False`; no code path can set `citations_valid=True` without a successful filesystem/index resolution.

### R-006 — Audit and purge every remaining hardcoded output
- **Problem.** R-001 to R-004 cover the known sites. The pattern's prevalence means others are likely — `copilot_tools.py:51-55` returned a fake `POST /api/login` execution flow for an endpoint this product does not expose, which suggests fixture data leaked into shared services too.
- **Root cause.** No lint rule, review checklist or test forbids returning literal analysis values.
- **Impact.** Unknown residual fabrication.
- **Risk.** High — a single missed site reproduces the whole problem after launch.
- **Fix.** Systematic sweep: grep every `return` in `services/` and `backend/` for float/int literals in fields named `confidence`, `score`, `*_ms`, `complexity`, `index`, `count`, `total_*`, `*_score`. For each hit, classify as *computed*, *legitimate default*, or *fabricated*. Fabricated → delete the capability or implement it. Produce `docs/AI-INTEGRITY-REPORT.md` listing every site and its disposition. Then add the guard: a CI test asserting no module under `services/` or `backend/` returns a hardcoded `confidence` value.
- **Effort.** 2 ed. **Priority.** P0.
- **Acceptance criteria.** `docs/AI-INTEGRITY-REPORT.md` exists, enumerates every candidate site with a disposition, and is signed off; the CI guard test passes and fails when a fabricated confidence literal is reintroduced.

### Phase 1 deliverables
- `docs/AI-INTEGRITY-REPORT.md` (R-006)
- ~1,500 LOC removed; 3 test files removed; 1 new verifier (~200 LOC)
- **Gate:** every number the product shows a user was computed from that user's repository.

---

## PHASE 2 — Architecture Consolidation

**Goal:** one architecture, one source of truth. **Effort: 11 ed.** **Depends on Phase 1.**

### R-007 — Invert the `services → backend` dependency
- **Problem.** `services/knowledge_graph_builder.py:131,169,189,216-219` and `services/symbol_service.py:96` import `backend.dependencies` from inside function bodies specifically to hide the import cycle from Python.
- **Root cause.** Singletons live in the delivery layer, so any service needing a collaborator reaches for the global rather than receiving it. Function-local imports made the cycle survive `import`-time.
- **Impact.** The business layer depends on FastAPI wiring. `services/` cannot be unit-tested in isolation, reused by the CLI, or extracted into a worker.
- **Risk.** High and compounding — this is the exact failure mode the project's own SDD identifies as the prior architecture's fatal flaw, arrived at one import at a time.
- **Fix.** Constructor injection. `RepositoryKnowledgeGraphBuilder.__init__` already accepts `twin_builder`/`cache`/`providers`; extend the pattern to providers (`SymbolProvider(symbol_service)`, `DependencyProvider(graph_service)`, `CallGraphProvider(graph_service)`) and to `SymbolService(snapshot_store=...)`. Delete every `from backend...` inside `services/`. Then port `tests/ria/integration/test_architecture_rules.py` — already reference-quality — to guard the legacy packages.
- **Effort.** 4 ed. **Priority.** P1.
- **Acceptance criteria.** `grep -rn "from backend" services/ core/ agents/ memory/ models/ storage/` returns zero results; the ported architecture test enforces it in CI and fails on reintroduction.

### R-008 — Move singleton construction out of module import
- **Problem.** `backend/dependencies.py:263-380` constructs ~40 singletons at import, including `EmbeddingService` (loads a sentence-transformer, `:290`) and `ChromaStore` (`:291`). `backend/api.py` additionally runs `configure_logging`, `run_migrations()`, `_load_analysis_store()` and `_warmup_services()` at import.
- **Root cause.** A documented decision ("constructing them once is both correct and significantly cheaper") that conflated *lifetime* with *construction site*. Singleton lifetime is fine; import-time side effects are not.
- **Impact.** Importing `backend.api` for any purpose — a unit test, `--help`, an OpenAPI dump — loads an ML model and opens a database. Dependency substitution in tests requires `mock.patch` on module attributes, which has already leaked into production shape (`backend/routers/pr.py:91` comments that a call is synchronous *so that a test patch intercepts it*).
- **Risk.** High. Blocks R-021 (fast CI), R-024 (real health checks) and any future worker extraction.
- **Fix.** Construct in FastAPI `lifespan`, store on `app.state`, expose via `Depends()` providers. Keep one process-wide instance each. Remove the four import-time calls from `api.py`. Delete the test-shaped synchronous call once patching is no longer needed.
- **Effort.** 4 ed. **Priority.** P1.
- **Acceptance criteria.** `python -c "import backend.api"` completes in under 1s and loads no ML model (asserted by a test that monkeypatches `SentenceTransformer` to raise); no router imports a service singleton by name.

### R-009 — Collapse triple router mounting to a single prefix
- **Problem.** `backend/api.py:300+` mounts all 25 routers at root, `/api`, and `/api/v1` — roughly 75 route trees.
- **Root cause.** Backward compatibility maintained additively without a deprecation mechanism.
- **Impact.** OpenAPI is 3× the real API. Every security rule, rate limit and cache key must be expressed three times — and the auth middleware covers only two of the three variants, which is precisely how the unauthenticated `graph_rag_chat` hole (R-018) arose.
- **Risk.** High — it is a security-defect generator, not just noise.
- **Fix.** Mount once at `/api/v1`. Add explicit 308 redirects from `/` and `/api` with a `Deprecation` header and a removal version. Since this is a pre-1.0 beta, prefer removing the legacy prefixes outright and documenting the single supported base path.
- **Effort.** 1.5 ed. **Priority.** P1.
- **Acceptance criteria.** `len(app.routes)` reduced by ≥60%; a test asserts every route path starts with `/api/v1`, `/health` or `/metrics`; frontend and extension clients updated and passing.

### R-010 — Delete confirmed dead code
- **Problem.** 463 LOC with zero inbound imports (E2), including `backend/main.py` — a **second FastAPI entry point** that nothing references while the `Dockerfile` uses `backend.api:app`.
- **Root cause.** No dead-code detection in CI; modules superseded in place rather than removed.
- **Impact.** Two plausible entry points is an operational hazard: a future deployment could serve the wrong app. `services/mcp_service.py` (53 LOC) duplicates `backend/mcp_server.py` (322 LOC) with unclear precedence.
- **Risk.** Medium — the duplicate entry point is the sharp edge.
- **Fix.** Delete `backend/main.py`, `agents/analyzer.py`, `agents/explainer.py`, `memory/cache.py`, `memory/sqlite_store.py`, `services/chat/performance.py`, `services/mcp_service.py`. Add `vulture` or `ruff`'s unused-code rules to CI. **Caveat to verify before deleting:** the detector under-counts relative imports (`from . import x`), so re-check each candidate with a direct grep for its leaf name.
- **Effort.** 1 ed. **Priority.** P2.
- **Acceptance criteria.** Test suite green after removal; exactly one ASGI application object exists in the repository; dead-code detection runs in CI.

### R-011 — Consolidate seven parallel graph implementations
- **Problem.** Independent graph representations exist in `graph_service` (file + module DiGraphs), `call_graph_service` (call DiGraph), `architecture_service` (persisted summaries), `twin_builder` (a dependency graph built solely for cycle counting), `knowledge_graph_builder` (the "unified" graph), `graph_rag`, `retrieval_engine`, and `graph_serializer`. Fifteen legacy modules import `networkx`.
- **Root cause.** Each feature built the graph shape it needed rather than extending a shared store, because no shared store had an owner.
- **Impact.** Any two can disagree and no test reconciles them. The "single source of truth" claim is contradicted by the module list.
- **Risk.** High — divergent answers to the same question across endpoints.
- **Fix.** Designate the store from R-025 as canonical. Convert `twin_builder`'s cycle graph, `graph_serializer`'s centrality computation, and `graph_rag`'s traversal into query functions over it. Do **not** attempt to unify `architecture_service`'s persisted summaries in this program — record as post-beta debt.
- **Effort.** 5 ed (of which 2 in Phase 2 for the inventory + ADR, 3 in Phase 5 for the migration). **Priority.** P1.
- **Acceptance criteria.** A reconciliation test asserts that node and edge counts for a fixture repository are identical across every endpoint that reports them.

### R-012 — Split the four god files
- **Problem.** `services/call_graph_service.py` 1,367 LOC; `services/chat/retrieval.py` 1,181; `vscode-extension/src/commands.ts` 1,153; `frontend/src/components/interactive/CallGraphAnalyzer.tsx` 1,262. `services/api.ts` 835 and `backend/routers/repositories.py` 764 are close behind.
- **Root cause.** No file-size budget; features appended to the nearest existing home.
- **Impact.** Unreviewable diffs, guaranteed merge conflicts, no unit-testable seams. For an OSS project accepting external PRs, these files are contribution blockers.
- **Risk.** Medium — maintainability, not correctness.
- **Fix.** Extract along existing internal seams: `call_graph_service` → extraction / persistence / traversal / metrics; `chat/retrieval` → detection / ranking / chunk-shaping. Target ≤400 LOC. Add a CI warning above 500 LOC and a failure above 800. Frontend and extension splits are handled in Phases 7 and 8.
- **Effort.** 4 ed (backend only in this phase). **Priority.** P2.
- **Acceptance criteria.** No Python file in `services/` or `backend/` exceeds 500 LOC; CI enforces the ceiling; behaviour covered by pre-existing tests unchanged.

### R-013 — Decide the fate of unmounted `reading_path` internals
- **Problem.** Phase 1 unmounts the Learning Workspace but retains `services/reading_path/*`. `progress_tracker.py` exposes `get_user_progress` (E5) despite there being no user identity in the product; its persistence semantics are **unverified**.
- **Root cause.** Progression was implemented before the identity it depends on.
- **Impact.** Unknown. If it writes shared state keyed by something non-user-specific, it is a cross-user data-leak vector the moment auth arrives.
- **Risk.** Medium, unquantified — hence the explicit investigation task.
- **Fix.** Read `progress_tracker.py` and determine what it persists and under what key. If it writes shared or global state, delete it. If it is pure, retain with the package README. Either way, record the finding.
- **Effort.** 0.5 ed. **Priority.** P2.
- **Acceptance criteria.** Finding documented in the Phase 2 ADR; no module under `services/reading_path/` writes persistent state keyed by anything other than an authenticated principal.

### Phase 2 deliverables
- `docs/adr/0001-single-architecture.md` — keep/merge/delete decisions with rationale
- `docs/adr/0002-graph-source-of-truth.md`
- ~640 LOC deleted; ~57 route trees removed; import cycle eliminated and guarded

### Phase 2 keep / merge / delete summary

| Disposition | Items |
|---|---|
| **KEEP** | `services/call_graph_service` · `architecture_service` · `architecture_drift_service` · `pr_intelligence_service` · `api_surface_service` · `impact_analysis_service` · `symbol_service` · `tree_sitter_service` · `git_history_service` · `github_service` · `services/chat/*` (real pipeline) · `services/llm/*` (reference-quality) · `core/{cache,registry,build_pipeline}` · `backend/mcp_server.py` |
| **MERGE** | 7 graph implementations → 1 store (R-011) · `twin_builder` cycle graph → graph store · `graph_serializer` centrality → build-time node attribute · extension webview HTML → the Astro frontend (R-048) · duplicate docs → one canonical each (R-050) |
| **DELETE** | `backend/copilot/` (29 files) · 3 VS Code views · `CopilotWorkstation.tsx` · `LearningWorkspace.tsx` · `routers/reading_path.py` mount · `routers/stability.py` · `routers/dependency_smells.py` · 3 `type(None)` registrations · 7 dead modules incl. `backend/main.py` · 3 fabrication-pinning test files · root + `/api` route mounts · `activationEvents` array · 2 VS Code commands |
| **FREEZE** | `ria/` — fix the import, keep CI green, no further development (R-016) |

---

## PHASE 3 — Security Recovery

**Goal:** safe to expose on a trusted network. **Effort: 9 ed.** **Depends on Phase 2 (R-009 must land first — see R-017).**

### R-014 — Remove `pickle` from all persistence paths
- **Problem.** `services/graph_service.py:159` writes graphs with `pickle.dump`; `:179` reads them with `pickle.load`. Every dependency-graph, call-graph and knowledge-graph read flows through it (`knowledge_graph_builder.py:170,190`, `graph_serializer`, `call_graph_service.py:300`, `architecture_service`).
- **Root cause.** `pickle` was the shortest path to persisting a `networkx.DiGraph`, which has no built-in stable serialization. The security property was not considered because the data was treated as internal.
- **Impact.** Three distinct failures. (1) **Arbitrary code execution:** `pickle.load` executes constructor code during deserialization, so write access to `data/graphs/` — a mounted volume, a restored backup, a CI artifact, a `git`-tracked `data/` directory — is RCE in the API process. The `except Exception` at `:182` catches nothing useful because the payload has already run. (2) **Version fragility:** pickled `networkx` objects are bound to library and interpreter versions, and `networkx>=3.0` is unpinned, so a routine `pip install -U` silently invalidates or misreads every cached graph. (3) **Opacity:** no schema, no version field, not diffable, not inspectable, not partially readable.
- **Risk.** **Critical.** This is the single most likely source of a CVE against this project post-launch, and `SECURITY.md` invites researchers to look.
- **Fix.** Define an explicit on-disk format with a `schema_version` field: node/edge JSON Lines for portability, or SQLite tables with covering indexes if R-025 lands first (preferred — it enables bounded reads too). Write a one-way migration that detects `.pkl`, ignores it, and triggers a rebuild. Delete the pickle code path entirely; do not leave a "legacy load" branch.
- **Effort.** 4 ed. **Priority.** P0.
- **Acceptance criteria.** `grep -rn "pickle" services/ backend/ core/ storage/` returns zero results; a test asserts a persisted graph round-trips identically; a test asserts a `.pkl` file present on disk is ignored rather than loaded.

### R-015 — Deny-by-default authentication
- **Problem.** `backend/security_middleware.py` returns `call_next(request)` immediately when `settings.api_key` is unset, and when set protects only a hardcoded prefix allowlist (`/api/analyze`, `/api/index`, `/api/chat`, `/api/retrieve`, `/api/issues/map`, their `/api/v1` twins, and any path containing `/report`). `/api/repositories`, `/api/graph`, `/api/twin`, `/api/knowledge-graph`, `/api/workspace`, `/api/memory`, `/api/execution`, `/api/symbols` are unauthenticated even when a key is configured.
- **Root cause.** Auth was introduced to protect *expensive* endpoints (cost control), not to establish a trust boundary. The mental model was rate-limiting-by-key, not authentication.
- **Impact.** A deployment that omits one environment variable is fully public. Even correctly configured, most of the API — including endpoints that expose the contents of private repositories cloned with the server's PAT — is open.
- **Risk.** **Critical.** Private source-code disclosure.
- **Fix.** Invert to deny-by-default: authenticate everything except an explicit `{"/health", "/metrics", "/docs", "/openapi.json"}` allowlist. **Fail closed on misconfiguration** — if `APP_ENV=production` and no key is set, refuse to start with a clear error rather than serving open. Use `secrets.compare_digest` for the comparison. Add per-key repository scoping: a key carries an allowed-repository set, enforced in one dependency used by every repo-scoped route.
- **Effort.** 2 ed. **Priority.** P0.
- **Acceptance criteria.** A parametrised test enumerates every route × {no key, wrong key, valid key, valid key wrong repo} and asserts 401/403/200 correctly — this single test would have caught both R-015 and R-018. App refuses to start in production without a key.

### R-016 — Fix the CI-breaking import in `ria/`, then freeze the package
- **Problem.** `ria/infrastructure/git/subprocess_git_client.py:45` does a module-level `from ria.config.settings import GitSettings`. `ria/config/settings.py` defines only `ObservabilitySettings` and `Settings` (E1). Because the import is module-level, collection of all 137 `tests/ria` files aborts, which aborts `pytest tests/`, which is the CI command. **`main` was red when `v1.0.0` was tagged.**
- **Root cause.** A settings class was renamed or folded into `Settings` without updating its consumer, and no green-CI gate existed to catch it.
- **Impact.** No working quality gate on the entire repository.
- **Risk.** **Critical** — every other quality claim in the project is unverified while this holds.
- **Fix.** Read `ria/config/settings.py`, determine whether git settings moved onto `Settings` or were dropped, and repair the import accordingly (prefer adjusting the consumer over resurrecting a class). Then **freeze `ria/`**: add `docs/adr/0003-ria-frozen.md` stating it is the intended future architecture, is not shipped, is not in the Docker image, and accepts no feature work during recovery. Keep it in CI so it stays green.
- **Effort.** 0.5 ed. **Priority.** P0 — do this on day one; it unblocks all measurement.
- **Acceptance criteria.** `pytest tests/` exits 0 and collects ≥1,100 tests; `docs/adr/0003-ria-frozen.md` merged.

### R-017 — Close the unauthenticated LLM-billing endpoint
- **Problem.** `graph_rag_router` mounts `POST /repositories/{username}/{repository}/chat` (`backend/routers/chat.py:383`) plus its `/api` and `/api/v1` variants. None matches the `/api/chat` protected prefix, so all three are unauthenticated paths to a billed LLM call.
- **Root cause.** Direct consequence of prefix-allowlist auth (R-015) combined with triple mounting (R-009): a route whose path does not begin with a listed prefix silently escapes protection.
- **Impact.** Anonymous cost drain; unmetered model access.
- **Risk.** **Critical** (financial).
- **Fix.** Subsumed by R-015 once deny-by-default lands, but verify explicitly because it is the canonical example of the class. Also replace the five-level Demeter chain used as the indexed-repository guard at `:387-392` with `graph_rag_service.is_indexed(repo_name)`.
- **Effort.** 0.5 ed. **Priority.** P0.
- **Acceptance criteria.** The R-015 route matrix covers `graph_rag` routes; unauthenticated request returns 401.

### R-018 — Add timeouts to every subprocess invocation
- **Problem.** No `timeout=` on any `subprocess.run` call: `services/github_service.py:140,167,236,246,283,304`, `services/git_history_service.py:322,430`, `backend/routers/repositories.py:648`, `services/twin_builder.py:65,79`.
- **Root cause.** `check=False` and `capture_output=True` were set consistently — timeouts were simply not part of the pattern that got copied.
- **Impact.** A slow or hostile git remote occupies a worker thread indefinitely. On a single-process server a handful of these exhausts the thread pool and the API stops responding, with no cancellation path.
- **Risk.** **Critical** (availability). Trivial to trigger.
- **Fix.** `timeout=30` for `ls-remote`/`rev-parse`, `timeout=300` for `clone`, configurable. Set `GIT_TERMINAL_PROMPT=0` in the subprocess environment so credential prompts cannot block forever. Handle `subprocess.TimeoutExpired` explicitly with a typed error surfaced to the client.
- **Effort.** 0.5 ed. **Priority.** P0 — best risk reduction per hour in the entire program.
- **Acceptance criteria.** A lint/AST test asserts every `subprocess.run` call site passes `timeout=`; a test simulating a hanging remote returns a 504 within the configured bound.

### R-019 — Remove the PAT from process arguments
- **Problem.** `services/github_service.py:152-158` embeds the token in the clone URL netloc and passes it as an argv element at `:167` and `:304`. Stderr is carefully redacted (`:166`, `:307`) — the risk was considered for logs and missed for argv.
- **Root cause.** URL-embedded credentials are the simplest way to authenticate `git clone`, and the argv exposure is non-obvious.
- **Impact.** On Linux, process arguments are world-readable via `/proc/<pid>/cmdline`, so any local user or sibling container can read the PAT. The token may also persist in the clone's `.git/config` remote URL.
- **Risk.** **High** — credential compromise with organisation-wide repository read scope.
- **Fix.** Use `git -c http.extraHeader="Authorization: Basic <base64>"` or a `GIT_ASKPASS` helper. After clone, rewrite the remote URL to the token-free form. Never log or store the constructed URL.
- **Effort.** 1 ed. **Priority.** P1.
- **Acceptance criteria.** A test asserts no argv element in any git invocation contains the token value; a cloned fixture's `.git/config` contains no credentials.

### R-020 — Prompt-injection mitigation
- **Problem.** Repository content is interpolated into prompts inside unescaped fenced blocks: `services/chat/context_builder.py:399-402` (code chunks) and `:229-231` (deterministic chunks). Documentation chunks — README, docs — are an explicit context slot (`:277`). Issue text enters via `POST /api/issues/map` (`backend/routers/chat.py:313-341`).
- **Root cause.** Untrusted repository content and trusted system instructions share one flat prompt string with no delimiter discipline, because the threat model assumed the analysed repository was the user's own.
- **Impact.** An attacker publishes a repository whose README closes the code fence and then issues instructions. Because README is a first-class slot and fences are not escaped, injected text lands in the same trust context as the system instruction. Any user analysing that public repository is affected — and analysing arbitrary public repositories is the product's primary use case. In the VS Code extension the output is rendered in a webview and drives review findings.
- **Risk.** **High.** Attacker-controlled output presented as grounded analysis.
- **Fix.** Layered: (1) escape or strip fence sequences (` ``` `, `~~~`) in all untrusted content before interpolation; (2) wrap untrusted blocks in unguessable per-request delimiters; (3) state explicitly in the system instruction that delimited content is data and never instructions; (4) cap untrusted content at a fraction of total prompt; (5) rely on R-005's deterministic citation verification as the post-generation backstop. Add a fixture repository containing a malicious README to the test suite.
- **Effort.** 2 ed. **Priority.** P1.
- **Acceptance criteria.** A test using the malicious-README fixture asserts the injected instruction does not alter the response structure and that no fence in untrusted content survives unescaped.

### R-021 — Supply chain and container hardening
- **Problem.** All dependencies are open lower bounds (`fastapi>=0.110`, `chromadb>=0.4`, `sentence-transformers>=3`, `networkx>=3`, `google-genai>=0.1.1`); `uv.lock` exists but CI installs from `requirements.txt`. `Dockerfile` runs as root with no `HEALTHCHECK`, no read-only filesystem and no dropped capabilities. `release.yml` pushes to GHCR without re-running tests, scanning the image, or emitting an SBOM or provenance attestation.
- **Root cause.** Release automation was built for convenience of publishing, not for supply-chain integrity.
- **Impact.** Non-reproducible builds; a compromised or merely breaking upstream release changes behaviour silently (and, with R-014 unfixed, can invalidate every persisted graph); a root container amplifies any RCE.
- **Risk.** **High.**
- **Fix.** Pin every dependency to an exact version with a lockfile as the CI install source. Add `pip-audit` and `npm audit --audit-level=high` as CI gates. Non-root `USER` in the Dockerfile plus a `HEALTHCHECK` hitting a real dependency-checking endpoint (R-024). In `release.yml`: re-run the full suite, scan the image (Trivy/Grype), generate an SBOM, attach provenance, and fail the release on high-severity findings.
- **Effort.** 1.5 ed. **Priority.** P1.
- **Acceptance criteria.** No unpinned dependency in `pyproject.toml`/`requirements.txt`; `pip-audit` and `npm audit` gate CI; image runs as non-root and reports healthy; release workflow produces an SBOM and fails on high-severity CVEs.

### R-022 — Input, output and resource validation
- **Problem.** `ChatRequest.history: List[Dict[str, Any]]` (`backend/routers/chat.py:49-53`) is unbounded and untyped and flows straight into prompt assembly; `message` has no `max_length`. `services/github_service.py` imposes no repository size limit, never evicts clones (only overwrites on re-clone of the same repo, `:282-288`), and has no disk quota. `backend/routers/chat.py:340` returns raw exception text to clients. CORS sets `allow_credentials=True` with dev origins injected into the production list.
- **Root cause.** Validation was applied where a user could plausibly err, not where an adversary could act.
- **Impact.** Unbounded request bodies enable prompt-stuffing and memory pressure; no size cap enables disk-exhaustion DoS; raw exception text leaks internals.
- **Risk.** **High** (availability), **Medium** (disclosure).
- **Fix.** Typed, length-bounded Pydantic models for chat history and message. Pre-flight repository size check via the GitHub API with a configurable cap; LRU eviction of clone directories; a disk-usage gauge with an alert threshold. Uniform error envelope that never includes `str(exception)`. Remove dev origins from the production CORS list. Replace the Windows `cmd /c rmdir` path (`:283-286`) with `shutil.rmtree` and **fail the analysis** on deletion failure rather than silently analysing a stale clone.
- **Effort.** 2 ed. **Priority.** P1.
- **Acceptance criteria.** Oversized request body returns 422; oversized repository returns a typed 413 before cloning; no 5xx response body contains an exception string; a disk-usage metric is exported.

### R-023 — Distributed rate limiting
- **Problem.** `RateLimitMiddleware` is an in-process sliding window keyed by client IP, with bypasses for `/health`, `/metrics`, pytest, `app_env=="test"`, and **any request from `127.0.0.1`/`::1`**.
- **Root cause.** Written for single-process local development.
- **Impact.** Behind any reverse proxy that presents `127.0.0.1` as the peer, the bypass is global. With more than one worker the limit is multiplied by the worker count.
- **Risk.** **High** — silently ineffective, which is worse than absent.
- **Fix.** Move the counter to shared storage (Redis, or a SQLite table with `BEGIN IMMEDIATE` for single-node beta). Key by API key, falling back to `X-Forwarded-For`'s leftmost trusted hop. Delete the loopback bypass; keep only the explicit test-environment bypass, gated on an env var that cannot be set in production.
- **Effort.** 1 ed. **Priority.** P1.
- **Acceptance criteria.** Limit holds across two worker processes in a test; a request from `127.0.0.1` is rate-limited.

### Phase 3 deliverables
- `SECURITY.md` updated with the real threat model, supported topology (single-user local for beta) and a disclosure SLA
- Route × credential authorisation matrix test
- Malicious-repository fixture

---

## PHASE 4 — Reliability Recovery

**Goal:** green, meaningful CI. **Effort: 10 ed.** **R-016 is a prerequisite and lands in Phase 3.**

### R-024 — Real health checks and graceful degradation
- **Problem.** `/health` is exempt from auth and rate limiting and does not check dependencies. `chat_health` genuinely probes providers (good) but runs live LLM auth checks on every call. No signal handling, no in-flight SSE draining, no clone cancellation on shutdown.
- **Root cause.** Health was implemented as a liveness ping; readiness was never modelled separately.
- **Impact.** An orchestrator sees healthy while Chroma is down, the disk is full or the graph store is unreadable. Deploys drop in-flight streams.
- **Risk.** Medium.
- **Fix.** Split `/health/live` (process up, no dependencies) from `/health/ready` (checks graph store readability, Chroma reachability, disk headroom, and provider circuit state — cached for 10s so it cannot be used as an amplification vector). Wire the Dockerfile `HEALTHCHECK` to `/health/live`. Add SIGTERM handling that stops accepting requests, drains SSE streams with a bounded deadline, and cancels in-flight clones.
- **Effort.** 2 ed. **Priority.** P1.
- **Acceptance criteria.** `/health/ready` returns 503 when the graph directory is unreadable; SIGTERM drains an active stream within the deadline and exits 0.

### R-025 — Replace exception swallowing with explicit degradation
- **Problem.** Verified `except Exception:` → `pass`/default sites: `services/twin_builder.py:180`, `services/retrieval_engine.py:328,376`, `services/report/composer.py:92`, `services/ingestion_service.py:86`, `services/graph_serializer.py:113,364`, `services/call_graph_service.py:436,829,1234`, `services/dead_code_service.py:115,217`, `services/architecture_drift_service.py:359`, `core/change_detector.py:82`, `backend/routers/architecture.py:314,417`, `backend/routers/inspection.py:44,53`, `backend/routers/monitoring.py:53,61`.
- **Root cause.** A deliberate resilience strategy — never fail a whole report because one section failed — implemented by coercing failure to a default value instead of to a recorded absence.
- **Impact.** A failed computation becomes a plausible number. `twin_builder.py:180` swallowing `nx.simple_cycles` leaves `cycles_count` at its initial value, so the twin reports "0 cycles" for a repository whose cycle detection crashed — and that figure flows into `knowledge_graph_builder.py:74` and then into the LLM prompt. This is the mechanism by which honest code produces dishonest output, and it is the most important item in the phase.
- **Risk.** **High.** It is the structural cousin of Phase 1's fabrication.
- **Fix.** Introduce a `Degraded`/`Computed` result wrapper or, minimally, an `errors: list[ComputationError]` field on every analysis model. Every current swallow site records a typed error and marks the affected field absent rather than zero. Serialise absence distinctly from zero in the API (`null` + an `errors` array, never `0`). Ban bare `except Exception: pass` with a ruff rule.
- **Effort.** 4 ed. **Priority.** P1.
- **Acceptance criteria.** A test injecting a cycle-detection failure asserts the response reports `cycles_count: null` with a populated `errors` array, and that no field reads `0`; ruff fails on new bare-swallow sites.

### R-026 — Type checking and coverage gates
- **Problem.** No `[tool.mypy]`, no `mypy.ini`, no type checker anywhere, despite a heavily annotated codebase. No `[tool.coverage]`, no `.coveragerc`, no `--cov` in CI. Ruff runs on defaults (E/F only) with no configured ruleset. `requires-python = ">=3.9"` while CI uses 3.12 and Docker uses 3.11.
- **Root cause.** Tooling was added incrementally as problems appeared; nothing forced a baseline.
- **Impact.** Substantial annotation effort produces zero verification. 976 tests have unknown reach. The 3.9 claim is untested and therefore false.
- **Risk.** Medium, compounding — silent rot.
- **Fix.** `mypy` on `backend/` and `services/` starting non-strict with a ratchet (error count may only decrease). Coverage measurement with a floor set at the measured baseline, ratcheted up. Configure a real ruff ruleset (E, F, I, B, C4, SIM, UP, S for bandit-equivalent security rules). Align Python to 3.12 across `pyproject.toml`, CI and Dockerfile, or test 3.9 in a matrix.
- **Effort.** 2 ed. **Priority.** P1.
- **Acceptance criteria.** CI runs ruff (configured), mypy and coverage; all three gate the build; the baseline is recorded in `docs/QUALITY-BASELINE.md`; Python version is consistent across all three files.

### R-027 — Observability of correctness
- **Problem.** Structured logging and `MetricsMiddleware` exist; there is no tracing, no cost/token accounting, and no metric that distinguishes "computed zero" from "computation failed" or counts dropped graph edges.
- **Root cause.** Observability was scoped to request-level health, not to analysis correctness.
- **Impact.** The degradation introduced in R-025 and the dropped edges in R-030 are invisible in aggregate — you cannot tell whether 1% or 40% of answers are partial.
- **Risk.** Medium.
- **Fix.** Counters for: analysis failures by stage, dropped edges by reason, degraded responses served, citations unresolved, prompt tokens and cost per provider per request (from provider-reported usage, not the `len//4` estimate). Add OpenTelemetry spans across ingest → parse → graph → retrieve → generate. Set a per-key daily token budget.
- **Effort.** 2 ed. **Priority.** P2.
- **Acceptance criteria.** `/metrics` exposes all listed counters; a trace spans a full chat request end to end; exceeding a key's daily budget returns 429.

### R-028 — Delete tests that pin fabricated behaviour, and add the missing categories
- **Problem.** `tests/test_copilot_skills.py:41` asserts `len(skills) == 12` and `:163` validates the shape of invented evidence. `tests/test_repository_copilot.py:31` asserts `len(tools) >= 5`. `tests/test_interactive_learning_workspace.py:121+` hits reading-path endpoints with the author's own repository hardcoded in the URL, which is precisely why those tests pass despite `DEFAULT_REPO_FILES`. Two Markdown files in `tests/` are named `test_*`. Frontend has zero tests and no test tooling. Extension tests run against a 276-line hand-written `vscode` mock rather than `@vscode/test-electron` (which is a declared but unused devDependency).
- **Root cause.** Tests were written to confirm the implementation rather than to specify behaviour, so fixtures and their tests were authored together.
- **Impact.** The suite actively resists the fix — the fabrications have green tests. Extension tests verify the mock's behaviour, not VS Code's, which is why `extension.ts:180-186` wraps every `createTreeView` in defensive try/catch (evidence that registration has failed in practice and no test caught it).
- **Risk.** **High** — a test suite that certifies falsehood is worse than none.
- **Fix.** Delete the three files with their subjects (Phase 1). Move the two Markdown checklists to `docs/manual-test-plans/`. Then add, in risk order: (1) route × credential auth matrix (R-015); (2) prompt-injection fixture (R-020); (3) citation-resolution test (R-005); (4) degradation-semantics test (R-025); (5) truncation-safety test asserting no unterminated code fence (R-031); (6) symbol/call-graph recall fixture (R-030).
- **Effort.** 2 ed for deletion and reorganisation; the six new suites are budgeted inside their parent items. **Priority.** P1.
- **Acceptance criteria.** No test asserts on a hardcoded analysis value; `tests/` contains no non-Python `test_*` files; all six new suites exist and pass.

### Phase 4 deliverables
- Green CI with six gates: ruff · mypy · coverage floor · pytest · pip-audit · npm audit
- `docs/QUALITY-BASELINE.md` recording measured coverage, mypy error count and Python version
- Manual test plans relocated out of `tests/`

---

## PHASE 5 — Knowledge Graph Recovery

**Goal:** one graph store that is genuinely the source of truth, with honest coverage. **Effort: 12 ed.** **Depends on Phases 2–4.**

### R-029 — Make the knowledge graph a real, persistent source of truth
- **Problem.** `services/knowledge_graph_builder.py` builds the KG by reading *from* four upstream stores — `twin_builder.build_twin()` (`:243`), `symbol_service.load()` (`:131`), `graph_service.load_graph()` (`:170`), and the call graph (`:190`) — then caches the result in an in-process LRU (`:264`) and **never persists it**. The actual sources of truth are `data/symbols/*.json` and two `.pkl` files. The documented claim that the KG is the single source of truth inverts the real data flow.
- **Root cause.** The KG was added last, as a unifying read model over existing stores, and then promoted in documentation to the architectural centre it never occupied in code.
- **Impact.** Full rebuild on every process restart; no cross-process sharing; no commit scoping; no ability to diff two versions; and the grounding guarantee the AI layer depends on is unsupportable as written.
- **Risk.** **High** — it is the load-bearing claim of the entire product narrative.
- **Fix.** Choose and execute one, honestly:
  - **(a) Make the claim true.** Persist the KG as the primary store; symbol, dependency and call-graph extraction write *into* it; all readers query it. ~6 ed.
  - **(b) Make the documentation true.** Rename to "Repository Read Model", document the real sources of truth, and drop the single-source-of-truth claim. ~0.5 ed.
  - **Recommendation: (a).** Option (b) leaves seven graph implementations (R-011) with no designated winner, so the consolidation has nowhere to land. (a) also gives R-014 its replacement storage target and R-032 its natural home.
- **Effort.** 6 ed. **Priority.** P1.
- **Acceptance criteria.** The graph survives process restart without rebuild; every graph-reading endpoint queries the one store; a test asserts the store is written by extraction and read by every consumer; the README's source-of-truth statement matches the code.

### R-030 — Fix symbol identity and stop silently dropping edges
- **Problem.** `SymbolProvider` builds identities by string concatenation (`:145`), and `CallGraphProvider` re-derives the same string from the call graph's own format (`:200-207`) before guarding `if u_id in graph and v_id in graph`. When the reconstructed identifier does not match, **the edge is discarded with no counter**. Same at `:177` (`IMPORTS`) and `:158-160` (class→method).
- **Root cause.** Two subsystems independently construct the same identity from different inputs, so any divergence in normalisation silently loses edges. Name-based matching also cannot distinguish overloads, same-named methods on different classes, re-exports or aliased imports.
- **Impact.** Unknown, unmeasured recall on `CALLS` and `IMPORTS` — the two edge types every impact-analysis and blast-radius answer depends on. Today "nothing calls this function" is indistinguishable from "we failed to match the identifier." Given that impact analysis is a headline v0.9.0 capability, this is the most important correctness item after Phase 1.
- **Risk.** **High.**
- **Fix.** Emit symbol identity once, from the extractor, as a value object; have the call-graph builder reference that identity rather than re-deriving a string. Count and export dropped edges by reason (R-027). Build a hand-labelled fixture repository with known call edges and assert measured recall in CI. Publish the measured number — a stated 78% recall is infinitely more valuable than an implied 100%.
- **Effort.** 4 ed. **Priority.** P1.
- **Acceptance criteria.** Dropped-edge count is exported and is zero for the fixture repository; a CI test asserts call-graph recall against the labelled fixture and fails on regression; the measured figure appears in the README capability matrix.

### R-031 — Coverage, provenance and confidence envelope
- **Problem.** `KnowledgeGraphNode`/`KnowledgeGraphEdge` carry only `properties: dict` — no `commit_sha`, no `derived_by`, no `confidence`, no `extraction_method`. Provider failures produce a silently partial graph (`:248-257`). Graph truncation to `max_nodes=500` is not surfaced to the caller.
- **Root cause.** The models were designed for rendering, not for grounding.
- **Impact.** An answer cannot state which commit it describes; two analyses of the same repository at different times are indistinguishable; nothing can express "this edge came from exact resolution" versus "heuristic name match" — which, given R-030, is exactly the distinction that determines whether an answer can be trusted.
- **Risk.** **High.** This item is what converts "confidently wrong" into "honestly partial", and it is the prerequisite for any legitimate confidence score anywhere in the product.
- **Fix.** Add `commit_sha`, `provenance`, `confidence` to node and edge models. Add `coverage: dict[str, ProviderStatus]` to `KnowledgeGraph`; providers report `OK`/`DEGRADED`/`FAILED` instead of failing silently. Propagate the envelope to every API response. Refuse to answer graph-dependent AI queries when the relevant provider is `FAILED` — say so instead. Surface truncation explicitly (`truncated: true, shown: 500, total: 2841`). Key the cache by `(repo, commit_sha, schema_version)`.
- **Effort.** 3 ed. **Priority.** P1.
- **Acceptance criteria.** Every intelligence response carries `coverage`, `provenance` and `commit_sha`; a test with a deliberately broken provider asserts `DEGRADED` is returned and the AI layer declines rather than answering; truncated graph responses declare truncation.

### R-032 — Bounded graph reads and build-time centrality
- **Problem.** `load_graph()` returns the entire `DiGraph`; `graph_serializer.py:113,364` and `call_graph_service.py:829,1234` compute `nx.degree_centrality` over the whole graph or subgraph per request. `nx.simple_cycles` is called with no `length_bound` in three places.
- **Root cause.** Whole-graph-in-memory was the natural shape for `networkx`, and centrality was needed per view so it was computed per view.
- **Impact.** Every neighbourhood query — "who calls this function", the most common operation — costs O(V+E) deserialization plus a full centrality pass. Memory scales with the largest repository ever analysed, held per process. There is no path to a repository larger than RAM. Unbounded `simple_cycles` is worst-case exponential and can hang.
- **Risk.** Medium for beta (single-user, moderate repositories); **High** for any later multi-user deployment.
- **Fix.** Move adjacency into the indexed store from R-029 and answer neighbourhood queries with bounded lookups. Precompute centrality once at build time and persist it as a node attribute. Set `length_bound` on cycle detection and cache the result at build time.
- **Effort.** 3 ed (overlaps R-029; net ~2 ed if sequenced immediately after). **Priority.** P2.
- **Acceptance criteria.** A neighbourhood query on a 10k-node fixture reads a bounded number of rows (asserted); no request path calls `degree_centrality` or `simple_cycles`.

### R-033 — Add inheritance edges
- **Problem.** The graph has no `INHERITS`/`IMPLEMENTS` edges at all. Node types are `repository`, `health`, `compliance`, `architecture`, `directory`, `file`, `symbol`; edge types are `HAS_HEALTH`, `HAS_COMPLIANCE`, `HAS_ARCHITECTURE`, `CONTAINS`, `DECLARES`, `IMPORTS`, `CALLS`.
- **Root cause.** Extraction focused on call and import relationships; inheritance requires resolving a base-class reference, which the name-matching identity scheme (R-030) could not do reliably.
- **Impact.** "What breaks if I change this base class" is unanswerable, and blast radius is materially understated for any object-oriented codebase. Impact Analysis is a headline v0.9.0 capability, so this is a correctness gap in a shipped feature.
- **Risk.** **High** for the shipped impact-analysis claim.
- **Fix.** Extract base-class references in the tree-sitter Python and JS/TS extractors; emit `INHERITS`/`IMPLEMENTS` edges through the R-030 identity scheme; include them in blast-radius traversal. This is the only *new* graph capability in the program and it is justified as a correctness fix to a shipped feature, not a new feature.
- **Effort.** 3 ed. **Priority.** P1 — but **descope to post-beta if the timeline slips**, provided the README states that blast radius does not currently follow inheritance. Honest limitation beats silent incompleteness.
- **Acceptance criteria.** Inheritance edges present for a fixture with a three-level hierarchy; blast radius includes subclasses; if descoped, the limitation is documented in the capability matrix.

### Phase 5 deliverables
- One persistent, commit-scoped graph store
- Published recall figures for `CALLS` and `IMPORTS`
- Coverage/provenance/confidence on every response
- `docs/adr/0004-graph-model.md` recording node/edge types, identity scheme and known blind spots

---

## PHASE 6 — Copilot Recovery

**Goal:** one assistant. **Effort: 3 ed.** **Depends on Phase 1 (deletion) and Phase 5 (grounding).**

### R-034 — Decision: delete Copilot, merge its two good ideas into the retrieval pipeline
- **Problem.** Two assistants exist. `services/chat/` is real: `retrieval_pipeline.py` (571 LOC), `intent_router.py` (529), `context_builder.py` (485), `provider_manager.py` (562), conversation memory, streaming, deterministic intent routing into real analysis services. `backend/copilot/` is a fixture (R-001).
- **Root cause.** The Copilot was built as a parallel v2 assistant rather than as an evolution of the working pipeline, so it had to re-implement retrieval, context and grounding — and those were the parts that got stubbed.
- **Impact.** Maintaining two assistants where one works.
- **Risk.** Medium after Phase 1 removes the fabrication; the residual risk is losing two genuinely good abstractions in the deletion.
- **Options considered.**
  - *Rebuild Copilot properly.* Rejected: ~20 ed to reach parity with something that already exists, and it would produce a second assistant competing with the first.
  - *Keep both, fix Copilot's bodies.* Rejected: duplicates retrieval, context assembly, provider management and grounding — four subsystems, permanently, in two places.
  - *Delete Copilot, port its ideas.* **Chosen.**
- **Fix.** Port exactly two things onto `services/chat/`: (1) **slash-command routing** — `intent_router.py` already routes intents to deterministic services, so add explicit `/explain`, `/trace`, `/impact`, `/review` commands as first-class intents with a documented registry; (2) **a tool schema registry** — a declarative list of the deterministic capabilities the assistant can invoke, exposed at one endpoint so clients can render available commands. Both are ~1 day each on top of existing machinery. Everything else in `backend/copilot/` is discarded.
- **Effort.** 3 ed. **Priority.** P2.
- **Acceptance criteria.** One assistant endpoint remains; `/explain`, `/trace`, `/impact` resolve to deterministic services and return verified citations (R-005); the command registry is discoverable via one route; no module named `copilot` exists.

### R-035 — Honest context assembly
- **Problem.** `services/chat/context_builder.py:34-40` sets `_CHARS_PER_TOKEN = 4` and `_TARGET_MAX_TOKENS = 5_000`, giving a 20,000-character ceiling. `:434` enforces the budget with a raw string slice `current[: len(current) - excess]`, and `:387` truncates oversized chunks the same way — both can cut mid-identifier and leave an unterminated code fence, while `:333` instructs the model to "reproduce only what is in the context".
- **Root cause.** The budget was calibrated against 2023-era context windows and never revisited; truncation was implemented on the concatenated string rather than on the chunk list.
- **Impact.** Two compounding failures. The heuristic understates real token count by 30–60% on code, so the reported `estimated_tokens` is wrong and provider-side truncation can occur silently. And 20,000 characters is roughly 1–2% of current frontier windows — the compression machinery is paying recall to solve a constraint that no longer binds. Mid-string truncation is a direct hallucination vector: the model receives a syntactically broken function and is told to reproduce it faithfully; the likely output is a plausible completion of the missing half.
- **Risk.** **High.**
- **Fix.** Use the provider's real tokenizer. Make the budget a per-model configuration derived from the model's window minus a reserve, defaulting an order of magnitude higher than today. **Never trim mid-chunk** — drop whole chunks and report `chunks_dropped: N` in the response. If a chunk must be shortened, cut at a line boundary and re-close the fence. Measure answer quality at two or three budget settings before fixing the default.
- **Effort.** 2 ed (counted in Phase 6; overlaps R-020). **Priority.** P1.
- **Acceptance criteria.** A property test asserts every assembled prompt has balanced code fences; token counts come from the provider tokenizer; dropped chunks are reported to the caller.

### R-036 — Prompt registry and versioned provenance
- **Problem.** The system instruction is a string literal inside a method (`context_builder.py:325-341`); the response-format block is another literal (`:283-295`). Prompts are unversioned, not diffable in isolation, and the prompt version appears in no response or log line.
- **Root cause.** Prompts were treated as implementation detail rather than as configuration that determines output quality.
- **Impact.** Answer-quality regressions cannot be attributed to a prompt change; A/B evaluation is impossible.
- **Risk.** Medium.
- **Fix.** A `prompts/` directory with versioned template files; a thin loader; `prompt_version` recorded in every response and log line.
- **Effort.** 1 ed. **Priority.** P2.
- **Acceptance criteria.** No prompt text is a literal inside a function; every chat response includes `prompt_version`.

### Phase 6 deliverables
- One assistant, one command registry
- `docs/adr/0005-single-assistant.md` recording the deletion decision and the two ported abstractions

---

## PHASE 7 — Frontend Recovery

**Goal:** maintainable, testable, contributable UI. **Effort: 12 ed.** **Depends on R-009 (single API prefix).**

### R-037 — Establish test and lint tooling
- **Problem.** `frontend/package.json` `devDependencies` contains only `@types/*` and `typescript`. No vitest, jest, testing-library or playwright. `"lint": "tsc --noEmit"` — there is no ESLint.
- **Root cause.** The frontend was treated as a demonstration surface for a backend-focused project, so quality tooling was never installed.
- **Impact.** 10,400 lines with no regression safety and no lint. For an open-source project inviting external PRs, every UI contribution is unverifiable — which makes accepting them irresponsible and rejecting them arbitrary.
- **Risk.** **High** for an OSS launch specifically.
- **Fix.** Vitest + Testing Library; Playwright for one end-to-end path (analyse → dashboard → chat); ESLint with `react-hooks` and `jsx-a11y` plugins. Wire all three into CI. The `react-hooks` rules alone will surface the missing-cleanup and stale-closure defects behind R-039 and R-040 automatically.
- **Effort.** 2 ed. **Priority.** P1.
- **Acceptance criteria.** `npm run lint` and `npm run test` exist and gate CI; ≥30 component tests and 1 E2E path pass; ESLint reports zero errors (warnings ratcheted).

### R-038 — Break up the god components
- **Problem.** `CallGraphAnalyzer.tsx` **1,262 LOC** (five independent fetches at `:833,850,859,876,893`, build orchestration at `:944`, and all rendering); `AnalysisDashboard.tsx` 805; `ChatInterface.tsx` 790; `ReportPanel.tsx` 735; `APISurfaceAnalyzer.tsx` 604; `PRIntelligence.tsx` 569; `ArchitectureDrift.tsx` 548; `GitHistoryAnalyzer.tsx` 541.
- **Root cause.** No component-size budget; each feature grew inside the component that first rendered it.
- **Impact.** Unreviewable diffs, guaranteed conflicts, no unit-testable seams, re-render cascades.
- **Risk.** Medium — maintainability and contribution friction.
- **Fix.** Extract one custom hook per server resource (`useCallGraph`, `useBlastRadius`, `useApiSurface`, …) and split presentational children. Target ≤300 LOC. Do this **after** R-039 so the hooks are written against the query layer, not against raw `fetch`.
- **Effort.** 5 ed. **Priority.** P2.
- **Acceptance criteria.** No `.tsx` file exceeds 300 LOC; CI enforces the ceiling; the E2E path from R-037 still passes.

### R-039 — Introduce a server-state layer
- **Problem.** ~24 raw `fetch()` call sites across 18 components, each with hand-rolled `isLoading`/`error` state. No caching, no request deduplication, no retry, no stale-while-revalidate, no shared invalidation. Exactly two sites use `AbortController` (`InteractiveDependencyGraph.tsx:133` and one other); the remaining ~22 will `setState` after unmount.
- **Root cause.** `frontend/src/lib/api.ts` correctly centralised the *base URL* (`:16`), which made per-component `fetch` feel adequate, so no caching layer was ever added.
- **Impact.** Duplicate in-flight requests when components mount together; full refetch on every navigation; inconsistent loading/error UX per view; React unmount warnings and potential state corruption.
- **Risk.** Medium.
- **Fix.** TanStack Query with one query key per endpoint. This also deletes several hundred lines of duplicated boilerplate and fixes the unmount issue structurally rather than by adding 22 `AbortController`s.
- **Effort.** 3 ed. **Priority.** P1.
- **Acceptance criteria.** No component calls `fetch` directly; a test mounting two components sharing an endpoint asserts one network call; no React unmount warnings in the test run.

### R-040 — Fix the request waterfall
- **Problem.** `frontend/src/components/reading/LearningWorkspace.tsx:43-67` performs five sequentially awaited, mutually independent fetches.
- **Root cause.** Sequential `await` inside a single effect.
- **Impact.** Time-to-content is the sum of five round trips instead of the max — roughly 800ms of avoidable latency on a 200ms link.
- **Risk.** Low.
- **Fix.** **Subsumed by R-003** — this component is deleted in Phase 1. Recorded here because the same pattern must not reappear; the correct reference implementation already exists at `APISurfaceAnalyzer.tsx:308-315` (`Promise.all`).
- **Effort.** 0 ed (deleted). **Priority.** N/A.
- **Acceptance criteria.** No component performs more than one sequential `await` on independent requests; ESLint or review checklist covers it.

### R-041 — Extract a UI primitives layer
- **Problem.** `clsx`, `tailwind-merge` and `class-variance-authority` are installed but there is no `components/ui/` directory. Every component hand-rolls its buttons, panels, badges and empty states.
- **Root cause.** The primitives dependencies were added for a design system that was never built.
- **Impact.** Visual inconsistency, duplicated markup, and no single place to fix accessibility or theming.
- **Risk.** Low individually; it is the enabler for R-042 and R-045.
- **Fix.** Extract ~12 primitives (Button, Card, Badge, Spinner, EmptyState, ErrorState, Table, Tabs, Dialog, Tooltip, Input, Skeleton) with `cva` variants.
- **Effort.** 2 ed. **Priority.** P2.
- **Acceptance criteria.** ≥12 primitives exist; the five largest views use them exclusively for those elements; hardcoded hex colours reduced to zero in components (tokens only).

### R-042 — Surface degradation and truncation in the UI
- **Problem.** With R-025 and R-031 adding `coverage`, `errors` and `truncated` to responses, the UI currently has nowhere to display them — and today silently renders a truncated 500-node graph as if complete.
- **Root cause.** The UI was designed against a success-only response contract.
- **Impact.** Honest backend, dishonest presentation. This would waste the entire Phase 4/5 investment.
- **Risk.** **High** — it is the last mile of the honesty programme.
- **Fix.** A shared `<CoverageBadge>` and `<DegradedBanner>` from the R-041 primitives, rendered by every view consuming an intelligence response. Graph views must state "showing 500 of 2,841 nodes". Chat must render unresolved citations distinctly.
- **Effort.** 2 ed. **Priority.** P1.
- **Acceptance criteria.** A test rendering a `DEGRADED` response asserts the banner appears; a truncated graph response renders the node counts; unresolved citations are visually distinguished.

### R-043 — Typed API client generated from OpenAPI
- **Problem.** Response shapes are typed by hand or as `any`; frontend types can drift from backend Pydantic models with no detection.
- **Root cause.** No contract enforcement between the two codebases.
- **Impact.** Runtime shape errors that types should have caught, especially after R-009's path changes and R-031's envelope additions.
- **Risk.** Medium.
- **Fix.** Generate types with `openapi-typescript` in CI; fail the build if the committed types differ from the generated ones.
- **Effort.** 1 ed. **Priority.** P2.
- **Acceptance criteria.** Types are generated, committed and drift-checked in CI.

### R-044 — Graph rendering performance
- **Problem.** ReactFlow renders DOM nodes; the only thing preventing collapse is the backend's `max_nodes=500` cap. Dagre layout runs on the main thread. No virtualization, no canvas fallback.
- **Root cause.** ReactFlow was chosen for interaction richness; the node-count ceiling was handled server-side rather than in the renderer.
- **Impact.** Main-thread jank at the upper bound on mid-range hardware.
- **Risk.** Low for beta.
- **Fix.** Move dagre layout into a Web Worker. Defer the canvas/WebGL renderer to post-beta and document the 500-node limit instead.
- **Effort.** 1 ed. **Priority.** P3.
- **Acceptance criteria.** Layout computation does not block the main thread for >50ms; the node limit is documented.

### R-045 — Accessibility baseline
- **Problem.** No ARIA attributes, focus management or keyboard handlers were found in the interactive components examined. ReactFlow graphs are pointer-only with no keyboard path to select a node and no text-equivalent view. `framer-motion` animations have no `prefers-reduced-motion` guard.
- **Root cause.** Accessibility was never in the definition of done.
- **Impact.** Likely WCAG 2.1 AA failures on 1.3.1, 2.1.1, 2.4.3, 2.4.7, 2.3.3 and 4.1.2. Blocks public-sector and many enterprise evaluations.
- **Risk.** **High** for adoption breadth; not a correctness risk.
- **Honest caveat.** Full WCAG validation requires manual testing with assistive technology and expert review. The above is a static-inspection estimate, not a conformance verdict, and this program does not claim to deliver conformance.
- **Fix (beta scope only).** `jsx-a11y` in CI; `prefers-reduced-motion` respected; keyboard operability and visible focus for all controls; a tabular fallback view for every graph; axe-core assertions in the Playwright run. Full conformance audit is scheduled post-beta and stated as such in the README.
- **Effort.** 3 ed. **Priority.** P2.
- **Acceptance criteria.** `jsx-a11y` passes with zero errors; axe-core reports no critical violations on the four main views; every graph has a keyboard-navigable table equivalent; README states the accessibility position honestly.

### Phase 7 deliverables
- Vitest + Playwright + ESLint in CI; ≥30 component tests
- Query layer; primitives layer; degradation surfaced in UI
- No `.tsx` over 300 LOC

---

## PHASE 8 — VS Code Recovery

**Goal:** a genuine presentation layer. **Effort: 8 ed.**

### R-046 — Remove test scaffolding from the production package
- **Problem.** `vscode-extension/package.json` declares `"dependencies": { "module-alias": "^2.2.3" }` and `"_moduleAliases": { "vscode": "./out/test/mocks/vscode.js" }` — a runtime dependency plus a manifest-level mapping from the real VS Code API to a 276-line test mock.
- **Root cause.** `module-alias` was the mechanism for running mocha tests outside the extension host, and the configuration was placed in the package manifest rather than in a test-only config.
- **Impact.** Test scaffolding ships in the published VSIX. If `module-alias/register` is ever loaded in the extension host, API calls resolve to a mock.
- **Risk.** **High** — a shipped extension that can silently substitute a mock for the editor API.
- **Fix.** Move `module-alias` to `devDependencies`; move the alias map into `.mocharc` or a test bootstrap; add `out/test/**` and `src/test/**` to `.vscodeignore`.
- **Effort.** 0.5 ed. **Priority.** P1.
- **Acceptance criteria.** `vsce ls` output contains no `test` path; `dependencies` is empty or contains only genuine runtime deps.

### R-047 — Bundle the extension
- **Problem.** `"compile": "tsc -p ./"` with `"main": "./out/extension.js"`. 141 source files compile to 141+ JS files, all loaded via CommonJS `require` at activation.
- **Root cause.** `tsc` was sufficient during development and bundling was never added.
- **Impact.** Larger VSIX, slower activation from hundreds of filesystem `require` calls, no tree-shaking or minification. VS Code's own guidelines call for bundling.
- **Risk.** Medium — activation latency is the first thing users perceive.
- **Fix.** esbuild producing a single minified bundle with sourcemaps; keep `tsc --noEmit` as the type gate.
- **Effort.** 1 ed. **Priority.** P1.
- **Acceptance criteria.** VSIX contains one bundled entry file; package size reduced ≥70%; activation time measured and recorded before/after.

### R-048 — Make the extension a presentation layer
- **Problem.** The "thin client" claim holds for data — `api.ts` is the single egress and no analysis runs locally — but fails for presentation: eight panels build roughly 2,000 lines of HTML/CSS/JS by string concatenation inside TypeScript (`panels/*.ts`, `review/repositoryReview.ts`, `providers/chatProvider.ts`), duplicating dashboards that already exist in the Astro frontend.
- **Root cause.** Webviews were built independently of the web UI because sharing a build across two toolchains was not set up.
- **Impact.** Two independent UI implementations of the same dashboards must be maintained in lockstep. Every change from Phase 7 — primitives, degradation banners, truncation notices — must be reimplemented by hand in TypeScript template strings.
- **Risk.** **High** as a maintenance multiplier, and it directly threatens R-042's honesty guarantee (a degradation banner added to the web UI would silently not exist in the editor).
- **Fix.** Serve the existing frontend build inside the webviews, passing configuration and auth via `postMessage`. Deletes ~2,000 lines and one whole UI codebase. If the toolchain integration proves costly, the fallback is to reduce webviews to the two that matter (chat, dashboard) and remove the rest — but do not maintain eight.
- **Effort.** 4 ed. **Priority.** P1.
- **Acceptance criteria.** No panel file contains more than 20 lines of HTML; the degradation banner from R-042 appears in the editor without duplicated code.

### R-049 — Webview security and real integration tests
- **Problem.** `views/{KnowledgeGraph,Learning,Architecture}View.ts:9` and `panels/WebviewHost.ts:17-19` set `enableScripts: true` with no CSP and no `localResourceRoots`. The panel layer does it correctly (`utils/webview.ts:11-14` nonce, applied in `panels/workspaceDashboard.ts:99`, `panels/timelinePanel.ts:123`, `review/repositoryReview.ts:82`, `providers/chatProvider.ts:124`) — the practice exists but is applied inconsistently. Separately, `"test"` runs mocha against the mocked `vscode` module; `@vscode/test-electron` is a declared but unused devDependency, so tree-view registration, webview lifecycle, command wiring and secret storage are untested against the real API. `extension.ts:180-186` wraps every `createTreeView` in try/catch with an error log — defensive code indicating registration has failed in practice with no test to catch it.
- **Root cause.** The CSP helper was written after the views; the mock-based test harness was the fastest path to a green suite.
- **Impact.** Three views are removed by R-002, but `WebviewHost` is a generic host — the moment any backend-derived string is interpolated, this is stored XSS inside the editor with access to `acquireVsCodeApi()`. And eleven test files verify a hand-written mock's behaviour rather than VS Code's.
- **Risk.** **Medium** (latent XSS), **High** (untested editor integration).
- **Fix.** Apply the nonce+CSP helper to every webview without exception, including `WebviewHost`; scope `localResourceRoots`; add a unit test that fails if any webview is created without a CSP meta tag. Migrate integration tests to `@vscode/test-electron`, covering tree-view registration explicitly; keep mocha only for pure logic. Remove the defensive try/catch once registration is genuinely tested.
- **Effort.** 2 ed. **Priority.** P1.
- **Acceptance criteria.** A test asserts every webview HTML template contains a nonce-based CSP; `@vscode/test-electron` runs in CI and covers activation, all tree views, and command registration.

### R-050 — Manifest hygiene and marketplace readiness
- **Problem.** 44 redundant `activationEvents` (VS Code has generated these automatically since 1.74; the manifest targets `^1.85.0`), producing 44 editor warnings on the manifest of a v1.0 release. No top-level `icon`. `"categories": ["Other", ...]` with `"Other"` first. No `walkthroughs` for a 60-command extension. No `capabilities.untrustedWorkspaces` declaration despite reading git state and calling a network backend. `version: "0.1.0"` while the platform is tagged `1.0.0`. `src/extension.ts:39-45` contains five `console.log` calls with the comment *"remove after confirming views appear"*.
- **Root cause.** Manifest was written against older guidance and never revalidated; debug logging was never cleaned up.
- **Impact.** 44 warnings, a placeholder marketplace tile, no onboarding, unspecified trust behaviour, and debug output on every activation.
- **Risk.** Medium — first-impression quality.
- **Fix.** Delete the `activationEvents` array. Add an icon; reorder categories. Add a three-step walkthrough. Declare `untrustedWorkspaces: { supported: "limited" }` with a stated reason. Align the version to `0.9.0`. Delete the DIAG block (the `Logger` service is already used elsewhere in the same file).
- **Effort.** 0.5 ed. **Priority.** P2.
- **Acceptance criteria.** Zero diagnostics on `package.json`; `vsce package` succeeds with an icon and walkthrough; no `console.log` in `src/`.

### R-051 — Split `commands.ts` and `api.ts`
- **Problem.** `commands.ts` 1,153 LOC registering ~60 commands; `api.ts` 835 LOC as a single client.
- **Root cause.** Same as R-012 and R-038 — no file budget.
- **Impact.** Single-owner bottlenecks; every feature touches both files.
- **Risk.** Low.
- **Fix.** One module per command group (graph, review, workspace, advisor, execution, reading); split the API client per resource. Command count also drops with R-002 and R-004.
- **Effort.** 2 ed. **Priority.** P3.
- **Acceptance criteria.** No `.ts` file in `vscode-extension/src/` exceeds 400 LOC.

### Phase 8 deliverables
- Bundled, test-scaffolding-free VSIX with `@vscode/test-electron` coverage
- CSP on every webview, enforced by test
- One UI codebase shared with the frontend

---

## PHASE 9 — Documentation Recovery

**Goal:** every document matches the code. **Effort: 5 ed.** **Must run last — documentation is written against the corrected architecture, not the current one.**

### R-052 — Honest capability matrix
- **Problem.** 18 capabilities are advertised. At least 3 are fabrications (Phase 1), 3 are `type(None)` registrations, and the two central architectural claims are false: *"The AI layer reasons ONLY over deterministic intelligence"* (contradicted by `backend/copilot/`) and *"Repository Knowledge Graph is the single source of truth"* (contradicted by `knowledge_graph_builder.py` reading from four upstream stores). `backend/copilot/tool_registry.py:4` claims 15 tools where 5 are registered.
- **Root cause.** Documentation was written aspirationally, ahead of implementation, and never reconciled.
- **Impact.** For an OSS launch this is the most damaging documentation defect — it is discoverable in minutes from the source and it undermines every other claim in the repository.
- **Risk.** **Critical.**
- **Fix.** A capability matrix in the README with per-feature status `Stable` / `Beta` / `Experimental` / `Planned` / `Removed in 0.9.0`, plus measured numbers where they exist (call-graph recall from R-030, language coverage, node limits). Nothing marked `Stable` or `Beta` may contain a fabricated value. State limitations explicitly: three languages, single-user local topology, 500-node graph cap, blast radius inheritance support (or its absence per R-033).
- **Effort.** 1 ed. **Priority.** P0.
- **Acceptance criteria.** Every capability in the matrix maps to a passing test and a live route; a reviewer can verify each claim in under five minutes.

### R-053 — Resolve documentation duplication and supersession
- **Problem.** Three API documents (`API.md`, `docs/api.md`, `docs/API_REFERENCE.md` at 1,737 lines), two installation guides, two troubleshooting guides, two contributing guides, two developer guides. Casing is inconsistent within `docs/`. Meanwhile `docs/foundation/01-PRD.md:5` explicitly states it *"Supersedes: all positioning and scope statements in `README.md`, `ARCHITECTURE.md`, `AUDIT_REPORT.md`"* — all three of which remain at the repository root as the first thing a visitor reads, and the PRD describes `ria/`, which does not ship.
- **Root cause.** Documents were added per initiative without a canonical-source policy; the foundation set was written as a redesign and never reconciled with the shipping product.
- **Impact.** External contributors cannot determine which document is authoritative. Duplicates have already diverged.
- **Risk.** **High** for contribution quality.
- **Fix.** One canonical file per topic; delete the rest; add `docs/README.md` as an index. Move `docs/foundation/` to `docs/design/future/` with a header stating it describes the frozen `ria/` architecture and is not the shipping design. Rewrite root `ARCHITECTURE.md` to describe what actually ships. Delete `AUDIT_REPORT.md` (superseded by the EDR).
- **Effort.** 1.5 ed. **Priority.** P1.
- **Acceptance criteria.** Exactly one document per topic; no document claims to supersede a published document that still exists; `docs/README.md` indexes everything.

### R-054 — Generate the API reference
- **Problem.** `docs/API_REFERENCE.md` is 1,737 hand-maintained lines describing an API that currently has ~75 mounted route trees, includes routes backed by `type(None)`, and is about to change substantially under R-009.
- **Root cause.** Manual documentation of a large, unstable API surface.
- **Impact.** Guaranteed drift; 1,737 lines of permanent maintenance burden.
- **Risk.** Medium.
- **Fix.** Generate from the FastAPI OpenAPI schema in CI and fail the build on drift. Delete the hand-written file.
- **Effort.** 1 ed. **Priority.** P1.
- **Acceptance criteria.** API reference is generated; CI fails if the committed output differs from the generated schema.

### R-055 — Contributor infrastructure
- **Problem.** No `CODE_OF_CONDUCT.md`, no `.github/ISSUE_TEMPLATE/`, no `.github/PULL_REQUEST_TEMPLATE.md`, no ADR directory despite the volume of design documentation, no architecture diagram matching the shipped system. `docs/performance.md` is 20 lines with no numbers.
- **Root cause.** The project has not previously accepted external contributions.
- **Impact.** An OSS launch without these produces unreviewable issues and PRs from day one.
- **Risk.** Medium.
- **Fix.** Add all of the above. `docs/adr/` receives the five ADRs produced by this program. Replace `docs/performance.md` with measured figures from R-027 and R-032 or delete it — an empty performance document is worse than none.
- **Effort.** 1.5 ed. **Priority.** P1.
- **Acceptance criteria.** All standard OSS files present; five ADRs merged; architecture diagram matches the post-recovery module structure.

### Phase 9 deliverables
- README capability matrix with measured numbers and stated limitations
- One canonical document per topic; generated API reference
- Five ADRs; contributor templates; honest `SECURITY.md`

---

## PHASE 10 — Release Recovery

**Goal:** ship v0.9.0-beta. **Effort: 4 ed.**

### R-056 — Release scope enforcement
- **Problem.** The tagged `v1.0.0` includes fabricated subsystems, non-functional routers, and a red test suite. Semver 1.0 promises a stable API contract that does not exist behind ~75 route trees about to be reduced to ~18.
- **Root cause.** No release gate distinguished "code exists" from "capability works".
- **Impact.** A version number that overpromises, published artifacts containing fixtures.
- **Risk.** **Critical.**
- **Fix.** Release as **`v0.9.0-beta.1`**, not 1.0.0. Publish a release checklist gate requiring: every capability in the matrix has a passing test and a live route; zero fabricated outputs; CI green on all six gates; security items P0/P1 closed; `CHANGELOG.md` documenting every removal explicitly and why. Yank or clearly deprecate the existing `v1.0.0` tag and GHCR image with a note pointing to 0.9.0-beta.
- **Effort.** 1 ed. **Priority.** P0.
- **Acceptance criteria.** `v0.9.0-beta.1` tagged from green `main`; `CHANGELOG.md` lists all removals; the prior `v1.0.0` artifact carries a deprecation notice.

### R-057 — Supported-topology statement
- **Problem.** The platform is documented as production-capable but cannot scale horizontally: in-process LRU cache, in-process rate limiter, module-global `ANALYSIS_STORE`, local filesystem state, single worker. Two replicas produce *incorrect answers*, not more throughput. There is no migration strategy for the graph format, no backup procedure for state that costs a full re-analysis to rebuild, and no SLOs.
- **Root cause.** Single-process assumptions accumulated without ever being declared.
- **Impact.** A user who deploys two replicas gets silent data inconsistency.
- **Risk.** **High** if unstated; **Low** if stated honestly.
- **Fix.** Declare **single-user, single-process, local deployment** as the only supported topology for 0.9.0-beta. Document the specific blockers to multi-instance operation so the limitation is verifiable rather than vague. Add a startup warning if more than one worker is configured. Provide a backup/restore procedure for `data/` and the clone directory.
- **Effort.** 1 ed. **Priority.** P1.
- **Acceptance criteria.** README states the supported topology and the multi-instance blockers; the app warns on `--workers > 1`; a documented backup/restore procedure has been executed successfully once.

### R-058 — Freeze feature work for the program duration
- **Problem.** The program's central risk is scope leakage: recovery competing with feature development.
- **Root cause.** No enforcement mechanism.
- **Impact.** Recovery stalls; the codebase grows while being cleaned.
- **Risk.** **High** — this is the most likely cause of program failure (see §11, RK-1).
- **Fix.** A CI check requiring every PR to carry a `recovery` or `docs` label; PRs labelled `feature` fail until the program closes. Announced in `CONTRIBUTING.md`.
- **Effort.** 0.5 ed. **Priority.** P1 — implement in week 1.
- **Acceptance criteria.** A `feature`-labelled PR fails CI; `CONTRIBUTING.md` documents the freeze and its end condition.

### R-059 — Beta feedback and disclosure channels
- **Problem.** `SECURITY.md` exists but its disclosure channel and response SLA are unverified. There is no beta feedback route.
- **Root cause.** Files added for completeness rather than as operational commitments.
- **Impact.** Publishing a self-hosted service that was unauthenticated by default will attract security reports; an unmanned channel is worse than a stated absence.
- **Risk.** Medium.
- **Fix.** Verify or establish the disclosure channel and state a response SLA that will actually be met. Add a beta feedback issue template. Explicitly state which findings are already known and in the roadmap (link the EDR) so researchers do not spend time on documented issues.
- **Effort.** 0.5 ed. **Priority.** P1.
- **Acceptance criteria.** `SECURITY.md` states a working channel and an SLA the maintainers accept; the EDR is linked as known-issues.

### R-060 — Post-beta debt register
- **Problem.** Items consciously descoped need a home, or they will be forgotten and rediscovered as regressions.
- **Fix.** `docs/POST-BETA-DEBT.md` carrying: full WCAG conformance audit (R-045), canvas graph renderer (R-044), `architecture_service` summary consolidation (R-011 residual), multi-instance support (R-057), inheritance edges if descoped (R-033), `ria/` migration decision, language breadth beyond Python/JS/TS, and the Learning Workspace rebuild with user identity (R-003).
- **Effort.** 0.5 ed. **Priority.** P2.
- **Acceptance criteria.** Register exists; every descoped item in this document appears in it with the reason it was descoped.

---

## 5. Mechanical items

Compact format as declared in the conventions. Each is independently verifiable and low-judgement.

| ID | Item | Phase | Effort | Priority | Acceptance criterion |
|---|---|---|---:|---|---|
| M-01 | Delete 44 redundant `activationEvents` | 8 | 0.1 | P2 | Zero manifest diagnostics |
| M-02 | Delete `console.log` DIAG block, `extension.ts:39-45` | 8 | 0.1 | P2 | No `console.log` in `src/` |
| M-03 | Move `module-alias` to `devDependencies` | 8 | 0.1 | P1 | `dependencies` free of test tooling |
| M-04 | Add `out/test/**` to `.vscodeignore` | 8 | 0.1 | P1 | `vsce ls` shows no test paths |
| M-05 | Add extension `icon`, reorder `categories` | 8 | 0.2 | P2 | Marketplace tile renders |
| M-06 | Align extension version to `0.9.0` | 10 | 0.1 | P2 | Versions match across manifests |
| M-07 | Declare `untrustedWorkspaces` capability | 8 | 0.1 | P2 | Declared with a reason |
| M-08 | Replace 5-level Demeter chain, `chat.py:387` | 2 | 0.1 | P2 | `is_indexed()` method used |
| M-09 | Replace `cmd /c rmdir` with `shutil.rmtree`, fail on error | 3 | 0.2 | P2 | Cross-platform; failure aborts analysis |
| M-10 | Move `test_*.md` files to `docs/manual-test-plans/` | 4 | 0.1 | P2 | `tests/` contains only Python tests |
| M-11 | Align Python version across pyproject/CI/Docker | 4 | 0.2 | P1 | One version, or a tested matrix |
| M-12 | Configure ruff ruleset (E,F,I,B,C4,SIM,UP,S) | 4 | 0.3 | P1 | Configured and gating |
| M-13 | Remove dev origins from production CORS list | 3 | 0.1 | P2 | Production origins only |
| M-14 | Uniform error envelope, no `str(exception)` in 5xx | 3 | 0.5 | P1 | Test asserts no exception text in bodies |
| M-15 | Delete `backend/main.py` (duplicate ASGI app) | 2 | 0.1 | P2 | Exactly one app object in repo |
| M-16 | Delete 6 remaining dead modules (E2) | 2 | 0.3 | P2 | Suite green; dead-code check in CI |
| M-17 | Add `vulture`/ruff dead-code detection to CI | 2 | 0.2 | P2 | Gates the build |
| M-18 | Add file-size CI gate (warn 500, fail 800 LOC) | 4 | 0.2 | P2 | Enforced |
| M-19 | Add `pip-audit` to CI | 3 | 0.1 | P1 | Gates on high severity |
| M-20 | Add `npm audit --audit-level=high` to CI | 3 | 0.1 | P1 | Gates |
| M-21 | Non-root `USER` + `HEALTHCHECK` in Dockerfile | 3 | 0.3 | P1 | Container runs as non-root, reports healthy |
| M-22 | Re-run tests in `release.yml` before publish | 3 | 0.2 | P1 | Release fails on red tests |
| M-23 | Image scan + SBOM + provenance in release | 3 | 0.4 | P1 | Artifacts produced; high CVEs block |
| M-24 | Pin all Python and npm dependencies | 3 | 0.4 | P1 | No open ranges; lockfile is CI source |
| M-25 | Add `GIT_TERMINAL_PROMPT=0` to git subprocess env | 3 | 0.1 | P0 | Set at every call site |
| M-26 | Delete `AUDIT_REPORT.md` (superseded) | 9 | 0.1 | P2 | Removed; EDR linked instead |
| M-27 | Set `length_bound` on all `simple_cycles` calls | 5 | 0.2 | P2 | No unbounded call remains |

**Mechanical subtotal: 5.2 ed.**

---

## 6. Effort reconciliation and release tracks

### 6.1 Correction to my own estimate

The per-item efforts in §4 sum to **116.5 ed** for the 31 substantive items plus **5.2 ed** of mechanical work — **≈122 ed**, not the 70–74 ed stated in §1.4. That estimate was produced before the items were costed individually and it was wrong by ~60%. Recording the correction rather than quietly reconciling it, because a recovery program premised on honesty cannot open with an unexamined number.

**Corrected full-recovery cost: ≈122 ed — 24 weeks for one engineer, 13–14 weeks calendar for two.**

That is too long to hold a release. So the program is split into three tracks, and the beta ships on Track A.

### 6.2 Three tracks

| Track | Content | Effort | Calendar (2 eng) | Ships |
|---|---|---:|---|---|
| **A — Minimum Honest Beta** | All P0 · all security P0/P1 · CI green · honesty envelope end-to-end · docs truthful · release hygiene | **52 ed** | **7 weeks** | **v0.9.0-beta.1** |
| **B — Structural Recovery** | Dependency inversion, singleton lifecycle, graph source of truth, symbol identity + recall, extension consolidation, frontend query layer and tests | 51 ed | +6 weeks | v0.9.0-beta.2 / 0.9.x |
| **C — Quality Debt** | God-file splits, primitives, accessibility baseline, tracing, canvas renderer, prompt registry, command-registry port | 34 ed | +4 weeks | 0.9.x → 1.0.0 |

Rationale for the split: **Track A is defined by one question — "can any user-visible value in this product be traced to a computation on their repository?"** Everything required to answer yes is in Track A. Everything that makes the codebase pleasant to work in is not, and does not justify delaying the removal of fabrications.

### 6.3 Track A contents (the critical path to beta)

| ID | Item | ed |
|---|---|---:|
| R-016 | Fix CI-breaking `GitSettings` import, freeze `ria/` | 0.5 |
| R-058 | Feature freeze CI gate | 0.5 |
| R-001 | Delete `backend/copilot/` | 1.0 |
| R-002 | Delete 3 fabricating VS Code views | 0.5 |
| R-003 | Remove Learning Workspace surface | 1.0 |
| R-004 | Remove 3 `type(None)` capabilities | 0.5 |
| R-005 | Deterministic citation verifier | 3.0 |
| R-006 | Fabrication sweep + AI Integrity Report + CI guard | 2.0 |
| R-009 | Single API prefix (prerequisite for correct auth) | 1.5 |
| R-014 | Remove `pickle` | 4.0 |
| R-015 | Deny-by-default auth + route matrix test | 2.0 |
| R-017 | Close unauthenticated LLM endpoint | 0.5 |
| R-018 | Subprocess timeouts | 0.5 |
| R-019 | PAT out of argv | 1.0 |
| R-020 | Prompt-injection mitigation | 2.0 |
| R-021 | Supply chain + container hardening | 1.5 |
| R-022 | Input/output/resource validation | 2.0 |
| R-023 | Distributed rate limiting | 1.0 |
| R-025 | Explicit degradation instead of swallowed exceptions | 4.0 |
| R-026 | mypy + coverage + ruff gates | 2.0 |
| R-028 | Delete fabrication-pinning tests; add 6 suites | 2.0 |
| R-031 | Coverage/provenance/confidence envelope | 3.0 |
| R-035 | Honest context assembly (tokenizer, no mid-chunk trim) | 2.0 |
| R-042 | Surface degradation in the UI | 2.0 |
| R-052 | Honest capability matrix | 1.0 |
| R-053 | Resolve doc duplication and supersession | 1.5 |
| R-054 | Generate API reference | 1.0 |
| R-055 | Contributor infrastructure | 1.5 |
| R-056 | Release scope enforcement, tag 0.9.0-beta.1 | 1.0 |
| R-057 | Supported-topology statement | 1.0 |
| R-059 | Disclosure + feedback channels | 0.5 |
| M-11,12,14,19–25 | Mechanical P0/P1 | 2.6 |
| **Total** | | **≈52 ed** |

Recounted honestly: **52 ed, not 37** — 6–7 weeks calendar for two engineers. R-025 (4 ed) and R-031 (3 ed) could be argued out of the beta, but they are the mechanism by which honest code produces honest output, so removing them would defeat the program's purpose. They stay.

**Track A: 52 ed · 6–7 weeks with two engineers · 11 weeks with one.**

---

## 7. GitHub Milestones

| Milestone | Title | Track | Exit gate | Target |
|---|---|---|---|---|
| **M0** | Unblock: green CI + feature freeze | A | `pytest tests/` exits 0; feature PRs blocked | Day 2 |
| **M1** | AI Integrity | A | No user-visible value originates from a literal | Week 1 |
| **M2** | Architecture Consolidation | A (partial) / B | One API prefix; import cycle gone; dead code removed | Week 3 / Week 8 |
| **M3** | Security Recovery | A | All P0/P1 security items closed; route matrix green | Week 3 |
| **M4** | Reliability Recovery | A | Six CI gates green; degradation explicit | Week 4 |
| **M5** | Knowledge Graph Recovery | A (envelope) / B (store) | Envelope shipped; recall published | Week 4 / Week 10 |
| **M6** | Copilot Recovery | A (delete) / C (port) | One assistant | Week 1 / Week 14 |
| **M7** | Frontend Recovery | A (degradation UI + tests) / B / C | Degradation surfaced; tooling in CI | Week 5 / Week 12 |
| **M8** | VS Code Recovery | A (security) / B (consolidation) | CSP everywhere; no test scaffolding shipped | Week 5 / Week 11 |
| **M9** | Documentation Recovery | A | Every claim verifiable in under 5 minutes | Week 6 |
| **M10** | **Release v0.9.0-beta.1** | A | §11 acceptance criteria pass in full | Week 7 |
| **M11** | Post-beta: Structural | B | — | Week 13 |
| **M12** | Post-beta: Quality Debt | C | — | Week 17 |

---

## 8. GitHub Issues

Ready to import. `Deps` are blocking issues. `T` is track.

### Milestone M0 — Unblock
| ID | Title | T | ed | Pri | Deps |
|---|---|---|---:|---|---|
| R-016 | fix: repair `GitSettings` import so `pytest tests/` collects; freeze `ria/` via ADR | A | 0.5 | P0 | — |
| R-058 | ci: block `feature`-labelled PRs for program duration | A | 0.5 | P1 | — |

### Milestone M1 — AI Integrity
| ID | Title | T | ed | Pri | Deps |
|---|---|---|---:|---|---|
| R-001 | remove: delete `backend/copilot/` package, router mounts, frontend workstation, 2 test files | A | 1.0 | P0 | R-016 |
| R-002 | remove: delete `KnowledgeGraphView`, `LearningView`, `ArchitectureView` | A | 0.5 | P0 | — |
| R-003 | remove: unmount Learning Workspace; retain `services/reading_path` with README | A | 1.0 | P0 | R-016 |
| R-004 | remove: delete 3 `type(None)` registrations, 2 stub routers, 2 VS Code commands | A | 0.5 | P0 | — |
| R-005 | feat: deterministic citation verifier; `citations_valid` defaults False | A | 3.0 | P0 | R-016 |
| R-006 | chore: fabrication sweep; publish `AI-INTEGRITY-REPORT.md`; add CI guard | A | 2.0 | P0 | R-001..R-004 |

### Milestone M2 — Architecture Consolidation
| ID | Title | T | ed | Pri | Deps |
|---|---|---|---:|---|---|
| R-009 | refactor: mount routers once at `/api/v1`; update both clients | A | 1.5 | P1 | R-001, R-003, R-004 |
| R-007 | refactor: invert `services → backend`; constructor injection; port architecture test | B | 4.0 | P1 | R-009 |
| R-008 | refactor: move singleton construction into `lifespan`/`app.state`/`Depends` | B | 4.0 | P1 | R-007 |
| R-010 | remove: delete 7 dead modules incl. duplicate ASGI entry point | B | 1.0 | P2 | — |
| R-011 | refactor: inventory + ADR for consolidating 7 graph implementations | B | 2.0 | P1 | R-029 |
| R-012 | refactor: split 4 backend god files to ≤500 LOC | C | 4.0 | P2 | R-007 |
| R-013 | investigate: determine persistence semantics of `progress_tracker.py`; delete or retain | B | 0.5 | P2 | R-003 |
| M-08, M-15, M-16, M-17, M-18 | mechanical (Demeter chain, dead code, CI gates) | B | 0.9 | P2 | — |

### Milestone M3 — Security Recovery
| ID | Title | T | ed | Pri | Deps |
|---|---|---|---:|---|---|
| R-018 | fix: add `timeout=` and `GIT_TERMINAL_PROMPT=0` to every subprocess call | A | 0.5 | P0 | — |
| R-015 | feat: deny-by-default auth; fail closed in production; per-key repo scoping; route matrix test | A | 2.0 | P0 | R-009 |
| R-017 | fix: close unauthenticated `graph_rag` chat route; replace Demeter guard | A | 0.5 | P0 | R-015 |
| R-014 | refactor: replace `pickle` persistence with versioned format; ignore-and-rebuild migration | A | 4.0 | P0 | R-016 |
| R-019 | fix: remove PAT from git argv; scrub remote URL post-clone | A | 1.0 | P1 | — |
| R-020 | feat: prompt-injection mitigation; malicious-README fixture | A | 2.0 | P1 | R-035 |
| R-021 | ci: pin dependencies; pip-audit; npm audit; non-root container; image scan; SBOM | A | 1.5 | P1 | — |
| R-022 | feat: bounded request models; repo size cap; clone eviction; error envelope | A | 2.0 | P1 | — |
| R-023 | refactor: rate limiting in shared storage; remove loopback bypass | A | 1.0 | P1 | R-015 |
| M-09, M-13, M-14, M-19–25 | mechanical (security/supply chain) | A | 2.1 | P0/P1 | — |

### Milestone M4 — Reliability Recovery
| ID | Title | T | ed | Pri | Deps |
|---|---|---|---:|---|---|
| R-026 | ci: add mypy (ratcheted), coverage floor, configured ruff; align Python version | A | 2.0 | P1 | R-016 |
| R-028 | test: delete fabrication-pinning tests; add 6 missing suites | A | 2.0 | P1 | R-001, R-003 |
| R-025 | refactor: replace exception swallowing with explicit degradation | A | 4.0 | P1 | R-026 |
| R-024 | feat: split `/health/live` and `/health/ready`; SIGTERM draining | B | 2.0 | P1 | R-008 |
| R-027 | feat: correctness metrics, cost accounting, OpenTelemetry spans, per-key budget | C | 2.0 | P2 | R-025 |
| M-10, M-11, M-12, M-18 | mechanical (test hygiene, tooling config) | A | 0.8 | P1/P2 | — |

### Milestone M5 — Knowledge Graph Recovery
| ID | Title | T | ed | Pri | Deps |
|---|---|---|---:|---|---|
| R-031 | feat: coverage/provenance/confidence envelope; providers report status; surface truncation | A | 3.0 | P1 | R-025 |
| R-029 | refactor: persist the graph; make it the real source of truth (option a) | B | 6.0 | P1 | R-014 |
| R-030 | fix: single symbol identity; count dropped edges; publish measured recall | B | 4.0 | P1 | R-029 |
| R-033 | feat: extract `INHERITS`/`IMPLEMENTS` edges; include in blast radius | B | 3.0 | P1 | R-030 |
| R-032 | perf: bounded neighbourhood reads; build-time centrality; bounded cycle detection | C | 3.0 | P2 | R-029 |
| M-27 | mechanical (`length_bound` on `simple_cycles`) | A | 0.2 | P2 | — |

### Milestone M6 — Copilot Recovery
| ID | Title | T | ed | Pri | Deps |
|---|---|---|---:|---|---|
| R-035 | fix: real tokenizer; per-model budget; never trim mid-chunk; report dropped chunks | A | 2.0 | P1 | R-001 |
| R-034 | feat: port slash-command routing and tool schema registry onto `services/chat` | C | 3.0 | P2 | R-005, R-031 |
| R-036 | refactor: prompt registry with versioned provenance | C | 1.0 | P2 | R-035 |

### Milestone M7 — Frontend Recovery
| ID | Title | T | ed | Pri | Deps |
|---|---|---|---:|---|---|
| R-037 | ci: add Vitest, Playwright, ESLint + jsx-a11y; ≥30 component tests | A | 2.0 | P1 | R-009 |
| R-042 | feat: surface coverage/degradation/truncation in every view | A | 2.0 | P1 | R-031, R-041 |
| R-039 | refactor: introduce TanStack Query; remove all direct `fetch` | B | 3.0 | P1 | R-037 |
| R-041 | refactor: extract ~12 UI primitives | B | 2.0 | P2 | R-037 |
| R-043 | ci: generate typed API client from OpenAPI with drift check | B | 1.0 | P2 | R-009 |
| R-038 | refactor: split god components to ≤300 LOC | C | 5.0 | P2 | R-039 |
| R-045 | feat: accessibility baseline (keyboard, focus, reduced-motion, table fallbacks, axe) | C | 3.0 | P2 | R-041 |
| R-044 | perf: dagre layout in a Web Worker | C | 1.0 | P3 | R-038 |

### Milestone M8 — VS Code Recovery
| ID | Title | T | ed | Pri | Deps |
|---|---|---|---:|---|---|
| R-046 | fix: remove `module-alias` and test-mock aliasing from the shipped package | A | 0.5 | P1 | — |
| R-049 | fix: CSP + nonce on every webview incl. `WebviewHost`; migrate to `@vscode/test-electron` | A | 2.0 | P1 | R-002 |
| R-047 | build: bundle with esbuild | A | 1.0 | P1 | R-046 |
| R-048 | refactor: serve the frontend build in webviews; delete ~2,000 lines of embedded HTML | B | 4.0 | P1 | R-042, R-047 |
| R-050 | chore: manifest hygiene, walkthrough, icon, trust declaration, version alignment | B | 0.5 | P2 | — |
| R-051 | refactor: split `commands.ts` and `api.ts` | C | 2.0 | P3 | R-048 |
| M-01–M-07 | mechanical (manifest, logging, packaging) | A/B | 0.8 | P1/P2 | — |

### Milestone M9 — Documentation Recovery
| ID | Title | T | ed | Pri | Deps |
|---|---|---|---:|---|---|
| R-052 | docs: honest capability matrix with measured numbers and stated limits | A | 1.0 | P0 | all of M1–M8 Track A |
| R-053 | docs: one canonical doc per topic; relocate `foundation/`; rewrite `ARCHITECTURE.md` | A | 1.5 | P1 | R-052 |
| R-054 | ci: generate API reference from OpenAPI; delete the 1,737-line hand-written file | A | 1.0 | P1 | R-009 |
| R-055 | docs: CODE_OF_CONDUCT, issue/PR templates, 5 ADRs, architecture diagram | A | 1.5 | P1 | R-053 |
| M-26 | mechanical (delete superseded `AUDIT_REPORT.md`) | A | 0.1 | P2 | R-053 |

### Milestone M10 — Release
| ID | Title | T | ed | Pri | Deps |
|---|---|---|---:|---|---|
| R-057 | docs: declare supported topology; warn on `--workers > 1`; backup/restore procedure | A | 1.0 | P1 | R-024 |
| R-059 | docs: verify disclosure channel and SLA; beta feedback template; link EDR as known issues | A | 0.5 | P1 | R-055 |
| R-056 | release: tag `v0.9.0-beta.1`; CHANGELOG of removals; deprecate `v1.0.0` artifacts | A | 1.0 | P0 | everything Track A |
| R-060 | docs: post-beta debt register | A | 0.5 | P2 | R-056 |

---

## 9. Task Dependencies

### 9.1 Critical path to v0.9.0-beta.1

```
R-016 (CI green)
  └─► R-001 ─┬─► R-006 (integrity sweep) ──────────────────────┐
     R-002 ──┤                                                 │
     R-003 ──┤                                                 │
     R-004 ──┘                                                 │
              └─► R-009 (single prefix) ─► R-015 (auth) ─► R-017│
                                    └─► R-054 (API ref)         │
  └─► R-014 (pickle) ─► R-029 (graph SoT) [Track B]             │
  └─► R-026 (gates) ─► R-025 (degradation) ─► R-031 (envelope) ─┼─► R-042 (UI) ─┐
  └─► R-005 (citations) ────────────────────────────────────────┤               │
  └─► R-035 (context) ─► R-020 (injection) ────────────────────┘               │
                                                                                ▼
                                                        R-052 (capability matrix)
                                                                 │
                                                        R-053 ─► R-055 ─► R-059
                                                                 │
                                                        R-056 (tag 0.9.0-beta.1)
```

**Longest chain:** `R-016 → R-026 → R-025 → R-031 → R-042 → R-052 → R-053 → R-055 → R-056` = 0.5 + 2 + 4 + 3 + 2 + 1 + 1.5 + 1.5 + 1 = **16.5 ed of strictly serial work.** With two engineers the wall-clock floor is therefore ~4 weeks even with perfect parallelism; 6–7 weeks is the realistic figure with review and integration overhead.

### 9.2 Hard ordering constraints (violating these wastes work)

| Constraint | Reason |
|---|---|
| R-016 before everything | Nothing is measurable while CI cannot collect |
| R-001..R-004 before R-006 | The sweep must run against the post-deletion codebase |
| R-001, R-003 before R-028 | Do not repair tests that are about to be deleted |
| R-009 before R-015 | Auth correctness is unverifiable across three prefixes; the prefix sprawl *caused* R-017 |
| R-014 before R-029 | The new graph store is the replacement target for pickle |
| R-025 before R-031 | The envelope needs a degradation mechanism to report |
| R-031 before R-042 | The UI cannot surface fields that do not exist |
| R-035 before R-020 | Escaping untrusted content is pointless if chunk trimming then breaks the delimiters |
| R-029 before R-030, R-032 | Identity and bounded reads both depend on the store's shape |
| R-030 before R-033 | Inheritance edges need the fixed identity scheme |
| R-007 before R-008 | Cannot move construction while services reach for globals |
| R-037 before R-039, R-041 | Refactors without tests are unverifiable |
| R-042, R-047 before R-048 | Share the frontend only after it carries the degradation UI |
| **All of M1–M8 Track A before R-052** | The capability matrix documents reality; writing it earlier documents fiction |
| R-052 before R-053, R-055 | The matrix determines what the other documents must say |
| Everything before R-056 | Release gate |

### 9.3 Parallelisable streams (2 engineers)

| Stream | Engineer A | Engineer B |
|---|---|---|
| Week 1 | R-016, R-058, R-001, R-002, R-003, R-004 | R-018, M-25, R-019, R-021, M-19–24 |
| Week 2 | R-006, R-009 | R-014 |
| Week 3 | R-015, R-017, R-023 | R-014 (cont.), R-022 |
| Week 4 | R-026, R-028 | R-005, R-035 |
| Week 5 | R-025 | R-020, R-046, R-047, R-049 |
| Week 6 | R-031 | R-037, R-042 |
| Week 7 | R-052, R-053 | R-054, R-055, R-057, R-059 |
| Week 7 (end) | **R-056 — tag `v0.9.0-beta.1`** | |

---

## 10. Estimated Timeline

### 10.1 Track A — to beta

| Week | Focus | Milestone closed |
|---|---|---|
| 1 | Green CI, feature freeze, delete all fabrications, subprocess timeouts, supply chain | M0, M1 |
| 2 | Single API prefix; begin pickle replacement | — |
| 3 | Deny-by-default auth + route matrix; finish pickle; input/resource validation; rate limiting | M2 (partial), M3 |
| 4 | CI gates (mypy/coverage/ruff); test cleanup; citation verifier; context assembly | M4 (partial), M6 (partial) |
| 5 | Explicit degradation; injection mitigation; extension security and bundling | M4, M8 (partial) |
| 6 | Coverage envelope; frontend tooling; degradation surfaced in UI | M5 (partial), M7 (partial) |
| 7 | Documentation recovery; release hygiene; **tag `v0.9.0-beta.1`** | M9, M10 |

**Track A: 7 weeks, 2 engineers, 52 ed.**

### 10.2 Tracks B and C — post-beta

| Weeks | Track | Content | Milestone |
|---|---|---|---|
| 8–13 | B | Dependency inversion, singleton lifecycle, graph source of truth, symbol identity + published recall, inheritance edges, extension UI consolidation, frontend query layer, health/readiness split | M11 |
| 14–17 | C | God-file splits, UI primitives, accessibility baseline, tracing and cost accounting, command-registry port, prompt registry, canvas renderer | M12 |

**Full program: 17 weeks, 2 engineers, ≈122 ed → `v1.0.0` candidate at week 17.**

### 10.3 Single-engineer variant

Track A becomes 11 weeks; the full program 24 weeks. The critical-path serial floor (16.5 ed) means a second engineer buys roughly 40% calendar reduction, not 50%. A third engineer adds coordination cost against a mostly serial honesty chain and is not recommended before Track B, where the streams genuinely diverge.

---

## 11. Risk Assessment

| ID | Risk | Likelihood | Impact | Mitigation | Owner |
|---|---|---|---|---|---|
| **RK-1** | **Scope leakage** — feature work resumes mid-program and recovery stalls | **High** | **High** | R-058 CI gate in week 1; program has a named owner with authority to reject; weekly milestone burn-down published | Principal Eng |
| **RK-2** | **Deletion resistance** — reluctance to remove ~1,500 LOC of Copilot and Learning work | **High** | **High** | Frame as capability deferral, not loss: `services/reading_path/*` and the skill/tool abstractions are preserved in code and ADRs. Decide once, in writing, at the §1.5 gate | Principal Eng |
| **RK-3** | **Hidden fabrication survives R-006** — the sweep misses a site and the problem recurs post-launch | Medium | **High** | Grep-based sweep plus a permanent CI guard test; second reviewer signs the AI Integrity Report; measured-value provenance required for every numeric response field | Reviewer |
| **RK-4** | **Measured recall is embarrassing** — R-030 reveals call-graph recall well below expectations | **Medium-High** | Medium | This is a success, not a failure. Publish the number; the capability matrix states it. A stated 78% is more valuable than an implied 100%. Do not delay the beta for a better number | Principal Eng |
| **RK-5** | **Auth inversion breaks clients** — deny-by-default plus single prefix breaks frontend and extension simultaneously | Medium | Medium | R-009 and R-015 land with client updates in the same PR; the route matrix test covers both clients' actual call sites; E2E path from R-037 gates the merge |Eng A |
| **RK-6** | **Pickle migration loses cached analysis** | Medium | Low | Ignore-and-rebuild is the designed behaviour; rebuild cost is bounded and acceptable for a beta. Document it in CHANGELOG |Eng B |
| **RK-7** | **Graph source-of-truth work overruns** (R-029, 6 ed, is the largest single item) | Medium | Medium | It is Track B, not Track A. The beta ships with the envelope (R-031) and the honest documentation that the KG is a derived read model. Option (b) in R-029 remains the fallback |Eng B |
| **RK-8** | **Extension frontend-sharing proves costly** (R-048) | Medium | Low | Explicit fallback stated in R-048: reduce to two webviews rather than maintain eight |Eng B |
| **RK-9** | **Estimate is wrong again** — this document already corrected itself by 60% | **Medium** | Medium | Re-estimate at each milestone close; treat week-3 actuals as the calibration point; publish variance rather than absorbing it |Principal Eng |
| **RK-10** | **`ria/` drifts further while frozen** | Medium | Low | It stays in CI, so it cannot break silently. ADR 0003 states the freeze. No feature work permitted |Principal Eng |
| **RK-11** | **Security researcher finds an issue during the beta** | **High** | Medium | Expected and planned for: R-059 links the EDR as known issues so effort is not spent on documented problems; disclosure SLA stated honestly |Principal Eng |
| **RK-12** | **Accessibility descope criticised** | Medium | Low | R-045 states the position explicitly rather than implying conformance; full audit is in the post-beta register | Principal Eng |
| **RK-13** | **Single maintainer burnout** across a 7–17 week program with no feature gratification | **High** | **High** | Track A is deliberately front-loaded with deletion, which is fast and visible; ship `beta.1` at week 7 to bank a result before Track B begins | Principal Eng |

**Highest-probability failure mode is RK-1 + RK-13 in combination:** the program stalls at week 3–4 because deletion feels like regression and no release has landed. The mitigation is structural — Track A exists specifically so a release lands at week 7.

---

## 12. Acceptance Criteria (v0.9.0-beta.1 release gate)

All must pass. No exceptions, no partial credit.

### 12.1 Integrity
- [ ] `grep -ri "copilot" backend/ services/ frontend/src/ vscode-extension/src/ tests/` returns matches only in `docs/` and ADRs.
- [ ] No response field named `confidence`, `score`, `*_ms`, `*_index`, or `mastery_*` returns a value not computed from the analysed repository. Enforced by CI guard test.
- [ ] `docs/AI-INTEGRITY-REPORT.md` merged, enumerating every candidate site with a disposition, signed off by a second reviewer.
- [ ] No webview or component template contains a numeric literal presented as repository data.
- [ ] Every AI answer carries citations verified against the symbol index and filesystem; unresolved citations are marked and `citations_valid` is `False`.
- [ ] Injecting an answer that cites `nonexistent/file.py:1-5` produces an unresolved-citation report.

### 12.2 CI and quality
- [ ] `pytest tests/` exits 0 and collects ≥1,100 tests.
- [ ] Six CI gates green: ruff (configured ruleset) · mypy (ratcheted) · coverage (floor) · pytest · pip-audit · npm audit.
- [ ] `docs/QUALITY-BASELINE.md` records measured coverage, mypy error count and Python version.
- [ ] No test asserts on a hardcoded analysis value.
- [ ] Frontend: ESLint zero errors; ≥30 component tests; 1 E2E path passing.
- [ ] Extension: `@vscode/test-electron` covers activation, all tree views and command registration.
- [ ] Python version consistent across `pyproject.toml`, CI and Dockerfile.

### 12.3 Security
- [ ] Route × credential matrix test covers every route and passes.
- [ ] App refuses to start when `APP_ENV=production` and no API key is configured.
- [ ] `grep -rn "pickle" services/ backend/ core/ storage/` returns zero results.
- [ ] AST test asserts `timeout=` on every `subprocess.run` call site.
- [ ] No git invocation places the PAT in argv; cloned fixture `.git/config` contains no credentials.
- [ ] Malicious-README fixture does not alter response structure.
- [ ] All dependencies pinned; lockfile is the CI install source.
- [ ] Container runs as non-root with a working `HEALTHCHECK`.
- [ ] Release workflow re-runs tests, scans the image, emits an SBOM, and fails on high-severity CVEs.
- [ ] Rate limit holds across two worker processes; loopback bypass removed.
- [ ] No 5xx response body contains an exception string.
- [ ] Every webview HTML template contains a nonce-based CSP, asserted by test.
- [ ] Shipped VSIX contains no test paths and no `module-alias` runtime dependency.

### 12.4 Honesty of output
- [ ] Every intelligence response carries `coverage`, `provenance` and `commit_sha`.
- [ ] A deliberately broken provider yields `DEGRADED`; the AI layer declines rather than answering.
- [ ] A failed computation reports `null` plus a populated `errors` array — never `0`.
- [ ] Truncated graph responses declare `truncated`, `shown` and `total`, and the UI displays them.
- [ ] Every assembled prompt has balanced code fences (property test).
- [ ] Token counts come from the provider tokenizer, not a character heuristic.

### 12.5 Architecture
- [ ] `grep -rn "from backend" services/ core/ agents/ memory/ models/ storage/` returns zero results **(Track B — for beta, this criterion is deferred and the deferral is recorded in the post-beta register)**.
- [ ] Every route path begins with `/api/v1`, `/health` or `/metrics`.
- [ ] Exactly one ASGI application object exists in the repository.
- [ ] `analysis_registry` contains no `type(None)` builder.
- [ ] No VS Code command resolves to a 404 route.

### 12.6 Documentation
- [ ] Every capability in the README matrix maps to a passing test and a live route, verifiable by a reviewer in under five minutes.
- [ ] Exactly one canonical document per topic; `docs/README.md` indexes all.
- [ ] No document claims to supersede a published document that still exists.
- [ ] API reference generated from OpenAPI with a CI drift check.
- [ ] Five ADRs merged; architecture diagram matches the post-recovery module structure.
- [ ] `SECURITY.md` states a working disclosure channel and an SLA the maintainers accept.
- [ ] Supported topology declared; app warns on `--workers > 1`; backup/restore procedure executed once successfully.
- [ ] `CHANGELOG.md` documents every removal and its reason.
- [ ] `docs/POST-BETA-DEBT.md` lists every descoped item with its reason.

---

## 13. Definition of Done

### 13.1 Per issue
An issue is Done when: code merged to `main` via review; its stated acceptance criteria demonstrably pass; a test guards the fixed behaviour against regression (or the issue documents why no automated guard is possible); no new ruff/mypy/coverage regression; documentation touched by the change updated in the same PR; and the issue links the commit that closes it.

### 13.2 Per phase
A phase is Done when every Track-A issue in its milestone is Done, its exit gate in §7 passes, its ADR (where specified) is merged, and CI is green on `main`.

### 13.3 Program Done — v0.9.0-beta.1
The program is Done when all §12 criteria pass and:

1. **Zero fabricated outputs.** Every number a user sees was computed from that user's repository. Verified by the CI guard, the integrity report, and a manual spot-check of six responses by a second reviewer.
2. **Every AI response is evidence-backed.** Citations resolve deterministically; unresolved citations are reported, not hidden.
3. **CI is green** on six gates, and the suite collects.
4. **Security P0/P1 closed.** Deny-by-default auth, no pickle, no unauthenticated LLM route, timeouts everywhere, pinned dependencies, non-root container.
5. **One architecture ships.** One ASGI app, one API prefix, one assistant, `ria/` frozen and green.
6. **Source of truth is documented accurately** — as a derived read model for beta, with the persistence work scheduled in Track B and stated as such.
7. **Documentation matches implementation.** Six capabilities claimed, six capabilities working, twelve capabilities explicitly listed as removed or deferred with reasons.
8. **`v0.9.0-beta.1` is tagged** from green `main`, the prior `v1.0.0` artifact carries a deprecation notice, and the release notes lead with what was removed.

### 13.4 The single test of success

A senior engineer clones the repository, runs the documented setup, analyses a repository they know well, and finds **no claim they can disprove**. Where the platform does not know something, it says so. That is the whole objective, and it is the only criterion that cannot be gamed by the others.
