"""Documentation Inspection Pack.

Audits documentation coverage, API specs, and missing docstrings.
"""

import uuid
from typing import List

from models.inspection import Finding, InspectionContext
from services.inspection.base import InspectionPack


class DocumentationInspector(InspectionPack):
    """Audits public API documentation completeness and missing comments/README files."""

    def inspect(self, context: InspectionContext) -> List[Finding]:
        findings = []

        files = context.twin.get("files", [])
        
        # Check if README.md exists
        has_readme = False
        for f in files:
            name = f if isinstance(f, str) else f.get("path", "")
            if name.lower() in ("readme.md", "readme"):
                has_readme = True
                break

        if not has_readme:
            findings.append(
                Finding(
                    id=str(uuid.uuid4()),
                    category="documentation",
                    severity="medium",
                    confidence=1.0,
                    title="Missing Project README",
                    description="No README.md file detected in the root directory. This makes onboard onboarding difficult.",
                    affected_entities=["Project Root"],
                    evidence=["No file matching README.md found in codebase file list."],
                    recommendations=[
                        "Create a README.md file detailing codebase setup, scripts, and architecture."
                    ],
                    estimated_effort="1 hour",
                    metadata={"has_readme": False},
                )
            )

        # Check for missing docstrings on symbols
        symbols = context.twin.get("symbols", {}).get("declarations", [])
        if not symbols:
            # Extract symbols from Knowledge Graph
            for node in context.knowledge_graph.get("nodes", []):
                if node.get("type") == "symbol":
                    props = node.get("properties", {})
                    node_id = node.get("id")
                    parts = node_id.split("::")
                    file_path = parts[1] if len(parts) > 1 else ""
                    symbols.append({
                        "name": props.get("name", ""),
                        "file_path": file_path,
                        "docstring": props.get("docstring", "")
                    })
        missing_doc_symbols = []
        for s in symbols:
            if isinstance(s, dict) and not s.get("docstring"):
                missing_doc_symbols.append(s.get("name", "unknown"))

        if missing_doc_symbols:
            findings.append(
                Finding(
                    id=str(uuid.uuid4()),
                    category="documentation",
                    severity="info",
                    confidence=0.9,
                    title="Undocumented Code Symbols Found",
                    description="Several public/nested symbol declarations lack docstrings or code comments.",
                    affected_entities=missing_doc_symbols[:5],
                    evidence=[f"Declaration '{name}' lacks docstrings." for name in missing_doc_symbols[:3]],
                    recommendations=[
                        "Add descriptive docstrings detailing parameters, return values, and exceptions."
                    ],
                    estimated_effort="2 hours",
                    metadata={"undocumented_symbols_count": len(missing_doc_symbols)},
                )
            )

        return findings
