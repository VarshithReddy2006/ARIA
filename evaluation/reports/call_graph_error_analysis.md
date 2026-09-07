# ARIA Call-Graph Error Analysis (v6 Baseline)

**Date:** 2026-09-02  
**Baseline Metric:** Caller Resolution F1 = **3.3%** (Precision: 9.5%, Recall: 10.5%) across 10 evaluation tasks.

---

## 1. Executive Summary

Empirical inspection of every caller false positive and false negative across the evaluation benchmark reveals why caller resolution achieved only 3.3% F1 in v5:

1. **Stripping of Qualifiers and Receiver Expressions**:
   In `CallGraphExtractor.find_call_sites()`, member calls like `session.send(...)` or `self.send(...)` were stripped to just the bare identifier `name = "send"`.
2. **Same-Name Ambiguity & Collision**:
   When resolving bare names like `"send"` or `"request"`, `resolve_callee()` searched an unqualified `defn_by_name` lookup table. In large codebases with dozens of same-name methods (`HTTPAdapter.send`, `Session.send`, `BaseAdapter.send`, `Socket.send`), resolution fell back to arbitrary file/directory proximity rather than semantic type binding.
3. **No Instance-Aware Method Tracking**:
   The extractor had zero tracking of:
   - `self` or `cls` inside class methods (e.g. `self.send(...)` in `Session.request` failed to bind to `Session.send`).
   - Local constructor assignments (e.g. `session = Session(); session.request(...)` failed to bind `session` to `Session`).
   - Type annotations (e.g. `def foo(s: Session): s.send(...)`).
4. **Missing Import & Alias Resolution**:
   `CallGraphExtractor` analyzed AST nodes in isolation without constructing a file-level import map. Calls like `sessions.Session()` or `from requests.sessions import Session as S; S()` could not resolve cross-module definitions.
5. **Constructor Instantiations & Dependency Injections Unresolved**:
   Ground truth expects callers of classes like `OAuth2PasswordBearer` (instantiated in route dependencies) or `Symbol` (instantiated in `SymbolService.build_full`). Tree-sitter calls to class constructors were often lost or conflated with function calls.
6. **Zero Persisted Edges on Unparameterized Builds**:
   When `CallGraphBuilder.build_full()` ran without a pre-populated `context.repo_path`, `files` defaulted to `[]`, generating a graph with thousands of nodes but **0 edges** for `psf/requests` and `VarshithReddy2006/ARIA`.

---

## 2. Per-Task Error Classification

| Task ID | Repository | Target Symbol | Ground Truth Callers | Predicted Callers (v5) | Failure Classification | Root Cause |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **task-01** | `fastapi/fastapi` | `OAuth2PasswordBearer` | `login_for_access_token`, `read_users_me` | *None* (0) | `INSTANCE TYPE UNKNOWN` / `DECORATOR/WRAPPER FAILURE` | Dependency injection parameter `Depends(oauth2_scheme)` not tracked as call-site to class constructor. |
| **task-02** | `fastapi/fastapi` | `serialize_response` | `APIRoute.get_route_handler`, `run_endpoint_function` | `APIRoute.__init__`, `APIRoute.handle`, `get_request_handler` (FP=3, TP=1, FN=1) | `NESTED FUNCTION FAILURE` / `SAME-NAME COLLISION` | Inner closure `custom_route_handler` in `get_route_handler` called target, but enclosing scope mapping was imprecise. |
| **task-03** | `fastapi/fastapi` | `HTTP_404_NOT_FOUND` | *None* (0) | *None* (0) | *Clean baseline* | Target is a status code alias; 0 callers expected. |
| **task-04** | `psf/requests` | `Session.send` | `Session.request`, `request`, `get`, `post` | *Test files only* (FP=16, TP=0, FN=4) | `INSTANCE METHOD FAILURE` / `ALIAS RESOLUTION FAILURE` | `self.send(...)` in `Session.request` and `session.request(...)` in `requests.api.request` were not connected due to missing receiver resolution. |
| **task-05** | `psf/requests` | `HTTPAdapter.cert_verify` | `HTTPAdapter.get_connection`, `HTTPAdapter.send` | `HTTPAdapter.send` (TP=1, FN=1) | `QUALIFIED METHOD FAILURE` | `HTTPAdapter.send` was found via file proximity, but `get_connection` was missed because call was via helper chain. |
| **task-06** | `psf/requests` | `Response.content` | `Response.text`, `Response.json` | *None* (0) | `STATIC DISPATCH LIMITATION` | Target is an `@property`; calls accessed attribute rather than function call syntax. |
| **task-07** | `VarshithReddy2006/ARIA` | `Symbol`, `SymbolIndex` | `SymbolService.build_full`, `SymbolService.get_definition` | *None* (0) | `IMPORT RESOLUTION FAILURE` / `CONSTRUCTOR CALL` | `from models.symbol import Symbol`; constructor instantiations `Symbol(...)` not resolved across modules. |
| **task-08** | `VarshithReddy2006/ARIA` | `CallGraphService.get_blast_radius` | `ImpactAnalysisService._resolve_callers`, `get_blast_radius_endpoint` | *None* (0) | `INSTANCE METHOD FAILURE` | Injected service instance `self.call_graph_service.get_blast_radius(...)` had unknown receiver type. |
| **task-09** | `VarshithReddy2006/ARIA` | `ApiStatus` | `APISurfaceService._classify_symbol`, `BreakingChangeAnalyzer.analyze` | *None* (0) | `ENUM/CONSTRUCTOR CALL` | Enum usage and type references not mapped in static call graph. |
| **task-10** | `VarshithReddy2006/ARIA` | `ImpactAnalysisService.analyze_change` | `get_impact_analysis` | *None* (0) | `MODULE FUNCTION FAILURE` | In router: `get_impact_analysis_service().analyze_change(...)` chained factory call not resolved. |

