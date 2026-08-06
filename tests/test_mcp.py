import json
import io
from unittest.mock import patch, MagicMock
import pytest

from backend.mcp_server import execute_tool, run_mcp_server, TOOLS


def test_execute_tool_list_repositories():
    store = {
        "owner/repo1": {"analysis": MagicMock(), "architecture": MagicMock()},
        "owner/repo2": {"analysis": MagicMock(), "architecture": MagicMock()},
    }
    res = execute_tool("list_repositories", {}, store, None, None, None, None)
    assert sorted(res) == ["owner/repo1", "owner/repo2"]


def test_execute_tool_get_repository_summary():
    mock_analysis = MagicMock()
    mock_analysis.model_dump.return_value = {"metadata": {"local_path": "/path"}}
    mock_arch = MagicMock()
    mock_arch.model_dump.return_value = {"nodes": []}

    store = {"owner/repo": {"analysis": mock_analysis, "architecture": mock_arch}}

    res = execute_tool(
        "get_repository_summary",
        {"owner": "owner", "repo": "repo"},
        store,
        None,
        None,
        None,
        None,
    )
    assert res["analysis"] == {"metadata": {"local_path": "/path"}}
    assert res["architecture"] == {"nodes": []}


def test_execute_tool_get_repository_summary_not_indexed():
    with pytest.raises(ValueError, match="is not indexed"):
        execute_tool(
            "get_repository_summary",
            {"owner": "owner", "repo": "not_indexed"},
            {},
            None,
            None,
            None,
            None,
        )


def test_execute_tool_get_file_symbols():
    mock_symbols_service = MagicMock()
    mock_symbol = MagicMock()
    mock_symbol.model_dump.return_value = {"name": "func_name", "kind": "function"}
    mock_symbols_service.get_file_symbols.return_value = [mock_symbol]

    res = execute_tool(
        "get_file_symbols",
        {"owner": "owner", "repo": "repo", "file_path": "core/cache.py"},
        {},
        mock_symbols_service,
        None,
        None,
        None,
    )
    assert res == [{"name": "func_name", "kind": "function"}]
    mock_symbols_service.get_file_symbols.assert_called_once_with(
        "owner/repo", "core/cache.py"
    )


def test_execute_tool_get_file_symbols_none():
    mock_symbols_service = MagicMock()
    mock_symbols_service.get_file_symbols.return_value = None

    with pytest.raises(ValueError, match="No symbol index found"):
        execute_tool(
            "get_file_symbols",
            {"owner": "owner", "repo": "repo", "file_path": "core/cache.py"},
            {},
            mock_symbols_service,
            None,
            None,
            None,
        )


def test_execute_tool_get_symbol_definition():
    mock_symbols_service = MagicMock()
    mock_def = MagicMock()
    mock_def.model_dump.return_value = {"name": "func_name", "line": 10}
    mock_symbols_service.get_definition.return_value = mock_def

    res = execute_tool(
        "get_symbol_definition",
        {"owner": "owner", "repo": "repo", "symbol_name": "func_name"},
        {},
        mock_symbols_service,
        None,
        None,
        None,
    )
    assert res == {"name": "func_name", "line": 10}
    mock_symbols_service.get_definition.assert_called_once_with(
        "owner/repo", "func_name"
    )


def test_execute_tool_get_symbol_definition_not_found():
    mock_symbols_service = MagicMock()
    mock_symbols_service.get_definition.return_value = None

    with pytest.raises(ValueError, match="not found in repo"):
        execute_tool(
            "get_symbol_definition",
            {"owner": "owner", "repo": "repo", "symbol_name": "unknown"},
            {},
            mock_symbols_service,
            None,
            None,
            None,
        )


def test_execute_tool_get_symbol_references():
    mock_symbols_service = MagicMock()
    mock_ref = MagicMock()
    mock_ref.model_dump.return_value = {"file": "other.py", "line": 20}
    mock_symbols_service.get_references.return_value = [mock_ref]

    res = execute_tool(
        "get_symbol_references",
        {"owner": "owner", "repo": "repo", "symbol_name": "func_name"},
        {},
        mock_symbols_service,
        None,
        None,
        None,
    )
    assert res == [{"file": "other.py", "line": 20}]
    mock_symbols_service.get_references.assert_called_once_with(
        "owner/repo", "func_name"
    )


