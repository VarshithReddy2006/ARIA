"""Unit tests verifying import and initialization interface for agent classes."""

import pytest
from agents import (
    IssueMapper,
    EvaluationAgent,
)


def test_issue_mapper_init() -> None:
    """Verifies IssueMapper can be instantiated and exposes implemented methods."""
    mapper = IssueMapper()
    assert mapper is not None
    assert hasattr(mapper, "parse_issue")
    assert hasattr(mapper, "identify_relevant_files")
    assert hasattr(mapper, "map_issue")


class MockLLMProvider:
    def __init__(self, should_fail=False, response_json=None):
        self.should_fail = should_fail
        self.response_json = response_json or {
            "citations_valid": True,
            "hallucination_detected": False,
            "confidence_score": 0.95,
            "feedback": "Mock evaluation successful",
            "unsupported_claims": [],
            "unknown_files": [],
            "used_chunks_indices": [0],
            "chunk_citations": [],
        }

    def generate_json(self, prompt, schema=None, system_instruction=None):
        if self.should_fail:
            raise RuntimeError("LLM Failure")
        return self.response_json


def test_evaluation_agent_init() -> None:
    """Verifies EvaluationAgent can be instantiated."""
    provider = MockLLMProvider()
    agent = EvaluationAgent(llm_provider=provider)
    assert agent is not None


def test_evaluation_agent_evaluate_claim_success() -> None:
    """Verifies EvaluationAgent produces expected result when LLM succeeds."""
    provider = MockLLMProvider()
    agent = EvaluationAgent(llm_provider=provider)
    result = agent.evaluate_claim(
        answer="The system uses BGE for embeddings.",
        retrieved_chunks=["BGE is used for local embeddings."],
        repo_files=["services/embedding_service.py"],
    )
    assert result["citations_valid"] is True
    assert result["confidence_score"] == 0.95


def test_evaluation_agent_evaluate_claim_fallback() -> None:
    """Verifies EvaluationAgent degrades gracefully when LLM fails."""
    provider = MockLLMProvider(should_fail=True)
    agent = EvaluationAgent(llm_provider=provider)
    result = agent.evaluate_claim(
        answer="Some answer",
        retrieved_chunks=["chunk"],
        repo_files=["file.py"],
    )
    assert result["citations_valid"] is False
    assert result["confidence_score"] == 0.0
