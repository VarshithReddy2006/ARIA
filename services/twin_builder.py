"""Repository Twin Builder Service.

Thin orchestrator that aggregates repository state and delegates to dedicated
providers to compose the read-only RepositoryTwin and RepositoryTwinSummary views.
"""

import os
import logging
import subprocess
import networkx as nx
from typing import Any, Dict, Optional

from models.twin import RepositorySnapshot, RepositoryTwin, RepositoryTwinSummary

logger = logging.getLogger(__name__)


class RepositoryTwinBuilder:
    """Builds the composed RepositoryTwin view by aggregating existing services."""

    def __init__(
        self,
        store: Optional[Dict[str, Any]] = None,
        symbol_service: Optional[Any] = None,
        graph_service: Optional[Any] = None,
        architecture_service: Optional[Any] = None,
        report_composer: Optional[Any] = None,
        dead_code_service: Optional[Any] = None,
        github_service: Optional[Any] = None,
        snapshot_store: Optional[Any] = None,
    ) -> None:
        """Initialise the twin builder. Resolves dependencies lazily if not provided."""
        from backend.dependencies import (
            ANALYSIS_STORE as default_store,
            symbol_service as ss,
            graph_service as gs,
            architecture_service as as_srv,
            report_composer as rc,
            dead_code_service as dcs,
            github_service as gh,
            snapshot_store as snap_store,
        )

        self.store = store if store is not None else default_store
        self.symbol_service = symbol_service or ss
        self.graph_service = graph_service or gs
        self.architecture_service = architecture_service or as_srv
        self.report_composer = report_composer or rc
        self.dead_code_service = dead_code_service or dcs
        self.github_service = github_service or gh
        self.snapshot_store = snapshot_store or snap_store

    def build_snapshot(
        self,
        repo_name: str,
        local_path: Optional[str],
        manifest: Optional[Dict[str, Any]],
    ) -> RepositorySnapshot:
        """Constructs a RepositorySnapshot representation pinning the current repository state."""
        commit_sha = "unknown"
        if manifest and "repository_hash" in manifest:
            commit_sha = manifest["repository_hash"]
        elif local_path and os.path.exists(os.path.join(local_path, ".git")):
            try:
                res = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=local_path,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                commit_sha = res.stdout.strip()
            except Exception as e:
                logger.debug("Failed to retrieve commit SHA via git: %s", e)

        branch = "main"
        if local_path and os.path.exists(os.path.join(local_path, ".git")):
            try:
                res = subprocess.run(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    cwd=local_path,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                branch = res.stdout.strip()
            except Exception as e:
                logger.debug("Failed to retrieve branch via git: %s", e)

        indexed_timestamp = 0.0
        if manifest and "last_successful_build" in manifest:
            indexed_timestamp = manifest["last_successful_build"]

        analysis_version = "1.0.0"
        if manifest and "application_version" in manifest:
            analysis_version = manifest["application_version"]

        return RepositorySnapshot(
            commit_sha=commit_sha,
            branch=branch,
            indexed_timestamp=indexed_timestamp,
            analysis_version=analysis_version,
        )

    def build_twin(self, repo_name: str) -> RepositoryTwin:
        """Aggregates existing services to build the full RepositoryTwin view."""
        if repo_name not in self.store:
            raise ValueError(
                f"Repository '{repo_name}' is not indexed. Analyze it first."
            )

        entry = self.store[repo_name]
        analysis_data = entry["analysis"]
        architecture_data = entry["architecture"]

        local_path = self.github_service.get_local_repo_path(repo_name)
        manifest = self.snapshot_store.load(repo_name, "build_manifest")

        # 1. Build RepositorySnapshot
        snapshot = self.build_snapshot(repo_name, local_path, manifest)

        # 2. Extract files list and metadata
        file_hashes = manifest.get("file_hashes", {}) if manifest else {}
        files = list(file_hashes.keys()) if file_hashes else []

        metadata_dict = getattr(analysis_data, "metadata", {}) or {}
        total_loc = int(metadata_dict.get("loc", 0))
        commits_count = int(metadata_dict.get("commits_count", 0))
        tech_stack = getattr(analysis_data, "tech_stack", []) or []

        metadata = {
            "tech_stack": tech_stack,
            "total_loc": total_loc,
            "commits_count": commits_count,
            "local_path": local_path,
        }

        # 3. Retrieve Symbols summary
        symbol_index = self.symbol_service.load(repo_name)
        total_symbols = symbol_index.symbol_count if symbol_index else 0
        public_symbols = 0
        private_symbols = 0
        if symbol_index:
            for sym in symbol_index.symbols:
                if sym.name.startswith("_"):
                    private_symbols += 1
                else:
                    public_symbols += 1
        public_private_ratio = public_symbols / max(1, private_symbols)

        symbols_summary = {
            "total_symbols": total_symbols,
            "public_symbols": public_symbols,
            "private_symbols": private_symbols,
            "public_private_ratio": round(public_private_ratio, 2),
        }

        # 4. Retrieve Dependencies summary
        dep_graph = self.graph_service.load_graph(repo_name)
        dependencies_list = getattr(analysis_data, "dependencies", []) or []
        dependencies_summary = {
            "dependencies": dependencies_list,
            "import_relationships_count": dep_graph.number_of_edges()
            if dep_graph is not None
            else 0,
            "dependency_nodes_count": dep_graph.number_of_nodes()
            if dep_graph is not None
            else 0,
        }

        # 5. Retrieve Architecture summary
        cycles_count = 0
        strongly_connected_components = 0
        if dep_graph is not None and dep_graph.number_of_nodes() > 0:
            strongly_connected_components = nx.number_strongly_connected_components(
                dep_graph
            )
            try:
                cycles_count = len(list(nx.simple_cycles(dep_graph)))
            except Exception:
                pass

        entry_points = []
        if hasattr(architecture_data, "entry_points"):
            entry_points = getattr(architecture_data, "entry_points") or []
        elif dep_graph is not None:
            entry_points = [n for n, d in dep_graph.in_degree() if d == 0]

        architecture_summary = {
            "summary": getattr(architecture_data, "summary", ""),
            "cycles_count": cycles_count,
            "strongly_connected_components": strongly_connected_components,
            "entry_points": entry_points,
            "reading_order": getattr(architecture_data, "reading_order", []) or [],
        }

        # 6. Retrieve Health summary
        report = self.report_composer.compose_report(repo_name)
        health_summary = {
            "overall_score": report.scores.overall,
            "grade": report.scores.grade,
            "breakdown": {
                "architecture": report.scores.architecture,
                "api": report.scores.api,
                "hygiene": report.scores.hygiene,
                "churn": report.scores.churn,
                "readability": report.scores.readability,
            },
        }

        # 7. Compute lightweight Compliance summary
        dead_code_result = self.dead_code_service.analyze(repo_name)
        dead_code_ratio = 0.0
        if dead_code_result and symbol_index and symbol_index.symbol_count > 0:
            dead_code_ratio = (
                len(dead_code_result.unused_files) / symbol_index.symbol_count
            )

        has_license = any(f.lower().startswith("license") for f in files)

        compliance_status = "compliant"
        reasons = []
        if cycles_count > 5:
            compliance_status = "non-compliant"
            reasons.append("High number of circular dependency cycles (>5).")
        elif cycles_count > 0:
            compliance_status = "warning"
            reasons.append("Circular dependency cycles detected.")

        if dead_code_ratio > 0.30:
            compliance_status = "non-compliant"
            reasons.append("Dead code ratio is too high (>30%).")
        elif dead_code_ratio > 0.15 and compliance_status != "non-compliant":
            compliance_status = "warning"
            reasons.append("Dead code ratio is high (>15%).")

        if not has_license:
            if compliance_status != "non-compliant":
                compliance_status = "warning"
            reasons.append("Missing LICENSE file.")

        compliance_summary = {
            "status": compliance_status,
            "reasons": reasons,
            "has_license": has_license,
            "cycles_count": cycles_count,
            "dead_code_ratio": round(dead_code_ratio * 100, 1),
        }

        return RepositoryTwin(
            repository_name=repo_name,
            snapshot=snapshot,
            metadata=metadata,
            files=files,
            symbols_summary=symbols_summary,
            dependencies_summary=dependencies_summary,
            architecture_summary=architecture_summary,
            health_summary=health_summary,
            compliance_summary=compliance_summary,
        )

    def build_twin_summary(self, repo_name: str) -> RepositoryTwinSummary:
        """Builds a lightweight summary version of the Repository Twin."""
        twin = self.build_twin(repo_name)
        return RepositoryTwinSummary(
            repository_name=twin.repository_name,
            snapshot=twin.snapshot,
            tech_stack=twin.metadata.get("tech_stack", []),
            overall_health_score=twin.health_summary.get("overall_score", 0.0),
            health_grade=twin.health_summary.get("grade", "F"),
            compliance_status=twin.compliance_summary.get("status", "non-compliant"),
            total_files=len(twin.files),
            total_symbols=twin.symbols_summary.get("total_symbols", 0),
        )
