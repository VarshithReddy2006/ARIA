# Repository Chat v2 — Architecture & Developer Guide

## Overview

Repository Chat v2 transforms the chat subsystem from a simple embedding search
into a full intelligence layer that leverages every analysis capability built
into ARIA.

**Before v2:**
```
User → Embedding Search → LLM → Answer
```

**After v2:**
```
User
 ↓
Conversation Memory (pronoun resolution, follow-up context)
 ↓
Intent Detector (rule-based, zero-latency)
 ↓
Intent Router (Architecture / Call Graph / Symbol / API Surface / Impact / Reading Order)
 ↓
Repository Intelligence Layer (structured data from graph/symbol services)
 ↓
Weighted Retrieval (top-15 → tier-weight → rerank → dedup → top-5)
 ↓
Context Builder (dynamic token budget, priority slots, 3k–5k tokens)
 ↓
Provider Manager (circuit breaker, multi-provider fallback)
 ↓
Gemini / DeepSeek
 ↓
Professional Structured Answer
```

---

## Component Reference

### `services/chat/` — Chat Intelligence Package

| Module | Responsibility |
|---|---|
| `conversation_memory.py` | Per-session entity/file tracking, pronoun resolution, 30-min TTL |
| `intent_detector.py` | Rule-based intent classification (9 intents, zero LLM calls) |
| `intent_router.py` | Dispatches intents to structured repository intelligence services |
| `retrieval.py` | Lockfile exclusion, tier weighting, BGE asymmetric prefix, reranking |
| `context_builder.py` | Token budgeting (3k–5k tokens), priority slot assembly |
| `provider_manager.py` | Circuit breaker, multi-provider fallback, streaming retry safety |
| `retrieval_pipeline.py` | **Authoritative pipeline** — `retrieve()` + `retrieve_stream()` |
| `fallback_renderer.py` | Professional fallback UX when LLM unavailable |
| `observability.py` | Structured `CHAT_PIPELINE` log per request |
| `performance.py` | Per-stage timing report |

### `backend/routers/chat.py` — Thin Router

The chat router is now ~100 lines. It:
1. Validates the request with Pydantic
2. Delegates entirely to `get_retrieval_pipeline().retrieve_stream()`
3. Returns the SSE StreamingResponse

No prompt building. No LLM calls. No retry logic.

---

## Intent Types

| Intent | Trigger Keywords (examples) | Routes To |
|---|---|---|
| `ARCHITECTURE` | "architecture", "overview", "entry point", "structure" | `ArchitectureService.get_summary()` |
| `CIRCULAR_DEPENDENCY` | "circular", "cycle", "cyclic", "import loop" | `ArchitectureService.get_summary()` (cycle data) |
| `API_SURFACE` | "api surface", "endpoints", "routes", "exports" | `APISurfaceService.load()` |
| `CALL_GRAPH` | "who calls", "call graph", "callers of", "called by" | `CallGraphService.get_summary()` |
| `SYMBOL` | "where is defined", "find definition", "definition of" | `SymbolService.find_definition()` |
| `READING_ORDER` | "reading order", "onboard", "start reading", "new developer" | `ReadingOrderService.get_reading_order()` |
| `IMPACT_ANALYSIS` | "blast radius", "what breaks", "impact", "affected files" | `ImpactAnalysisService.analyze()` |
| `GENERAL_QA` | "how does", "what does", "explain", "describe" | Vector search only |
| `UNKNOWN` | (no match) | Vector search only |

---

## Retrieval Pipeline

### Tier Weights

| Tier | Weight | File Patterns |
|---|---|---|
| 1 | 1.0 | `backend/`, `services/`, `models/`, `frontend/src/`, `*.py`, `*.ts` |
| 2 | 0.6 | `README.*`, `docs/`, `*.md`, `*.rst` |
| 3 | 0.2 | `requirements.txt`, `pyproject.toml`, `package.json`, `*.toml` |
| 4 | 0.0 | lock files, `node_modules/`, `dist/`, `coverage/`, binaries |

### Reranking Score

```
score = (0.5 × similarity + 0.3 × token_overlap) × tier_weight
```

