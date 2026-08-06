"""Tests for deterministic citation verification service (Recovery Item R-005)."""

import pytest
from services.chat.citation_verifier import CitationVerifier, CitationReport
from agents.evaluator import EvaluationAgent
from models.schemas import EvaluationResult


def test_nonexistent_file_citation_returns_unresolved_and_invalid():
    """R-005 Acceptance Criteria: Injected answer citing nonexistent/file.py:1-5 must return unresolved and citations_valid=False."""
    verifier = CitationVerifier()
    answer = "The feature is defined in nonexistent/file.py:1-5."
    source_contexts = [{"metadata": {"file_path": "backend/api.py"}, "content": "..."}]

    report = verifier.verify_answer(answer, source_contexts=source_contexts)

    assert isinstance(report, CitationReport)
    assert report.citations_valid is False
    assert len(report.unresolved) == 1
    assert report.unresolved[0].file_path == "nonexistent/file.py"
    assert report.unresolved[0].start_line == 1
    assert report.unresolved[0].end_line == 5
    assert "does not exist" in report.unresolved[0].reason


def test_evaluation_agent_with_nonexistent_file_citation():
    """Assert EvaluationAgent sets citations_valid=False when nonexistent file is cited."""
    from tests.test_agents import MockLLMProvider

    agent = EvaluationAgent(provider=MockLLMProvider())
    res = agent.evaluate_response(
        prompt="Where is it?",
        response="Look at nonexistent/file.py:1-5 for implementation.",
        source_contexts=[{"metadata": {"file_path": "backend/api.py"}, "content": "..."}],
    )

    assert isinstance(res, EvaluationResult)
    assert res.citations_valid is False
    assert "nonexistent/file.py" in res.unknown_files


def test_valid_existing_file_citation():
    """Existing file with valid line numbers must verify successfully."""
    verifier = CitationVerifier()
    answer = "Implementation in backend/api.py:1-10."
    source_contexts = [{"metadata": {"file_path": "backend/api.py"}, "content": "..."}]

    report = verifier.verify_answer(answer, source_contexts=source_contexts)

    assert report.citations_valid is True
    assert len(report.verified) == 1
    assert report.verified[0].file_path == "backend/api.py"
    assert len(report.unresolved) == 0


def test_out_of_bounds_line_number_fails_verification():
    """Line number exceeding file length must set citations_valid=False."""
    verifier = CitationVerifier()
    # backend/api.py has ~370 lines. Line 99999 is out of bounds.
    answer = "Implementation in backend/api.py:99999-100000."
    source_contexts = [{"metadata": {"file_path": "backend/api.py"}, "content": "..."}]

    report = verifier.verify_answer(answer, source_contexts=source_contexts)

    assert report.citations_valid is False
    assert len(report.unresolved) == 1
    assert "exceeds total file length" in report.unresolved[0].reason


def test_no_citations_has_zero_unresolved():
    """If no citations exist in text, total_citations is 0 and unresolved is empty."""
    verifier = CitationVerifier()
    answer = "There are no files mentioned here."

    report = verifier.verify_answer(answer)

    assert report.total_citations == 0
    assert len(report.unresolved) == 0
