# API Guide — ARIA v1.5.0

The ARIA API is built on FastAPI and operates within the **API Layer** of the Repository Intelligence Architecture (RIA). It exposes HTTP REST endpoints, server-sent events (SSE) progress streams, and Prometheus metrics.

All endpoints are versioned under `/api/v1/` while maintaining legacy root paths (`/api/...`) for 100% backward compatibility.

---

## Observability & Metrics

### `GET /metrics` or `GET /api/v1/metrics`
Exposes application health metrics, active requests, build durations, individual analysis durations, and cache hit/miss stats.

#### Sample Scrape Response:
```text
# HELP http_requests_total Total number of HTTP requests.
# TYPE http_requests_total counter
http_requests_total{method="GET",path="/health",status="200"} 12.0

# HELP active_requests_count Total number of active requests.
# TYPE active_requests_count gauge
active_requests_count 0.0

# HELP cache_hits_total Total number of analysis cache hits.
# TYPE cache_hits_total counter
cache_hits_total{cache_key="symbols"} 3.0
```

---

## Key REST Endpoints

### 1. `POST /api/v1/analyze` or `POST /api/analyze`
Triggers code checkout, syntax parsing, and AI embeddings indexing. Streams SSE progress JSON.
- **Request Body**:
  ```json
  {
    "url": "https://github.com/owner/repo",
    "branch": "main",
    "model": "deepseek-ai/deepseek-v4-flash"
  }
  ```

### 2. `GET /api/v1/architecture/{owner}/{repo}/graph` or `GET /api/architecture/{owner}/{repo}/graph`
Exposes the repository dependency graph in a React-Flow-friendly node/edge schema.
- **Response**:
  ```json
  {
    "nodes": [
      { "id": "main.py", "type": "file" }
    ],
    "edges": [
      { "id": "e1", "source": "main.py", "target": "utils.py" }
    ]
  }
  ```

### 3. `GET /health` or `GET /api/v1/health`
Returns detailed application settings validation, LLM providers, and storage path health check details.

### 4. `POST /api/v1/report/{owner}/{repo}/build`
Generates or updates the Repository Intelligence Report for the specified repository and returns the complete report model JSON.
- **Response**: `ReportDataModel`

### 5. `GET /api/v1/report/{owner}/{repo}/summary`
Fetches a brief summary of the latest health report (overall score, grade, generated timestamp).

### 6. `GET /api/v1/report/{owner}/{repo}/download`
Downloads the compiled repository intelligence report.
- **Query Parameters**:
  - `format` (optional): `html` (default), `pdf`, or `markdown`.
- **Response**: Binary stream with `Content-Disposition: attachment; filename="..."` header.

### 7. `GET /api/v1/repositories/{owner}/{repo}/workspace`
 consolidated snaphot endpoint for all IDE panel datasets.
