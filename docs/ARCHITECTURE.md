# ARIA System Architecture & Engine Design

## 1. System Components

ARIA (Repo-Intelligence-Agent) is an end-to-end repository intelligence platform combining AST-based code analysis, dependency & call graphs, dense semantic search, and grounded LLM reasoning:

1. **Frontend Tier (Astro + React)**:
   - Modern Astro static site with interactive React components for graph visualization, real-time job progress polling, architecture analysis dashboard, and streaming chat.
2. **API & Orchestration Tier (FastAPI)**:
   - Provides REST & SSE streaming endpoints (`/api/v1/analyze`, `/api/v1/jobs/{job_id}`, `/api/v1/chat`, `/api/v1/call-graph`, `/api/v1/api-surface`, `/api/v1/report`).
3. **Intelligence & Analysis Engine**:
   - **Ingestion & Classification**: `services/ingestion_service.py` & `core/file_classifier.py` for deterministic language detection and file categorization.
   - **AST Parsing & Symbols**: Tree-sitter powered symbol extraction (`services/symbol_service.py`).
   - **Chunking & Embeddings**: Semantic code chunking (`services/chunking_service.py`) and local BGE embeddings (`services/embedding_service.py`).
   - **Vector Database**: Isolated Qdrant store with deterministic point indexing and version-staged publication (`memory/qdrant_store.py`).
   - **Graph Analytics**: Dependency DAGs, Call Graphs, and non-trivial Strongly Connected Component (SCC) cycle analysis (`services/graph_service.py`, `services/call_graph_service.py`).
   - **Health & Scoring**: Architecture Health, Dead Code detection, API surface index, and engineering memory snapshots.
4. **Storage & Persistence**:
   - SQLite (`repo_understanding.db`) with WAL mode for non-blocking concurrent access.
   - JSON Snapshot Store (`storage/snapshot_store.py`) with atomic writes (`write_json_atomic`).

---

## 2. End-to-End Data Flow

```
[GitHub Repository]
       │
       ▼ (git clone / shallow fetch)
[Local Source Tree]
       │
       ├─► [AST Parsing / Symbols] ──► [Symbol Index (symbols/)]
       │
       ├─► [File Chunking] ──────────► [BGE Embeddings (384d)] ──► [Qdrant Vector DB]
       │
       ├─► [Dependency Resolver] ────► [Dependency DiGraph] ────► [Architecture Health]
       │
       ├─► [Call Graph Builder] ─────► [Function Call Graph] ───► [Dead Code Service]
       │
       └─► [API Surface Indexer] ────► [Public Symbols Index] ──► [Report Composer]
                                                                          │
                                                                          ▼
                                                                 [Engineering Memory]
```
