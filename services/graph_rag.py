"""Graph-RAG Orchestration Service.

Implements the ChatPipeline coordinating Retrieval, Reasoning, PromptBuilder,
TokenBudgetManager, LLM Providers, GroundingValidator, and Tracing Metrics.
"""

import re
import time
import logging
from typing import Any, Dict, List, Optional, AsyncIterator
from pydantic import BaseModel, Field

from models.retrieval import RepositoryRetrievalContext, ContextReference
from models.reasoning import ReasoningResult, Hypothesis, Contradiction, Recommendation
from models.graph_rag import GraphRAGResult
from services.llm import ProviderFactory

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompt Document & Builder & Renderer (Model-Agnostic Prompt Abstraction)
# ---------------------------------------------------------------------------


class PromptDocument(BaseModel):
    """An intermediate structured representation of the compiled prompt content."""

    system_instruction: str
    question: str
    policy: str
    references: List[ContextReference] = Field(default_factory=list)
    hypotheses: List[Hypothesis] = Field(default_factory=list)
    contradictions: List[Contradiction] = Field(default_factory=list)
    recommendations: List[Recommendation] = Field(default_factory=list)


class PromptBuilder:
    """Constructs a model-agnostic PromptDocument from context and reasoning."""

    def build_document(
        self, context: RepositoryRetrievalContext, reasoning: ReasoningResult
    ) -> PromptDocument:
        system_instruction = (
            "You are an expert AI software architect. Answer the user's question based strictly "
            "on the provided repository evidence, reasoning hypotheses, and recommendations. "
            "Always cite your sources using stable IDs in format [stable_id](file:///path/to/file) or [stable_id](file:///path/to/file#Lline). "
            "Do not hallucinate references. If evidence is lacking, explain what is missing."
        )

        return PromptDocument(
            system_instruction=system_instruction,
            question=context.question,
            policy=reasoning.policy,
            references=context.references,
            hypotheses=reasoning.hypotheses,
            contradictions=reasoning.contradictions,
            recommendations=reasoning.recommendations,
        )


class PromptRenderer:
    """Renders a structured PromptDocument into vendor-specific string prompts."""

    def render(self, doc: PromptDocument) -> str:
        prompt_parts = []

        # 1. Question section
        prompt_parts.append(f"## QUESTION\n{doc.question}\n")

        # 2. Reasoning Policy
        prompt_parts.append(f"## POLICY\nActive reasoning policy: {doc.policy}\n")

        # 3. Engineering Hypotheses
        if doc.hypotheses:
            prompt_parts.append("## EVALUATED HYPOTHESES")
            for h in doc.hypotheses:
                prompt_parts.append(f"- [{h.id}] {h.description} (Status: {h.status})")
            prompt_parts.append("")

        # 4. Detected Contradictions
        if doc.contradictions:
            prompt_parts.append("## DETECTED CONTRADICTIONS / WARNINGS")
            for c in doc.contradictions:
                prompt_parts.append(
                    f"- WARNING [{c.id}]: {c.description} (Severity: {c.severity})"
                )
            prompt_parts.append("")

        # 5. Proposed Recommendations
        if doc.recommendations:
            prompt_parts.append("## PROPOSED RECOMMENDATIONS")
            for r in doc.recommendations:
                prompt_parts.append(
                    f"- [{r.id}] Type: {r.type} targeting '{r.target}' (Priority: {r.priority}, Effort: {r.estimated_effort})"
                )
            prompt_parts.append("")

        # 6. Repository Context References
        prompt_parts.append("## CODEBASE CONTEXT REFERENCES")
        for ref in doc.references:
            prompt_parts.append(f"### REFERENCE [{ref.id}] (Type: {ref.type})")
            prompt_parts.append(f"Source: {ref.source}")
            if ref.properties:
                prompt_parts.append("Properties:")
                for k, v in ref.properties.items():
                    prompt_parts.append(f"  {k}: {v}")
            if ref.snippet:
                prompt_parts.append(f"Snippet:\n```\n{ref.snippet}\n```")
            prompt_parts.append("")

        return "\n".join(prompt_parts)


# ---------------------------------------------------------------------------
# Token Budget Manager & Grounding Validator
# ---------------------------------------------------------------------------


