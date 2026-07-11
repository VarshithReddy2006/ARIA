"""Architecture Inspection Pack.

Audits architectural coupling, dependency density, and structural integrity.
"""

import uuid
from typing import List

from models.inspection import Finding, InspectionContext
from services.inspection.base import InspectionPack


class ArchitectureInspector(InspectionPack):
    """Audits architectural structures and component coupling boundaries."""

    def inspect(self, context: InspectionContext) -> List[Finding]:
        findings = []

        relationships = context.twin.get("architecture", {}).get("relationships", [])
        if not relationships:
            # Extract relationships from Knowledge Graph IMPORTS edges
            for edge in context.knowledge_graph.get("edges", []):
                if edge.get("type") == "IMPORTS":
                    src = edge.get("source", "").split("::")[-1]
                    tgt = edge.get("target", "").split("::")[-1]
                    relationships.append(
                        {"source": src, "target": tgt, "dependencies": [tgt]}
                    )

        # Check for high coupling
        high_coupling_components = []
        for rel in relationships:
            coupling_score = rel.get("coupling_score", 0.0) or (
                len(rel.get("dependencies", [])) * 2
            )
            if coupling_score > 10:
                high_coupling_components.append(rel)

        if high_coupling_components:
            affected = [r.get("source", "unknown") for r in high_coupling_components]
            findings.append(
                Finding(
                    id=str(uuid.uuid4()),
                    category="architecture",
                    severity="high",
                    confidence=0.9,
                    title="High Component Coupling Detected",
                    description="Several modules exhibit high coupling, making the codebase rigid and fragile.",
                    affected_entities=affected,
                    evidence=[
                        f"Component '{r.get('source')}' has {len(r.get('dependencies', []))} dependencies on '{r.get('target')}'"
                        for r in high_coupling_components[:3]
                    ],
                    recommendations=[
                        "Introduce abstractions or interface layers to isolate components.",
                        "Refactor high-coupling components into smaller, independent modules.",
                    ],
                    estimated_effort="4 hours",
                    metadata={"high_coupling_count": len(high_coupling_components)},
                )
            )

        # Check for cyclic dependencies in relationships
        # We can extract edges and find cycles or read them from twin/KG
        # (e.g. source -> target and target -> source)
        mutual_relations = []
        pairs_seen = set()
        for r1 in relationships:
            src, tgt = r1.get("source"), r1.get("target")
            if not src or not tgt or src == tgt:
                continue
            pair = tuple(sorted([src, tgt]))
            if pair in pairs_seen:
                continue
            # Search for reverse
            for r2 in relationships:
                if r2.get("source") == tgt and r2.get("target") == src:
                    mutual_relations.append((src, tgt))
                    pairs_seen.add(pair)
                    break

        if mutual_relations:
            affected = [f"{s} <-> {t}" for s, t in mutual_relations]
            findings.append(
                Finding(
                    id=str(uuid.uuid4()),
                    category="architecture",
                    severity="critical",
                    confidence=0.95,
                    title="Circular Dependency Cycles Detected",
                    description="Cycles detected between architectural layers, violating clean architecture boundaries.",
                    affected_entities=affected,
                    evidence=[
                        f"Bidirectional dependency path between {s} and {t}"
                        for s, t in mutual_relations
                    ],
                    recommendations=[
                        "Apply Dependency Inversion Principle using interfaces.",
                        "Extract shared logic into a separate utility or leaf component.",
                    ],
                    estimated_effort="8 hours",
                    metadata={"cycles_count": len(mutual_relations)},
                )
            )

        return findings
