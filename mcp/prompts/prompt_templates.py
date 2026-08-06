"""MCP Prompt Templates.

Pre-built prompts that orchestrate MCP tools to answer common
engineering questions about repositories.

Prompts provide structured messages that LLMs can use with the
available tools to perform complex analysis tasks.
"""

import logging
from typing import Any

logger = logging.getLogger("mcp.prompts")


def register(server: Any) -> None:
    """Register all MCP prompts on the server."""

    @server.prompt()
    def explain_repository(owner: str, repo: str) -> str:
        """Generate a comprehensive explanation of a repository's purpose,
        architecture, and key components.

        Args:
            owner: Repository owner or organization.
            repo: Repository name.
        """
        return (
            f"Please analyze the repository '{owner}/{repo}' and provide a comprehensive explanation. "
            f"Use the following tools in sequence:\n\n"
            f"1. Call `get_repository_summary` with owner='{owner}' and repo='{repo}' to understand "
            f"the tech stack, dependencies, and file structure.\n"
            f"2. Call `get_architecture_summary` with owner='{owner}' and repo='{repo}' to understand "
            f"the system architecture and component relationships.\n"
            f"3. Call `get_call_graph` with owner='{owner}' and repo='{repo}' to understand "
            f"the execution flow and function dependencies.\n\n"
            f"Based on these results, provide:\n"
            f"- A clear summary of what the repository does\n"
            f"- The main architectural patterns used\n"
            f"- Key entry points and critical paths\n"
            f"- Notable design decisions\n"
            f"- Recommended reading order for new contributors"
        )

    @server.prompt()
    def review_architecture(owner: str, repo: str) -> str:
        """Analyze and review the architecture quality of a repository,
        identifying potential issues and improvements.

        Args:
            owner: Repository owner or organization.
            repo: Repository name.
        """
        return (
            f"Please perform an architecture review of '{owner}/{repo}'.\n\n"
            f"Use these tools:\n"
            f"1. `get_architecture_summary` to understand the current architecture\n"
            f"2. `get_dependency_graph` to check for dependency issues\n"
            f"3. `get_dead_code` to identify unused code\n"
            f"4. `get_api_surface` to review public API design\n\n"
            f"Provide a review covering:\n"
            f"- Architecture pattern assessment\n"
            f"- Dependency health (circular deps, tight coupling)\n"
            f"- Code hygiene (dead code, unused imports)\n"
            f"- API surface quality\n"
            f"- Specific improvement recommendations"
        )

    @server.prompt()
    def trace_execution_path(owner: str, repo: str, function_name: str) -> str:
        """Trace the call chain of a specific function through the codebase.

        Args:
            owner: Repository owner or organization.
            repo: Repository name.
            function_name: The function or method name to trace.
        """
        return (
            f"Please trace the execution path of '{function_name}' in '{owner}/{repo}'.\n\n"
            f"Use these tools:\n"
            f"1. `get_symbol_definition` to find where '{function_name}' is defined\n"
            f"2. `get_symbol_references` to find all callers of '{function_name}'\n"
            f"3. `get_call_graph` to understand the broader call relationships\n\n"
            f"Provide:\n"
            f"- The definition location and signature\n"
            f"- Complete caller chain (who calls this function)\n"
            f"- Complete callee chain (what this function calls)\n"
            f"- Data flow analysis\n"
            f"- Potential side effects"
        )

    @server.prompt()
    def analyze_blast_radius(owner: str, repo: str, file_path: str) -> str:
        """Determine the impact of changing a specific file in the repository.

        Args:
            owner: Repository owner or organization.
            repo: Repository name.
            file_path: Path to the file to analyze (relative to repo root).
        """
        return (
            f"Please analyze the blast radius of changes to '{file_path}' in '{owner}/{repo}'.\n\n"
            f"Use these tools:\n"
            f"1. `get_file_symbols` to understand what's defined in '{file_path}'\n"
            f"2. `get_impact_analysis` to identify affected components\n"
            f"3. `get_symbol_references` for each symbol to map dependencies\n\n"
            f"Provide:\n"
            f"- List of all symbols defined in the file\n"
            f"- Direct dependents (files that import from this file)\n"
            f"- Transitive impact (indirect dependents)\n"
            f"- Risk assessment (high/medium/low) for modifying this file\n"
            f"- Recommended testing strategy"
        )

    @server.prompt()
    def generate_health_report(owner: str, repo: str) -> str:
        """Generate a comprehensive repository health report.

        Args:
            owner: Repository owner or organization.
            repo: Repository name.
        """
        return (
            f"Please generate a health report for '{owner}/{repo}'.\n\n"
            f"Use the `generate_report` tool with owner='{owner}' and repo='{repo}'.\n\n"
            f"Then analyze the report and provide:\n"
            f"- Overall health score and grade interpretation\n"
            f"- Key strengths of the codebase\n"
            f"- Critical issues that need attention\n"
            f"- Prioritized improvement recommendations\n"
            f"- Comparison to industry best practices"
        )