def test_execute_tool_get_call_graph():
    mock_cg_service = MagicMock()
    mock_summary = MagicMock()
    mock_summary.model_dump.return_value = {"nodes": [], "edges": []}
    mock_cg_service.load_summary.return_value = mock_summary

    res = execute_tool(
        "get_call_graph",
        {"owner": "owner", "repo": "repo"},
        {},
        None,
        mock_cg_service,
        None,
        None,
    )
    assert res == {"nodes": [], "edges": []}
    mock_cg_service.load_summary.assert_called_once_with("owner/repo")


def test_execute_tool_get_call_graph_none():
    mock_cg_service = MagicMock()
    mock_cg_service.load_summary.return_value = None

    with pytest.raises(ValueError, match="No call graph indexed"):
        execute_tool(
            "get_call_graph",
            {"owner": "owner", "repo": "repo"},
            {},
            None,
            mock_cg_service,
            None,
            None,
        )


def test_execute_tool_get_dead_code():
    mock_analysis = MagicMock()
    mock_analysis.metadata = {"local_path": "/path"}
    store = {"owner/repo": {"analysis": mock_analysis}}

    with patch("services.dead_code_service.DeadCodeService") as MockDeadCodeService:
        mock_dc_instance = MagicMock()
        mock_res = MagicMock()
        mock_res.model_dump.return_value = {"dead_functions": ["foo"]}
        mock_dc_instance.analyze.return_value = mock_res
        MockDeadCodeService.return_value = mock_dc_instance

        res = execute_tool(
            "get_dead_code",
            {"owner": "owner", "repo": "repo"},
            store,
            None,
            None,
            None,
            None,
        )
        assert res == {"dead_functions": ["foo"]}
        mock_dc_instance.analyze.assert_called_once_with("owner/repo")


def test_execute_tool_get_dead_code_not_indexed():
    with pytest.raises(ValueError, match="is not indexed"):
        execute_tool(
            "get_dead_code",
            {"owner": "owner", "repo": "repo"},
            {},
            None,
            None,
            None,
            None,
        )


def test_execute_tool_query_codebase():
    mock_retrieval_service = MagicMock()
    mock_source = MagicMock()
    mock_source.model_dump.return_value = {"file": "a.py", "score": 0.8}
    mock_retrieval_service.retrieve_and_answer.return_value = {
        "answer": "Answer here",
        "sources": [mock_source],
        "confidence": 0.85,
        "verified": True,
    }

    res = execute_tool(
        "query_codebase",
        {"owner": "owner", "repo": "repo", "query": "what is this"},
        {},
        None,
        None,
        None,
        mock_retrieval_service,
    )
    assert res == {
        "answer": "Answer here",
        "sources": [{"file": "a.py", "score": 0.8}],
        "confidence": 0.85,
        "verified": True,
    }
    mock_retrieval_service.retrieve_and_answer.assert_called_once_with(
        "owner/repo", "what is this"
    )


def test_execute_tool_unsupported():
    with pytest.raises(ValueError, match="is not supported"):
        execute_tool("invalid_tool_name", {}, {}, None, None, None, None)


def test_run_mcp_server_handshake():
    # Simulate a run with only initialize call
    input_data = (
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        + "\n"
    )

    mock_stdin = io.StringIO(input_data)
    mock_stdout = io.StringIO()

    # Mock the dependencies lazy-loaded inside run_mcp_server
    mock_deps = {
        "ANALYSIS_STORE": {},
        "symbol_service": MagicMock(),
        "call_graph_service": MagicMock(),
        "dead_code_service": MagicMock(),
        "retrieval_service": MagicMock(),
    }

    with (
        patch("sys.stdin", mock_stdin),
        patch("sys.stdout", mock_stdout),
        patch.dict("sys.modules", {"backend.dependencies": MagicMock(**mock_deps)}),
    ):
        run_mcp_server()

    response = json.loads(mock_stdout.getvalue().strip())
    assert response["id"] == 1
    assert response["result"]["protocolVersion"] == "2024-11-05"
    assert response["result"]["serverInfo"]["name"] == "repo-intelligence-mcp"


