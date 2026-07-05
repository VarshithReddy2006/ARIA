# Changelog — Repo Intelligence Agent

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] — 2026-07-04

This is the initial production-ready release of the Repo Intelligence Platform, incorporating all core implementations and subsequent stabilization passes.

### Added
- **Repository Ingestion Pipeline**: Clones public/private repos, detects programming stacks (Python, TypeScript, JavaScript), parses source files via Tree-sitter AST, and builds a NetworkX representation of the dependency graph.
- **Repository Chat (v2)**: Advanced retrieval pipeline that runs a rule-based intent router to categorize queries (Architecture, Dependencies, Churn, Dead Code, Symbol Lookup) and routes them to appropriate AST/graph indices or ChromaDB vector store.
- **Interactive Graphs**: Web portals displaying file-level dependency graphs and function-level call graphs using React Flow and Dagre topological positioning.
- **Repository Health Scorecards**: High-level engineering dashboard rating repositories across Architecture Stability, API Quality, Code Hygiene, Hotspots/Churn, and Onboarding path completeness.
- **VS Code Extension**: Integrates symbol hover cards, CodeLens annotation triggers, inline chats, and webview graphs directly into the IDE (version `0.1.0`).
- **Multi-Provider LLM Orchestration**: Eager startup validation and failover management between Google Gemini (primary) and NVIDIA NIM DeepSeek (fallback) models.
- **API Key Middleware**: Introduced an optional `API_KEY` configuration to safeguard resource-intensive endpoints (cloning, indexing, LLM chat, report generation). Authenticates clients via `X-API-Key` or standard `Authorization: Bearer` headers.
- **Latency Telemetry**: Connected request duration timers inside `MetricsMiddleware` to the Prometheus `MetricsRegistry` as `http_request_duration_seconds` summary metrics.

### Changed
- **FastAPI Event Loop Concurrency**: Wrapped CPU-bound and blocking network/disk calls inside async endpoints (issue mapper, ingestion pipeline, git history chunking, call graph parsing, and BGE embedding generation) in `asyncio.to_thread` executors to prevent ASGI main thread freezing.
- **Rate Limiter Memory Sweep**: Replaced the sliding-window `defaultdict` with a standard dictionary and implemented a thread-safe periodic cleanup sweep (every 5 minutes) to prune inactive client IP keys.
- **LRU Cache Eviction**: Added capacity-based eviction (`settings.cache_size_limit`) using Least Recently Used (LRU) algorithms inside `AnalysisCache`.
- **Scorecard Layout**: Overhauled Health Report scorecard grid into a spacious 4-column layout on desktop to prevent visual clutter and squashed text wrapping.
- **Action Items Restructuring**: Restructured the Health Report page, moving prioritized action items to a balanced 2-column grid at the bottom of the page.
- **Digital Twin Mapping**: Standardized backend digital twin lookup schemes to match actual generated schemas (e.g. `compliance_summary` instead of `compliance`).
- **Graph Fallbacks**: Configured inspectors (Architecture, Dependency, Documentation, Complexity) to dynamically query the knowledge graph when raw twin summaries are not populated.

### Improved
- **Floating Controls**: Standardized all React Flow graph actions (Zoom In/Out, Fit, Reset, Center Graph) into unified dark glassmorphic panels.
- **MiniMap Styling**: Updated MiniMaps on both call and dependency graphs to match the dark slate design system.
- **Directory Breadcrumbs**: Integrated segment path breadcrumbs inside the file explorer sidebar preview.
- **Chat Stop/Regenerate Buttons**: Added AbortController integration for canceling long response streams, regeneration actions, and timestamp labels.

### Fixed
- **Windows Path Traversal Hardening**: Stripped backslashes `\` alongside forward slashes in repository name sanitization logic inside `JsonSnapshotStore` and `github_service` to block Windows path traversal vectors.
- **Unbounded Memory Leakages**: Added cache-TTL capacity pruning for `_FILE_PATHS_CACHE` in retrieval services and capped the persistent `ISSUE_CACHE` size at 500 records.
- **Scroll Overlap**: Resolved a z-index stacking context bug on the Health Report export footer, forcing scrolling cards to pass cleanly behind the footer panel.
- **Card Height Overflow**: Resolved issues where the bottom borders of critical refactoring issue cards would clip through estimated impacts and recommended fixes.
- **Uvicorn Reload Loop**: Added strict directories and file exclusions to WatchFiles to prevent uvicorn restarts when cloned repository analysis files are written.
- **Extension Routing**: Corrected execution planner API path inside the VS Code client to use `/execution-plan` instead of `/execution`.
- **Packaging Readiness**: Removed temporary diagnostic console logs from the TreeView Providers, resolved missing icon configurations, and verified complete `.vsix` build.

### Performance
- **Startup Warmup**: Eagerly pre-loads the BGE embedding model, tokenizer, and Tree-sitter parsers on server initialization to eliminate cold-start latencies.
- **Topological Memoization**: Memoized coordinates calculations on the client-side to prevent unnecessary canvas redraws.
