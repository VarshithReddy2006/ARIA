"""First-party CLI for ARIA (AI-Powered Repository Intelligence Agent) using Typer."""

import os
import json
import httpx
import typer
from typing import Optional

app = typer.Typer(help="ARIA CLI")


def get_api_url(url: Optional[str]) -> str:
    """Resolves the backend API server base URL."""
    if url:
        return url.rstrip("/")
    env_url = os.environ.get("API_SERVER_URL")
    if env_url:
        return env_url.rstrip("/")
    # Default fallback
    return "http://localhost:8001"


@app.command()
def analyze(
    repo_url: str = typer.Argument(..., help="GitHub repository URL"),
    branch: str = typer.Option("main", "--branch", "-b", help="Git branch or ref"),
    model: str = typer.Option(
        "deepseek-ai/deepseek-v4-flash",
        "--model",
        "-m",
        help="LLM model variant to use",
    ),
    url: Optional[str] = typer.Option(
        None, "--url", "-u", help="Base URL of the API server"
    ),
) -> None:
    """Initiates repository analysis and streams progress."""
    base_url = get_api_url(url)
    api_endpoint = f"{base_url}/api/v1/analyze"

    typer.echo(f"Submitting analysis request to {api_endpoint}...")

    try:
        with httpx.stream(
            "POST",
            api_endpoint,
            json={"url": repo_url, "branch": branch, "model": model},
            timeout=None,
        ) as response:
            if response.status_code != 200:
                # Read response body for error detail
                err_content = response.read().decode("utf-8", errors="ignore")
                typer.echo(f"Error {response.status_code}: {err_content}", err=True)
                raise typer.Exit(code=1)

            for line in response.iter_lines():
                if not line.strip():
                    continue
                if line.startswith("data:"):
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        typer.echo("Analysis complete.")
                        break
                    try:
                        data = json.loads(data_str)
                        event = data.get("event") or data.get("status")
                        message = data.get("message") or data.get("step") or ""
                        if event:
                            typer.echo(f"[{event}] {message}")
                        else:
                            typer.echo(data_str)
                    except json.JSONDecodeError:
                        typer.echo(data_str)
    except Exception as exc:
        typer.echo(f"Connection failed: {exc}", err=True)
        raise typer.Exit(code=1)


@app.command()
def graph(
    owner: str = typer.Argument(..., help="Repository owner/organization"),
    repo: str = typer.Argument(..., help="Repository name"),
    url: Optional[str] = typer.Option(
        None, "--url", "-u", help="Base URL of the API server"
    ),
) -> None:
    """Retrieves the React-Flow compatible dependency graph data."""
    base_url = get_api_url(url)
    api_endpoint = f"{base_url}/api/v1/architecture/{owner}/{repo}/graph"

    try:
        response = httpx.get(api_endpoint, timeout=30.0)
        if response.status_code == 200:
            typer.echo(json.dumps(response.json(), indent=2))
        else:
            typer.echo(f"Error {response.status_code}: {response.text}", err=True)
            raise typer.Exit(code=1)
    except Exception as exc:
        typer.echo(f"Request failed: {exc}", err=True)
        raise typer.Exit(code=1)


@app.command(name="call-graph")
def call_graph(
    owner: str = typer.Argument(..., help="Repository owner/organization"),
    repo: str = typer.Argument(..., help="Repository name"),
    url: Optional[str] = typer.Option(
        None, "--url", "-u", help="Base URL of the API server"
    ),
) -> None:
    """Retrieves call graph summary details for the repository."""
    base_url = get_api_url(url)
    api_endpoint = f"{base_url}/api/v1/call-graph/{owner}/{repo}"

    try:
        response = httpx.get(api_endpoint, timeout=30.0)
        if response.status_code == 200:
            typer.echo(json.dumps(response.json(), indent=2))
        else:
            typer.echo(f"Error {response.status_code}: {response.text}", err=True)
            raise typer.Exit(code=1)
    except Exception as exc:
        typer.echo(f"Request failed: {exc}", err=True)
        raise typer.Exit(code=1)


@app.command(name="api-surface")
def api_surface(
    owner: str = typer.Argument(..., help="Repository owner/organization"),
    repo: str = typer.Argument(..., help="Repository name"),
    url: Optional[str] = typer.Option(
        None, "--url", "-u", help="Base URL of the API server"
    ),
) -> None:
    """Retrieves the API surface data for a repository."""
    base_url = get_api_url(url)
    api_endpoint = f"{base_url}/api/v1/api-surface/{owner}/{repo}"

    try:
        response = httpx.get(api_endpoint, timeout=30.0)
        if response.status_code == 200:
            typer.echo(json.dumps(response.json(), indent=2))
        else:
            typer.echo(f"Error {response.status_code}: {response.text}", err=True)
            raise typer.Exit(code=1)
    except Exception as exc:
        typer.echo(f"Request failed: {exc}", err=True)
        raise typer.Exit(code=1)


