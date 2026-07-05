# API Reference

All endpoints are hosted at `http://127.0.0.1:8001`. Every route is also available under the `/api/v1/` versioned prefix.

---

## Authentication

When the application is configured with an `API_KEY` (via the environment variable), all expensive endpoints (indexing, ingestion, chat, issues, reports) require authentication. 

You must supply the API key in one of the following HTTP headers:

1. **X-API-Key Header**:
   ```http
   X-API-Key: your_secret_api_key_here
   ```

2. **Authorization Bearer Token Header**:
   ```http
   Authorization: Bearer your_secret_api_key_here
   ```

Failed authentication requests return a `401 Unauthorized` response:
```json
{
  "detail": "Unauthorized. Invalid or missing API key."
}
```

---

## Navigation

- [System Status & Utility](#system-status--utility)
- [Repository Processing](#repository-processing)
- [Semantic Querying](#semantic-querying)
- [Repository Chat (v2)](#repository-chat-v2)
- [Architecture Intelligence](#architecture-intelligence)
- [Interactive Graph Intelligence](#interactive-graph-intelligence)
- [Symbol Intelligence](#symbol-intelligence)
- [Call Graph Intelligence](#call-graph-intelligence)
- [API Surface Intelligence](#api-surface-intelligence)
- [Git History & Churn](#git-history--churn)
- [PR & Architecture Drift Intelligence](#pr--architecture-drift-intelligence)
- [Dead Code Intelligence](#dead-code-intelligence)
- [Repository Intelligence Report](#repository-intelligence-report)
- [AI Engineering Advisor](#ai-engineering-advisor)
- [Autonomous Engineering Agent (AEA²)](#autonomous-engineering-agent-aea2)
- [Intelligent IDE Workspace](#intelligent-ide-workspace)

---

## System Status & Utility

### GET /health

Returns the static configuration health — active LLM provider, model, embedding provider, and vector DB. This endpoint makes no external calls and is suitable for load balancer health probes.

#### Response (200 OK)
```json
{
  "backend": "online",
  "llm_provider": "gemini",
  "llm_model": "gemini-2.5-flash",
  "embedding_provider": "BAAI/bge-small-en-v1.5",
  "vector_db": "chromadb",
  "status": "healthy"
}
```

---

### GET /metrics

Returns application metrics in Prometheus text format. Exempt from rate limiting. Available at both `/metrics` and `/api/v1/metrics`.

#### Request Example
```bash
curl http://127.0.0.1:8001/metrics
```

#### Response (200 OK — `text/plain; version=0.0.4`)
```
# HELP http_requests_total Total number of HTTP requests.
# TYPE http_requests_total counter
http_requests_total{method="GET",path="/health",status="200"} 12.0

# HELP active_requests_count Total number of active requests.
# TYPE active_requests_count gauge
active_requests_count 0.0

# HELP build_duration_seconds Build pipeline durations in seconds.
# TYPE build_duration_seconds summary
build_duration_seconds_sum{repository="fastapi/fastapi"} 45.123
build_duration_seconds_count{repository="fastapi/fastapi"} 1

# HELP cache_hits_total Total number of analysis cache hits.
# TYPE cache_hits_total counter
cache_hits_total{cache_key="symbols"} 3.0

# HELP cache_size Total number of entries currently in the cache.
# TYPE cache_size gauge
cache_size 12.0
```

---

### GET /api/repos/examples
Fetch a list of pre-configured example repositories designed for testing.

#### Request Example
```bash
curl http://127.0.0.1:8001/api/repos/examples
```

#### Response (200 OK)
```json
[
  {
    "name": "google/guava",
    "url": "https://github.com/google/guava",
    "tech_stack": ["Java", "Maven"],
    "description": "Google core libraries for Java."
  },
  {
    "name": "fastapi/fastapi",
    "url": "https://github.com/fastapi/fastapi",
    "tech_stack": ["Python", "Pydantic", "Starlette"],
    "description": "High performance, easy to learn, fast to code, ready for production API framework."
  },
  {
    "name": "vercel/next.js",
    "url": "https://github.com/vercel/next.js",
    "tech_stack": ["JavaScript", "TypeScript", "React", "Rust"],
    "description": "The React Framework for the Web."
  }
]
```

---

### GET /api/repos/recent
Fetch a list of repositories processed during the current server session, loaded from the persisted store.

#### Request Example
```bash
curl http://127.0.0.1:8001/api/repos/recent
```

#### Response (200 OK)
```json
[
  {
    "name": "Ankita15k/GitNest",
    "url": "https://github.com/Ankita15k/GitNest",
    "tech_stack": ["JavaScript", "TypeScript"],
    "analyzed_at": "Just now"
  }
]
```

---

## Repository Processing

### POST /api/analyze (SSE Stream)
Trigger a full repository cloning, language parsing, code chunking, indexing, and architecture mapping pipeline. This endpoint streams real-time progress events using the `text/event-stream` mime-type.

#### Request Schema (AnalyzeRequest)
- `url` (string, required): GitHub repository URL.
- `branch` (string, optional): Git branch or ref. Defaults to `"main"`.
- `model` (string, optional): LLM model variant to use. Defaults to `"deepseek-ai/deepseek-v4-flash"`.

```json
{
  "url": "https://github.com/owner/repository",
  "branch": "main",
  "model": "deepseek-ai/deepseek-v4-flash"
}
```

#### Request Example
```bash
curl -N -X POST http://127.0.0.1:8001/api/analyze \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "url": "https://github.com/Ankita15k/GitNest",
    "branch": "main"
  }'
```

#### SSE Stream Events Progress Output
```
data: {"status": "cloning", "message": "Cloning repository from GitHub..."}
data: {"status": "cloned", "message": "✓ Repository cloned successfully"}
data: {"status": "detecting", "message": "Detecting languages and frameworks..."}
data: {"status": "detected", "message": "✓ Technologies detected: ['JavaScript', 'TypeScript']"}
data: {"status": "chunking", "message": "START: chunking"}
data: {"status": "chunking", "message": "END: chunking"}
data: {"status": "embedding", "message": "START: embeddings"}
data: {"status": "embedding", "message": "END: embeddings"}
data: {"status": "chroma", "message": "START: chroma indexing"}
data: {"status": "chroma", "message": "END: chroma indexing"}
data: {"status": "building_graph", "message": "Building file dependency graph..."}
data: {"status": "graph_built", "message": "✓ Dependency graph: 328 files parsed, 1440 edges", "files_parsed": 328, "dependencies_found": 1440, "entry_points": ["backend/src/index.js"]}
data: {"status": "analyzed", "message": "✓ Architecture analyzed"}
data: {"status": "complete", "message": "✓ Repository analysis complete!"}
data: {"status": "done", "repo": "Ankita15k/GitNest"}
```

---

### POST /api/index
Clones, chunks, and indexes a repository's vector embeddings in ChromaDB, without building structural dependency graphs.

#### Request Schema (IndexRequest)
- `repo_url` (string, required): GitHub repository URL.

```json
{
  "repo_url": "https://github.com/owner/repository"
}
```

#### Response (200 OK)
```json
{
  "status": "indexed",
  "files": 328,
  "chunks": 1549
}
```

---

### GET /api/analysis/{owner}/{repo_name}
Fetch the complete metadata results of a repository analysis.

#### Response (200 OK)
```json
{
  "analysis": {
    "structure": {
      ".": ["README.md", "package.json"],
      "src": ["app.js", "server.js"]
    },
    "dependencies": ["express", "cors", "jsonwebtoken"],
    "tech_stack": ["JavaScript", "TypeScript"],
    "metadata": {
      "owner": "Ankita15k",
      "name": "GitNest",
      "local_path": "C:\\Users\\Varshith Reddy\\.repo_intelligence\\cloned_repos\\Ankita15k_GitNest"
    }
  },
  "architecture": {
    "summary": "GitNest is a full-stack Git hosting dashboard built with Node.js and Express...",
    "reading_order": [
      "backend/src/index.js",
      "backend/src/app.js"
    ],
    "relationships": [
      {
        "source": "backend/src/index.js",
        "target": "backend/src/app.js",
        "relationship_type": "imports",
        "description": "Imports app instance to launch listener server."
      }
    ]
  }
}
```

---

## Semantic Querying

### POST /api/retrieve
Query the vector space index directly for a repository using BGE embeddings and generate a grounded LLM response.

#### Request Schema (RetrieveRequest)
- `repo` (string, required): Repository identifier (owner/repo).
- `question` (string, required): Question query.

```json
{
  "repo": "owner/repository",
  "question": "How is authentication handled?"
}
```

#### Response (200 OK)
```json
{
  "answer": "Authentication is implemented using JWT tokens inside authMiddleware.js...",
  "sources": [
    {
      "file": "backend/src/middleware/authMiddleware.js",
      "content": "const token = req.headers.authorization.split(' ')[1]; ...",
      "score": 0.92
    }
  ]
}
```

---

### POST /api/chat (SSE Stream)

See [Repository Chat (v2) → POST /api/chat](#post-apichat) for the full request/response specification including `session_id`, SSE event format, and streaming behavior.

---

### POST /api/issues/map

See [Repository Chat (v2) → POST /api/issues/map](#post-apiissuesmap) for the full request/response specification.

---

---

## Architecture Intelligence

### POST /api/architecture/build
Trigger Tree-sitter AST parsing over local cloned repository files and construct the dependency NetworkX graph.

#### Request Schema (ArchitectureBuildRequest)
- `repo` (string, required): Repository identifier (owner/repo).

```json
{
  "repo": "owner/repository"
}
```

#### Response (200 OK)
```json
{
  "status": "built",
  "repo": "Ankita15k/GitNest",
  "files_parsed": 328,
  "dependencies_found": 1440,
  "entry_points": [
    "backend/src/index.js"
  ]
}
```

---

### GET /api/architecture/{owner}/{repo_name}
Fetch the generated architecture summary, reading order, and relationship schemas.

#### Response (200 OK - ArchitectureSummary)
```json
{
  "summary": "GitNest is a full-stack Git dashboard using Express and local git hooks...",
  "reading_order": [
    "backend/src/index.js",
    "backend/src/app.js"
  ],
  "relationships": [
    {
      "source": "backend/src/index.js",
      "target": "backend/src/app.js",
      "relationship_type": "imports",
      "description": "Instantiates app config schemas."
    }
  ]
}
```

---

### GET /api/architecture/{owner}/{repo_name}/graph
Retrieve React Flow-compatible node and edge datasets for visualization.

#### Query Parameters
- `q` (string, optional): Substring filter for file names/module paths.

#### Response (200 OK)
```json
{
  "nodes": [
    {
      "id": "backend/src/index.js",
      "data": { "label": "index.js" },
      "position": { "x": 120, "y": 80 },
      "style": { "background": "#1e293b", "color": "#f8fafc" }
    }
  ],
  "edges": [
    {
      "id": "e_backend/src/index.js_backend/src/app.js",
      "source": "backend/src/index.js",
      "target": "backend/src/app.js",
      "animated": true
    }
  ]
}
```

---

### POST /api/reading-order
Generate an optimal, ranked file list for onboarding new developers based on graph centrality metrics.

#### Request Schema (ReadingOrderRequest)
- `repo` (string, required): Repository identifier (owner/repo).

```json
{
  "repo": "owner/repository"
}
```

#### Response (200 OK - ReadingOrder)
```json
{
  "repo": "Ankita15k/GitNest",
  "ordered_files": [
    {
      "rank": 1,
      "file_path": "backend/src/index.js",
      "reason": "Primary application entry point initializing server configurations.",
      "tier": "entry_point",
      "score": 150.0
    }
  ],
  "reasoning": [
    "Timeline starts with detected application entry points.",
    "Order prioritizes modules with high degree centrality scores."
  ],
  "estimated_reading_time": 45,
  "total_files_ranked": 328
}
```

---

### POST /api/impact-analysis
Predict downstream affected modules and components resulting from a proposed change.

#### Request Schema (ImpactAnalysisRequest)
- `repo` (string, required): Repository identifier (owner/repo).
- `issue` (string, required): Change request or GitHub issue text.

```json
{
  "repo": "Ankita15k/GitNest",
  "issue": "Add API key authentication"
}
```

#### Response (200 OK - ImpactAnalysis)
```json
{
  "repo": "Ankita15k/GitNest",
  "issue_text": "Add API key authentication",
  "directly_affected_files": [
    "backend/src/middleware/authMiddleware.js"
  ],
  "indirectly_affected_files": [
    "backend/src/routes/auth.routes.js",
    "backend/src/app.js"
  ],
  "affected_components": [
    "Authentication",
    "API Layer"
  ],
  "risk_level": "medium",
  "estimated_file_count": 3,
  "dependency_paths": [
    {
      "path": [
        "backend/src/middleware/authMiddleware.js",
        "backend/src/routes/auth.routes.js",
        "backend/src/app.js"
      ]
    }
  ],
  "confidence": 85
}
```

---
---

## Repository Chat (v2)

### GET /api/chat/health

Live provider health diagnostic. Runs a health check against all configured LLM providers. Use for operational monitoring — not load balancer probes (has 200–400 ms latency due to live API calls).

#### Request Example
```bash
curl http://127.0.0.1:8001/api/chat/health
```

#### Response (200 OK)
```json
{
  "status": "ok",
  "provider": "gemini",
  "api_key_present": true,
  "authenticated": true,
  "healthy": true,
  "latency_ms": 234.1,
  "error_type": null,
  "error_message": null,
  "recommendation": null,
  "circuit_states": [
    {"name": "gemini", "circuit_state": "CLOSED", "failure_count": 0}
  ],
  "all_providers": {
    "gemini": {
      "provider": "gemini",
      "model": "gemini-2.5-flash",
      "healthy": true,
      "authenticated": true,
      "latency_ms": 234.1,
      "error_type": null,
      "error_message": null,
      "recommendation": null
    }
  },
  "timestamp": 1750000000.0
}
```

`status` values: `ok` (all configured providers healthy), `degraded` (at least one healthy), `unhealthy` (none healthy), `error` (health check failed).

#### Status Codes
| Code | Meaning |
|------|---------|
| 200 | Health check ran — inspect `status` field for result |
| 500 | Health check itself failed unexpectedly |

---

### POST /api/chat/reload

Hot-reload the LLM provider without restarting the server. Call this after updating `GEMINI_API_KEY` or `DEEPSEEK_API_KEY` in `.env`. Resets the `ProviderFactory` cache, `ProviderManager`, and all circuit breakers, then verifies the new provider with a test call.

#### Request Example
```bash
curl -X POST http://127.0.0.1:8001/api/chat/reload
```

#### Response (200 OK)
```json
{
  "status": "ok",
  "message": "LLM provider reloaded successfully. Chat is ready.",
  "test_response": "ready"
}
```

#### Error Response (500)
```json
{
  "status": "error",
  "detail": "Provider loaded but test call failed: 401 UNAUTHENTICATED"
}
```

---

### POST /api/chat

Interactive streaming chat over a repository's codebase context. Streams token-by-token via SSE.

The v2 pipeline runs: conversation memory → intent detection → intent routing → weighted retrieval (top-15 reranked to top-5) → context assembly → LLM streaming → memory update.

#### Request Schema (ChatRequest)
- `repo` (string, required): Repository identifier (`owner/repo`)
- `message` (string, required): User message
- `history` (list, optional): Conversation history turns
- `session_id` (string, optional): Session identifier for conversation memory. Defaults to `"default"`

```json
{
  "repo": "fastapi/fastapi",
  "message": "How does dependency injection work?",
  "history": [
    {"role": "user", "content": "What is the entry point?"},
    {"role": "assistant", "content": "The entry point is fastapi/applications.py..."}
  ],
  "session_id": "user-abc-session-1"
}
```

#### SSE Stream Output
```
data: {"text": "FastAPI"}
data: {"text": "'s "}
data: {"text": "dependency "}
data: {"text": "injection "}
data: {"text": "uses "}
data: {"text": "the "}
data: {"text": "Depends() "}
data: {"text": "system..."}
data: {"sources": ["fastapi/dependencies/utils.py", "fastapi/routing.py"], "confidence": 91, "fallback_mode": false, "status": "done"}
```

The final SSE event always includes `"status": "done"`.

#### Status Codes
| Code | Meaning |
|------|---------|
| 200 | SSE stream opened |
| 400 | `repo` field is empty |
| 422 | Request body validation failed |

---

### POST /api/issues/map

Map a GitHub issue to relevant source files and generate a grounded implementation plan. Uses exactly 2 LLM calls: one to parse the issue and rank files, one to generate the implementation plan. Results are cached by `sha256(issue_text)`.

#### Request Schema (IssueMapRequest)
- `repo` (string, required): Repository identifier (`owner/repo`)
- `title` (string, optional): GitHub issue title
- `description` (string, optional): GitHub issue body
- `issue` (string, optional): Combined issue text (alternative to title + description)

```json
{
  "repo": "fastapi/fastapi",
  "title": "Dependency injection fails with async generators",
  "description": "When using yield-based dependencies with async context managers, cleanup is not called."
}
```

#### Response (200 OK)
```json
{
  "issue_summary": "Async generator dependencies do not trigger cleanup",
  "issue_type": "bug",
  "relevant_files": [
    "fastapi/dependencies/utils.py",
    "fastapi/concurrency.py"
  ],
  "affected_components": ["Services", "API Layer"],
  "implementation_plan": [
    {
      "step_number": 1,
      "description": "In fastapi/dependencies/utils.py, locate solve_dependencies() and ensure async generator cleanup is awaited.",
      "files_to_modify": ["fastapi/dependencies/utils.py"]
    }
  ],
  "complexity": "medium",
  "confidence": 84,
  "verified": true,
  "sources": ["fastapi/dependencies/utils.py", "fastapi/concurrency.py"]
}
```

---

## Interactive Graph Intelligence

### GET /api/graph/{owner}/{repo}/full
Retrieve the full dependency graph for visualization in the interactive layout.

#### Query Parameters
- `q` (string, optional): Query substring to filter node files.

#### Request Example
```bash
curl http://127.0.0.1:8001/api/graph/VarshithReddy2006/Repo-Intelligence-Agent/full?q=service
```

#### Response (200 OK)
```json
{
  "nodes": [
    {
      "id": "services/symbol_service.py",
      "label": "symbol_service.py",
      "category": "file",
      "language": "python"
    }
  ],
  "edges": [
    {
      "source": "services/symbol_service.py",
      "target": "models/symbol.py",
      "relationship": "imports"
    }
  ]
}
```

---

### GET /api/graph/{owner}/{repo}/neighbors/{node_path:path}
Retrieve the immediate neighborhood of a single file node.

#### Request Example
```bash
curl http://127.0.0.1:8001/api/graph/VarshithReddy2006/Repo-Intelligence-Agent/neighbors/services/symbol_service.py
```

#### Response (200 OK)
```json
{
  "nodes": [
    { "id": "services/symbol_service.py", "label": "symbol_service.py", "category": "focus", "language": "python" },
    { "id": "backend/api.py", "label": "api.py", "category": "predecessor", "language": "python" },
    { "id": "models/symbol.py", "label": "symbol.py", "category": "successor", "language": "python" }
  ],
  "edges": [
    { "source": "backend/api.py", "target": "services/symbol_service.py", "relationship": "imports" },
    { "source": "services/symbol_service.py", "target": "models/symbol.py", "relationship": "imports" }
  ]
}
```

---

### GET /api/graph/{owner}/{repo}/trace/{node_path:path}
Trace all reachable nodes in the dependency graph starting from a node.

#### Query Parameters
- `direction` (string, optional): Direction of walk. Options: `forward`, `backward`, `both`. Defaults to `both`.
- `depth` (int, optional): BFS walk limit. Minimum 1, Maximum 12. Defaults to 6.

#### Request Example
```bash
curl "http://127.0.0.1:8001/api/graph/VarshithReddy2006/Repo-Intelligence-Agent/trace/services/symbol_service.py?direction=backward&depth=3"
```

#### Response (200 OK)
```json
{
  "nodes": [
    { "id": "services/symbol_service.py", "label": "symbol_service.py", "category": "focus", "language": "python" },
    { "id": "backend/api.py", "label": "api.py", "category": "dependent", "language": "python" }
  ],
  "edges": [
    { "source": "backend/api.py", "target": "services/symbol_service.py", "relationship": "imports" }
  ]
}
```

---

### GET /api/graph/{owner}/{repo}/search
Search for nodes by label or file path, returning matches highlighted with their immediate context.

#### Query Parameters
- `q` (string, required): Query term.

#### Request Example
```bash
curl http://127.0.0.1:8001/api/graph/VarshithReddy2006/Repo-Intelligence-Agent/search?q=dead_code
```

#### Response (200 OK)
```json
{
  "nodes": [
    { "id": "services/dead_code_service.py", "label": "dead_code_service.py", "category": "file", "language": "python", "highlighted": true },
    { "id": "backend/api.py", "label": "api.py", "category": "file", "language": "python", "highlighted": false }
  ],
  "edges": [
    { "source": "backend/api.py", "target": "services/dead_code_service.py", "relationship": "imports" }
  ]
}
```

---

## Symbol Intelligence

### GET /api/symbols/{owner}/{repo}/file/{file_path:path}
Retrieve all AST symbols (classes, functions, methods) defined in a file.

#### Request Example
```bash
curl http://127.0.0.1:8001/api/symbols/VarshithReddy2006/Repo-Intelligence-Agent/file/services/symbol_service.py
```

#### Response (200 OK)
```json
{
  "file": "services/symbol_service.py",
  "repo": "VarshithReddy2006/Repo-Intelligence-Agent",
  "symbol_count": 2,
  "symbols": [
    {
      "name": "SymbolService",
      "type": "class",
      "file_path": "services/symbol_service.py",
      "line_number": 26,
      "language": "python",
      "parent_class": null
    },
    {
      "name": "get_file_symbols",
      "type": "function",
      "file_path": "services/symbol_service.py",
      "line_number": 95,
      "language": "python",
      "parent_class": "SymbolService"
    }
  ]
}
```

---

### GET /api/symbols/{owner}/{repo}/definition/{symbol_name}
Find the definition site of a symbol.

#### Request Example
```bash
curl http://127.0.0.1:8001/api/symbols/VarshithReddy2006/Repo-Intelligence-Agent/definition/SymbolService
```

#### Response (200 OK)
```json
{
  "symbol": "SymbolService",
  "repo": "VarshithReddy2006/Repo-Intelligence-Agent",
  "definition": {
    "name": "SymbolService",
    "type": "class",
    "file_path": "services/symbol_service.py",
    "line_number": 26,
    "language": "python",
    "parent_class": null
  }
}
```

---

### GET /api/symbols/{owner}/{repo}/references/{symbol_name}
Search for references to a symbol across the repository symbol index.

#### Request Example
```bash
curl http://127.0.0.1:8001/api/symbols/VarshithReddy2006/Repo-Intelligence-Agent/references/SymbolService
```

#### Response (200 OK)
```json
{
  "symbol": "SymbolService",
  "repo": "VarshithReddy2006/Repo-Intelligence-Agent",
  "references": [
    {
      "name": "SymbolService",
      "type": "class",
      "file_path": "services/symbol_service.py",
      "line_number": 26,
      "language": "python",
      "parent_class": null
    }
  ],
  "reference_count": 1,
  "note": "MVP: name-based matching only. Full cross-file call graph planned for PH2-003."
}
```

---

## Call Graph Intelligence

### POST /api/call-graph/build

Build the function-level call graph for a repository. Streams SSE progress. Requires the repository to have been analyzed (`POST /api/analyze`) and the symbol index to exist (`POST /api/architecture/build`).

#### Request Schema
- `repo` (string, required): Repository identifier (`owner/repo`)

```json
{"repo": "fastapi/fastapi"}
```

#### SSE Stream Events
```
data: {"status": "progress", "message": "Parsing function calls..."}
data: {"status": "result", "data": {"total_functions": 142, "total_edges": 389}}
data: {"status": "done"}
```

---

### GET /api/call-graph/{owner}/{repo}

Return the call graph as React Flow JSON for visualization.

#### Query Parameters
- `q` (string, optional): Filter by function name substring
- `max_nodes` (int, optional): Maximum nodes to return. Range: 1–1000. Default: 300

#### Request Example
```bash
curl "http://127.0.0.1:8001/api/call-graph/fastapi/fastapi?q=router&max_nodes=50"
```

#### Response (200 OK)
```json
{
  "nodes": [
    {"id": "fastapi.routing:APIRouter.add_api_route", "label": "add_api_route", "file": "fastapi/routing.py"}
  ],
  "edges": [
    {"source": "fastapi.routing:APIRouter.add_api_route", "target": "fastapi.routing:APIRoute.__init__"}
  ],
  "node_count": 1,
  "edge_count": 1
}
```

---

### GET /api/call-graph/{owner}/{repo}/callers/{function_id}

Return all functions that directly call the given function.

#### Request Example
```bash
curl http://127.0.0.1:8001/api/call-graph/fastapi/fastapi/callers/fastapi.routing:APIRouter.add_api_route
```

#### Response (200 OK)
```json
{
  "function_id": "fastapi.routing:APIRouter.add_api_route",
  "callers": [
    {"id": "fastapi.routing:APIRouter.get", "name": "get", "file": "fastapi/routing.py", "line": 412}
  ]
}
```

---

### GET /api/call-graph/{owner}/{repo}/callees/{function_id}

Return all functions directly called by the given function.

---

### GET /api/call-graph/{owner}/{repo}/hierarchy/{function_id}

Return the call hierarchy tree for a function (callers tree or callees tree).

#### Query Parameters
- `direction` (string, optional): `down` (callees) or `up` (callers). Default: `down`
- `depth` (int, optional): BFS depth limit. Range: 1–12. Default: 6

---

### GET /api/call-graph/{owner}/{repo}/blast-radius/{function_id}

Return the function-level blast radius — all functions reachable from this one, with risk scoring.

---

### GET /api/call-graph/{owner}/{repo}/stats

Return aggregate call graph statistics (total functions, total edges, most-called functions, most-calling functions).

---

### GET /api/call-graph/{owner}/{repo}/neighbors/{function_id}

Return immediate callers and callees of a function as React Flow JSON.

---

### GET /api/call-graph/{owner}/{repo}/trace/{function_id}

BFS trace from a function as React Flow JSON.

#### Query Parameters
- `direction` (string, optional): `forward`, `backward`, or `both`. Default: `both`
- `depth` (int, optional): BFS depth limit. Range: 1–12. Default: 6

---

## API Surface Intelligence

### POST /api/api-surface/build

Build the API surface index — classifies every exported symbol as public, internal, or deprecated, and computes Martin's instability metrics. Streams SSE progress. Requires analyzed repository and symbol index.

#### Request Schema
- `repo` (string, required): Repository identifier (`owner/repo`)

```json
{"repo": "fastapi/fastapi"}
```

#### SSE Stream Events
```
data: {"status": "progress", "message": "Classifying symbols..."}
data: {"status": "result", "data": {"total_symbols": 142, "public": 42, "internal": 98, "deprecated": 2}}
data: {"status": "done"}
```

---

### GET /api/api-surface/{owner}/{repo}

Return the full API surface report including all symbols, stability metrics, and visibility ratio.

#### Request Example
```bash
curl http://127.0.0.1:8001/api/api-surface/fastapi/fastapi
```

---

### GET /api/api-surface/{owner}/{repo}/stats

Return aggregate API surface statistics.

#### Response (200 OK)
```json
{
  "total_symbols": 142,
  "public_count": 42,
  "internal_count": 98,
  "deprecated_count": 2,
  "visibility_ratio": 0.296
}
```

---

### GET /api/api-surface/{owner}/{repo}/public

Return all public symbols. Supports optional `q` search and `kind` filter query parameters, and a `limit` (default 100, max 1000).

---

### GET /api/api-surface/{owner}/{repo}/internal

Return all internal symbols. Supports `limit` query parameter.

---

### GET /api/api-surface/{owner}/{repo}/deprecated

Return all deprecated symbols.

---

### GET /api/api-surface/{owner}/{repo}/breaking

Detect breaking changes between two API surfaces, or return orphaned public APIs if `compare_repo` is omitted.

#### Query Parameters
- `compare_repo` (string, optional): Baseline repository identifier (`owner/repo`) to diff against

#### Response (200 OK — with compare_repo)
```json
{
  "breaking_changes": [
    {
      "symbol": "authenticate_user",
      "type": "function",
      "change_type": "removed",
      "file_path": "services/auth_service.py"
    }
  ],
  "count": 1
}
```

#### Response (200 OK — without compare_repo)
```json
{
  "orphans": [
    {
      "name": "legacy_helper",
      "type": "function",
      "file_path": "services/legacy_helper.py",
      "visibility": "public"
    }
  ],
  "count": 1
}
```

---

### GET /api/api-surface/{owner}/{repo}/{symbol_name}

Return classification details for a single symbol by name.

---

## Git History & Churn

### POST /api/churn/analyze

Mine git commit history and compute per-file churn scores. Streams SSE progress.

#### Request Schema
- `repo` (string, required): Repository identifier (`owner/repo`)
- `since_days` (int, optional): Days of history to mine. Range: 7–3650. Default: 365

```json
{
  "repo": "fastapi/fastapi",
  "since_days": 365
}
```

#### SSE Stream Events
```
data: {"status": "progress", "message": "Processing 1200 commits..."}
data: {"status": "result", "data": {"total_commits": 1200, "files_analyzed": 89}}
data: {"status": "done"}
```

---

### GET /api/churn/{owner}/{repo}

Return the full churn summary. Requires `POST /api/churn/analyze` to have been run first.

#### Query Parameters
- `since_days` (int, optional): Must match the value used during analysis. Default: 365

#### Response (200 OK)
```json
{
  "repo": "fastapi/fastapi",
  "since_days": 365,
  "total_commits": 1200,
  "files_analyzed": 89,
  "top_churned_files": [
    {"file_path": "fastapi/routing.py", "commit_count": 87, "churn_score": 0.94}
  ],
  "timeline": [...]
}
```

---

### GET /api/churn/{owner}/{repo}/hotspots

Return the top-N hotspot files (high churn × high graph centrality).

#### Query Parameters
- `since_days` (int, optional): Default: 365
- `top_n` (int, optional): Range: 1–100. Default: 25

#### Response (200 OK)
```json
{
  "hotspots": [
    {
      "file_path": "fastapi/routing.py",
      "churn_score": 0.94,
      "centrality_score": 0.87,
      "hotspot_score": 0.91,
      "commit_count": 87,
      "risk_level": "HIGH"
    }
  ]
}
```

---

### GET /api/churn/{owner}/{repo}/file/{file_path}

Return churn data for a single file.

#### Request Example
```bash
curl http://127.0.0.1:8001/api/churn/fastapi/fastapi/file/fastapi/routing.py
```

---

### GET /api/churn/{owner}/{repo}/timeline

Return the weekly commit activity timeline.

#### Response (200 OK)
```json
{
  "timeline": [
    {"week": "2026-01-06", "commit_count": 12},
    {"week": "2026-01-13", "commit_count": 8}
  ]
}
```

---

## PR & Architecture Drift Intelligence

### POST /api/pr/analyze
Perform risk assessment, changed files extraction, symbol diffs, and blast radius propagation for a Pull Request.

#### Request Schema (PRAnalyzeRequest)
- `owner` (string, required): GitHub repository owner.
- `repo` (string, required): GitHub repository name.
- `pr_number` (int, required): GitHub pull request ID.

```json
{
  "owner": "VarshithReddy2006",
  "repo": "Repo-Intelligence-Agent",
  "pr_number": 2
}
```

#### Response (200 OK)
```json
{
  "repo": "VarshithReddy2006/Repo-Intelligence-Agent",
  "pr_number": 2,
  "risk_score": 24.5,
  "pr_size": "M",
  "blast_radius": "MEDIUM",
  "changed_files": [
    {
      "filename": "services/pr_intelligence_service.py",
      "status": "modified",
      "additions": 45,
      "deletions": 10,
      "changes": 55
    }
  ],
  "added_symbols": [],
  "modified_symbols": [
    {
      "name": "analyze_pull_request",
      "type": "function",
      "file_path": "services/pr_intelligence_service.py",
      "line_number": 85,
      "language": "python",
      "change_type": "modified",
      "parent_class": "PRIntelligenceService"
    }
  ],
  "removed_symbols": [],
  "affected_files": [
    "backend/api.py"
  ],
  "propagation_paths": [
    {
      "source": "services/pr_intelligence_service.py",
      "target": "backend/api.py",
      "path": ["backend/api.py", "services/pr_intelligence_service.py"],
      "depth": 1
    }
  ],
  "risk_breakdown": {
    "size_risk": "MEDIUM",
    "blast_radius_risk": "LOW",
    "drift_risk": "LOW",
    "hotspot_risk": "HIGH"
  },
  "review_focus_areas": [
    {
      "area": "hotspots",
      "description": "Changes to services/pr_intelligence_service.py modify highly coupled module logic.",
      "severity": "HIGH"
    }
  ],
  "analyzed_at": "2026-06-20T14:14:00Z"
}
```

---

### GET /api/pr/health
Health diagnostics check for PR Intelligence configurations.

#### Query Parameters
- `owner` (string, optional): GitHub owner.
- `repo` (string, optional): GitHub repo.

#### Request Example
```bash
curl "http://127.0.0.1:8001/api/pr/health?owner=VarshithReddy2006&repo=Repo-Intelligence-Agent"
```

#### Response (200 OK)
```json
{
  "github_token": true,
  "github_token_loaded": true,
  "github_token_prefix": "github_pat_1...",
  "github_rate_limit_authenticated": true,
  "rate_limit_remaining": 4982,
  "analysis_exists": true,
  "graph_available": true,
  "symbol_index_available": true,
  "status": "healthy"
}
```

---

### POST /api/repos/repair
Repair a repository by forcefully regenerating its missing graph and symbol indices.

#### Request Schema
- `owner` (string, required): GitHub owner.
- `repo` (string, required): GitHub repo.

```json
{
  "owner": "VarshithReddy2006",
  "repo": "Repo-Intelligence-Agent"
}
```

#### Response (200 OK)
```json
{
  "status": "success",
  "message": "Repository indexes rebuilt successfully for 'VarshithReddy2006/Repo-Intelligence-Agent'",
  "details": {
    "architecture": { "status": "built", "repo": "VarshithReddy2006/Repo-Intelligence-Agent", "files_parsed": 34, "dependencies_found": 80 },
    "symbols": { "repo": "VarshithReddy2006/Repo-Intelligence-Agent", "symbols_parsed": 122 }
  }
}
```

---

### POST /api/architecture/drift
Detect architectural drift, cycle additions, and coupling shifts introduced by a Pull Request.

#### Request Schema (PRDriftRequest)
- `owner` (string, required): GitHub owner.
- `repo` (string, required): GitHub repo.
- `pr_number` (int, required): GitHub PR ID.

```json
{
  "owner": "VarshithReddy2006",
  "repo": "Repo-Intelligence-Agent",
  "pr_number": 2
}
```

#### Response (200 OK)
```json
{
  "repo": "VarshithReddy2006/Repo-Intelligence-Agent",
  "pr_number": 2,
  "added_dependencies": [],
  "removed_dependencies": [],
  "new_cycles": [],
  "resolved_cycles": [],
  "coupling_increase": [
    { "file": "services/pr_intelligence_service.py", "before": 4, "after": 5 }
  ],
  "coupling_decrease": [],
  "new_entry_points": [],
  "removed_entry_points": [],
  "architectural_hotspots": [
    "services/pr_intelligence_service.py"
  ],
  "risk_score": 10.0,
  "improvement_score": 0.0,
  "analyzed_at": "2026-06-20T14:14:00Z"
}
```

---

## Dead Code Intelligence

### POST /api/dead-code/analyze
Traces reachability from application entry points to sweep unreachable files, orphaned modules, and dead dependency chains.

#### Request Schema (DeadCodeRequest)
- `owner` (string, required): GitHub owner.
- `repo` (string, required): GitHub repo.

```json
{
  "owner": "VarshithReddy2006",
  "repo": "Repo-Intelligence-Agent"
}
```

#### Response (200 OK)
```json
{
  "repo": "VarshithReddy2006/Repo-Intelligence-Agent",
  "cleanup_score": 92,
  "previous_cleanup_score": null,
  "estimated_cleanup_effort": "LOW",
  "unused_files": [
    {
      "file_path": "scripts/unused_script.py",
      "confidence": 0.95,
      "risk_level": "SAFE",
      "recommendation": "Consider removing unused file scripts/unused_script.py"
    }
  ],
  "orphan_modules": [
    {
      "file_path": "services/legacy_helper.py",
      "confidence": 0.90,
      "risk_level": "REVIEW",
      "recommendation": "Review orphaned module services/legacy_helper.py; no active execution path reaches it.",
      "last_reachable_parent": "services/architecture_service.py"
    }
  ],
  "dead_dependency_chains": [
    {
      "chain": ["services/dead_chain_a.py", "services/dead_chain_b.py"],
      "confidence": 0.95,
      "risk_level": "SAFE",
      "recommendation": "Dependency chain [dead_chain_a.py -> dead_chain_b.py] appears unreachable and may be removable as a unit.",
      "length": 1,
      "total_nodes": 2,
      "max_centrality": 0.012
    }
  ],
  "cleanup_recommendations": [
    "Remove unused file scripts/unused_script.py (no active imports).",
    "Review orphaned module services/legacy_helper.py (previously connected via services/architecture_service.py)."
  ],
  "analyzed_at": "2026-06-20T14:14:00Z"
}
```

---

## Repository Intelligence Report

### POST /api/v1/report/{owner}/{repo}/build
Triggers the full scoring, rating, and serialization pipeline for a repository. Compiles raw analyses (circular dependencies, stability index, dead code, change risks) and persists the result to SQLite before returning the model.

#### Response (200 OK)
```json
{
  "scores": {
    "overall": 87.5,
    "grade": "B",
    "breakdown": {
      "stability": 92.0,
      "api_distance": 85.0,
      "hygiene": 95.0,
      "churn": 80.0,
      "onboarding": 88.0
    }
  },
  "architecture": {
    "circular_dependencies": [
      ["services/a.py", "services/b.py", "services/a.py"]
    ],
    "coupling_hotspots": ["services/pr_intelligence_service.py"],
    "design_smells": [
      {
        "type": "HIGH_COUPLING",
        "file_path": "services/pr_intelligence_service.py",
        "description": "File has high in-degree / out-degree ratio."
      }
    ]
  },
  "api_surface": {
    "total_symbols": 142,
    "exported_symbols": 42,
    "visibility_ratio": 0.295,
    "instability_metrics": [
      {
        "module": "services/github_service",
        "efferent_coupling": 2,
        "afferent_coupling": 8,
        "instability": 0.20
      }
    ]
  },
  "hygiene": {
    "dead_functions": 12,
    "unreachable_files_count": 2,
    "registry": [
      {
        "symbol": "legacy_cleanup",
        "file_path": "services/legacy_helper.py",
        "line": 42
      }
    ]
  },
  "onboarding": {
    "entry_points": ["backend/api.py", "backend/cli.py"],
    "reading_path": [
      "models/report.py",
      "services/report/composer.py",
      "backend/routers/report.py"
    ]
  },
  "metadata": {
    "repo_name": "VarshithReddy2006/Repo-Intelligence-Agent",
    "commit_hash": "a8f4c2e",
    "generated_at": "2026-06-23T04:00:00Z"
  }
}
```

---

### GET /api/v1/report/{owner}/{repo}/summary
Retrieves the overall health rating and score summary from the cache without running a full re-build.

#### Response (200 OK)
```json
{
  "repo_name": "VarshithReddy2006/Repo-Intelligence-Agent",
  "score": 87.5,
  "grade": "B",
  "analyzed_at": "2026-06-23T04:00:00Z"
}
```

---

### GET /api/v1/report/{owner}/{repo}/download
Downloads the formatted report in the requested file type.

#### Query Parameters
- `format` (string, optional): One of `html` (default), `pdf`, or `markdown`.

#### Response (200 OK)
- **Binary Stream** with appropriate MIME type (`text/html` or `text/markdown`) and `Content-Disposition` attachment header.

---

## AI Engineering Advisor

### POST /api/v1/repositories/{owner}/{repo}/advisor
Runs the full AI Engineering Advisor pipeline and returns a structured AdvisorReport. Consolidates information from the Repository Inspector, Engineering Memory, and Continuous Monitoring.

#### Response (200 OK)
```json
{
  "repository": "fastapi/fastapi",
  "overall_priority": "medium",
  "total_recommendations": 12,
  "top_recommendations": [
    {
      "id": "rec-1",
      "title": "Resolve cycle between main and routing",
      "category": "architecture",
      "priority": "high",
      "estimated_effort": "medium"
    }
  ],
  "roadmap_phases": 3,
  "roadmap_summary": [
    {
      "phase": 1,
      "title": "Mitigate Security & Dependency Issues",
      "recommendation_count": 4
    }
  ]
}
```

---

### GET /api/v1/repositories/{owner}/{repo}/advisor/latest
Returns the most recently persisted AdvisorReport.

#### Response (200 OK)
*(Same schema format as Advisor Report)*

---

### GET /api/v1/repositories/{owner}/{repo}/advisor/recommendations
Returns the prioritized recommendation list from the latest AdvisorReport.

#### Query Parameters
- `priority` (string, optional): Filter by: `critical` | `high` | `medium` | `low`.
- `category` (string, optional): Filter by category name.
- `limit` (int, optional): Maximum number to return (default `50`).

#### Response (200 OK)
```json
[
  {
    "id": "rec-1",
    "title": "Resolve cycle between main and routing",
    "category": "architecture",
    "priority": "high",
    "estimated_effort": "medium"
  }
]
```

---

### GET /api/v1/repositories/{owner}/{repo}/advisor/roadmap
Returns the phased engineering roadmap from the latest AdvisorReport.

#### Response (200 OK)
```json
[
  {
    "phase": 1,
    "title": "Mitigate Security & Dependency Issues",
    "recommendation_count": 4
  }
]
```

---

## Autonomous Engineering Agent (AEA²)

### POST /api/v1/repositories/{owner}/{repo}/execution-plan
Generates a structured implementation plan from the latest AdvisorReport. Requires a previously generated AdvisorReport to exist.

#### Response (200 OK)
```json
{
  "repository": "fastapi/fastapi",
  "total_tasks": 8,
  "total_batches": 2,
  "critical_path_length": 5,
  "rollback_checkpoints": 2,
  "conflict_count": 0,
  "overall_risk": "low",
  "batches": [
    {
      "batch_id": "batch-1",
      "order": 1,
      "title": "Initial Refactoring Pass",
      "task_count": 3,
      "parallel": true,
      "estimated_effort": "1 day"
    }
  ],
  "critical_path": ["task-1", "task-3"],
  "metadata": {}
}
```

---

### GET /api/v1/repositories/{owner}/{repo}/execution-plan/latest
Returns the most recently persisted ExecutionPlan.

#### Response (200 OK)
*(Same schema format as ExecutionPlan)*

---

### GET /api/v1/repositories/{owner}/{repo}/execution-plan/batches
Returns the ordered execution batches from the latest ExecutionPlan.

#### Response (200 OK)
*(Returns batches summary array)*

---

### GET /api/v1/repositories/{owner}/{repo}/execution-plan/critical-path
Returns the critical path of execution tasks.

#### Response (200 OK)
```json
["task-1", "task-3"]
```

---

## Intelligent IDE Workspace

### GET /api/v1/repositories/{owner}/{repo}/workspace
Returns the complete consolidated IDE workspace snapshot for a repository.

#### Query Parameters
- `file` (string, optional): Currently open file path.
- `symbol` (string, optional): Currently selected symbol.
- `panel` (string, optional): Active workspace panel name (default `overview`).

#### Response (200 OK)
```json
{
  "state": {
    "repository": "fastapi/fastapi",
    "selected_file": "main.py",
    "selected_symbol": "app",
    "active_panel": "overview",
    "filters": {},
    "ui_preferences": {}
  },
  "overview": {
    "repository": "fastapi/fastapi",
    "description": "High performance API framework",
    "primary_language": "Python",
    "languages": ["Python"],
    "total_files": 342,
    "total_symbols": 1821,
    "architecture_style": "FastAPI Router Structure",
    "dependency_count": 12,
    "health": {
      "overall_score": 88,
      "overall_priority": "medium",
      "critical_count": 0,
      "high_count": 2,
      "medium_count": 4,
      "low_count": 6,
      "trend_direction": "stable"
    },
    "last_indexed_at": 1719543600,
    "metadata": {}
  },
  "explorer": null,
  "chat": null,
  "findings": null,
  "timeline": null,
  "monitor": null,
  "advisor": null,
  "execution": null,
  "available_panels": ["overview", "explorer", "chat", "findings", "timeline", "monitor", "advisor", "execution"],
  "metadata": {}
}
```

---

### GET /api/v1/repositories/{owner}/{repo}/workspace/{panel}
Fetches details for a specific dashboard panel in the workspace. Available panels: `overview`, `explorer`, `chat`, `findings`, `timeline`, `monitor`, `advisor`, `execution`.
Prefixes can be root `/repositories/...`, `/api/repositories/...`, or `/api/v1/repositories/...`.