def test_run_mcp_server_tools_list():
    input_data = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}) + "\n"

    mock_stdin = io.StringIO(input_data)
    mock_stdout = io.StringIO()

    mock_deps = {
        "ANALYSIS_STORE": {},
        "symbol_service": MagicMock(),
        "call_graph_service": MagicMock(),
        "dead_code_service": MagicMock(),
        "retrieval_service": MagicMock(),
    }

    with (
        patch("sys.stdin", mock_stdin),
        patch("sys.stdout", mock_stdout),
        patch.dict("sys.modules", {"backend.dependencies": MagicMock(**mock_deps)}),
    ):
        run_mcp_server()

    response = json.loads(mock_stdout.getvalue().strip())
    assert response["id"] == 2
    assert len(response["result"]["tools"]) == len(TOOLS)


def test_run_mcp_server_tools_call():
    # Call list_repositories
    input_data = (
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "list_repositories", "arguments": {}},
            }
        )
        + "\n"
    )

    mock_stdin = io.StringIO(input_data)
    mock_stdout = io.StringIO()

    # We populate the store to see if it lists properly
    store = {"org/project": {"analysis": MagicMock(), "architecture": MagicMock()}}
    mock_deps = {
        "ANALYSIS_STORE": store,
        "symbol_service": MagicMock(),
        "call_graph_service": MagicMock(),
        "dead_code_service": MagicMock(),
        "retrieval_service": MagicMock(),
    }

    with (
        patch("sys.stdin", mock_stdin),
        patch("sys.stdout", mock_stdout),
        patch.dict("sys.modules", {"backend.dependencies": MagicMock(**mock_deps)}),
    ):
        run_mcp_server()

    response = json.loads(mock_stdout.getvalue().strip())
    assert response["id"] == 3
    assert response["result"]["content"][0]["type"] == "text"
    result_list = json.loads(response["result"]["content"][0]["text"])
    assert result_list == ["org/project"]


def test_run_mcp_server_unknown_method():
    input_data = (
        json.dumps({"jsonrpc": "2.0", "id": 4, "method": "unsupported/method"}) + "\n"
    )

    mock_stdin = io.StringIO(input_data)
    mock_stdout = io.StringIO()

    mock_deps = {
        "ANALYSIS_STORE": {},
        "symbol_service": MagicMock(),
        "call_graph_service": MagicMock(),
        "dead_code_service": MagicMock(),
        "retrieval_service": MagicMock(),
    }

    with (
        patch("sys.stdin", mock_stdin),
        patch("sys.stdout", mock_stdout),
        patch.dict("sys.modules", {"backend.dependencies": MagicMock(**mock_deps)}),
    ):
        run_mcp_server()

    response = json.loads(mock_stdout.getvalue().strip())
    assert response["id"] == 4
    assert "error" in response
    assert response["error"]["code"] == -32601


def test_run_mcp_server_parse_error():
    input_data = "not-json-content\n"

    mock_stdin = io.StringIO(input_data)
    mock_stdout = io.StringIO()

    mock_deps = {
        "ANALYSIS_STORE": {},
        "symbol_service": MagicMock(),
        "call_graph_service": MagicMock(),
        "dead_code_service": MagicMock(),
        "retrieval_service": MagicMock(),
    }

    with (
        patch("sys.stdin", mock_stdin),
        patch("sys.stdout", mock_stdout),
        patch.dict("sys.modules", {"backend.dependencies": MagicMock(**mock_deps)}),
    ):
        run_mcp_server()

    response = json.loads(mock_stdout.getvalue().strip())
    assert "error" in response
    assert response["error"]["code"] == -32700
