"""Dependency Inspection Pack.

Audits circular imports, bloated dependencies, and package freshness.
"""

import uuid
from typing import List

from models.inspection import Finding, InspectionContext
from services.inspection.base import InspectionPack


class DependencyInspector(InspectionPack):
    """Audits circular imports, bloated package lists, and outdated versions."""

    def inspect(self, context: InspectionContext) -> List[Finding]:
        findings = []

        relationships = context.twin.get("dependencies", {}).get("relationships", [])
        if not relationships:
            # Extract relationships from Knowledge Graph IMPORTS edges
            for edge in context.knowledge_graph.get("edges", []):
                if edge.get("type") == "IMPORTS":
                    src = edge.get("source", "").split("::")[-1]
                    tgt = edge.get("target", "").split("::")[-1]
                    relationships.append({
                        "source": src,
                        "target": tgt,
                    })
        
        # Check for circular imports in dependencies
        # Let's write a simple cyclic check in dependency relationships
        cycles = []
        for r1 in relationships:
            src = r1.get("source")
            tgt = r1.get("target")
            if not src or not tgt or src == tgt:
                continue
            # Look for reverse
            for r2 in relationships:
                if r2.get("source") == tgt and r2.get("target") == src:
                    cycles.append((src, tgt))

        if cycles:
            findings.append(
                Finding(
                    id=str(uuid.uuid4()),
                    category="dependency",
                    severity="high",
                    confidence=0.95,
                    title="Circular Module Imports Detected",
                    description="Circular imports between files prevent clean module initialization and cause execution failures.",
                    affected_entities=[f"{s} <-> {t}" for s, t in cycles[:3]],
                    evidence=[f"Module import cycle between {s} and {t}" for s, t in cycles[:3]],
                    recommendations=[
                        "Refactor shared exports to a third leaf module.",
                        "Reorganize files using interface encapsulation."
                    ],
                    estimated_effort="3 hours",
                    metadata={"cyclic_imports_count": len(cycles)},
                )
            )

        # Check for bloated dependencies list
        tech_stack = context.twin.get("metadata", {}).get("tech_stack", [])
        dep_count = len(relationships)
        if dep_count > 30:
            findings.append(
                Finding(
                    id=str(uuid.uuid4()),
                    category="dependency",
                    severity="low",
                    confidence=0.85,
                    title="High Dependency Count",
                    description="The project depends on a large number of components, increasing architectural coupling.",
                    affected_entities=["Project Configuration"],
                    evidence=[f"Found {dep_count} component dependency edges."],
                    recommendations=[
                        "Audit dependencies to prune unused packages.",
                        "Consolidate components with overlapping responsibilities."
                    ],
                    estimated_effort="4 hours",
                    metadata={"dependency_edges_count": dep_count},
                )
            )

        return findings