class TokenBudgetManager:
    """Prunes and ranks ContextReferences in a PromptDocument to fit within token limits."""

    def optimize(self, doc: PromptDocument, max_tokens: int) -> PromptDocument:
        # Estimate overall size using string length divided by 4 as token approximation
        # Base overhead (system instruction, hypotheses, recommendations)
        overhead_str = (
            doc.system_instruction
            + doc.question
            + doc.policy
            + str(doc.hypotheses)
            + str(doc.contradictions)
            + str(doc.recommendations)
        )
        base_tokens = len(overhead_str) // 4

        if base_tokens >= max_tokens:
            # Budget is extremely small, return document with empty references
            return PromptDocument(
                system_instruction=doc.system_instruction,
                question=doc.question,
                policy=doc.policy,
                references=[],
                hypotheses=doc.hypotheses,
                contradictions=doc.contradictions,
                recommendations=doc.recommendations,
            )

        # Rank references by score
        type_weights = {
            "repository": 10,
            "component": 9,
            "health": 8,
            "compliance": 8,
            "file": 6,
            "symbol": 4,
            "document": 2,
        }

        scored_refs = []
        for ref in doc.references:
            score = float(type_weights.get(ref.type, 0))
            # Boost if verified by reasoning hypotheses
            for hyp in doc.hypotheses:
                if ref.id in hyp.supporting_evidence:
                    score += 5.0

            # Boost if referenced by a recommendation target
            for rec in doc.recommendations:
                if ref.id == rec.target:
                    score += 4.0

            scored_refs.append((score, ref))

        # Sort descending by score
        scored_refs.sort(key=lambda x: x[0], reverse=True)

        # Fill budget incrementally
        remaining_budget = max_tokens - base_tokens
        accepted_refs = []
        current_ref_tokens = 0

        for score, ref in scored_refs:
            # Render a single reference to estimate its size
            ref_str = (
                f"### REFERENCE [{ref.id}] (Type: {ref.type})\nSource: {ref.source}\n"
            )
            if ref.snippet:
                ref_str += ref.snippet
            ref_tokens = len(ref_str) // 4

            if current_ref_tokens + ref_tokens <= remaining_budget:
                accepted_refs.append(ref)
                current_ref_tokens += ref_tokens
            else:
                # Truncate rest
                break

        return PromptDocument(
            system_instruction=doc.system_instruction,
            question=doc.question,
            policy=doc.policy,
            references=accepted_refs,
            hypotheses=doc.hypotheses,
            contradictions=doc.contradictions,
            recommendations=doc.recommendations,
        )


class GroundingValidator:
    """Scans LLM output to verify citations and reference list presence against the context."""

    def validate(
        self, answer: str, context: RepositoryRetrievalContext
    ) -> tuple[str, List[str]]:
        # Match citations like [EVD-001](...) or [ref_id](...) or [id]
        # Look for square bracket patterns
        brackets_pattern = re.compile(r"\[([^\]]+)\]")
        citations_found = brackets_pattern.findall(answer)

        # Fetch valid reference IDs in context
        valid_ids = {ref.id for ref in context.references}

        validated_citations = []
        for citation in citations_found:
            # Clean citation string
            cit_id = citation.strip()
            if cit_id in valid_ids and cit_id not in validated_citations:
                validated_citations.append(cit_id)

        # If answer mentions filenames or symbols without brackets, validate them
        for ref in context.references:
            name = ref.properties.get("name") or ref.properties.get("path")
            if name and name in answer and ref.id not in validated_citations:
                # Auto-append matching context references
                validated_citations.append(ref.id)
        return answer, validated_citations


# ---------------------------------------------------------------------------
# Chat Pipeline & Orchestrator Service
# ---------------------------------------------------------------------------


