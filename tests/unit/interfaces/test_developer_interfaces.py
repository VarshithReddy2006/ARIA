"""Unit tests for C9 Developer Interfaces (REST, CLI, MCP, Python SDK, VS Code)."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from ria.interfaces.cli import CLIRunner
from ria.interfaces.mcp import MCPServer
from ria.interfaces.rest import RESTAPIServer
from ria.interfaces.sdk.python import RIAClient
from ria.interfaces.vscode.extension import VSCodeCommandDispatcher


def test_rest_api_server_endpoints() -> None:
    mock_sync = MagicMock()
    mock_search = MagicMock()
    mock_query = MagicMock()
    mock_context = MagicMock()
    mock_knowledge = MagicMock()

    mock_sync.register_repository.return_value = MagicMock(is_success=True, repo_id="r1", status="SYNCED")
    mock_sync.synchronize_repository.return_value = MagicMock(is_success=True, repo_id="r1", current_commit_sha="abc")
    mock_search.search_symbol.return_value = MagicMock(is_success=True, results=MagicMock(payload=(1, 2, 3, 4, 5)))
    mock_query.find_definition.return_value = MagicMock(is_success=True, query_id="q1")
    mock_context.build_context.return_value = MagicMock(is_success=True, package_id="p1", total_tokens=150, content="{}")
    mock_knowledge.answer_question.return_value = MagicMock(is_success=True, answer_text="Ans", is_grounded=True, grounding_score=0.98)

    server = RESTAPIServer(mock_sync, mock_search, mock_query, mock_context, mock_knowledge)

    # Health
    resp = server.handle_request("GET", "/health")
    assert resp.is_success
    assert resp.data["status"] == "healthy"

    # Version
    resp = server.handle_request("GET", "/version")
    assert resp.is_success
    assert resp.data["version"] == "2.0.0"

    # Register repo
    resp = server.handle_request("POST", "/repositories", {"remote_url": "https://repo.git", "name": "repo"})
    assert resp.is_success
    assert resp.data["repo_id"] == "r1"

    # Search
    resp = server.handle_request("POST", "/search", {"repo_id": "r1", "query_text": "main"})
    assert resp.is_success
    assert resp.data["total_matches"] == 5


def test_mcp_server_tools() -> None:
    mock_sync = MagicMock()
    mock_search = MagicMock()
    mock_query = MagicMock()
    mock_context = MagicMock()
    mock_knowledge = MagicMock()

    mock_search.search_symbol.return_value = MagicMock(is_success=True, results=MagicMock(payload=(1, 2)))
    mock_knowledge.answer_question.return_value = MagicMock(is_success=True, answer_text="Ans", is_grounded=True)

    mcp = MCPServer(mock_sync, mock_search, mock_query, mock_context, mock_knowledge)
    tools = mcp.list_tools()
    assert len(tools) == 14

    res = mcp.invoke_tool("search_symbol", {"repo_id": "r1", "query": "login"})
    assert res["is_success"]

    res = mcp.invoke_tool("ask_repository", {"repo_id": "r1", "question": "how to login?"})
    assert res["is_success"]
    assert res["answer"] == "Ans"


def test_python_sdk_client() -> None:
    mock_sync = MagicMock()
    mock_search = MagicMock()
    mock_query = MagicMock()
    mock_context = MagicMock()
    mock_knowledge = MagicMock()

    mock_search.search_symbol.return_value = MagicMock(is_success=True, results=MagicMock(payload=tuple(range(10))))
    mock_knowledge.answer_question.return_value = MagicMock(is_success=True, answer_text="SDK Ans", is_grounded=True)

    client = RIAClient(mock_sync, mock_search, mock_query, mock_context, mock_knowledge)

    srch_resp = client.search("r1", "AuthService")
    assert srch_resp.is_success
    assert srch_resp.data["total_matches"] == 10

    ask_resp = client.ask("r1", "AuthService?")
    assert ask_resp.is_success
    assert ask_resp.data["answer"] == "SDK Ans"


def test_cli_runner() -> None:
    mock_sync = MagicMock()
    mock_search = MagicMock()
    mock_query = MagicMock()
    mock_context = MagicMock()
    mock_knowledge = MagicMock()

    mock_sync.register_repository.return_value = MagicMock(is_success=True, repo_id="r1", status="SYNCED")
    mock_search.search_symbol.return_value = MagicMock(is_success=True, results=MagicMock(payload=(1,)))

    cli = CLIRunner(mock_sync, mock_search, mock_query, mock_context, mock_knowledge)
    ret = cli.run(["init", "--remote-url", "https://repo.git", "--name", "repo"])
    assert ret == 0

    ret = cli.run(["search", "--repo-id", "r1", "--query", "login"])
    assert ret == 0


def test_vscode_command_dispatcher() -> None:
    mock_search = MagicMock()
    mock_query = MagicMock()
    mock_context = MagicMock()
    mock_knowledge = MagicMock()

    mock_knowledge.answer_question.return_value = MagicMock(is_success=True, answer_text="VS Code Ans")

    disp = VSCodeCommandDispatcher(mock_search, mock_query, mock_context, mock_knowledge)
    res = disp.execute_command("ria.askRepository", {"repo_id": "r1", "question": "auth?"})
    assert res["is_success"]
    assert res["answer"] == "VS Code Ans"
