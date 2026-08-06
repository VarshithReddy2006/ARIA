# API Reference Guide — Repo Intelligence Agent v1.5.0

This document details the REST endpoints and Server-Sent Event (SSE) streams exposed by the FastAPI backend server. The API Layer is part of the **Repository Intelligence Architecture (RIA)**, the platform's modular production architecture.

All endpoints are versioned under the `/api/v1` prefix. Legacy root paths (e.g. `/api/...`) are supported as backward-compatible shims.

---

## Authentication

When the application is configured with an `API_KEY` (via the environment variable), all resource-intensive endpoints require authentication.

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

## 1. Repository Ingestion & Analysis

### Index Repository (Sync)
Triggers synchronous metadata ingestion for a repository.

- **Endpoint**: `POST /api/v1/index` or `POST /api/index`
- **Method**: `POST`
- **Request Body**:
  ```json
  {
    "repo_url": "https://github.com/fastapi/fastapi",
    "branch": "master"
  }
  ```
- **Response (200 OK)**:
  ```json
  {
    "status": "completed",
    "owner": "fastapi",
    "repo_name": "fastapi",
    "files_count": 342,
    "symbols_count": 1821
  }
  ```

---

### Index Repository (Streaming Analysis)
Triggers repository cloning and AST parsing, streaming progress updates as Server-Sent Events (SSE).

- **Endpoint**: `POST /api/v1/analyze` or `POST /api/analyze`
- **Method**: `POST`
- **Request Body**:
  ```json
  {
    "url": "https://github.com/fastapi/fastapi",
    "branch": "master",
    "model": "deepseek-ai/deepseek-v4-flash",
    "force_rebuild": false
  }
  ```
- **SSE Stream Data (Progress Events)**:
  ```text
  event: progress
  data: {"status": "cloning", "percent": 15, "message": "Cloning repository..."}

  event: progress
  data: {"status": "parsing", "percent": 50, "message": "Parsing abstract syntax trees..."}

  event: progress
  data: {"status": "completed", "percent": 100, "message": "Analysis completed."}
  ```

---

### Get Ingested Analysis Details
Returns metadata for an already analyzed repository.

- **Endpoint**: `GET /api/v1/analysis/{owner}/{repo_name}` or `GET /api/analysis/{owner}/{repo_name}`
- **Method**: `GET`
- **Response (200 OK)**:
  ```json
  {
    "owner": "fastapi",
    "repo_name": "fastapi",
    "indexed_at": "2026-07-04T12:00:00Z",
    "primary_language": "Python",
    "files_indexed": 342,
    "status": "ready"
  }
  ```

---

### Repair Repository Index
Rebuilds the dependency graph and symbol index from the already-cloned repository on disk without re-cloning or re-embedding.

- **Endpoint**: `POST /api/v1/repos/repair` or `POST /api/repos/repair`
- **Method**: `POST`
- **Request Body**:
  ```json
  {
    "owner": "fastapi",
    "repo": "fastapi"
  }
  ```
- **Response (200 OK)**:
  ```json
  {
    "status": "completed",
    "message": "Repository index repaired successfully."
  }
  ```

---

## 2. Codebase Chat & Issue Engine

### Chat Query (Streaming)
Queries the multi-agent chatbot about the codebase. Responses are streamed as SSE chunks.

- **Endpoint**: `POST /api/v1/chat` or `POST /api/chat`
- **Method**: `POST`
- **Request Body**:
  ```json
  {
    "repo": "fastapi/fastapi",
    "message": "What is the entry point of the app?",
    "history": [
      {"role": "user", "content": "Hi"},
      {"role": "assistant", "content": "Hello! How can I help?"}
    ]
  }
  ```
- **Headers Required**: `Accept: text/event-stream`
- **SSE Stream Data Chunks**:
  ```text
  event: chunk
  data: "The "

  event: chunk
  data: "main "

  event: chunk
  data: "entrypoint "

  event: citations
  data: [{"file": "fastapi/main.py", "lines": "1-15", "confidence": 0.95}]

  event: done
  data: [DONE]
  ```

---

### Chat Health & LLM Provider Status
Runs a live health check against every configured LLM provider.

- **Endpoint**: `GET /api/v1/chat/health` or `GET /api/chat/health`
- **Method**: `GET`
- **Response (200 OK)**:
  ```json
  {
    "status": "ok",
    "healthy": true,
    "primary_provider": "gemini",
    "healthy_providers": ["gemini", "deepseek"],
    "unhealthy_providers": []
  }
  ```

---

### Reload LLM Providers
Hot-reloads the LLM provider configuration from `.env` without restarting the server.

- **Endpoint**: `POST /api/v1/chat/reload` or `POST /api/chat/reload`
- **Method**: `POST`
- **Response (200 OK)**:
  ```json
  {
    "status": "success",
    "message": "LLM provider reloaded successfully. Chat is ready."
  }
  ```

