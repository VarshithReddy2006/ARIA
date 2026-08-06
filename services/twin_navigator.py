"""Repository Twin Navigator Service.

Provides APIs to query and navigate the Repository Digital Twin. Delegates directly
to the underlying domain-specific services without replicating business logic.
"""

import os
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class RepositoryTwinNavigator:
    """Query and navigation façade (RepositoryTwinNavigator) over codebase intelligence services."""

    def __init__(
        self,
        symbol_service: Optional[Any] = None,
        graph_service: Optional[Any] = None,
        architecture_service: Optional[Any] = None,
        report_composer: Optional[Any] = None,
        impact_analysis_service: Optional[Any] = None,
        github_service: Optional[Any] = None,
        twin_builder: Optional[Any] = None,
    ) -> None:
        self.symbol_service = symbol_service
        self.graph_service = graph_service
        self.architecture_service = architecture_service
        self.report_composer = report_composer
        self.impact_analysis_service = impact_analysis_service
        self.github_service = github_service
        self.twin_builder = twin_builder

    def get_twin_builder(self) -> Any:
        """Return the injected twin builder."""
        return self.twin_builder

    def find_symbol(self, repo_name: str, symbol_name: str) -> Dict[str, Any]:
        """Finds definition and references for the specified symbol name."""
        definition = self.symbol_service.get_definition(repo_name, symbol_name)
        references = self.symbol_service.get_references(repo_name, symbol_name) or []

        return {
            "symbol_name": symbol_name,
            "definition": definition.model_dump() if definition else None,
            "references": [ref.model_dump() for ref in references],
        }

    def find_file(self, repo_name: str, file_path: str) -> Dict[str, Any]:
        """Reads file content from the local clone if it exists."""
        local_repo_path = self.github_service.get_local_repo_path(repo_name)
        # Prevent directory traversal attacks
        safe_path = os.path.abspath(os.path.join(local_repo_path, file_path))
        if not safe_path.startswith(os.path.abspath(local_repo_path)):
            raise ValueError(f"Path traversal detected: {file_path}")

        if not os.path.exists(safe_path):
            raise FileNotFoundError(
                f"File '{file_path}' not found in repository clone."
            )

        with open(safe_path, "r", encoding="utf-8", errors="replace") as fh:
            content = fh.read()

        return {
            "file_path": file_path,
            "content": content,
            "size_bytes": os.path.getsize(safe_path),
        }

    def find_dependencies(self, repo_name: str, file_path: str) -> List[str]:
        """Returns direct imports/dependencies of the specified file path."""
        dep_graph = self.graph_service.load_graph(repo_name)
        if dep_graph is None or not dep_graph.has_node(file_path):
            return []
        return list(dep_graph.successors(file_path))

    def find_dependents(self, repo_name: str, file_path: str) -> List[str]:
        """Returns files that depend on/import the specified file path."""
        dep_graph = self.graph_service.load_graph(repo_name)
        if dep_graph is None or not dep_graph.has_node(file_path):
            return []
        return list(dep_graph.predecessors(file_path))

    def find_architecture(self, repo_name: str) -> Dict[str, Any]:
        """Retrieves summary and relationships from architecture service."""
        summary = self.architecture_service.get_summary(repo_name)
        if summary is None:
            return {}
        return summary.model_dump()

    def find_health(self, repo_name: str) -> Dict[str, Any]:
        """Returns composed health scoring report."""
        report = self.report_composer.compose_report(repo_name)
        return report.model_dump()

    def find_compliance(self, repo_name: str) -> Dict[str, Any]:
        """Returns the lightweight compliance summary."""
        builder = self.get_twin_builder()
        twin = builder.build_twin(repo_name)
        return twin.compliance_summary

    def calculate_impact(self, repo_name: str, issue_text: str) -> Dict[str, Any]:
        """Predicts the blast radius of changes for the given issue or file description."""
        analysis = self.impact_analysis_service.analyze_change(repo_name, issue_text)
        return analysis.model_dump()
