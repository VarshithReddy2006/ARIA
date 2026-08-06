from typer.testing import CliRunner
import httpx
from backend.cli import app

runner = CliRunner()


def test_cli_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "Client" in result.stdout
    assert "1.5.0" in result.stdout


def test_cli_stability():
    from unittest.mock import patch

    mock_response = httpx.Response(404, text="Not Found")
    with patch("httpx.get", return_value=mock_response):
        result = runner.invoke(app, ["stability", "owner", "repo"])
    assert result.exit_code == 0
    assert "not yet implemented" in result.stdout


def test_cli_health(respx_mock=None):
    # If using pytest-respx, we can mock httpx, otherwise we mock via monkeypatch or unittest.mock
    # Let's use standard unittest.mock to mock httpx.get for simplicity and independence from extra plugins
    from unittest.mock import patch

    mock_response = httpx.Response(200, json={"status": "healthy", "backend": "online"})
    with patch("httpx.get", return_value=mock_response) as mock_get:
        result = runner.invoke(app, ["health", "--url", "http://test-server"])
        assert result.exit_code == 0
        assert "healthy" in result.stdout
        mock_get.assert_called_once_with(
            "http://test-server/api/v1/health", timeout=10.0
        )


def test_cli_graph():
    from unittest.mock import patch

    mock_response = httpx.Response(200, json={"nodes": [], "edges": []})
    with patch("httpx.get", return_value=mock_response) as mock_get:
        result = runner.invoke(
            app, ["graph", "owner", "repo", "--url", "http://test-server"]
        )
        assert result.exit_code == 0
        assert "nodes" in result.stdout
        mock_get.assert_called_once_with(
            "http://test-server/api/v1/architecture/owner/repo/graph", timeout=30.0
        )


def test_cli_mcp():
    from unittest.mock import patch

    with patch("backend.mcp_server.run_mcp_server") as mock_run:
        result = runner.invoke(app, ["mcp"])
        assert result.exit_code == 0
        mock_run.assert_called_once()
