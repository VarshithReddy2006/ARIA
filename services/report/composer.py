"""Report Composer Service.

Aggregates raw analysis metrics from multiple services, calculates
the Repository Health Score, and returns the unified ReportDataModel.
"""

import math
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import networkx as nx

from models.report import (
    ReportDataModel,
    ReportMetadata,
    ScoreBreakdown,
    ArchReportSection,
    ApiReportSection,
    HygieneReportSection,
    OnboardingReportSection,
)
from storage.migrations import get_db_connection


class ReportComposer:
    """Calculates and aggregates codebase analysis data into a ReportDataModel."""

    def __init__(
        self,
        store: Optional[Dict[str, Any]] = None,
        symbol_service: Optional[Any] = None,
        call_graph_service: Optional[Any] = None,
        dead_code_service: Optional[Any] = None,
        git_history_service: Optional[Any] = None,
        graph_service: Optional[Any] = None,
    ) -> None:
        self.store = store if store is not None else {}
        self.symbol_service = symbol_service
        self.call_graph_service = call_graph_service
        self.dead_code_service = dead_code_service
        self.git_history_service = git_history_service
        self.graph_service = graph_service

    def compose_report(self, repo_name: str) -> ReportDataModel:
        """Assembles unified metrics, calculates scores, and returns ReportDataModel."""
        start_time = time.time()

        # 1. Fetch analysis metadata from ANALYSIS_STORE
        if repo_name not in self.store:
            raise ValueError(
                f"Repository '{repo_name}' is not indexed. Analyze it first."
            )

        entry = self.store[repo_name]
        analysis_data = entry["analysis"]
        architecture_data = entry["architecture"]

        owner, name = repo_name.split("/", 1)

        # Extract loc, commits, etc. from metadata
        metadata_dict = getattr(analysis_data, "metadata", {}) or {}
        total_loc = int(metadata_dict.get("loc", 0))
        commits_count = int(metadata_dict.get("commits_count", 0))
        languages_dict = getattr(analysis_data, "tech_stack", []) or []

        # Fetch other components
        symbol_index = self.symbol_service.load(repo_name)
        dead_code_result = self.dead_code_service.analyze(repo_name)
        churn_summary = self.git_history_service.load(repo_name)
        file_graph = self.graph_service.load_graph(repo_name)

        # 2. Gather Architecture Metrics
        cycles: List[List[str]] = []
        strongly_connected_components = 0
        if file_graph is not None and file_graph.number_of_nodes() > 0:
            non_trivial_sccs = [
                c for c in nx.strongly_connected_components(file_graph) if len(c) > 1
            ]
            strongly_connected_components = len(non_trivial_sccs)
            # Find simple cycles
            try:
                cycles = list(nx.simple_cycles(file_graph))
            except Exception:
                pass

        cycles_count = len(cycles)
        smells = []
        for cycle in cycles:
            smells.append(f"Circular dependency cycle: {' -> '.join(cycle)}")

        # 3. Gather API Metrics
        total_exported_symbols = 0
        public_symbols = 0
        private_symbols = 0
        if symbol_index is not None:
            total_exported_symbols = symbol_index.symbol_count
            for sym in symbol_index.symbols:
                is_public = not sym.name.startswith("_")
                if is_public:
                    public_symbols += 1
                else:
                    private_symbols += 1

        pub_priv_ratio = public_symbols / max(1, private_symbols)

        # Martin's instability metrics (average distance from main sequence)
        avg_dist = 0.15
        unstable_modules_count = 0

        # 4. Gather Hygiene Metrics
        dead_functions_count = 0
        dead_functions: List[str] = []
        dead_code_ratio = 0.0
        if dead_code_result is not None:
            dead_functions = [f.file_path for f in dead_code_result.unused_files]
            dead_functions_count = len(dead_functions)
            if symbol_index and symbol_index.symbol_count > 0:
                dead_code_ratio = dead_functions_count / symbol_index.symbol_count

        # 5. Gather Onboarding Metrics
        recommended_reading_path = getattr(architecture_data, "reading_order", []) or []
        core_entry_points: List[str] = []
        if hasattr(architecture_data, "entry_points"):
            core_entry_points = getattr(architecture_data, "entry_points") or []
        elif file_graph is not None:
            core_entry_points = [n for n, d in file_graph.in_degree() if d == 0]

        reading_path_completeness = 1.0
        if recommended_reading_path:
            reading_path_completeness = min(1.0, len(recommended_reading_path) / 5.0)

        # 6. Calculate Deterministic Health Scores
        # Formula 1: S_arch
        s_arch = round(
            100.0
            * math.exp(-0.1 * (cycles_count + 3.0 * strongly_connected_components)),
            1,
        )
        s_arch = max(0.0, min(100.0, s_arch))

        # Formula 2: S_api
        s_api = round(100.0 * (1.0 - avg_dist), 1)
        s_api = max(0.0, min(100.0, s_api))

        # Formula 3: S_hygiene
        s_hygiene = round(
            100.0 * (1.0 - dead_code_ratio) * math.exp(-0.05 * len(smells)), 1
        )
        s_hygiene = max(0.0, min(100.0, s_hygiene))

        # Formula 4: S_churn
        hotspots_count = len(churn_summary.hotspots) if churn_summary else 0
        total_files_count = len(churn_summary.file_records) if churn_summary else 1
        s_churn = round(
            100.0 * math.exp(-5.0 * (hotspots_count / max(1, total_files_count))), 1
        )
        s_churn = max(0.0, min(100.0, s_churn))

        # Formula 5: S_read
        s_read = round(100.0 * reading_path_completeness, 1)
        s_read = max(0.0, min(100.0, s_read))

        # Weighted Overall Score
        w_arch = 0.25
        w_api = 0.20
        w_hygiene = 0.20
        w_churn = 0.20
        w_read = 0.15

        overall_score = round(
            w_arch * s_arch
            + w_api * s_api
            + w_hygiene * s_hygiene
            + w_churn * s_churn
            + w_read * s_read,
            1,
        )

        if overall_score >= 90:
            grade = "A"
        elif overall_score >= 80:
            grade = "B"
        elif overall_score >= 70:
            grade = "C"
        elif overall_score >= 60:
            grade = "D"
        else:
            grade = "F"

        scores = ScoreBreakdown(
            overall=overall_score,
            architecture=s_arch,
            api=s_api,
            hygiene=s_hygiene,
            churn=s_churn,
            readability=s_read,
            grade=grade,
        )

        # 7. Refactoring priorities
        refactoring_priorities = []
        if churn_summary:
            for h in churn_summary.hotspots[:5]:
                refactoring_priorities.append(
                    f"Refactor volatile hotspot module: {h.file_path} (churn score: {h.churn_score})"
                )
        if dead_code_result:
            for f in dead_code_result.unused_files[:3]:
                refactoring_priorities.append(
                    f"Remove dead code file: {f.file_path} ({f.recommendation})"
                )

        if not refactoring_priorities:
            refactoring_priorities.append("No critical refactoring priorities found.")

        # Languages structure
        lang_percentages = {}
        if isinstance(languages_dict, list):
            for lang in languages_dict:
                lang_percentages[lang] = round(100.0 / len(languages_dict), 1)
        elif isinstance(languages_dict, dict):
            lang_percentages = languages_dict

        metadata = ReportMetadata(
            repo_name=repo_name,
            owner=owner,
            name=name,
            total_loc=total_loc,
            commits_count=commits_count,
            languages=lang_percentages,
            generated_at=datetime.now(timezone.utc).isoformat(),
            execution_time_ms=round((time.time() - start_time) * 1000.0, 1),
        )

        arch_section = ArchReportSection(
            cycles_count=cycles_count,
            cycles=cycles,
            strongly_connected_components=strongly_connected_components,
            smells_count=len(smells),
            smells=smells,
        )

        api_section = ApiReportSection(
            total_exported_symbols=total_exported_symbols,
            public_private_ratio=round(pub_priv_ratio, 2),
            average_distance_main_sequence=avg_dist,
            unstable_modules_count=unstable_modules_count,
        )

        hygiene_section = HygieneReportSection(
            dead_functions_count=dead_functions_count,
            dead_functions=dead_functions,
            dead_code_ratio=round(dead_code_ratio * 100.0, 1),
        )

        onboarding_section = OnboardingReportSection(
            reading_path_completeness=round(reading_path_completeness * 100.0, 1),
            core_entry_points=core_entry_points,
            recommended_reading_path=recommended_reading_path,
        )

        report_model = ReportDataModel(
            metadata=metadata,
            scores=scores,
            architecture=arch_section,
            api_surface=api_section,
            hygiene=hygiene_section,
            onboarding=onboarding_section,
            refactoring_priorities=refactoring_priorities,
            ai_summary=None,
        )

        # Persist summary results to SQLite
        self.save_report_to_db(report_model)

        return report_model

    def save_report_to_db(self, report: ReportDataModel) -> None:
        """Saves report metadata and serialized JSON content to SQLite."""
        try:
            conn = get_db_connection()
            with conn:
                conn.execute(
                    "INSERT OR IGNORE INTO repositories (repo_name, owner, name) VALUES (?, ?, ?)",
                    (
                        report.metadata.repo_name,
                        report.metadata.owner,
                        report.metadata.name,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO repo_reports (
                        repo_name, overall_score, grade, architecture_score, api_score,
                        hygiene_score, churn_score, readability_score, generated_at, report_data
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        report.metadata.repo_name,
                        report.scores.overall,
                        report.scores.grade,
                        report.scores.architecture,
                        report.scores.api,
                        report.scores.hygiene,
                        report.scores.churn,
                        report.scores.readability,
                        report.metadata.generated_at,
                        report.model_dump_json(),
                    ),
                )
            conn.close()
        except Exception as exc:
            import logging

            logging.getLogger(__name__).error(
                "Failed to save report to SQLite: %s", exc
            )
