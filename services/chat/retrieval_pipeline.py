"""Retrieval Pipeline — Phase 1 (authoritative implementation).

This is the single, canonical implementation of the Repository Chat pipeline.
It replaces the duplicated logic previously spread across:
  - backend/routers/chat.py  (streaming path)
  - services/retrieval_service.py  (non-streaming path)

Both paths now delegate here. chat.py becomes a thin router.

Pipeline stages:
  1.  Session memory lookup + pronoun resolution
  2.  Intent detection
  3.  Intent routing → structured repository intelligence
  4.  Intelligent vector retrieval (top-15 → rerank → dedup → top-5)
  5.  Context assembly with token budgeting
  6.  LLM generation via ProviderManager (with circuit breaker)
  7.  Conversation memory update
  8.  Observability emit

Public API:
  retrieve(...)          → Dict  (for non-streaming callers / tests / REST)
  retrieve_stream(...)   → AsyncIterator[str]  (for SSE endpoints)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

from services.arch_context_service import ArchContextService
from services.embedding_service import EmbeddingService
from memory.chroma_store import ChromaStore

from .conversation_memory import ConversationMemoryStore, conversation_memory
from .conversation_orchestrator import ConversationOrchestrator
from .intent_detector import IntentDetector, RuleBasedIntentDetector
from .intent_router import IntentRouter, RepositoryIntelligence
from .retrieval import intelligent_retrieve, detect_deterministic_retrieval
from .context_builder import ContextBuilder
from .provider_manager import ProviderManager
from .fallback_renderer import render_fallback, render_mid_stream_termination
from .citation_verifier import CitationVerifier
from .observability import ChatObservability, PipelineTrace, chat_observability
from .followup_engine import FollowUpEngine

logger = logging.getLogger(__name__)


class RetrievalPipeline:
    """The authoritative Repository Chat v2 pipeline.

    All constructor arguments are injectable for testability.
    The production instance (created in dependencies.py) is shared globally.
    """

    def __init__(
        self,
        embedding_service: EmbeddingService,
        chroma_store: ChromaStore,
        arch_context_service: Optional[ArchContextService] = None,
        intent_detector: Optional[IntentDetector] = None,
        intent_router: Optional[IntentRouter] = None,
        context_builder: Optional[ContextBuilder] = None,
        provider_manager: Optional[ProviderManager] = None,
        memory_store: Optional[ConversationMemoryStore] = None,
        observability: Optional[ChatObservability] = None,
        symbol_service: Optional[Any] = None,
        orchestrator: Optional[ConversationOrchestrator] = None,
        citation_verifier: Optional[CitationVerifier] = None,
        followup_engine: Optional[FollowUpEngine] = None,
    ) -> None:
        self.embedding_service = embedding_service
        self.chroma_store = chroma_store
        self.arch_context_service = arch_context_service or ArchContextService()
        self.intent_detector = intent_detector or RuleBasedIntentDetector()
        self.intent_router = intent_router or IntentRouter()
        self.context_builder = context_builder or ContextBuilder()
        self.provider_manager = provider_manager or ProviderManager()
        self.memory_store = memory_store or conversation_memory
        self.observability = observability or chat_observability
        self.symbol_service = symbol_service or getattr(
            self.intent_router, "_symbols", None
        )
        self.orchestrator = orchestrator or ConversationOrchestrator(
            memory_store=self.memory_store
        )
        self.citation_verifier = citation_verifier or CitationVerifier()
        self.followup_engine = followup_engine or FollowUpEngine()

    @staticmethod
    def _session_id(session_id: Optional[str]) -> str:
        return (
            session_id.strip()
            if session_id and session_id.strip()
            else uuid.uuid4().hex
        )

    def _verify_answer(
        self, answer: str, source_contexts: List[Any]
    ) -> tuple[bool, Dict[str, Any]]:
        try:
            report = self.citation_verifier.verify_answer(
                answer, source_contexts=source_contexts
            )
            return report.citations_valid, report.model_dump()
        except Exception as exc:
            logger.warning("Citation verification failed: %s", exc)
            return False, {
                "citations_valid": False,
                "feedback": "Citation verification failed.",
            }

    # ------------------------------------------------------------------
    # Non-streaming path (for RetrievalService compatibility + tests)
    # ------------------------------------------------------------------

    async def retrieve(
        self,
        repo_name: str,
        question: str,
        session_id: Optional[str] = None,
        history: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """Generate a complete answer (non-streaming).

        Returns the same schema as the legacy RetrievalService so existing
        callers are unaffected:
            {
                "answer": str,
                "sources": List[str],
                "confidence": int,
                "verified": bool,
                "evaluation": {},
                "intent": str,
                "fallback_mode": bool,
            }
        """
        session_id = self._session_id(session_id)
        trace = PipelineTrace(repo_name=repo_name, session_id=session_id)
        # Called for its side effect: ensures the session row exists before the
        # orchestrator reads conversation history below.
        self.memory_store.get_or_create(repo_name, session_id)

        # 1. Orchestration & Query Rewriting
        orch_res = self.orchestrator.process_incoming_query(
            repo_name, session_id, question
        )
        resolved_question = orch_res.rewritten_query
        trace.question_length = len(resolved_question)

        # 2. Intent detection
        intent_result = self.intent_detector.detect(resolved_question)
        trace.intent = intent_result.intent.value

        # Check for deterministic match
        det_match = await asyncio.to_thread(
            detect_deterministic_retrieval,
            resolved_question,
            repo_name,
            self.chroma_store,
            self.symbol_service,
        )

        if det_match and det_match.get("clarification_needed"):
            choices = det_match["choices"]
            cand = det_match["candidate"]
            msg = (
                f"Multiple production files named '{cand}' exist in the repository:\n"
                + "\n".join(f"- `{f}`" for f in choices)
                + "\n\nPlease clarify which file you would like to retrieve."
            )
            citation_valid, citation_report = self._verify_answer(msg, [])
            return {
                "answer": msg,
                "sources": choices,
                "confidence": 98,
                "verified": citation_valid,
                "citation_report": citation_report,
                "evaluation": {},
                "intent": intent_result.intent.value,
                "fallback_mode": False,
            }

        # 3. Intent routing
        if det_match:
            # Bypass intent router for deterministic retrieval
            intelligence = RepositoryIntelligence(intent=intent_result.intent)
        else:
            intelligence = self.intent_router.route(
                repo_name, resolved_question, intent_result
            )
        trace.router_has_data = intelligence.has_data
        trace.router_elapsed_ms = intelligence.router_elapsed_ms

        # 4. Vector/Deterministic retrieval
        try:
            chunks, ret_metrics = await asyncio.to_thread(
                intelligent_retrieve,
                question=resolved_question,
                repo_name=repo_name,
                embedding_service=self.embedding_service,
                chroma_store=self.chroma_store,
                symbol_service=self.symbol_service,
                conversation_context=orch_res.context,
                conversation_settings=self.orchestrator.settings,
                disable_previous_boosts=orch_res.disable_previous_boosts,
            )
            trace.from_retrieval_metrics(ret_metrics)
            trace.from_chunks(chunks)
        except Exception as exc:
            logger.error("RetrievalPipeline.retrieve: retrieval failed: %s", exc)
            chunks = []
            ret_metrics = {}
            trace.fallback_triggered = True
            trace.fallback_reason = f"retrieval_error: {exc}"

        # 5. Architecture context
        arch_ctx = self.arch_context_service.get_context(repo_name)
        arch_block = arch_ctx.to_prompt_block() if arch_ctx.available else ""

        # 6. Build context
        t_cb = time.perf_counter()
        built = self.context_builder.build(
            repo_name=repo_name,
            question=resolved_question,
            arch_context_block=arch_block,
            structured_intelligence=intelligence.structured_context,
            code_chunks=chunks,
            conversation_history=history,
            intent_name=intent_result.intent.value,
            deterministic_file_path=ret_metrics.get("matched_file")
            if ret_metrics.get("deterministic")
            else None,
        )
        context_build_ms = (time.perf_counter() - t_cb) * 1000
        non_llm_latency_ms = (time.perf_counter() - trace._start_time) * 1000
        trace.context_estimated_tokens = built.estimated_tokens
        logger.info(
            "[CHAT_CONTEXT] repo=%s session=%s estimated_tokens=%d slots=%s",
            repo_name,
            session_id,
            built.estimated_tokens,
            list(built.slot_breakdown.keys()),
        )
        logger.info(
            "CHAT_LATENCY | embedding=%.1fms retrieval/ranking=%.1fms context_building=%.1fms non_llm=%.1fms",
            ret_metrics.get("embed_ms", 0.0),
            ret_metrics.get("search_ms", 0.0) + ret_metrics.get("rerank_ms", 0.0),
            context_build_ms,
            non_llm_latency_ms,
        )

        # 7. LLM generation
        normalised_history = self._normalise_history(history or [])
        answer = ""
        provider_used = ""
        fallback_triggered = False
        fallback_reason = ""

        t_llm = time.perf_counter()
        try:
            answer, provider_used = await self.provider_manager.generate(
                prompt=built.prompt,
                system_instruction=built.system_instruction,
                history=normalised_history,
            )
            trace.llm_latency_ms = (time.perf_counter() - t_llm) * 1000
            trace.provider_used = provider_used
        except Exception as exc:
            trace.llm_latency_ms = (time.perf_counter() - t_llm) * 1000
            fallback_triggered = True
            fallback_reason = str(exc)
            logger.warning("RetrievalPipeline.retrieve: all providers failed: %s", exc)
            answer = render_fallback(
                question=resolved_question,
                structured_intelligence=intelligence.structured_context,
                chunks=chunks,
                source_files=built.source_files,
                fallback_reason="provider_failure",
                provider_error=str(exc),
            )

        trace.fallback_triggered = fallback_triggered
        trace.fallback_reason = fallback_reason
        citation_valid, citation_report = self._verify_answer(answer, chunks)

        # 8. Update conversation memory
        if not fallback_triggered:
            self.orchestrator.finalize_turn(
                repo_name=repo_name,
                session_id=session_id,
                raw_question=question,
                rewritten_query=resolved_question,
                answer=answer,
                retrieved_chunks=chunks,
                retrieval_metrics=ret_metrics,
                orchestration_result=orch_res,
            )

        # 9. Collect sources & Synthesize Follow-ups
        all_sources = sorted(set(intelligence.source_files + built.source_files))
        follow_ups = self.followup_engine.synthesize_follow_ups(
            repo_name=repo_name,
            question=resolved_question,
            answer=answer,
            intent=intent_result.intent.value,
            code_chunks=chunks,
            source_files=all_sources,
            conversation_history=history,
            structured_context=intelligence.structured_context,
        )

        trace.finish()
        self.observability.emit(trace)

        return {
            "answer": answer,
            "sources": all_sources,
            "confidence": ret_metrics.get("confidence", 85)
            if not fallback_triggered
            else 0,
            "verified": citation_valid and not fallback_triggered,
            "citation_report": citation_report,
            "evaluation": {},
            "intent": intent_result.intent.value,
            "fallback_mode": fallback_triggered,
            "follow_ups": follow_ups,
        }

    # ------------------------------------------------------------------
    # Streaming path (for /api/chat SSE endpoint)
    # ------------------------------------------------------------------

    async def retrieve_stream(
        self,
        repo_name: str,
        question: str,
        session_id: Optional[str] = None,
        history: Optional[List[Dict]] = None,
    ) -> AsyncIterator[str]:
        """Stream answer tokens as SSE-formatted strings.

        Yields SSE data strings in the format:
          data: {"text": "..."}\n\n
          data: {"sources": [...], "confidence": N, ...,"status": "done"}\n\n

        This is the ONLY streaming implementation in the codebase.
        """
        session_id = self._session_id(session_id)
        trace = PipelineTrace(repo_name=repo_name, session_id=session_id)
        # Called for its side effect: ensures the session row exists before the
        # orchestrator reads conversation history below.
        self.memory_store.get_or_create(repo_name, session_id)

        # ── 1. Orchestration & Query Rewriting ────────────────────────────
        orch_res = self.orchestrator.process_incoming_query(
            repo_name, session_id, question
        )
        resolved_question = orch_res.rewritten_query
        trace.question_length = len(resolved_question)

        # ── 2. Intent detection ──────────────────────────────────────────
        intent_result = self.intent_detector.detect(resolved_question)
        trace.intent = intent_result.intent.value

        # Check for deterministic match
        det_match = await asyncio.to_thread(
            detect_deterministic_retrieval,
            resolved_question,
            repo_name,
            self.chroma_store,
            self.symbol_service,
        )

        if det_match and det_match.get("clarification_needed"):
            choices = det_match["choices"]
            cand = det_match["candidate"]
            msg = (
                f"Multiple production files named '{cand}' exist in the repository:\n"
                + "\n".join(f"- `{f}`" for f in choices)
                + "\n\nPlease clarify which file you would like to retrieve."
            )
            citation_valid, citation_report = self._verify_answer(msg, [])
            yield self._sse({"text": msg})
            yield self._sse(
                {
                    "sources": choices,
                    "confidence": 98,
                    "verified": citation_valid,
                    "citation_report": citation_report,
                    "fallback_mode": False,
                    "intent": intent_result.intent.value,
                    "status": "done",
                }
            )
            return

        # ── 3. Intent routing ────────────────────────────────────────────
        if det_match:
            # Bypass intent router for deterministic retrieval
            intelligence = RepositoryIntelligence(intent=intent_result.intent)
        else:
            intelligence = self.intent_router.route(
                repo_name, resolved_question, intent_result
            )
        trace.router_has_data = intelligence.has_data
        trace.router_elapsed_ms = intelligence.router_elapsed_ms

        # ── 4. Vector/Deterministic retrieval ────────────────────────────
        chunks: List[Dict] = []
        try:
            chunks, ret_metrics = await asyncio.to_thread(
                intelligent_retrieve,
                question=resolved_question,
                repo_name=repo_name,
                embedding_service=self.embedding_service,
                chroma_store=self.chroma_store,
                symbol_service=self.symbol_service,
                conversation_context=orch_res.context,
                conversation_settings=self.orchestrator.settings,
                disable_previous_boosts=orch_res.disable_previous_boosts,
            )
            trace.from_retrieval_metrics(ret_metrics)
            trace.from_chunks(chunks)
        except Exception as exc:
            logger.error(
                "RetrievalPipeline.stream: retrieval failed "
                "repo=%s exc_type=%s fallback_triggered=true",
                repo_name,
                type(exc).__name__,
                exc_info=True,
            )
            ret_metrics = {}
            trace.fallback_triggered = True
            trace.fallback_reason = f"retrieval_error: {exc}"

        # ── 5. Architecture context ──────────────────────────────────────
        arch_ctx = self.arch_context_service.get_context(repo_name)
        arch_block = arch_ctx.to_prompt_block() if arch_ctx.available else ""

        # ── 6. Build context ─────────────────────────────────────────────
        t_cb = time.perf_counter()
        built = self.context_builder.build(
            repo_name=repo_name,
            question=resolved_question,
            arch_context_block=arch_block,
            structured_intelligence=intelligence.structured_context,
            code_chunks=chunks,
            conversation_history=history,
            intent_name=intent_result.intent.value,
            deterministic_file_path=ret_metrics.get("matched_file")
            if ret_metrics.get("deterministic")
            else None,
        )
        context_build_ms = (time.perf_counter() - t_cb) * 1000
        non_llm_latency_ms = (time.perf_counter() - trace._start_time) * 1000
        trace.context_estimated_tokens = built.estimated_tokens
        trace.context_slot_breakdown = built.slot_breakdown

        logger.info(
            "CHAT_STREAM_LATENCY | embedding=%.1fms retrieval/ranking=%.1fms context_building=%.1fms non_llm=%.1fms",
            ret_metrics.get("embed_ms", 0.0),
            ret_metrics.get("search_ms", 0.0) + ret_metrics.get("rerank_ms", 0.0),
            context_build_ms,
            non_llm_latency_ms,
        )

        normalised_history = self._normalise_history(history or [])

        # ── 7. Stream from LLM ───────────────────────────────────────────
        full_text = ""
        tokens_streamed = 0
        provider_used = ""
        fallback_triggered = False
        fallback_reason = ""

        if trace.fallback_triggered:
            # Retrieval failed — go straight to fallback
            fallback_triggered = True
            fallback_reason = trace.fallback_reason
        else:
            t_llm = time.perf_counter()
            try:
                async for token, pname in self.provider_manager.stream(
                    prompt=built.prompt,
                    system_instruction=built.system_instruction,
                    history=normalised_history,
                ):
                    full_text += token
                    tokens_streamed += 1
                    provider_used = pname
                    yield self._sse({"text": token})

                trace.llm_latency_ms = (time.perf_counter() - t_llm) * 1000
                trace.tokens_streamed = tokens_streamed
                trace.provider_used = provider_used

                if full_text.strip() == "":
                    fallback_triggered = True
                    fallback_reason = "empty_completion"
                    fallback_text = render_fallback(
                        question=resolved_question,
                        structured_intelligence=intelligence.structured_context,
                        chunks=chunks,
                        source_files=built.source_files,
                        fallback_reason="empty_completion",
                        provider_error="Provider returned an empty completion.",
                    )
                    full_text = fallback_text
                    yield self._sse({"text": fallback_text})

            except asyncio.CancelledError:
                # Client disconnected cleanly
                trace.llm_latency_ms = (time.perf_counter() - t_llm) * 1000
                trace.finish()
                self.observability.emit(trace)
                return

            except Exception as exc:
                trace.llm_latency_ms = (time.perf_counter() - t_llm) * 1000
                fallback_triggered = True
                fallback_reason = str(exc)

                logger.error(
                    "RetrievalPipeline.stream: provider failure "
                    "repo=%s intent=%s tokens_streamed=%d provider_used=%s "
                    "fallback_reason=%s exc_type=%s",
                    repo_name,
                    trace.intent,
                    tokens_streamed,
                    provider_used,
                    fallback_reason,
                    type(exc).__name__,
                    exc_info=True,
                )

                if tokens_streamed > 0 and full_text.strip():
                    # Phase 9: mid-stream failure with existing text — append graceful termination
                    termination_msg = render_mid_stream_termination(tokens_streamed)
                    yield self._sse({"text": termination_msg})
                else:
                    # 0 tokens or whitespace only — render full fallback with actual error
                    fallback_text = render_fallback(
                        question=resolved_question,
                        structured_intelligence=intelligence.structured_context,
                        chunks=chunks,
                        source_files=built.source_files,
                        fallback_reason="provider_failure",
                        provider_error=str(exc),
                    )
                    full_text = fallback_text
                    yield self._sse({"text": fallback_text})

        # Emit fallback if triggered before LLM started (retrieval failure)
        if fallback_triggered and not full_text.strip():
            fallback_text = render_fallback(
                question=resolved_question,
                structured_intelligence=intelligence.structured_context,
                chunks=chunks,
                source_files=built.source_files,
                fallback_reason=fallback_reason,
                provider_error=fallback_reason,
            )
            full_text = fallback_text
            yield self._sse({"text": fallback_text})

        citation_valid, citation_report = self._verify_answer(full_text, chunks)

        # ── 8. Update conversation memory ────────────────────────────────
        if not fallback_triggered and full_text.strip():
            self.orchestrator.finalize_turn(
                repo_name=repo_name,
                session_id=session_id,
                raw_question=question,
                rewritten_query=resolved_question,
                answer=full_text,
                retrieved_chunks=chunks,
                retrieval_metrics=ret_metrics,
                orchestration_result=orch_res,
            )

        # ── 9. Collect sources + Synthesize Follow-ups + terminal done event ──
        all_sources = sorted(set(intelligence.source_files + built.source_files))
        confidence = ret_metrics.get("confidence", 85) if not fallback_triggered else 0

        follow_ups = self.followup_engine.synthesize_follow_ups(
            repo_name=repo_name,
            question=resolved_question,
            answer=full_text,
            intent=intent_result.intent.value,
            code_chunks=chunks,
            source_files=all_sources,
            conversation_history=history,
            structured_context=intelligence.structured_context,
        )

        trace.fallback_triggered = fallback_triggered
        trace.fallback_reason = fallback_reason
        trace.finish()
        self.observability.emit(trace)

        try:
            yield self._sse(
                {
                    "sources": all_sources,
                    "confidence": confidence,
                    "verified": citation_valid and not fallback_triggered,
                    "citation_report": citation_report,
                    "fallback_mode": fallback_triggered,
                    "intent": intent_result.intent.value,
                    "follow_ups": follow_ups,
                    "status": "done",
                }
            )
        finally:
            logger.info(
                "CHAT_STREAM_COMPLETED repo=%s session=%s intent=%s follow_ups=%d",
                repo_name,
                session_id,
                intent_result.intent.value,
                len(follow_ups),
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _sse(payload: Dict[str, Any]) -> str:
        return f"data: {json.dumps(payload)}\n\n"

    @staticmethod
    def _normalise_history(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalise frontend history format to provider-compatible format."""
        normalised = []
        for turn in history:
            role = turn.get("role", "user")
            if role == "model":
                role = "assistant"

            # Handle parts-based format (Gemini frontend format)
            parts = turn.get("parts", [])
            if parts:
                content = parts[0] if isinstance(parts[0], str) else str(parts[0])
            elif "content" in turn:
                content = turn["content"]
            else:
                continue

            if content:
                normalised.append({"role": role, "content": content})
        return normalised