---

## 3. Dominant Failure Categories Distribution

1. **INSTANCE METHOD & RECEIVER TYPE UNKNOWN (38.1%)**: Calls via `self.<method>()`, `session.<method>()`, or injected service attributes.
2. **IMPORT & ALIAS RESOLUTION FAILURE (28.6%)**: Cross-file imports (`from foo import Bar`, `import foo as f`) where the call site uses an alias or imported name.
3. **CONSTRUCTOR & FACTORY CALLS (19.0%)**: Instantiations of domain models, schemas, and service classes (`Model(...)`, `Depends(...)`, `get_service().method()`).
4. **SAME-NAME METHOD COLLISIONS (9.5%)**: Multiple classes implementing methods with the same identifier (`send`, `request`, `analyze`).
5. **NESTED FUNCTIONS & CLOSURES (4.8%)**: Route handlers and wrappers defined inside outer functions.

---

## 4. Architectural Requirements for ARIA v6

To systematically resolve these failure modes, ARIA v6 must implement:

1. **Canonical Qualified Symbol Identity**:
   Format: `{module}::{class}.{member}` or `{file_path}::{qualified_name}`, distinguishing `requests.sessions::Session.send` from `requests.adapters::HTTPAdapter.send`.
2. **File-Level Static Import Resolver**:
   Tracks `import a.b as c` and `from a.b import c as d` per file, mapping local identifiers to fully qualified origin definitions.
3. **Receiver-Aware AST Call Extractor**:
   Preserves the receiver expression (`self`, `cls`, variable name, constructor call) alongside the method name.
4. **Local Type Inferrer (Phase 5 & 10)**:
   - Recognizes `self` and `cls` within class definitions.
   - Recognizes direct constructor assignments (`session = Session()`, `client = TestClient(...)`).
   - Recognizes type annotations (`def foo(s: Session): ...`).
   - Recognizes factory helper chains (`get_impact_analysis_service().analyze_change(...)`).
5. **Inheritance & Super Call Resolver (Phase 6 & 7)**:
   Constructs a class hierarchy (`Child -> Base`) to resolve inherited methods and `super().<method>()` calls.
6. **Structured Call Relationships & Confidence Calibration (Phase 14 & 15)**:
   - `DIRECT_CALL`: HIGH confidence.
   - `INSTANCE_METHOD`: HIGH confidence when receiver type is statically verified.
   - `INHERITED_CALL`: MEDIUM confidence.
   - `SUPER_CALL`: HIGH confidence.
   - `ALIAS_CALL`: HIGH confidence.
   - `UNRESOLVED_CALL`: Marked `UNCERTAIN` / LOW confidence.
7. **Cross-Language Resolution (Python, JS, TS - Phase 11-13)**:
   CommonJS `require()` / ES module `import`, TypeScript interface/class method calls.
8. **Snapshot-Aware Performance Caching (Phase 17)**:
   Call graph and call-site indices must be cached by `(repo_name, commit_sha)`, strictly preserving v5 warm query performance (< 200 ms).