---

### Map GitHub Issue to Implementation Plan
Generates a grounded implementation plan for a given issue using a two-LLM-call pipeline.

- **Endpoint**: `POST /api/v1/issues/map` or `POST /api/issues/map`
- **Method**: `POST`
- **Request Body**:
  ```json
  {
    "repo": "fastapi/fastapi",
    "title": "Fix memory leaks in cache",
    "description": "The cache store is leaking reference counts."
  }
  ```
- **Response (200 OK)**:
  ```json
  {
    "issue_summary": "Fix memory leaks in cache",
    "issue_type": "Bugfix",
    "relevant_files": ["backend/dependencies.py"],
    "affected_components": ["Cache System"],
    "implementation_plan": [
      {
        "step": 1,
        "action": "Introduce eviction logic to clean stale references."
      }
    ],
    "complexity": "Medium",
    "confidence": 0.9,
    "verified": true,
    "sources": ["backend/dependencies.py"]
  }
  ```

---

## 3. Visualizations, Graphs, and Metrics

### Get File Dependency Graph
Returns node and edge representations for the file-level import graph.

- **Endpoint**: `GET /api/v1/graph/{owner}/{repo}/full` or `GET /api/graph/{owner}/{repo}/full`
- **Method**: `GET`
- **Query Parameters**:
  - `q`: Optional search keyword to filter nodes.
- **Response (200 OK)**:
  ```json
  {
    "nodes": [
      {
        "id": "fastapi/main.py",
        "label": "main.py",
        "category": "entry_point",
        "highlighted": false,
        "is_focus": false
      }
    ],
    "edges": [
      {
        "source": "fastapi/main.py",
        "target": "fastapi/applications.py",
        "relationship": "imports"
      }
    ],
    "matched_count": 1
  }
  ```

---

### Get Neighborhood Subgraph
Returns only the immediate imports and dependents of a focus node.

- **Endpoint**: `GET /api/v1/graph/{owner}/{repo}/neighbors/{focus_id}` or `GET /api/graph/{owner}/{repo}/neighbors/{focus_id}`
- **Method**: `GET`
- **Response (200 OK)**:
  *(Same schema format as full graph, filtered to neighborhood nodes)*

---

### Trace Paths (Reachability/Blast Radius)
Computes a reachability subgraph using BFS in forward, backward, or bidirectional orientations.

- **Endpoint**: `GET /api/v1/graph/{owner}/{repo}/trace/{focus_id}` or `GET /api/graph/{owner}/{repo}/trace/{focus_id}`
- **Method**: `GET`
- **Query Parameters**:
  - `direction`: `forward` (imports), `backward` (dependents), or `both`.
  - `depth`: Maximum depth search limit (default `6`).
- **Response (200 OK)**:
  *(Returns sub-graph representing reachability paths)*

---

### Get Call Graph Summary
Returns function-level call graph details for the repository.

- **Endpoint**: `GET /api/v1/call-graph/{owner}/{repo}` or `GET /api/call-graph/{owner}/{repo}`
- **Method**: `GET`
- **Response (200 OK)**:
  *(Returns function node call mappings)*

---

### Get Function Blast Radius
Computes the blast radius of changing a specific function.

- **Endpoint**: `GET /api/v1/call-graph/{owner}/{repo}/blast-radius/{function_id}` or `GET /api/call-graph/{owner}/{repo}/blast-radius/{function_id}`
- **Method**: `GET`
- **Response (200 OK)**:
  ```json
  {
    "function_id": "fastapi/main.py:app",
    "affected_functions": ["fastapi/applications.py:FastAPI"],
    "affected_files": ["fastapi/applications.py"],
    "depth": 1,
    "risk_level": "LOW",
    "recursive_cycles": []
  }
  ```

---

### Get Churn Hotspots
Identifies code files with high commit frequency and high topological dependency centrality.

- **Endpoint**: `GET /api/v1/churn/{owner}/{repo}/hotspots` or `GET /api/churn/{owner}/{repo}/hotspots`
- **Method**: `GET`
- **Query Parameters**:
  - `top_n`: Maximum items to return (default `25`).
  - `since_days`: Git history window (default `365`).
- **Response (200 OK)**:
  ```json
  {
    "hotspots": [
      {
        "file_path": "backend/api.py",
        "commit_count": 42,
        "churn_score": 8.4
      }
    ]
  }
  ```

---

## 4. Reports & Engineering Advisor

### Compile Health Report
Triggers report generation or fetches the cached analysis report.

- **Endpoint**: `POST /api/v1/report/{owner}/{repo}/build`
- **Method**: `POST`
- **Response (200 OK)**:
  ```json
  {
    "metadata": {
      "repo_name": "fastapi",
      "owner": "fastapi",
      "total_loc": 25410,
      "generated_at": "2026-07-04T18:00:00Z"
    },
    "scores": {
      "overall": 88,
      "architecture": 90,
      "api": 85,
      "hygiene": 92,
      "churn": 80,
      "readability": 95,
      "grade": "A"
    },
    "refactoring_priorities": [
      "Refactor volatile hotspot module: fastapi/applications.py (churn score: 95.0)"
    ]
  }
  ```

