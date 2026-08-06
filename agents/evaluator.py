"""Evaluation Agent module.

Responsible for evaluating agent responses, validating citations,
detecting hallucinations, and scoring answer confidence.

Uses the provider-agnostic LLM layer (DeepSeek V4 Flash via NVIDIA NIM)
instead of the previous Gemini dependency.
"""

import asyncio
import inspect
import json
import logging
from typing import List, Optional, Any

from models.schemas import EvaluationResult
from services.llm import ProviderFactory, BaseLLMProvider
from services.chat.citation_verifier import CitationVerifier, CitationReport

logger = logging.getLogger(__name__)


class EvaluationAgent:
    """Agent that performs quality checks, citation verification, and confidence scoring."""

    def __init__(
        self,
        client: Any = None,  # accepted but ignored (legacy Gemini client arg)
        provider: Optional[BaseLLMProvider] = None,
        citation_verifier: Optional[CitationVerifier] = None,
        *,
        llm_provider: Optional[Any] = None,
    ) -> None:
        """Initialise the EvaluationAgent.

        Args:
            client:            Ignored — kept for call-site compatibility.
            provider:          Optional pre-built provider using the current interface.
            citation_verifier: Optional deterministic citation verifier.
            llm_provider:      Legacy provider alias supporting ``generate_json``.
        """
        if client is not None:
            logger.debug(
                "EvaluationAgent: 'client' parameter is ignored — using LLM provider."
            )
        self._provider = provider or llm_provider or ProviderFactory.get_provider()
        self._citation_verifier = citation_verifier or CitationVerifier()

    def evaluate_claim(
        self,
        answer: str,
        retrieved_chunks: List[str],
        repo_files: List[str],
    ) -> dict[str, Any]:
        """Evaluate a legacy claim payload through the current response evaluator."""
        source_contexts = [
            {
                "metadata": {
                    "file_path": (
                        repo_files[index] if index < len(repo_files) else "unknown_path"
                    )
                },
                "content": chunk,
            }
            for index, chunk in enumerate(retrieved_chunks)
        ]
        return self.evaluate_response(
            prompt="Evaluate the generated claim.",
            response=answer,
            source_contexts=source_contexts,
        ).model_dump()

    def evaluate_response(
        self,
        prompt: str,
        response: str,
        source_contexts: List[Any],
    ) -> EvaluationResult:
        """Evaluate whether the agent response matches the retrieved context.

        Synchronous wrapper around the async implementation so existing
        synchronous callers continue to work unchanged.

        Args:
            prompt:          The original question or prompt.
            response:        The generated response to evaluate.
            source_contexts: Code/document contexts used by the generating agent.

        Returns:
            An EvaluationResult model.
        """
        try:
            try:
                loop = asyncio.get_running_loop()
                is_running = loop.is_running()
            except RuntimeError:
                is_running = False

            if is_running:
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        self._evaluate_async(prompt, response, source_contexts),
                    )
                    return future.result()
            else:
                return asyncio.run(
                    self._evaluate_async(prompt, response, source_contexts)
                )
        except Exception as exc:
            logger.error(
                "EvaluationAgent.evaluate_response failed: %s", exc, exc_info=True
            )
            return _fallback_eval(source_contexts)

    async def _evaluate_async(
        self,
        prompt: str,
        response: str,
        source_contexts: List[Any],
    ) -> EvaluationResult:
        if not source_contexts:
            return EvaluationResult(
                citations_valid=False,
                hallucination_detected=True,
                confidence_score=0.0,
                feedback="No source context was provided for evaluation.",
                retrieved_chunks=0,
                used_chunks=0,
                coverage_percentage=0.0,
                unsupported_claims=["No source context provided"],
                unknown_files=[],
                chunk_citations=[],
            )

        # Format source snippets
        formatted_sources = []
        for idx, src in enumerate(source_contexts):
            if isinstance(src, str):
                formatted_sources.append(f"Snippet [{idx}]:\n{src}")
            elif isinstance(src, dict):
                meta = src.get("metadata", {})
                file_path = meta.get("file_path", "unknown_path")
                chunk_id = meta.get("chunk_id", idx)
                content = src.get("content", "")
                formatted_sources.append(
                    f"Snippet [{idx}] - File: {file_path} (Chunk: {chunk_id}):\n{content}"
                )
            else:
                formatted_sources.append(f"Snippet [{idx}]:\n{str(src)}")

        formatted_sources_str = "\n\n".join(formatted_sources)

        system_instruction = (
            "You are an expert code quality judge and code auditor. "
            "Your task is to evaluate a generated developer answer against retrieved codebase context snippets. "
            "Analyse formatting, accuracy, and file pathways carefully. "
            "You must return your response as a strict JSON object matching the requested schema."
        )

        eval_prompt = (
            f"User Question: {prompt}\n\n"
            f"Generated Answer: {response}\n\n"
            f"Retrieved Codebase Context Snippets (indexed 0 to {len(source_contexts) - 1}):\n"
            f"=======================\n"
            f"{formatted_sources_str}\n"
            f"=======================\n\n"
            f"Perform the following evaluations:\n"
            f"1. Check if the answer references any file path NOT present in the retrieved snippets (unknown files).\n"
            f"2. Check if the answer makes any claims/implementations not supported by the retrieved snippets (unsupported claims).\n"
            f"3. Identify which snippets (by index 0 to {len(source_contexts) - 1}) were actually used to construct the answer.\n"
            f"4. Verify that citations are valid (i.e. file paths exist in the context snippets).\n"
            f"5. Rate overall confidence in the answer from 0.0 to 1.0 based on factual correctness against context.\n\n"
            f"Return a JSON object conforming exactly to this structure:\n"
            f"{{\n"
            f'  "citations_valid": true,\n'
            f'  "hallucination_detected": false,\n'
            f'  "confidence_score": 0.9,\n'
            f'  "feedback": "detailed reason summary",\n'
            f'  "unsupported_claims": [],\n'
            f'  "unknown_files": [],\n'
            f'  "used_chunks_indices": [0, 1],\n'
            f'  "chunk_citations": [\n'
            f'    {{"file_path": "string", "chunk_id": "0", "reason": "string"}}\n'
            f"  ]\n"
            f"}}\n"
        )

        # 1. Deterministic Citation Verification (R-005)
        citation_report = self._citation_verifier.verify_answer(
            answer=response,
            source_contexts=source_contexts,
        )

        try:
            if hasattr(self._provider, "generate_json"):
                raw = self._provider.generate_json(
                    eval_prompt,
                    system_instruction=system_instruction,
                )
                if inspect.isawaitable(raw):
                    raw = await raw
            else:
                raw = await self._provider.generate(
                    prompt=eval_prompt,
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                )
            data = raw if isinstance(raw, dict) else json.loads(raw)
        except Exception as exc:
            logger.error("LLM evaluation call failed: %s", exc, exc_info=True)
            return _fallback_eval(source_contexts, citation_report)

        # Fail-closed default False for LLM response
        llm_citations_valid = bool(data.get("citations_valid", False))
        # Enforce deterministic verifier: citations_valid is True ONLY IF deterministic verifier succeeded
        citations_valid = citation_report.citations_valid and llm_citations_valid

        hallucination_detected = bool(data.get("hallucination_detected", False)) or (len(citation_report.unresolved) > 0)
        confidence_score = max(0.0, min(1.0, float(data.get("confidence_score", 0.0 if not citations_valid else 1.0))))
        feedback = str(data.get("feedback", citation_report.feedback))
        unsupported_claims = list(data.get("unsupported_claims", []))

        # Merge unknown files from verifier and LLM
        unknown_files = list(
            set([c.file_path for c in citation_report.unresolved] + list(data.get("unknown_files", [])))
        )

        used_chunks_indices = list(data.get("used_chunks_indices", []))
        chunk_citations = [
            {
                "file_path": c.file_path,
                "chunk_id": "verified" if c.status == "verified" else "unresolved",
                "reason": c.reason or "verified",
            }
            for c in citation_report.verified + citation_report.unresolved
        ]

        retrieved_count = len(source_contexts)
        unique_used = {i for i in used_chunks_indices if 0 <= i < retrieved_count}
        used_count = len(unique_used)
        coverage = (
            (used_count / retrieved_count * 100.0) if retrieved_count > 0 else 0.0
        )

        return EvaluationResult(
            citations_valid=citations_valid,
            hallucination_detected=hallucination_detected,
            confidence_score=confidence_score,
            feedback=feedback,
            retrieved_chunks=retrieved_count,
            used_chunks=used_count,
            coverage_percentage=round(coverage, 2),
            unsupported_claims=unsupported_claims,
            unknown_files=unknown_files,
            chunk_citations=chunk_citations,
        )


def _fallback_eval(
    source_contexts: List[Any],
    citation_report: Optional[CitationReport] = None,
) -> EvaluationResult:
    """Fail closed while retaining deterministic citation findings when available."""
    unresolved = citation_report.unresolved if citation_report is not None else []
    return EvaluationResult(
        citations_valid=False,
        hallucination_detected=True,
        confidence_score=0.0,
        feedback="Evaluation failed.",
        retrieved_chunks=len(source_contexts),
        used_chunks=0,
        coverage_percentage=0.0,
        unsupported_claims=[],
        unknown_files=[citation.file_path for citation in unresolved],
        chunk_citations=[
            {
                "file_path": citation.file_path,
                "chunk_id": "unresolved",
                "reason": citation.reason or "unresolved",
            }
            for citation in unresolved
        ],
    )