@app.command()
def stability(
    owner: str = typer.Argument(..., help="Repository owner/organization"),
    repo: str = typer.Argument(..., help="Repository name"),
    url: Optional[str] = typer.Option(
        None, "--url", "-u", help="Base URL of the API server"
    ),
) -> None:
    """Retrieves module stability scores.

    Note: The module stability router is not yet implemented. This command
    will return a 404 until the stability endpoints are added in a future release.
    """
    base_url = get_api_url(url)
    api_endpoint = f"{base_url}/api/v1/stability/{owner}/{repo}"
    try:
        response = httpx.get(api_endpoint, timeout=30.0)
        if response.status_code == 200:
            typer.echo(json.dumps(response.json(), indent=2))
        elif response.status_code == 404:
            typer.echo(
                "Module stability endpoints are not yet implemented. Check back in a future release."
            )
        else:
            typer.echo(f"Error {response.status_code}: {response.text}", err=True)
            raise typer.Exit(code=1)
    except Exception as exc:
        typer.echo(f"Request failed: {exc}", err=True)
        raise typer.Exit(code=1)


@app.command()
def health(
    url: Optional[str] = typer.Option(
        None, "--url", "-u", help="Base URL of the API server"
    ),
) -> None:
    """Verifies connection and checks health status of backend systems."""
    base_url = get_api_url(url)
    api_endpoint = f"{base_url}/api/v1/health"

    try:
        response = httpx.get(api_endpoint, timeout=10.0)
        if response.status_code == 200:
            typer.echo(json.dumps(response.json(), indent=2))
        else:
            typer.echo(f"Error {response.status_code}: {response.text}", err=True)
            raise typer.Exit(code=1)
    except Exception as exc:
        typer.echo(f"Health check failed: {exc}", err=True)
        raise typer.Exit(code=1)


@app.command()
def version(
    url: Optional[str] = typer.Option(
        None, "--url", "-u", help="Base URL of the API server"
    ),
) -> None:
    """Prints the CLI version and backend version."""
    typer.echo("Client Version: 1.5.0")

    base_url = get_api_url(url)
    api_endpoint = f"{base_url}/api/v1/health"
    try:
        response = httpx.get(api_endpoint, timeout=5.0)
        if response.status_code == 200:
            status = response.json().get("status", "unknown")
            typer.echo(f"Backend Status: {status}")
        else:
            typer.echo("Backend: Offline")
    except Exception:
        typer.echo("Backend: Offline")


@app.command()
def report(
    repo_name: str = typer.Argument(..., help="Repository identifier (owner/repo)"),
    html: bool = typer.Option(False, "--html", help="Generate HTML report"),
    pdf: bool = typer.Option(
        False, "--pdf", help="Generate print-ready PDF-friendly HTML report"
    ),
    markdown: bool = typer.Option(
        False, "--markdown", "--md", help="Generate Markdown report"
    ),
    output_path: Optional[str] = typer.Option(
        None, "--output-path", "-o", help="Path to write the report file"
    ),
    url: Optional[str] = typer.Option(
        None, "--url", "-u", help="Base URL of the API server"
    ),
) -> None:
    """Generates and downloads the Repository Intelligence Report."""
    if "/" not in repo_name:
        typer.echo(
            "Error: Repository identifier must be in the format 'owner/repo_name'",
            err=True,
        )
        raise typer.Exit(code=1)

    base_url = get_api_url(url)
    owner, repo = repo_name.split("/", 1)

    # 1. Trigger report build
    build_endpoint = f"{base_url}/api/v1/report/{owner}/{repo}/build"
    try:
        typer.echo(f"Building health report for {repo_name}...")
        resp = httpx.post(build_endpoint, timeout=60.0)
        if resp.status_code != 200:
            typer.echo(f"Error building report: {resp.text}", err=True)
            raise typer.Exit(code=1)

        report_data = resp.json()
        overall = report_data["scores"]["overall"]
        grade = report_data["scores"]["grade"]
        typer.echo(
            f"Report composed successfully. Health Score: {overall} (Grade: {grade})"
        )

        # Determine the format
        if markdown:
            fmt = "markdown"
            ext = "md"
        elif pdf:
            fmt = "pdf"
            ext = "html"
        else:
            fmt = "html"
            ext = "html"

        # 2. Download report
        download_endpoint = (
            f"{base_url}/api/v1/report/{owner}/{repo}/download?format={fmt}"
        )
        typer.echo(f"Downloading {fmt.upper()} report...")
        down_resp = httpx.get(download_endpoint, timeout=30.0)
        if down_resp.status_code != 200:
            typer.echo(f"Error downloading report: {down_resp.text}", err=True)
            raise typer.Exit(code=1)

        # Determine output file path
        if not output_path:
            output_path = f"{owner}_{repo}_report.{ext}"

        with open(output_path, "wb") as fh:
            fh.write(down_resp.content)

        typer.echo(
            f"{fmt.upper()} report successfully saved to {os.path.abspath(output_path)}"
        )
    except Exception as exc:
        typer.echo(f"Failed to generate report: {exc}", err=True)
        raise typer.Exit(code=1)


@app.command()
def mcp() -> None:
    """Launches the stdio JSON-RPC Model Context Protocol (MCP) server.

    Speaks JSON-RPC on stdin/stdout and logs to stderr, so it can be launched
    directly by any MCP client. The FastMCP implementation under ``mcp/`` stays
    importable for direct integrations but is deliberately not constructed here,
    to keep this entry point free of SDK-version-specific behaviour.
    """
    from backend.mcp_server import run_mcp_server

    run_mcp_server()


if __name__ == "__main__":
    app()
