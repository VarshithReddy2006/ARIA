"""Chat Observability — Phase 12.

Structured logging for every stage of the Repository Chat v2 pipeline.
Makes debugging simple without touching application logic.

Each pipeline execution emits a single structured log line at INFO level
using a consistent schema so logs can be parsed by any log aggregator.

Logged fields:
  repo           — repository identifier
  session_id     — conversation session
  intent         — detected intent
  router_decision— whether structured intelligence was available
  retrieved_files— files returned by vector search
  initial_count  — raw chunk count before filtering
  final_count    — chunk count after reranking
  similarity_scores — top-5 similarity scores
  rerank_scores  — top-5 reranked scores
  discarded      — chunks removed by tier/dedup filtering
  context_size   — estimated token count sent to LLM
  llm_latency_ms — time waiting for LLM response
  provider       — which provider was used
  fallback_reason— why fallback was triggered (if any)
  total_ms       — end-to-end pipeline latency
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineTrace:
    """Accumulates timing and metadata across one chat pipeline execution."""

    repo_name: str
    session_id: str = "default"
    question_length: int = 0
    intent: str = "UNKNOWN"
    router_has_data: bool = False
    router_elapsed_ms: float = 0.0

    # Retrieval metrics
    initial_retrieved: int = 0
    after_exclusion: int = 0
    after_dedup: int = 0
    final_returned: int = 0
    embed_ms: float = 0.0
    search_ms: float = 0.0
    rerank_ms: float = 0.0

    # Deterministic diagnostics
    entity_requested: Optional[str] = None
    resolved_file: Optional[str] = None
    resolved_symbol: Optional[str] = None
    symbol_start_line: Optional[int] = None
    symbol_end_line: Optional[int] = None
    coverage_percent: Optional[int] = None
    chunks_selected: int = 0

    # Top-chunk scores for quality inspection
    top_similarity_scores: List[float] = field(default_factory=list)
    top_rerank_scores: List[float] = field(default_factory=list)
    discarded_chunks: List[str] = field(default_factory=list)

    # Context
    retrieved_files: List[str] = field(default_factory=list)
    context_estimated_tokens: int = 0
    context_slot_breakdown: Dict[str, int] = field(default_factory=dict)

    # LLM
    llm_latency_ms: float = 0.0
    provider_used: str = ""
    fallback_triggered: bool = False
    fallback_reason: str = ""
    tokens_streamed: int = 0

    # Wall time
    _start_time: float = field(default_factory=time.perf_counter, init=False)
    total_ms: float = 0.0

    def from_retrieval_metrics(self, metrics: Dict[str, Any]) -> "PipelineTrace":
        """Populate retrieval fields from the metrics dict returned by intelligent_retrieve."""
        self.initial_retrieved = metrics.get("initial_retrieved", 0)
        self.after_exclusion = metrics.get("after_exclusion", 0)
        self.after_dedup = metrics.get("after_dedup", 0)
        self.final_returned = metrics.get("final_returned", 0)
        self.embed_ms = metrics.get("embed_ms", 0.0)
        self.search_ms = metrics.get("search_ms", 0.0)
        self.rerank_ms = metrics.get("rerank_ms", 0.0)
        self.entity_requested = metrics.get("entity_requested")
        self.resolved_file = metrics.get("matched_file")
        self.resolved_symbol = metrics.get("matched_symbol")
        self.symbol_start_line = metrics.get("symbol_start_line")
        self.symbol_end_line = metrics.get("symbol_end_line")
        self.coverage_percent = metrics.get("symbol_coverage")
        self.chunks_selected = metrics.get("final_returned", 0)
        return self

    def from_chunks(self, chunks: List[Dict[str, Any]]) -> "PipelineTrace":
        """Populate score fields from the final chunk list."""
        self.top_similarity_scores = [
            round(c.get("_similarity", 0.0), 4) for c in chunks[:5]
        ]
        self.top_rerank_scores = [
            round(c.get("_rerank_score", 0.0), 4) for c in chunks[:5]
        ]
        self.retrieved_files = [
            c.get("metadata", {}).get("file_path", "") for c in chunks
        ]
        return self

    def finish(self) -> "PipelineTrace":
        """Mark the trace as complete and compute total_ms."""
        self.total_ms = (time.perf_counter() - self._start_time) * 1000
        return self


class ChatObservability:
    """Emits structured pipeline traces to the application log.

    Usage::

        obs = ChatObservability()
        trace = PipelineTrace(repo_name="owner/repo", session_id="abc")
        # ... fill in trace fields as pipeline stages complete ...
        obs.emit(trace)
    """

    def emit(self, trace: PipelineTrace) -> None:
        """Emit the completed trace as a structured INFO log line."""
        payload = {
            "event": "chat_pipeline",
            "repo": trace.repo_name,
            "session": trace.session_id,
            "intent": trace.intent,
            "router_has_data": trace.router_has_data,
            "router_ms": round(trace.router_elapsed_ms, 1),
            # Retrieval
            "retrieved_initial": trace.initial_retrieved,
            "retrieved_final": trace.final_returned,
            "discarded_exclusion": trace.initial_retrieved - trace.after_exclusion,
            "discarded_dedup": trace.after_exclusion - trace.after_dedup,
            "retrieved_files": trace.retrieved_files,
            "similarity_top5": trace.top_similarity_scores,
            "rerank_top5": trace.top_rerank_scores,
            # Timing
            "embed_ms": round(trace.embed_ms, 1),
            "search_ms": round(trace.search_ms, 1),
            "rerank_ms": round(trace.rerank_ms, 1),
            "llm_ms": round(trace.llm_latency_ms, 1),
            "total_ms": round(trace.total_ms, 1),
            # Context
            "context_tokens": trace.context_estimated_tokens,
            "context_slots": trace.context_slot_breakdown,
            # LLM
            "provider": trace.provider_used,
            "tokens_streamed": trace.tokens_streamed,
            "fallback": trace.fallback_triggered,
            "fallback_reason": trace.fallback_reason,
            # Deterministic
            "deterministic_entity": trace.entity_requested,
            "resolved_file": trace.resolved_file,
            "resolved_symbol": trace.resolved_symbol,
            "symbol_start_line": trace.symbol_start_line,
            "symbol_end_line": trace.symbol_end_line,
            "coverage_percent": trace.coverage_percent,
        }

        logger.info(
            "CHAT_PIPELINE | repo=%s intent=%s provider=%s "
            "retrieved=%d→%d context_tokens=%d llm_ms=%.0f total_ms=%.0f "
            "fallback=%s",
            trace.repo_name,
            trace.intent,
            trace.provider_used or "none",
            trace.initial_retrieved,
            trace.final_returned,
            trace.context_estimated_tokens,
            trace.llm_latency_ms,
            trace.total_ms,
            trace.fallback_triggered,
        )

        # JSON structured log at DEBUG level for log aggregators
        logger.debug("CHAT_TRACE %s", json.dumps(payload))


# Module-level singleton
chat_observability = ChatObservability()