---

### Download Report Files
Downloads the report in static formats.

- **Endpoint**: `GET /api/v1/report/{owner}/{repo}/download`
- **Method**: `GET`
- **Query Parameters**:
  - `format`: `html`, `markdown`, or `pdf`.
- **Response**: File attachment stream (`text/html`, `text/markdown`, or `application/pdf`).

---

### Generate AI Engineering Advisor Report
Analyzes the digital twin structure and continuous monitoring states to generate prioritized advisor recommendations and roadmaps.

- **Endpoint**: `POST /api/v1/repositories/{owner}/{repo}/advisor` or `POST /api/repositories/{owner}/{repo}/advisor`
- **Method**: `POST`
- **Response (200 OK)**:
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

### Get Latest Advisor Report
Fetches the most recently generated advisor report details.

- **Endpoint**: `GET /api/v1/repositories/{owner}/{repo}/advisor/latest` or `GET /api/repositories/{owner}/{repo}/advisor/latest`
- **Method**: `GET`
- **Response (200 OK)**:
  *(Same schema format as Advisor Report)*

---

### Get Engineering Roadmap phases
Fetches the roadmap list from the latest Advisor report.

- **Endpoint**: `GET /api/v1/repositories/{owner}/{repo}/advisor/roadmap` or `GET /api/repositories/{owner}/{repo}/advisor/roadmap`
- **Method**: `GET`
- **Response (200 OK)**:
  *(Returns Roadmap Phases array)*

---

## 5. Execution Planner (AEA²)

### Generate Execution Plan
Constructs an autonomous implementation roadmap from the latest Advisor report.

- **Endpoint**: `POST /api/v1/repositories/{owner}/{repo}/execution-plan` or `POST /api/repositories/{owner}/{repo}/execution-plan`
- **Method**: `POST`
- **Response (200 OK)**:
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

### Get Latest Execution Plan
Fetches the most recently generated execution plan.

- **Endpoint**: `GET /api/v1/repositories/{owner}/{repo}/execution-plan/latest` or `GET /api/repositories/{owner}/{repo}/execution-plan/latest`
- **Method**: `GET`
- **Response (200 OK)**:
  *(Same schema format as Execution Plan)*

---

## 6. Intelligent IDE Workspace snapshot

### Get Full Workspace Snapshot
Returns the consolidated data for all workspace views to power the IDE dashboard panels in a single request.

- **Endpoint**: `GET /api/v1/repositories/{owner}/{repo}/workspace` or `GET /api/repositories/{owner}/{repo}/workspace`
- **Method**: `GET`
- **Query Parameters**:
  - `file`: Optional path of currently open file to contextualize snapshot.
  - `symbol`: Optional currently active symbol.
  - `panel`: Active panel focus name.
- **Response (200 OK)**:
  *(Returns `WorkspaceSnapshot` containing Overview, Explorer, Chat, Findings, Timeline, Monitor, Advisor, and Execution panel structures)*

---

### Get Workspace Panels Individually
Retrieve individual panel snapshots using these sub-routes (available with root, `/api`, and `/api/v1` prefixes):
- `GET /api/v1/repositories/{owner}/{repo}/workspace/overview` (Overview Panel)
- `GET /api/v1/repositories/{owner}/{repo}/workspace/explorer` (Knowledge Graph Explorer)
- `GET /api/v1/repositories/{owner}/{repo}/workspace/findings` (Findings Panel)
- `GET /api/v1/repositories/{owner}/{repo}/workspace/timeline` (Timeline Panel)
- `GET /api/v1/repositories/{owner}/{repo}/workspace/monitor` (Continuous Monitor Panel)
- `GET /api/v1/repositories/{owner}/{repo}/workspace/advisor` (Advisor Panel)
- `GET /api/v1/repositories/{owner}/{repo}/workspace/execution` (Execution Plan Panel)

---

## 7. Health, Status, and Observability

### Server Live Status
- **Endpoint**: `GET /health` or `GET /api/v1/health`
- **Method**: `GET`
- **Response (200 OK)**:
  ```json
  {
    "status": "healthy",
    "backend": "online",
    "llm_provider": "gemini",
    "llm_model": "gemini-2.5-flash",
    "embedding_provider": "BAAI/bge-small-en-v1.5",
    "vector_db": "chromadb"
  }
  ```

---

### Prometheus Metrics
- **Endpoint**: `GET /metrics` or `GET /api/v1/metrics`
- **Method**: `GET`
- **Response (200 OK)**:
  Standard Prometheus text format listing HTTP request counts, active gauges, and processing latencies.
