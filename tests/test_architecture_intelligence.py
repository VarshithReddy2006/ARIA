"""Architecture Intelligence Test Suite.

Verifies:
  1. Layer Classifier returns valid canonical layers for filenames and paths.
  2. Pattern Detector identifies architectural design patterns.
  3. Diagram Generator constructs valid Mermaid, PlantUML, ADR, and Sequence flow strings.
  4. FastAPI router endpoints for node-details and diagram generation return status 200.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from services.architecture.layer_classifier import classify_layer
from services.architecture.pattern_detector import detect_patterns
from services.architecture.diagram_generator import (
    generate_mermaid_diagram,
    generate_plantuml_diagram,
    generate_adr,
    generate_sequence_diagram,
)
from backend.api import app


client = TestClient(app)


def test_layer_classifier():
    """Verify architectural layer classification rules."""
    assert classify_layer("frontend/src/components/Chat.tsx") == "Presentation"
    assert classify_layer("services/chat/retrieval_pipeline.py") == "Application"
    assert classify_layer("models/schemas.py") == "Domain"
    assert classify_layer("services/db/repository.py") == "Data"
    assert classify_layer("services/llm/deepseek_provider.py") == "Infrastructure"
    assert classify_layer("tests/test_api.py") == "Test"
    assert classify_layer("config/settings.py") == "Configuration"


def test_pattern_detector():
    """Verify design pattern detection rules."""
    patterns = detect_patterns("services/db/repository.py", content="class UserStore:")
    assert "Repository Pattern" in patterns

    di_patterns = detect_patterns("backend/dependencies.py", content="def inject_db():")
    assert "Dependency Injection" in di_patterns

    pipe_patterns = detect_patterns(
        "services/chat/retrieval_pipeline.py", content="pipeline = Step()"
    )
    assert "Pipeline" in pipe_patterns


def test_diagram_generator():
    """Verify diagram and ADR generators produce valid syntax."""
    mermaid = generate_mermaid_diagram(
        "services/chat/api.py",
        depends_on=["services/chat/retrieval.py"],
        imported_by=["backend/main.py"],
    )
    assert "graph TD" in mermaid
    assert "api" in mermaid

    puml = generate_plantuml_diagram(
        "services/chat/api.py",
        depends_on=["services/chat/retrieval.py"],
        imported_by=["backend/main.py"],
    )
    assert "@startuml" in puml
    assert "@enduml" in puml

    adr = generate_adr(
        "services/chat/api.py",
        "Exposes REST endpoints",
        "Presentation",
        ["MVC", "Facade"],
    )
    assert "# ADR 001" in adr
    assert "Exposes REST endpoints" in adr

    seq = generate_sequence_diagram(
        "services/chat/api.py",
        depends_on=["services/chat/retrieval.py"],
        imported_by=["backend/main.py"],
    )
    assert "sequenceDiagram" in seq


def test_api_node_details_endpoint():
    """Verify GET /api/architecture/{owner}/{repo}/node-details/{node_id}."""
    resp = client.get(
        "/api/architecture/VarshithReddy2006/Repo-Intelligence-Agent/node-details/services/chat/retrieval_pipeline.py"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["node_id"] == "services/chat/retrieval_pipeline.py"
    assert "business_responsibility" in data
    assert "layer" in data
    assert "patterns" in data
    assert "system_position" in data


def test_api_generate_diagram_endpoint():
    """Verify POST /api/architecture/generate-diagram."""
    payload = {
        "repo": "VarshithReddy2006/Repo-Intelligence-Agent",
        "node_id": "services/chat/retrieval_pipeline.py",
        "diagram_type": "mermaid",
    }
    resp = client.post("/api/architecture/generate-diagram", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "code" in data
    assert "graph TD" in data["code"]


def test_api_node_details_does_not_fabricate_git_metadata():
    resp = client.get(
        "/api/architecture/VarshithReddy2006/Repo-Intelligence-Agent/"
        "node-details/services/chat/retrieval_pipeline.py"
    )
    assert resp.status_code == 200
    git_metrics = resp.json()["git_metrics"]
    assert all(value is None for value in git_metrics.values())


def test_architecture_quality_marks_unsupported_scores_unavailable():
    resp = client.get(
        "/api/architecture/VarshithReddy2006/Repo-Intelligence-Agent/quality"
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["overall_score"] is None
    assert payload["badge"] is None
    assert payload["subscores"] is None
