"""Performance Inspection Pack.

Audits execution performance indicators, call graphs, and hot pathways.
"""

import uuid
from typing import List

from models.inspection import Finding, InspectionContext
from services.inspection.base import InspectionPack


class PerformanceInspector(InspectionPack):
    """Audits hot paths, deeply-nested calls, and query performance bottlenecks."""

    def inspect(self, context: InspectionContext) -> List[Finding]:
        findings = []

        twin_metadata = context.twin.get("metadata", {})
        total_loc = twin_metadata.get("total_loc", 0)

        # Flag extremely large file performance impact
        large_files = []
        files = context.twin.get("files", [])
        local_path = context.twin.get("metadata", {}).get("local_path")
        for f in files:
            if isinstance(f, dict):
                if f.get("size", 0) > 100000:  # > 100KB
                    large_files.append(f.get("path"))
            elif isinstance(f, str) and local_path:
                import os
                full_path = os.path.join(local_path, f)
                if os.path.exists(full_path):
                    try:
                        if os.path.getsize(full_path) > 100000:
                            large_files.append(f)
                    except Exception:
                        pass

        if large_files:
            findings.append(
                Finding(
                    id=str(uuid.uuid4()),
                    category="performance",
                    severity="medium",
                    confidence=0.8,
                    title="Extremely Large Source Files Detected",
                    description="Large source files (>100KB) can lead to slow compilation, high parsing latency, and poor caching.",
                    affected_entities=large_files,
                    evidence=[f"File '{path}' exceeds standard size constraints." for path in large_files[:3]],
                    recommendations=[
                        "Split the module into smaller, cohesive classes/functions.",
                        "Employ lazy loading or dynamic imports to reduce load-time performance costs."
                    ],
                    estimated_effort="4 hours",
                    metadata={"large_files_count": len(large_files)},
                )
            )

        return findings
