# 📊 Validation & Telemetry Report

This report presents performance metrics, validation benchmarks, and pipeline latency figures collected during testing of the **ARIA** MVP and Phase 2 releases.

---

## 📈 Codebase Ingestion & Parsing Telemetry

Ingestion throughput, AST parsing, and vector generation were evaluated against the **Ankita15k/GitNest** repository (a full-stack collaborative Git hosting system).

| Metric | Measured Value | Operational Context |
| :--- | :--- | :--- |
| **Total Source Files walked** | 328 files | Excludes `node_modules`, `.venv`, `.git`, configurations, and binaries |
| **Total Chunks generated** | 1,549 chunks | Produced by `CodeChunker` (1500 chars / 200 overlap) |
| **Embedding Generation** | 1,549 vectors | 384-dimensional dense vectors using local `bge-small-en-v1.5` |
| **ChromaDB Write Latency** | ~28 seconds | Persistence write rate to local SSD storage |
| **Tree-sitter AST parse** | ~1.4 seconds | Structural analysis of Python, JavaScript, and TypeScript files |
| **Dependency Graph size** | 1,440 edges | Directed dependency linkages calculated by `GraphService` |
| **Framework Entry Points** | 17 entry points | Resolved using structural heuristics (excludes test and doc dirs) |

---

## 🧪 PR Intelligence E2E Validation Pass

The Pull Request Intelligence and Drift pipelines were validated against the **VarshithReddy2006/Repo-Intelligence-Agent** repository:

### Scenario A: Empty PR Changes (PR #1)
- **Files changed:** 0
- **Symbols matched:** 0
- **Size Classification:** `XS` (Score: 0.0)
- **Blast Radius:** `LOW`
- **Result:** Successfully returned HTTP 200 empty analysis payloads without throwing serialization errors.

### Scenario B: Populated PR Changes (PR #2)
- **Files changed:** 24 files
- **Symbols matched:** 77 symbols (including added and modified functions/classes)
- **Size Classification:** `M`
- **Blast Radius:** `HIGH` (initially `MEDIUM` based on 11 affected files, promoted to `HIGH` due to propagation depth = 3)
- **Cycles Detected:** 0 new, 0 resolved.
- **Architectural Hotspots:** Highlighted modified files residing in core services (e.g. `services/pr_intelligence_service.py`) representing high-coupling points.

---

## 🎯 Issue Mapper Target Grounding

The **Issue Mapper** was tested against realistic repository issue logs to verify target file identification accuracy and ensure 0% path hallucinations.

| Test Case Issue | Grounded File Targets | Hallucination Detected | Correct Components Identified |
| :--- | :--- | :--- | :--- |
| **"Login fails when password contains @"** | `auth.test.js`, `authStore.js`, `security.test.js` | **None** | `Authentication`, `Frontend`, `Services` |
| **"Pagination broken on repository page"** | `repository.controller.js`, `pullRequest.controller.js`, `App.jsx` | **None** | `API Layer`, `Frontend`, `Services` |
| **"Branch protection approval count incorrect"** | `branchProtectionEvaluator.service.js`, `BranchProtectionRuleCard.jsx` | **None** | `Frontend`, `Services` |

---

## 🔍 API Performance Benchmarks

Response latencies were compiled across all active FastAPI endpoints binding to port **8001** (averages calculated over 50 mock sessions):

