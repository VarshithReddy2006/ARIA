"""Unit tests for the Structural Retrieval Engine, executors, assembler, and REST router."""

import sys
import os
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

# Ensure root directory is in sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.api import app
from models.retrieval import (
    ContextReference,
    RetrievalPlan,
    RepositoryRetrievalContext,
)
from services.retrieval_engine import (
    SubgraphExecutor,
    DependencyExecutor,
    RepositoryContextAssembler,
    StructuralRetrievalEngine,
)

client = TestClient(app)


def test_retrieval_models() -> None:
    """Verifies that Pydantic models for structural retrieval validate correctly."""
    ref = ContextReference(id="repo1::main.py", type="file", source="subgraph")
    plan = RetrievalPlan(policy="architecture", steps=[])
    explanation = {
        "resolved_entities": ["main.py"],
        "policy": "architecture",
        "confidence": 1.0,
        "metrics": {},
    }
    context = RepositoryRetrievalContext(
        repository_name="test-owner/test-repo",
        question="What is the architecture?",
        references=[ref],
        subgraph=None,
        explanation=explanation,
    )

    assert context.repository_name == "test-owner/test-repo"
    assert len(context.references) == 1
    assert context.references[0].id == "repo1::main.py"
    assert context.explanation.policy == "architecture"


@pytest.mark.anyio
async def test_executors_and_assembler() -> None:
    """Verifies that specialized executors populate correct references and assembler ranks correctly."""
    repo_name = "test-owner/test-repo"

    # 1. SubgraphExecutor
    mock_nav = MagicMock()
    mock_nav.extract_subgraph.return_value = {
        "nodes": [{"id": f"{repo_name}::main.py", "type": "file", "properties": {}}],
        "edges": [],
    }
    subgraph_exec = SubgraphExecutor(navigator=mock_nav)
    refs = await subgraph_exec.execute(repo_name, [repo_name], {})
    assert len(refs) == 1
    assert refs[0].id == f"{repo_name}::main.py"

    # 2. DependencyExecutor
    mock_gs = MagicMock()
    mock_dep_graph = MagicMock()
    mock_dep_graph.has_node.return_value = True
    mock_dep_graph.successors.return_value = ["utils.py"]
    mock_dep_graph.predecessors.return_value = ["app.py"]
    mock_gs.load_graph.return_value = mock_dep_graph
    dep_exec = DependencyExecutor(graph_service=mock_gs)
    refs = await dep_exec.execute(repo_name, [f"{repo_name}::main.py"], {})
    assert len(refs) == 2
    assert any(r.properties.get("relationship") == "imports" for r in refs)

    # 3. Assembler
    mock_ghs = MagicMock()
    mock_ghs.load.return_value = MagicMock(hotspots=[])
    assembler = RepositoryContextAssembler(git_history_service=mock_ghs, navigator=mock_nav)

    combined_context = assembler.assemble(
        repo_name=repo_name,
        question="What does UserService do?",
        references_lists=[
            [ContextReference(id=f"{repo_name}::UserService", type="symbol", source="symbol_expansion")],
            [ContextReference(id=f"{repo_name}::main.py", type="file", source="subgraph")],
        ],
        policy="default",
        resolved_entities=["UserService"],
        confidence=1.0,
    )

    # Assert correct sorting/ranking and structure
    assert len(combined_context.references) == 2
    # UserService should be ranked higher due to match with resolved entity "UserService"
    assert combined_context.references[0].id == f"{repo_name}::UserService"


@pytest.mark.anyio
async def test_retrieval_engine_planning() -> None:
    """Verifies that retrieval engine generates correct plans and executes them."""
    repo_name = "test-owner/test-repo"

    engine = StructuralRetrievalEngine()
    
    # 1. Architecture policy plan
    plan_arch = engine.generate_plan("What is the architecture?", "architecture")
    executors = {step.executor for step in plan_arch.steps}
    assert "subgraph" in executors
    assert "dependency" in executors

    # 2. Implementation policy plan
    plan_impl = engine.generate_plan("Where is UserService defined?", "implementation")
    executors_impl = {step.executor for step in plan_impl.steps}
    assert "symbol" in executors_impl
    assert "embedding" in executors_impl


def test_retrieval_router_endpoint() -> None:
    """Verifies POST /retrieve endpoint returns context payload."""
    repo_name = "test-owner/test-repo"

    from unittest.mock import AsyncMock
    with patch("backend.routers.retrieval.structural_retrieval_engine") as mock_engine:
        # Mock navigate builder storage
        mock_builder = MagicMock()
        mock_builder.twin_builder.store = {repo_name: {}}
        mock_engine.navigator.get_builder.return_value = mock_builder

        # Mock retrieval return
        mock_engine.retrieve = AsyncMock(return_value=RepositoryRetrievalContext(
            repository_name=repo_name,
            question="What is the architecture?",
            references=[
                ContextReference(id=f"{repo_name}::main.py", type="file", source="subgraph")
            ],
            subgraph=None,
            explanation={
                "resolved_entities": [],
                "policy": "architecture",
                "confidence": 1.0,
                "metrics": {},
            },
        ))

        response = client.post(
            "/api/repositories/test-owner/test-repo/retrieve",
            json={"question": "What is the architecture?", "policy": "architecture"},
        )
        assert response.status_code == 200
        assert response.json()["repository_name"] == repo_name
        assert len(response.json()["references"]) == 1