class ChatPipeline:
    """Execution pipeline coordinating RAG + ERE + Prompting + LLM Generation + Validation."""

    def __init__(
        self,
        retrieval_engine: Optional[Any] = None,
        reasoning_engine: Optional[Any] = None,
        builder: Optional[PromptBuilder] = None,
        renderer: Optional[PromptRenderer] = None,
        budget_manager: Optional[TokenBudgetManager] = None,
        validator: Optional[GroundingValidator] = None,
    ) -> None:
        self.retrieval_engine = retrieval_engine
        self.reasoning_engine = reasoning_engine
        self.builder = builder or PromptBuilder()
        self.renderer = renderer or PromptRenderer()
        self.budget_manager = budget_manager or TokenBudgetManager()
        self.validator = validator or GroundingValidator()

    def get_retrieval_engine(self) -> Any:
        return self.retrieval_engine

    def get_reasoning_engine(self) -> Any:
        return self.reasoning_engine

    async def execute(
        self,
        repo_name: str,
        question: str,
        policy: str,
        options: Dict[str, Any],
    ) -> GraphRAGResult:
        metrics = {}

        # 1. Structural Retrieval
        t0 = time.perf_counter()
        retrieval_engine = self.get_retrieval_engine()
        context = await retrieval_engine.retrieve(repo_name, question, policy)
        metrics["retrieval_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)

        # 2. Engineering Reasoning
        t0 = time.perf_counter()
        reasoning_engine = self.get_reasoning_engine()
        reasoning_res = reasoning_engine.reason(repo_name, question, policy, context)
        metrics["reasoning_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)

        # 3. Prompt Building & Token Budget Manager
        t0 = time.perf_counter()
        doc = self.builder.build_document(context, reasoning_res)
        token_limit = options.get("token_limit", 8000)
        optimized_doc = self.budget_manager.optimize(doc, token_limit)
        rendered_prompt = self.renderer.render(optimized_doc)
        metrics["prompt_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)

        # 4. LLM Generation Call
        t0 = time.perf_counter()
        provider = ProviderFactory.get_provider()
        answer = await provider.generate(
            prompt=rendered_prompt,
            system_instruction=optimized_doc.system_instruction,
        )
        metrics["llm_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)

        # 5. Grounding Validation
        t0 = time.perf_counter()
        grounded_answer, citations = self.validator.validate(answer, context)
        metrics["validation_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)

        # Build Graph Paths & referenced entities from citations
        graph_paths = []
        if context.subgraph:
            for edge in context.subgraph.get("edges", []):
                if edge["source"] in citations or edge["target"] in citations:
                    graph_paths.append(
                        {
                            "source": edge["source"],
                            "target": edge["target"],
                            "type": edge["type"],
                        }
                    )

        referenced_files = [
            ref.properties.get("path")
            for ref in context.references
            if ref.id in citations and ref.type == "file"
        ]
        referenced_files = [f for f in referenced_files if f]

        referenced_symbols = [
            ref.properties.get("name")
            for ref in context.references
            if ref.id in citations and ref.type == "symbol"
        ]
        referenced_symbols = [s for s in referenced_symbols if s]

        # Token usage estimates
        prompt_tokens = len(rendered_prompt + optimized_doc.system_instruction) // 4
        completion_tokens = len(grounded_answer) // 4
        token_usage = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }

        model_metadata = {
            "provider": provider.__class__.__name__.replace("Provider", ""),
            "model": getattr(provider, "model", "unknown"),
        }

        # Composing brief summaries
        summary = (
            grounded_answer[:150] + "..."
            if len(grounded_answer) > 150
            else grounded_answer
        )
        reasoning_summary = f"ERE analyzed {len(reasoning_res.evidence)} evidence nodes, validating {len(reasoning_res.hypotheses)} hypotheses."

        return GraphRAGResult(
            answer=grounded_answer,
            summary=summary,
            reasoning_summary=reasoning_summary,
            citations=citations,
            confidence=reasoning_res.confidence,
            graph_paths=graph_paths,
            referenced_files=referenced_files,
            referenced_symbols=referenced_symbols,
            recommendations=reasoning_res.recommendations,
            token_usage=token_usage,
            processing_metrics=metrics,
            model_metadata=model_metadata,
        )


class GraphRAGService:
    """Graph-RAG Service orchestrator exposing generation and streaming methods."""

    def __init__(self, pipeline: Optional[ChatPipeline] = None) -> None:
        self.pipeline = pipeline or ChatPipeline()

    async def chat(
        self,
        repo_name: str,
        question: str,
        policy: str = "default",
        options: Optional[Dict[str, Any]] = None,
    ) -> GraphRAGResult:
        """Processes a chat query, running full retrieval, reasoning, generation, and validation."""
        opt = options or {}
        return await self.pipeline.execute(repo_name, question, policy, opt)

    async def stream_answer(
        self,
        repo_name: str,
        question: str,
        policy: str = "default",
        options: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[str]:
        """Streams answer chunks from the LLM provider directly."""
        opt = options or {}
        # Fetch retrieval & reasoning
        retrieval_engine = self.pipeline.get_retrieval_engine()
        context = await retrieval_engine.retrieve(repo_name, question, policy)
        reasoning_engine = self.pipeline.get_reasoning_engine()
        reasoning_res = reasoning_engine.reason(repo_name, question, policy, context)

        # Build prompt & optimize
        doc = self.pipeline.builder.build_document(context, reasoning_res)
        token_limit = opt.get("token_limit", 8000)
        optimized_doc = self.pipeline.budget_manager.optimize(doc, token_limit)
        rendered_prompt = self.pipeline.renderer.render(optimized_doc)

        provider = ProviderFactory.get_provider()
        async for chunk in provider.stream(
            prompt=rendered_prompt,
            system_instruction=optimized_doc.system_instruction,
        ):
            yield chunk