| Endpoint | Method | Average Latency | Primary Bottleneck |
| :--- | :--- | :--- | :--- |
| `/health` | GET | `< 3ms` | Minimal routing overhead |
| `/api/repos/examples` | GET | `< 2ms` | Minimal routing overhead |
| `/api/repos/recent` | GET | `< 2ms` | Disk read (deserialization of `analysis_store.json`) |
| `/api/index` | POST | `~ 2.5 minutes` | CPU-bound embedding generation (SentenceTransformers) |
| `/api/retrieve` | POST | `~ 150ms` | Network response time from NVIDIA NIM API |
| `/api/issues/map` | POST | `~ 4.8 seconds` | Sequential LLM completion calls (parse+rank, then plan) |
| `/api/architecture/build` | POST | `~ 1.8 seconds` | CPU-bound AST file parsing (Tree-sitter) |
| `/api/analysis/{owner}/{repo_name}` | GET | `< 5ms` | In-memory cache retrieval |
| `/api/reading-order` | POST | `~ 80ms` | CPU NetworkX topological sorting & centrality |
| `/api/impact-analysis` | POST | `~ 95ms` | BFS graph traversal and keyword component matching |
| `/api/architecture/{owner}/{repo_name}/graph` | GET | `~ 50ms` | Formatting graph nodes and edges to React Flow JSON |
| `/api/graph/.../full` | GET | `~ 45ms` | NetworkX node/edge conversion to React Flow format |
| `/api/graph/.../neighbors/...` | GET | `~ 12ms` | Edge filtering on directed graph |
| `/api/graph/.../trace/...` | GET | `~ 22ms` | BFS graph traversal walk up to specified depth |
| `/api/symbols/.../file/...` | GET | `~ 8ms` | Local symbol index lookup |
| `/api/symbols/.../definition/...`| GET | `~ 10ms` | Symbol table lookup |
| `/api/pr/analyze` | POST | `~ 1.5 seconds` | GitHub diff retrieval + Local symbol matching + BFS walk |
| `/api/architecture/drift` | POST | `~ 1.9 seconds` | GitHub file content retrieval + tree-sitter delta patching |
| `/api/dead-code/analyze` | POST | `~ 250ms` | BFS reachability sweep + centrality deductions scoring |

---

## ✅ Core Components Validation Checklist

| Feature Component | Implementation Status | Telemetry & Verification Method |
| :--- | :--- | :--- |
| **Repository Analysis** | ✅ **Complete** | SSE-stream progress index logging from `/api/analyze` |
| **Repository Chat** | ✅ **Complete** | Token-by-token SSE streaming evaluated by `EvaluationAgent` |
| **Issue Mapper** | ✅ **Complete** | Merged two-call model with caching via `f"{repo_name}:v2:{issue_hash}"` |
| **Architecture Graph** | ✅ **Complete** | Tree-sitter import mappings converted to React Flow visual nodes |
| **Reading Order** | ✅ **Complete** | Topological centrality timelines computed by `ReadingOrderService` |
| **Impact Analysis** | ✅ **Complete** | BFS graph sweep traversals (depth limit = 4) + Component Maps |
| **Repository Workspace** | ✅ **Complete** | Multi-tab UI dashboard caching states to prevent redundant re-analyzes |
| **Session Persistence** | ✅ **Complete** | LocalStorage state backup of active context + Startup JSON hydration |
| **Fallback Mode** | ✅ **Complete** | Local keyword + Chroma retrieved text parser on NIM rate limits |
| **Interactive Graph** | ✅ **Complete** | Neighbor highlights, node filters, BFS direction traces |
| **Symbol Indexer** | ✅ **Complete** | AST extraction, cross-file definition & reference lookup |
| **PR Intelligence** | ✅ **Complete** | PR size score, blast radius estimation with depth-promotion |
| **Architecture Drift** | ✅ **Complete** | Virtual delta-patched graph comparisons, cycles, coupling shifts |
| **Dead Code Sweep** | ✅ **Complete** | Reachability sweeps, cleanup deductions scoring, orphan tracking |

---

## Unit Test Coverage & Health

The backend test suite is composed of **535 unit and integration tests** verifying structural extraction, vector retrieval, caching logic, delta patching, cycle checks, dead code reachability, API surface classification, call graph traversal, git history mining, report generation, provider health checks, authentication hardening, incremental builds, and API route mapping.

- **Total Collected Tests:** 535 items
- **Overall Code Coverage:** ~85% across all core classes
- **Test Integrity:** Mock adapters isolate remote API network boundaries during testing, ensuring local test execution does not consume LLM API quota or require active GitHub PAT connections.
