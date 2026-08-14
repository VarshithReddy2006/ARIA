# Production Operations Guide

This document covers everything needed to deploy, monitor, and operate ARIA in production.

---

## Architecture Summary

The system is a single-process Python application. It does not require external message queues, external caches, or distributed storage. All state is local:

| Storage | Purpose | Location |
|---|---|---|
| ChromaDB | Vector embeddings | `data/chroma_db/` |
| NetworkX graphs | Dependency and call graphs | `data/graphs/` |
| Symbol index | AST symbol tables | `data/symbols/` |
| JSON Snapshot Store | All analysis artifacts | `data/snapshots/` |
| SQLite | Report metadata, migrations | `data/repo_understanding.db` |
| Analysis store | In-memory + disk backup | `data/analysis_store.json` |
| Cloned repos | Source code | `CLONED_REPOS_PATH` |

**Single-instance only.** SQLite and local ChromaDB are not cluster-safe. For multi-instance deployments see [Scalability Limitations](#scalability-limitations).

---

## Production Checklist

### Required environment variables

```env
APP_ENV=production
API_SERVER_HOST=0.0.0.0
API_SERVER_PORT=8001
LLM_PROVIDER=gemini          # or deepseek
GEMINI_API_KEY=<key>         # required when LLM_PROVIDER=gemini
DEEPSEEK_API_KEY=<key>       # required when LLM_PROVIDER=deepseek
GITHUB_TOKEN=<pat>           # recommended; raises GitHub API rate limit to 5000/hr
FRONTEND_URL=https://your-frontend-domain.com
ALLOWED_HOSTS=["your-api-domain.com"]
CLONED_REPOS_PATH=/var/lib/repo_intelligence/cloned_repos
LOG_LEVEL=INFO
LOG_FORMAT=json
RATE_LIMIT_PER_MINUTE=60
API_KEY=<secret-key>         # optional; enables API Key authentication for expensive endpoints
```

### Infrastructure requirements

| | Minimum | Recommended |
|---|---|---|
| CPU | 2 cores | 4 cores |
| RAM | 4 GB | 8 GB |
| Disk | 20 GB | 50 GB |
| Python | 3.10+ | 3.12 |
| OS | Linux, Windows 10+, macOS 12+ | Ubuntu 22.04 |

The BGE embedding model (`BAAI/bge-small-en-v1.5`) uses approximately 500 MB of RAM when loaded.

---

## Startup Behaviour

The startup sequence executes before the server accepts any traffic:

1. `configure_logging()` — structured logging configured (JSON format in production)
2. `run_migrations()` — SQLite schema migrations applied
3. Middlewares registered
4. `_load_analysis_store()` — previously analyzed repositories hydrated from disk
5. `_warmup_services()` — BGE model loaded and warmed; Python Tree-sitter parser warmed
6. `validate_llm_providers()` (inside FastAPI `lifespan`) — health checks all configured providers

**Production fail-fast rules:**
- If all LLM providers are unhealthy → `RuntimeError` raised, server does not start
- If primary provider is unhealthy but fallback is healthy → `ERROR` logged, server starts (ProviderManager handles failover automatically)
- If `GEMINI_API_KEY` / `DEEPSEEK_API_KEY` is missing for the configured provider → `ValueError` raised by Pydantic Settings

Expected startup log sequence:
```
INFO  backend.logging_config: Logging configured level=INFO format=json
INFO  storage.migrations: Migrations applied (or up to date)
INFO  backend.dependencies: GitHub token loaded: True
INFO  backend.dependencies: Loaded 5 repository entries from analysis store
INFO  backend.api: Warming up embedding model and tokenizer...
INFO  backend.api: Embedding model and tokenizer warmed up successfully.
INFO  backend.api: Warming up Python Tree-sitter parser...
INFO  backend.api: Python Tree-sitter parser warmed up successfully.
INFO  backend.startup: Validating LLM providers...
INFO  backend.startup: LLM_PROVIDER_HEALTH provider=gemini model=gemini-2.5-flash healthy=true latency_ms=234
INFO  backend.startup: LLM provider validation complete. healthy_providers=['gemini']
INFO  uvicorn: Application startup complete.
```

---

## Configuration

All configuration is in `backend/settings.py` via Pydantic Settings. Values are read from environment variables (or `.env` in development).

In production, `APP_ENV=production` activates:
- Fail-fast startup when all LLM providers are unhealthy
- Fail-fast when required API keys are missing (`GEMINI_API_KEY` or `DEEPSEEK_API_KEY`)
- Environment variable precedence over `.env` file (OS-injected vars win)

---

## Health Checks

### Static health check

```bash
curl http://localhost:8001/health
```

Use this for load balancer health probes. It returns immediately without making any external calls:

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

### Live provider diagnostic

```bash
curl http://localhost:8001/api/chat/health
```

Makes live calls to all configured LLM providers. Use for operational monitoring, not load balancer probes (has ~200–400 ms latency):

```json
{
  "status": "ok",
  "provider": "gemini",
  "authenticated": true,
  "healthy": true,
  "latency_ms": 234.1,
  "error_type": null,
  "circuit_states": [{"name": "gemini", "circuit_state": "CLOSED", "failure_count": 0}],
  "all_providers": {"gemini": {"healthy": true}, "deepseek": {"healthy": true}},
  "timestamp": 1750000000.0
}
```

`status` values: `ok` (all healthy), `degraded` (fallback only), `unhealthy` (none healthy), `error` (check failed).

### Metrics endpoint

```bash
curl http://localhost:8001/metrics
```

Returns Prometheus-format text. Scrape this with Prometheus or a compatible collector.

The endpoint exposes the following metric categories:
- **HTTP Request Total**: `http_requests_total`
- **Active Requests Gauge**: `active_requests_count`
- **HTTP Latency Summary**: `http_request_duration_seconds` (sum and count)
- **Codebase Build Durations**: `build_duration_seconds`
- **Analysis Task Durations**: `analysis_task_duration_seconds`
- **Cache Statistics**: `cache_hits_total` / `cache_misses_total`

---

## Monitoring

### Key metrics to alert on

| Metric | Alert condition |
|---|---|
| `active_requests_count` | > 50 sustained for > 5 min |
| `http_requests_total{status="429"}` | Spike indicates rate limit being hit |
| `http_requests_total{status="500"}` | Any sustained non-zero value |
| `http_request_duration_seconds_sum / http_request_duration_seconds_count` | Average latency > 2.0s sustained |
| `build_duration_seconds_sum` | Sudden increase may indicate large repos |
| `cache_misses_total` | High ratio to hits may indicate memory pressure |

### Logs to watch

| Log pattern | Meaning |
|---|---|
| `LLM_PROVIDER_HEALTH healthy=false` | Provider credentials or network issue |
| `STARTUP WARNING — No LLM providers are healthy` | Development mode; would be fatal in production |
| `circuit_state=OPEN` in chat/health | Provider failing; fallback in use |
| `CHAT_PIPELINE fallback=True` | LLM fallback renderer being used |
| `Stale or malformed build manifest ignored` | Schema version mismatch; full rebuild will occur |
| `Failed to persist analysis store` | Disk write failure; check available space |

---

## Logging

Set `LOG_FORMAT=json` in production for structured log aggregation:

```json
{
  "timestamp": "2026-06-23T10:00:00Z",
  "level": "INFO",
  "logger": "backend.api",
  "message": "CHAT_PIPELINE",
  "repo": "fastapi/fastapi",
  "intent": "ARCHITECTURE",
  "provider": "gemini",
  "retrieved": "15→5",
  "context_tokens": 3842,
  "llm_ms": 1240,
  "total_ms": 1650,
  "fallback": false,
  "request_id": "req-abc123"
}
```

Every request carries an `X-Request-ID` header (injected by `RequestIdMiddleware`) that appears in all log lines for that request.

---

## Performance

### Observed timings (from production audit)

| Operation | Small repo | Medium repo | Large repo |
|---|---|---|---|
| Fresh build (total) | ~25 s | ~45 s | ~55 s |
| Incremental build | ~0.8 s | ~1.5 s | ~1.8 s |
| Chat first token | ~1.5 s | ~2.0 s | ~2.5 s |
| Chat streaming | ~50 ms/token | ~70 ms/token | ~90 ms/token |
| Architecture graph build | ~1.8 s | ~3 s | ~5 s |
| PR analysis | ~1.5 s | ~2 s | ~2.5 s |
| Report generation (cached) | < 250 ms | < 250 ms | < 250 ms |

### Performance tuning

- Set `CLONED_REPOS_PATH` to a fast local SSD path outside the project tree
- The BGE model loads once at startup — subsequent embedding calls are fast
- Use incremental builds: the `force_rebuild: false` default in `POST /api/analyze` re-uses unchanged embeddings
- The `AnalysisCache` (in-memory, schema-versioned) avoids re-reading artifacts from disk on repeated requests

---

## Security

See [SECURITY.md](../SECURITY.md) for the full security architecture.

Production-specific checklist:
- [ ] `APP_ENV=production`
- [ ] `FRONTEND_URL` set to your actual frontend domain (not `localhost`)
- [ ] `ALLOWED_HOSTS` set to your API domain(s)
- [ ] TLS termination at reverse proxy (nginx, Caddy, Cloudflare)
- [ ] `GITHUB_TOKEN` set with minimum required scopes (`contents:read`, `metadata:read`)
- [ ] Rate limit tuned for your expected traffic (`RATE_LIMIT_PER_MINUTE`)
- [ ] `API_KEY` configured in environment to restrict access to expensive endpoints
- [ ] LLM provider API keys stored securely in a secrets manager (not committed to source control)

---

## Deployment

### Docker (recommended)

```bash
# Production build with named volume persistence
docker compose -f docker-compose.prod.yml up -d --build
```

Named volumes:
- `repo-intel-data` → `/app/data` (ChromaDB, graphs, SQLite, analysis store)
- `repo-intel-cloned` → `/root/.repo_intelligence/cloned_repos`

### Direct (bare metal / VM)

```bash
# Install
pip install -e .

# Build frontend
cd frontend && npm install && npm run build && cd ..

# Start backend
APP_ENV=production python backend/main.py
# or
APP_ENV=production uvicorn backend.api:app --host 0.0.0.0 --port 8001 --workers 1
```

> Use `--workers 1`. The in-memory `AnalysisCache` and `ProviderManager` circuit breakers are process-local. Multiple workers would have independent caches and circuit breakers.

### Startup verification

```bash
# Wait for the server to be ready
curl --retry 10 --retry-delay 2 http://localhost:8001/health

# Confirm provider health
curl http://localhost:8001/api/chat/health | python -m json.tool
```

---

## Rollback

There are no database migrations that cannot be reversed. To roll back:

1. Stop the server
2. Deploy the previous version
3. Start the server — `run_migrations()` is idempotent and safe to re-run
4. The analysis store (`data/analysis_store.json`) is format-stable across versions

If a schema version bump caused a full rebuild and you want to restore the previous artifacts:
- Restore `data/snapshots/` from backup
- Delete `data/snapshots/<repo_name>/build_manifest.json` to force a clean rebuild on next analyze

---

## Recovery

### After a crash mid-analysis

Analysis data is written atomically (tmp → rename). A crash mid-write leaves the previous state intact. On restart:
- `_load_analysis_store()` rehydrates from the last successful write
- The partial analysis is not stored — the next `POST /api/analyze` will redo the run
- ChromaDB vectors for partially indexed files may exist; run `POST /api/repos/repair` to rebuild indexes

### After disk full

1. Free disk space (delete old cloned repos from `CLONED_REPOS_PATH`)
2. Restart the server — it will rehydrate from the existing `data/analysis_store.json`
3. Re-run analysis for any repositories affected during the outage

### After provider failure (all LLM providers down)

1. Chat will use the `FallbackRenderer` — structured retrieval-grounded responses without LLM
2. Resolve the credential issue (update `.env` or secrets manager)
3. Call `POST /api/chat/reload` to reload providers without restarting the server
4. Verify recovery: `GET /api/chat/health`

---

## Failure Modes

| Failure | Detection | Behaviour | Recovery |
|---|---|---|---|
| Primary LLM provider credentials invalid | Startup log: `healthy=false` | Startup continues (dev), fails fast (prod) | Fix key, restart or `POST /api/chat/reload` |
| Primary LLM circuit breaker OPEN | `GET /api/chat/health` circuit_state=OPEN | Automatic failover to secondary provider | Auto-recovers after 60 s |
| All LLM providers unavailable | `GET /api/chat/health` status=unhealthy | FallbackRenderer returns retrieval-grounded response | Fix credentials, call reload |
| ChromaDB unavailable | First retrieval request fails | 500 error on chat/retrieve endpoints | Check disk space, restart |
| GitHub API rate limit exceeded | `rate_limit_remaining=0` in `/api/pr/health` | PR/drift analysis fails with 502 | Wait for reset or use authenticated token |
| Analysis store corrupted | Startup warning: `Could not read analysis store` | Store starts empty; re-analyze repos | Restore from backup or re-analyze |
| Disk full during analysis | `Failed to persist analysis store` in logs | Analysis completes in memory but not persisted | Free disk space, re-analyze |

---

## Known Operational Risks

1. **API Exposure / Access Control**: The API now natively supports optional API key authentication (`API_KEY`) to restrict access to expensive endpoints (like ingestion, indexing, and LLM chat). If disabled, the API is public; mitigate this by securing routes behind a reverse proxy auth layer (OAuth, Basic Auth).
2. **CPU-bound embedding**: A large repository (> 2 000 files) analysis blocks the Python process for several minutes. The server remains responsive via async routing, but embedding runs in a thread pool executor.
3. **Single instance**: In-memory caches (AnalysisCache, ProviderManager) are process-local. Running multiple instances will give inconsistent results. Deploy one instance per environment.
4. **Cloned repo disk growth**: Repositories are cloned to `CLONED_REPOS_PATH` and not automatically deleted. Monitor disk usage and implement a cleanup cron job if needed.
5. **BGE model download on first start**: The `BAAI/bge-small-en-v1.5` model (~130 MB) is downloaded from HuggingFace on first startup. Pre-download it in the Docker build or CI if air-gapped: `python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')"`
