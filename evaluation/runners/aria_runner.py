"""ARIA runner: Executes real ARIA evidence-backed impact analysis."""

import time
from typing import Dict, Any
from backend.dependencies import get_impact_analysis_service


class AriaRunner:
    """Evaluates task impact using ARIA's real deterministic services."""

    def __init__(self):
        self.service = get_impact_analysis_service()

    def run_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        start_time = time.perf_counter()

        repo_name = task["repository"]
        change_desc = task["change_description"]

        result = self.service.analyze_change(repo_name, change_desc)
        latency_ms = (time.perf_counter() - start_time) * 1000.0

        all_affected_files = sorted(
            list(set(result.directly_affected_files + result.indirectly_affected_files))
        )
        callers = sorted(
            list(
                set(
                    [
                        c.caller_name
                        for c in result.direct_callers + result.transitive_callers
                        if not self.service._is_test_file(c.file_path)
                    ]
                )
            )
        )
        tests = sorted(list(set([t.test_file for t in result.affected_tests])))
        tests_high = sorted(
            list(
                set(
                    [
                        t.test_file
                        for t in result.affected_tests
                        if t.confidence_tier == "HIGH"
                    ]
                )
            )
        )
        tests_med = sorted(
            list(
                set(
                    [
                        t.test_file
                        for t in result.affected_tests
                        if t.confidence_tier in ("HIGH", "MEDIUM")
                    ]
                )
            )
        )
        routes = (
            sorted(result.api_exposure.public_routes)
            if result.api_exposure and result.api_exposure.public_routes
            else []
        )

        return {
            "task_id": task["task_id"],
            "approach": "aria_impact_engine",
            "latency_ms": round(latency_ms, 2),
            "predicted_files": all_affected_files,
            "high_confidence_files": result.high_confidence_files,
            "medium_confidence_files": result.medium_confidence_files,
            "low_confidence_files": result.low_confidence_files,
            "predicted_callers": callers,
            "predicted_tests": tests,
            "predicted_tests_high": tests_high,
            "predicted_tests_high_med": tests_med,
            "predicted_api_surfaces": routes,
            "predicted_risk": result.risk_level,
            "blast_radius_category": result.blast_radius_category,
            "evidence_count": len(result.evidence_items),
            "implementation_order": result.implementation_order,
        }
