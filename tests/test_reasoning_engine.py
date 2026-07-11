"""Unit tests for the Engineering Reasoning Engine (ERE), rule packs, sub-engines, and REST router."""

import sys
import os
from unittest.mock import patch
from fastapi.testclient import TestClient

# Ensure root directory is in sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.api import app
from models.retrieval import (
    ContextReference,
    RepositoryRetrievalContext,
    RetrievalExplanation,
)
from models.reasoning import (
    Evidence,
    Hypothesis,
    ReasoningResult,
    ConfidenceBreakdown,
)
from services.reasoning_engine import (
    EvidenceAnalyzer,
    RuleEngine,
    ConfidenceEngine,
    RecommendationPlanner,
)

client = TestClient(app)


def test_reasoning_models() -> None:
    """Verifies that Pydantic models for reasoning validate correctly."""
    ev = Evidence(
        id="EVD-001",
        type="file",
        reference_id="repo1::main.py",
        description="Main file",
    )
    hyp = Hypothesis(
        id="HYP-01",
        description="Circular dependency",
        status="validated",
        supporting_evidence=["EVD-001"],
    )
    conf = ConfidenceBreakdown(
        evidence_quality=90.0,
        reasoning_confidence=100.0,
        recommendation_confidence=95.0,
    )

    res = ReasoningResult(
        repository_name="test-owner/test-repo",
        question="Find circular dependencies",
        policy="architecture",
        evidence=[ev],
        hypotheses=[hyp],
        contradictions=[],
        decision_analysis=None,
        recommendations=[],
        confidence=conf,
        confidence_explanation="Explanation",
    )

    assert res.repository_name == "test-owner/test-repo"
    assert len(res.evidence) == 1
    assert res.confidence.evidence_quality == 90.0


def test_ere_sub_engines() -> None:
    """Verifies ERE sub-engines correctly evaluate evidence, rules, confidence, and recommendations."""
    repo_name = "test-owner/test-repo"

    # 1. EvidenceAnalyzer
    analyzer = EvidenceAnalyzer()
    explanation = RetrievalExplanation(
        resolved_entities=[], policy="default", confidence=1.0, metrics={}
    )
    ref_context = RepositoryRetrievalContext(
        repository_name=repo_name,
        question="Is it compliant?",
        references=[
            ContextReference(
                id=f"{repo_name}::main.py", type="file", source="subgraph"
            ),
            ContextReference(
                id=f"{repo_name}::compliance",
                type="compliance",
                source="subgraph",
                properties={"status": "warning"},
            ),
        ],
        subgraph=None,
        explanation=explanation,
    )

    evidence = analyzer.analyze(ref_context)
    assert len(evidence) == 2
    assert evidence[0].type == "file"
    assert evidence[1].type == "compliance"
    assert evidence[0].quality_score == 1.0

    # 2. RuleEngine
    rule_engine = RuleEngine()
    hypotheses, contradictions = rule_engine.evaluate(evidence)
    # Since compliance node has status warning, it should validate a warning hypothesis
    assert len(hypotheses) == 1
    assert hypotheses[0].id == "HYP-COMP-01"
    assert hypotheses[0].status == "validated"

    # 3. ConfidenceEngine
    confidence_engine = ConfidenceEngine()
    breakdown = confidence_engine.calculate(evidence, contradictions, len(hypotheses))
    assert breakdown.evidence_quality > 0
    assert breakdown.reasoning_confidence == 100.0  # no contradictions

    # 4. RecommendationPlanner
    planner = RecommendationPlanner()
    decision, recs = planner.plan(repo_name, hypotheses, breakdown)
    assert decision is not None
    assert len(decision.options) == 2
    assert len(recs) == 1
    assert recs[0].type == "compliance_fix"


def test_reasoning_router_endpoint() -> None:
    """Verifies POST /reason endpoint returns reasoning conclusions."""
    repo_name = "test-owner/test-repo"

    with patch("backend.routers.reasoning.engineering_reasoning_engine") as mock_engine:
        # Mock engine reasoning return
        conf = ConfidenceBreakdown(
            evidence_quality=90.0,
            reasoning_confidence=100.0,
            recommendation_confidence=95.0,
        )
        mock_engine.reason.return_value = ReasoningResult(
            repository_name=repo_name,
            question="Find circular dependencies",
            policy="architecture",
            evidence=[],
            hypotheses=[],
            contradictions=[],
            decision_analysis=None,
            recommendations=[],
            confidence=conf,
            confidence_explanation="Good confidence",
        )

        response = client.post(
            "/api/repositories/test-owner/test-repo/reason",
            json={
                "question": "Find circular dependencies",
                "policy": "architecture",
                "context": {
                    "repository_name": repo_name,
                    "question": "Find circular dependencies",
                    "references": [],
                    "subgraph": None,
                    "explanation": {
                        "resolved_entities": [],
                        "policy": "architecture",
                        "confidence": 1.0,
                        "metrics": {},
                    },
                },
            },
        )
        assert response.status_code == 200
        assert response.json()["repository_name"] == repo_name
        assert response.json()["policy"] == "architecture"
        assert response.json()["confidence"]["evidence_quality"] == 90.0