Where:
- `similarity = 1 / (1 + chroma_distance)`
- `token_overlap` = normalised query-content keyword overlap (no ML model)
- `tier_weight` from table above

### BGE Asymmetric Embeddings

Queries are prefixed with `"Represent this sentence for searching relevant passages: "`.
Documents are indexed without any prefix (as BGE asymmetric design requires).

---

## Conversation Memory

Sessions are keyed by `(repo_name, session_id)`. Default session_id is `"default"`.

The session tracks:
- Last 20 conversation turns
- Up to 10 recently mentioned code entities (PascalCase identifiers)
- Up to 10 recently mentioned file paths
- Last detected intent

**Pronoun resolution** operates on patterns like:
- `"What calls it?"` → `"What calls UserService?"` (when `UserService` was last discussed)
- `"Explain this"` → `"Explain UserService"` (when entity is tracked)

Sessions expire after 30 minutes of inactivity.

---

## Provider Manager

The ProviderManager wraps all LLM providers with:

1. **Priority ordering** — primary provider tried first, secondary as fallback
2. **Circuit breaker** — opens after 3 failures, retries after 60s
3. **Streaming retry safety (Phase 9)**:
   - 0 tokens yielded → safe to retry with next provider
   - Tokens already yielded → **never retry** (prevents duplicate output)
   - Terminates gracefully with a short user-visible message

---

## Fallback UX

When the LLM is unavailable, the response shows:
1. A clear "AI unavailable" notice (no provider names, no stack traces)
2. Structured intelligence from IntentRouter (if available)
3. Relevant files list (from vector search)
4. Suggested retry action

Raw code is never dumped. Chunks are never shown in full.

---

## Answer Format

Every successful LLM response is guided toward this structure:

1. **Summary** — 1–2 sentence direct answer
2. **Explanation** — technical detail with file/function references
3. **Evidence** — code excerpts (only from context)
4. **Repository Insights** — patterns, risks, architecture notes
5. **Relevant Files** — bullet list
6. **Suggested Next Questions** — 2–3 natural follow-ups

---

## Observability

Every request emits a `CHAT_PIPELINE` log line:

```
CHAT_PIPELINE | repo=owner/repo intent=ARCHITECTURE provider=gemini \
  retrieved=15→5 context_tokens=3842 llm_ms=1240 total_ms=1650 fallback=False
```

And a `CHAT_TRACE` JSON debug log with full stage breakdown including:
- similarity scores, rerank scores, discarded chunks
- per-slot context breakdown (architecture / structured_intelligence / code / docs / config)
- provider circuit state, fallback reason

---

## Backward Compatibility

| Component | Status |
|---|---|
| `POST /api/chat` SSE contract | ✅ Identical (same event schema) |
| `POST /api/issues/map` | ✅ Unchanged |
| `RetrievalService.retrieve_and_answer()` | ✅ Shim delegates to pipeline |
| Frontend `ChatInterface.tsx` | ✅ Zero changes required |
| All existing tests | ✅ All pass (535 total) |

The `session_id` field is a new **optional** field in `ChatRequest` (defaults to `"default"`).
Existing clients that don't send it continue to work correctly.

---

## Files Modified

| File | Change |
|---|---|
| `backend/routers/chat.py` | Rewritten as thin router (delegates to pipeline) |
| `backend/dependencies.py` | Added `get_retrieval_pipeline()` factory |
| `services/retrieval_service.py` | Replaced impl with shim delegating to pipeline |
| `services/chat/__init__.py` | New package |
| `services/chat/conversation_memory.py` | New |
| `services/chat/intent_detector.py` | New |
| `services/chat/intent_router.py` | New |
| `services/chat/retrieval.py` | New |
| `services/chat/context_builder.py` | New |
| `services/chat/provider_manager.py` | New |
| `services/chat/retrieval_pipeline.py` | New (authoritative pipeline) |
| `services/chat/fallback_renderer.py` | New |
| `services/chat/observability.py` | New |
| `services/chat/performance.py` | New |
| `tests/test_retrieval_v2.py` | New (68 tests) |
| `docs/repository-chat-v2.md` | New (this file) |
