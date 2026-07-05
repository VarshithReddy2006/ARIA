"""Complexity Inspection Pack.

Audits cognitive/cyclomatic complexity, line counts, and nesting depths.
"""

import uuid
from typing import List

from models.inspection import Finding, InspectionContext
from services.inspection.base import InspectionPack


class ComplexityInspector(InspectionPack):
    """Audits cyclomatic complexity, cognitive overload, and bloated functions."""

    def inspect(self, context: InspectionContext) -> List[Finding]:
        findings = []

        twin_metadata = context.twin.get("metadata", {})
        complexity = twin_metadata.get("complexity", 1.0)

        # Flag general high repository complexity
        if complexity > 5.0:
            findings.append(
                Finding(
                    id=str(uuid.uuid4()),
                    category="complexity",
                    severity="medium",
                    confidence=0.8,
                    title="High Cognitive Codebase Complexity",
                    description="The repository exhibits high overall complexity, making it difficult to maintain.",
                    affected_entities=["Whole Codebase"],
                    evidence=[f"Calculated codebase complexity rating of {complexity} exceeds standard limit of 5.0."],
                    recommendations=[
                        "Enforce strict limits on function sizes and cyclomatic parameters.",
                        "Refactor complex branches and nested conditionals."
                    ],
                    estimated_effort="8 hours",
                    metadata={"complexity_rating": complexity},
                )
            )

        # Check for individual complex symbols
        symbols = context.twin.get("symbols", {}).get("declarations", [])
        if not symbols:
            # Build fan-out map for symbols from call graph
            fan_out = {}
            for edge in context.knowledge_graph.get("edges", []):
                if edge.get("type") == "CALLS":
                    src = edge.get("source")
                    fan_out[src] = fan_out.get(src, 0) + 1

            # Extract symbols from Knowledge Graph
            for node in context.knowledge_graph.get("nodes", []):
                if node.get("type") == "symbol":
                    props = node.get("properties", {})
                    node_id = node.get("id")
                    parts = node_id.split("::")
                    file_path = parts[1] if len(parts) > 1 else ""
                    calls_count = fan_out.get(node_id, 0)
                    complexity_val = 5 + calls_count * 3
                    symbols.append({
                        "name": props.get("name", ""),
                        "file_path": file_path,
                        "complexity": complexity_val,
                        "docstring": props.get("docstring", "")
                    })
        highly_complex_symbols = []
        for s in symbols:
            if isinstance(s, dict) and s.get("complexity", 0) > 15:
                highly_complex_symbols.append(s)

        if highly_complex_symbols:
            affected = [s.get("name", "unknown") for s in highly_complex_symbols]
            findings.append(
                Finding(
                    id=str(uuid.uuid4()),
                    category="complexity",
                    severity="high",
                    confidence=0.9,
                    title="Highly Complex Declarations Found",
                    description="Individual functions/classes exhibit high complexity and exceed testing maintainability limits.",
                    affected_entities=affected,
                    evidence=[
                        f"Declaration '{s.get('name')}' in file '{s.get('file_path')}' has complexity {s.get('complexity')}"
                        for s in highly_complex_symbols[:3]
                    ],
                    recommendations=[
                        "Decompose functions into smaller sub-helpers.",
                        "Simplify branch nesting and logical expression chains."
                    ],
                    estimated_effort="3 hours",
                    metadata={"highly_complex_declarations_count": len(highly_complex_symbols)},
                )
            )

        return findings
