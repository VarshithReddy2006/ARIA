# ARIA Production-Readiness Specification

## 1. Architecture Overview & Lifecycle

ARIA executes repository intelligence via an asynchronous, decoupled serverless architecture:

```
Browser / Frontend (Astro)
       │
       ▼
ASGI Web Application (FastAPI) ───[ 202 Accepted + job_id ]───► Frontend Polls
       │
       ▼
Background Worker Dispatch (JobExecutor)
       │
       ├─► 01 CLONE: GitHub repo fetch / shallow clone
       ├─► 02 DETECT: Tech stack & file categorization (production, test, doc, example)
       ├─► 03 PARSE: Tree-sitter & AST change detection
       ├─► 04 EMBED & INDEX: BGE embeddings (256 outer batch / 128 inner) + Qdrant
       ├─► 05 GRAPH: Symbol index & DAG cycle detection (non-trivial SCC only)
       ├─► 06 PRE-BUILD: Call Graph & API Surface indices
       ├─► 07 REPORT: Health report & Engineering memory snapshot
       └─► 08 PERSIST: data_volume.commit() & atomic store hydration
```

---

## 2. Job State Machine

Jobs transition through explicit deterministic states:
- `QUEUED`: Request validated and dispatched to worker queue.
- `RUNNING`: Worker actively executing analysis steps (`clone` → `detect` → `parse` → `chunk` → `embed` → `index` → `graphs` → `report` → `answer`).
- `COMPLETED`: Analysis finished, volume committed, artifacts ready.
- `FAILED`: Analysis aborted due to a non-recoverable error. Diagnostics captured in `error` field.
- `CANCELLED`: Analysis terminated by user/system request.

---

## 3. Persistence & Concurrency Safety

1. **Atomic Writes**: All JSON snapshots and store records are written via `write_json_atomic` (`.tmp` file + `os.replace`), preventing corrupted reads during concurrent updates.
2. **Repository Locking**: In-process and distributed `repository_lock(repo_name)` prevents parallel analysis runs from clobbering identical repository files.
3. **SQLite WAL Mode**: SQLite runs with `PRAGMA journal_mode=WAL;` and `PRAGMA busy_timeout=5000;`, enabling concurrent non-blocking reads from web instances while workers write.
4. **Volume Synchronization**:
   - Worker calls `data_volume.commit()` immediately after finishing analysis.
   - Web ASGI middleware reloads volume (`data_volume.reload()`) on incoming API requests.

---

## 4. Idempotency & Resumability

1. **Vector Point IDs**:
   - Vector points are indexed in Qdrant with deterministic UUIDv5 identifiers:
     $$\text{point\_id} = \text{uuid5}(\text{NAMESPACE\_DNS}, \text{repo\_name} + \text{"\_"} + \text{version} + \text{"\_"} + \text{path} + \text{"\_"} + \text{chunk\_id})$$
   - Re-analyzing the same repository performs an idempotent upsert (`client.upsert`) without creating duplicate records.
2. **Atomic Version Publishing**:
   - New embeddings are staged under version tag $V_{new}$. Upon completion, $V_{new}$ is published and $V_{old}$ points are purged atomically.

---

## 5. Structured Telemetry

Every phase boundary emits structured JSON logs:
```json
{
  "event": "analysis_phase",
  "repo": "fastapi/fastapi",
  "job_id": "9f2bb4a127b84d2a927695a34ce77c77",
  "phase": "embed",
  "status": "running",
  "items_processed": 10496,
  "items_total": 12459,
  "elapsed_seconds": 160.5,
  "memory_mb": 468.2,
  "request_id": "e2f7bf77-55d0-4574-b6bd-1ec6cbf51bf6",
  "timestamp": "2026-08-22T01:45:00.000000Z"
}
```
