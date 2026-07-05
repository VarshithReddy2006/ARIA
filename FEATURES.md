# Features Catalog — Repo Intelligence Agent v1.0.0

This document outlines all functional modules, intelligence engines, and developer tools of the Repo Intelligence Agent, categorized by their implementation status.

---

## Implemented

### 1. Repository Ingestion & Parsing
- **Technology Stack Detection**: Automatically parses repository files to identify primary languages (Python, TypeScript, JavaScript) and package manifests (`requirements.txt`, `package.json`, `pyproject.toml`).
- **Abstract Syntax Tree (AST) Parsing**: Utilizes Tree-sitter parsers to extract code symbols:
  - Classes (definitions, inheritance trees)
  - Functions (parameters, return types, docstrings)
  - Methods (decorators, visibility scopes)
  - Imports and Exports (module-level inputs/outputs)
- **Deterministic File Indexing**: Maintains an in-memory SQL/JSON database of parsed symbol metadata, allowing instant lookups of any code segment without calling LLM endpoints.

### 2. Architecture & Dependency Analysis
- **Dependency Graph Constructor**: Feeds imported and exported symbol relations into a directed NetworkX graph, mapping file-to-file and module-to-module dependencies.
- **Circular Dependency Detection**: Detects import loops (cycles) that lead to compiler lockouts or tight coupling.
- **Strongly Connected Components (SCC)**: Groups modules into cohesive clusters to analyze architectural boundaries.

### 3. Grounded Repository Chat (v2)
- **Rule-Based Intent Router**: Categorizes user queries before calling LLMs to avoid hallucinations:
  - `architecture`: Queries the directed NetworkX graph.
  - `dependency`: Extracts import/export paths.
  - `symbol`: Searches the AST database for class/function definitions.
  - `churn` / `pr`: Inspects commit histories or files in a pull request.
  - `explanation` / `general`: Routes to semantic document blocks.
- **AST-Weighted Retrieval**: For structural queries, AST symbol definitions are prioritized over semantic vector search hits, reducing hallucinations.
- **Vector Search (ChromaDB)**: Embeds source code chunks using the `BAAI/bge-small-en-v1.5` model, storing them in ChromaDB for semantic concept searches.
- **Stream responses**: Streams answers token-by-token using Server-Sent Events (SSE).
- **Source Citations**: Attaches exact file paths, line ranges, and confidence match ratings to every chatbot response.
- **Stop & Regenerate Actions**: Instantly aborts in-flight streams or requests a revised response.

### 4. Code Quality & Health Reports
- **Overall Health Score**: An aggregate rating computed from architectural stability, API encapsulation, dead code sweeps, and file documentation coverage.
- **Sub-dimension Metrics**: Clear progress bars detailing scores for Onboarding Path, API Quality, Code Hygiene, and Dependency Stability.
- **Prioritized Action Items**: Parses smells into structured cards showing Category, Severity (Critical, High, Medium, Low), Affected Files, and Recommended Fixes.
- **Export formats**: Exports full interactive reports as single-file HTML, markdown, or Print-ready PDFs.

### 5. Visualizations & Interactive Graphs
- **File Dependency Graph**: Graph showing how files link. Highly-coupled directories and entry points are colored distinctively.
- **Function Call Graph**: Detailed function-level trace canvas. Focuses on caller/callee paths.
- **Interactive Controls**: Floating toolbar providing Zoom In, Zoom Out, Reset, Fit View, and Center Graph actions.
- **Filters**: Toggles to filter out external dependencies (node_modules/std libraries) and recursive cycles.
- **MiniMap**: Translucent guide mapping node groupings on large graphs.

### 6. Developer Experience & IDE Integrations
- **VS Code Extension**: Integrates intelligence directly into your workspace:
  - **Symbol Hovers**: Hover over a class or function to view its AST definition, docstring, and import references.
  - **CodeLenses**: Interactive actions above functions to trace call graphs or chat with the agent about that segment.
  - **IDE Chat Panel**: Sidebar chat companion.
  - **Webview Graph Canvases**: Explores call and file graphs directly inside VS Code editors.
- **In-House CLI**: `repo-intel` command-line utility for cloning, indexing, and printing architecture guides straight from the terminal.

### 7. Production Engineering
- **LLM Failover Engine**: Validates Gemini (primary) and DeepSeek (fallback) keys during startup. Automatically handles model failovers.
- **WatchFiles Exclusion Filter**: Restricts Uvicorn auto-reload dirs to source code folder trees, avoiding restarts during analysis cloning.
- **CORS & Rate Limiting**: Production-ready middleware securing API endpoints.

---

## Experimental

- **Module Stability Analysis**: Computes package distance from the *Main Sequence* (balance between abstractness and instability). Backend service layers are implemented; however, the router `backend/routers/stability.py` is registered as a placeholder with no active endpoints.
- **Design Smell Engine**: Detects structural issues like high-coupling hotspots, orphan helper files, and volatile base modules. The router `backend/routers/dependency_smells.py` is registered as a placeholder.

---

## Planned

- **JetBrains IDE Plugin**: Bringing the same symbol hover, CodeLens annotations, and interactive graph capabilities to JetBrains IDEs.
- **Multi-Repository Workspaces**: Cross-codebase search, dependency resolution, and pull request workflows across multiple repositories.
- **Distributed Agent Teams**: Spawns concurrent, specialized agents working collaboratively to solve codebase tickets.
