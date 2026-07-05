"""Unit tests for the Graph-RAG pipeline, prompt builder, token budget manager, validator, and router."""

import sys
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

# Ensure root directory is in sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.api import app
from models.retrieval import RepositoryRetrievalContext, ContextReference
from models.reasoning import (
    ReasoningResult,
    ConfidenceBreakdown,
    Recommendation,
)
from models.graph_rag import GraphRAGResult
from services.graph_rag import (
    PromptBuilder,
    PromptRenderer,
    TokenBudgetManager,
    GroundingValidator,
    ChatPipeline,
)

client = TestClient(app)


def test_graph_rag_models() -> None:
    """Verifies that Pydantic models for Graph-RAG validate correctly."""
    conf = ConfidenceBreakdown(evidence_quality=85.0, reasoning_confidence=90.0, recommendation_confidence=87.5)
    rec = Recommendation(id="REC-001", type="refactor", target="repo::file", priority="high", estimated_effort="2h")
    
    res = GraphRAGResult(
        answer="This is the answer.",
        summary="Summary.",
        reasoning_summary="ERE reason.",
        citations=["repo::file"],
        confidence=conf,
        recommendations=[rec],
    )
    assert res.answer == "This is the answer."
    assert len(res.citations) == 1
    assert res.recommendations[0].type == "refactor"


def test_prompt_abstractions_and_budget() -> None:
    """Verifies PromptBuilder, PromptRenderer, and TokenBudgetManager behave correctly."""
    repo_name = "test-owner/test-repo"

    # Mocks
    context = RepositoryRetrievalContext(
        repository_name=repo_name,
        question="Is there coupling?",
        references=[
            ContextReference(id=f"{repo_name}::main.py", type="file", source="subgraph"),
            ContextReference(id=f"{repo_name}::doc1", type="document", source="embedding", snippet="long doc text" * 200),
        ],
        subgraph=None,
        explanation={"resolved_entities": [], "policy": "default", "confidence": 1.0, "metrics": {}},
    )
    conf = ConfidenceBreakdown(evidence_quality=85.0, reasoning_confidence=90.0, recommendation_confidence=87.5)
    reasoning = ReasoningResult(
        repository_name=repo_name,
        question="Is there coupling?",
        policy="default",
        evidence=[],
        hypotheses=[],
        contradictions=[],
        recommendations=[],
        confidence=conf,
        confidence_explanation="explanation",
    )

    # 1. PromptBuilder
    builder = PromptBuilder()
    doc = builder.build_document(context, reasoning)
    assert len(doc.references) == 2
    assert doc.question == "Is there coupling?"

    # 2. PromptRenderer
    renderer = PromptRenderer()
    rendered = renderer.render(doc)
    assert "## QUESTION" in rendered
    assert "## CODEBASE CONTEXT REFERENCES" in rendered

    # 3. TokenBudgetManager
    budget_mgr = TokenBudgetManager()
    # Optimize with small budget that only fits 1 reference
    optimized = budget_mgr.optimize(doc, max_tokens=150)
    assert len(optimized.references) < 2  # should prune document snippet reference due to token limit


def test_grounding_validator() -> None:
    """Verifies GroundingValidator correctly filters hallucinated citations."""
    repo_name = "test-owner/test-repo"
    context = RepositoryRetrievalContext(
        repository_name=repo_name,
        question="Find files",
        references=[
            ContextReference(id=f"{repo_name}::main.py", type="file", source="subgraph"),
        ],
        subgraph=None,
        explanation={"resolved_entities": [], "policy": "default", "confidence": 1.0, "metrics": {}},
    )

    validator = GroundingValidator()
    # Citations in LLM answer
    answer = "Based on [test-owner/test-repo::main.py] and [test-owner/test-repo::fake.py], main is the entrypoint."
    grounded, citations = validator.validate(answer, context)

    assert f"{repo_name}::main.py" in citations
    assert f"{repo_name}::fake.py" not in citations  # fake.py does not exist in context!


@pytest.mark.anyio
async def test_chat_pipeline_execution() -> None:
    """Verifies that ChatPipeline orchestrates sub-engines and LLM call successfully."""
    repo_name = "test-owner/test-repo"

    # Mocks
    mock_sre = MagicMock()
    mock_sre.retrieve = AsyncMock(return_value=RepositoryRetrievalContext(
        repository_name=repo_name,
        question="Query?",
        references=[ContextReference(id=f"{repo_name}::main.py", type="file", source="subgraph")],
        subgraph=None,
        explanation={"resolved_entities": [], "policy": "default", "confidence": 1.0, "metrics": {}},
    ))

    mock_ere = MagicMock()
    conf = ConfidenceBreakdown(evidence_quality=90.0, reasoning_confidence=90.0, recommendation_confidence=90.0)
    mock_ere.reason.return_value = ReasoningResult(
        repository_name=repo_name,
        question="Query?",
        policy="default",
        evidence=[],
        hypotheses=[],
        contradictions=[],
        recommendations=[],
        confidence=conf,
        confidence_explanation="Explanation",
    )

    pipeline = ChatPipeline(retrieval_engine=mock_sre, reasoning_engine=mock_ere)

    # Mock LLM provider call
    mock_provider = AsyncMock()
    mock_provider.generate.return_value = "Answer referencing [test-owner/test-repo::main.py]"
    
    with patch("services.graph_rag.ProviderFactory.get_provider", return_value=mock_provider):
        res = await pipeline.execute(repo_name, "Query?", "default", {})
        assert res.answer == "Answer referencing [test-owner/test-repo::main.py]"
        assert f"{repo_name}::main.py" in res.citations
        assert "retrieval_ms" in res.processing_metrics
        assert "llm_ms" in res.processing_metrics


def test_graph_rag_router_endpoint() -> None:
    """Verifies POST /chat endpoint returns GraphRAGResult."""
    repo_name = "test-owner/test-repo"

    with patch("backend.routers.chat.graph_rag_service") as mock_service:
        # Mock navigate builder storage
        mock_builder = MagicMock()
        mock_builder.twin_builder.store = {repo_name: {}}
        mock_service.pipeline.get_retrieval_engine.return_value.navigator.get_builder.return_value = mock_builder

        # Mock service chat return
        conf = ConfidenceBreakdown(evidence_quality=90.0, reasoning_confidence=90.0, recommendation_confidence=90.0)
        mock_service.chat = AsyncMock(return_value=GraphRAGResult(
            answer="LLM response",
            summary="summary",
            reasoning_summary="reason summary",
            citations=[],
            confidence=conf,
        ))

        response = client.post(
            "/api/repositories/test-owner/test-repo/chat",
            json={"question": "Query?", "policy": "default", "options": {}},
        )
        assert response.status_code == 200
        assert response.json()["answer"] == "LLM response"
