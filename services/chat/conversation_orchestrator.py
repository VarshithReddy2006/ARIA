"""Conversation Orchestrator — Drives step-by-step conversation-aware retrieval flow.

Pipeline Priority:
  1. Load ConversationContext for session
  2. Execute ExplicitEntityResolver (Highest Priority)
  3. Execute TopicSwitchDetector
  4. Execute FollowUpDetector
  5. Manage Topic Confidence (boost / decay / switch) & Disable Previous Context Boosts
  6. Execute QueryRewriter (resolves against canonical query memory & NavigationGraph)
  7. Invoke Retrieval & Contextual Ranking Boosts
  8. Update ConversationContext with turn & canonical query
  9. Emit structured JSON debug logs when DEBUG_CHAT=true

Ensures explicit entity mentions always take immediate priority over previous conversation context.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from services.chat.conversation_context import ConversationContext
from services.chat.conversation_memory import (
    ConversationMemoryStore,
    conversation_memory,
)
from services.chat.conversation_settings import ConversationSettings
from services.chat.explicit_entity_resolver import (
    ExplicitEntityResolver,
    ExplicitEntityResult,
)
from services.chat.followup_detector import FollowUpDetector, FollowUpResult
from services.chat.query_rewriter import QueryRewriter
from services.chat.topic_switch_detector import TopicSwitchDetector, TopicSwitchResult

logger = logging.getLogger("services.chat.conversation_orchestrator")


@dataclass(frozen=True, slots=True)
class OrchestrationResult:
    """Immutable result bundle from Orchestrator pre-retrieval phase."""

    context: ConversationContext
    explicit_entity_result: ExplicitEntityResult
    followup_result: FollowUpResult
    topic_switch_result: TopicSwitchResult
    raw_question: str
    rewritten_query: str
    disable_previous_boosts: bool
    stage_latencies_ms: Dict[str, float]


class ConversationOrchestrator:
    """Core orchestrator executing conversation-aware retrieval pipeline steps."""

    def __init__(
        self,
        memory_store: Optional[ConversationMemoryStore] = None,
        settings: Optional[ConversationSettings] = None,
        explicit_resolver: Optional[ExplicitEntityResolver] = None,
        followup_detector: Optional[FollowUpDetector] = None,
        topic_switch_detector: Optional[TopicSwitchDetector] = None,
        query_rewriter: Optional[QueryRewriter] = None,
    ) -> None:
        self.memory_store = memory_store or conversation_memory
        self.settings = settings or ConversationSettings.default()
        self.explicit_resolver = explicit_resolver or ExplicitEntityResolver()
        self.followup_detector = followup_detector or FollowUpDetector()
        self.topic_switch_detector = topic_switch_detector or TopicSwitchDetector()
        self.query_rewriter = query_rewriter or QueryRewriter()

    def process_incoming_query(
        self,
        repo_name: str,
        session_id: str,
        question: str,
    ) -> OrchestrationResult:
        """Execute pre-retrieval pipeline stages in strict priority order."""
        latencies: Dict[str, float] = {}
        t0 = time.perf_counter()

        # 1. Load Session & Context
        session = self.memory_store.get_or_create(repo_name, session_id)
        context = session.get_context()
        latencies["context_load"] = (time.perf_counter() - t0) * 1000.0

        # 2. Execute ExplicitEntityResolver (Highest Priority)
        t_ee = time.perf_counter()
        explicit_res = self.explicit_resolver.resolve(question)
        latencies["explicit_entity_resolution"] = (time.perf_counter() - t_ee) * 1000.0

        # 3. Execute TopicSwitchDetector
        t_ts = time.perf_counter()
        switch_res = self.topic_switch_detector.detect(question, context, explicit_res)
        latencies["topic_switch_detection"] = (time.perf_counter() - t_ts) * 1000.0

        # 4. Execute FollowUpDetector
        t_f = time.perf_counter()
        if explicit_res.has_explicit_entity:
            # Explicit entity introduced -> not a follow-up query on previous topic
            followup_res = FollowUpResult(
                is_followup=False, confidence=0.0, followup_kind="NONE"
            )
        else:
            followup_res = self.followup_detector.detect(question, context)
        latencies["followup_detection"] = (time.perf_counter() - t_f) * 1000.0

        disable_previous_boosts = False

        # 5. Manage Topic Confidence & State Transition
        if switch_res.is_topic_switch or explicit_res.has_explicit_entity:
            target_f = switch_res.target_file or explicit_res.target_file
            target_s = (
                switch_res.target_symbol
                or explicit_res.target_symbol
                or explicit_res.entity_name
            )
            context = context.with_topic_switch(
                new_file=target_f,
                new_symbol=target_s,
                settings=self.settings,
            )
            disable_previous_boosts = True
        elif followup_res.is_followup:
            context = context.with_same_topic_boost(settings=self.settings)
        elif context.current_file and not followup_res.is_followup:
            # Query is not a follow-up and not an explicit topic switch -> decay confidence
            context = context.with_unrelated_decay(settings=self.settings)

        # 6. Execute QueryRewriter
        t_rw = time.perf_counter()
        rewritten_q = self.query_rewriter.rewrite(
            question, context, followup_res, switch_res, explicit_res
        )
        latencies["query_rewriting"] = (time.perf_counter() - t_rw) * 1000.0

        # Save active context back to session
        session.set_context(context)

        return OrchestrationResult(
            context=context,
            explicit_entity_result=explicit_res,
            followup_result=followup_res,
            topic_switch_result=switch_res,
            raw_question=question,
            rewritten_query=rewritten_q,
            disable_previous_boosts=disable_previous_boosts,
            stage_latencies_ms=latencies,
        )

    def finalize_turn(
        self,
        repo_name: str,
        session_id: str,
        raw_question: str,
        rewritten_query: str,
        answer: str,
        retrieved_chunks: List[Dict[str, Any]],
        retrieval_metrics: Dict[str, Any],
        orchestration_result: OrchestrationResult,
    ) -> ConversationContext:
        """Finalize turn: update context memory, store canonical resolved query, and emit structured debug logs."""
        session = self.memory_store.get_or_create(repo_name, session_id)
        current_ctx = session.get_context()

        # Extract files and symbols from retrieved chunks
        files_mentioned: List[str] = []
        symbols_mentioned: List[str] = []
        for c in retrieved_chunks:
            meta = c.get("metadata", {})
            f = meta.get("file_path")
            if f and f not in files_mentioned:
                files_mentioned.append(f)
            syms = meta.get("matched_symbols", "")
            if syms:
                for s in syms.split(","):
                    clean_s = s.split("(")[0].strip()
                    if clean_s and clean_s not in symbols_mentioned:
                        symbols_mentioned.append(clean_s)

        # Update turns and context
        session.add_turn("user", raw_question)
        session.add_turn("assistant", answer[:2000])

        updated_ctx = current_ctx.with_turn(
            question=raw_question,
            answer=answer[:2000],
            resolved_query=rewritten_query,
            files_mentioned=tuple(files_mentioned),
            symbols_mentioned=tuple(symbols_mentioned),
            settings=self.settings,
        )
        session.set_context(updated_ctx)

        # Emit Machine-Readable JSON Debug Metadata if DEBUG_CHAT=true
        if self.settings.debug_chat or logger.isEnabledFor(logging.DEBUG):
            self.emit_debug_metadata(
                session_id=session_id,
                raw_question=raw_question,
                rewritten_query=rewritten_query,
                orchestration_result=orchestration_result,
                updated_context=updated_ctx,
                retrieved_chunks=retrieved_chunks,
                retrieval_metrics=retrieval_metrics,
            )

        return updated_ctx

    def emit_debug_metadata(
        self,
        session_id: str,
        raw_question: str,
        rewritten_query: str,
        orchestration_result: OrchestrationResult,
        updated_context: ConversationContext,
        retrieved_chunks: List[Dict[str, Any]],
        retrieval_metrics: Dict[str, Any],
    ) -> None:
        """Emit machine-readable JSON debug logs."""
        top_files = [
            c.get("metadata", {}).get("file_path")
            for c in retrieved_chunks
            if c.get("metadata", {}).get("file_path")
        ]
        top_symbols = [
            c.get("metadata", {}).get("matched_symbols")
            for c in retrieved_chunks
            if c.get("metadata", {}).get("matched_symbols")
        ]

        debug_payload = {
            "conversation_id": session_id,
            "original_query": raw_question,
            "rewritten_query": rewritten_query,
            "explicit_entity": {
                "has_explicit_entity": orchestration_result.explicit_entity_result.has_explicit_entity,
                "entity_type": orchestration_result.explicit_entity_result.entity_type,
                "entity_name": orchestration_result.explicit_entity_result.entity_name,
            },
            "follow_up": {
                "is_followup": orchestration_result.followup_result.is_followup,
                "confidence": orchestration_result.followup_result.confidence,
                "kind": orchestration_result.followup_result.followup_kind,
            },
            "topic_switch": {
                "is_topic_switch": orchestration_result.topic_switch_result.is_topic_switch,
                "kind": orchestration_result.topic_switch_result.switch_kind,
                "target_file": orchestration_result.topic_switch_result.target_file,
            },
            "topic_confidence": updated_context.topic_confidence,
            "disable_previous_boosts": orchestration_result.disable_previous_boosts,
            "conversation_context": {
                "current_repo": updated_context.current_repo,
                "current_file": updated_context.current_file,
                "current_symbol": updated_context.current_symbol,
                "current_module": updated_context.current_module,
                "recently_discussed_files": updated_context.recently_discussed_files[
                    :5
                ],
            },
            "ranking_boosts": {
                "current_file": self.settings.current_file_boost
                if not orchestration_result.disable_previous_boosts
                else 0.0,
                "current_symbol": self.settings.current_symbol_boost
                if not orchestration_result.disable_previous_boosts
                else 0.0,
                "current_module": self.settings.current_module_boost
                if not orchestration_result.disable_previous_boosts
                else 0.0,
                "repository": self.settings.repository_boost,
                "recent_file": self.settings.recent_file_boost,
            },
            "retrieval_tier": retrieval_metrics.get(
                "retrieval_tier", "ENTIRE_REPOSITORY"
            ),
            "retrieved_files": top_files[:5],
            "retrieved_symbols": top_symbols[:5],
            "latency": orchestration_result.stage_latencies_ms,
        }
        logger.info("[RETRIEVAL_DEBUG] %s", json.dumps(debug_payload))
