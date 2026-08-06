"""Architecture Diagram & ADR Generator.

Generates Mermaid diagrams, PlantUML syntax, ADR (Architecture Decision Record) documents, and sequence diagrams for repository nodes.
"""

from __future__ import annotations

import os
from typing import Dict, Any, List


def generate_mermaid_diagram(node_id: str, depends_on: List[str], imported_by: List[str]) -> str:
    """Generate a clean Mermaid class/dependency diagram for a node."""
    short_name = os.path.basename(node_id).replace(".", "_").replace("-", "_")
    lines = ["graph TD", f"    classDef target fill:#1e1b4b,stroke:#6366f1,stroke-width:2px,color:#fff;"]

    for dep in depends_on:
        dep_name = os.path.basename(dep).replace(".", "_").replace("-", "_")
        lines.append(f"    {short_name}[{os.path.basename(node_id)}] --> {dep_name}[{os.path.basename(dep)}]")

    for imp in imported_by:
        imp_name = os.path.basename(imp).replace(".", "_").replace("-", "_")
        lines.append(f"    {imp_name}[{os.path.basename(imp)}] --> {short_name}[{os.path.basename(node_id)}]")

    lines.append(f"    class {short_name} target;")
    return "\n".join(lines)


def generate_plantuml_diagram(node_id: str, depends_on: List[str], imported_by: List[str]) -> str:
    """Generate PlantUML component diagram syntax."""
    base = os.path.basename(node_id)
    lines = [
        "@startuml",
        "skinparam componentStyle uml2",
        "skinparam backgroundColor transparent",
        f"component [{base}] as Target #Indigo",
    ]

    for dep in depends_on:
        d_base = os.path.basename(dep)
        lines.append(f"component [{d_base}]")
        lines.append(f"Target --> [{d_base}] : depends on")

    for imp in imported_by:
        i_base = os.path.basename(imp)
        lines.append(f"component [{i_base}]")
        lines.append(f"[{i_base}] --> Target : imports")

    lines.append("@enduml")
    return "\n".join(lines)


def generate_adr(node_id: str, responsibility: str, layer: str, patterns: List[str]) -> str:
    """Generate an Architecture Decision Record (ADR) markdown document."""
    file_name = os.path.basename(node_id)
    pattern_str = ", ".join(patterns) if patterns else "Facade / Modular Component"
    return f"""# ADR 001: Architectural Role & Design of `{file_name}`

## Status
Accepted

## Context
The module `{node_id}` serves as a core component within the **{layer} Layer** of the repository architecture.

## Decision
We implement `{file_name}` following the **{pattern_str}** architectural pattern.

## Responsibilities
{responsibility}

## Consequences
- **Positive**: Maintains separation of concerns and clear layer boundaries.
- **Negative**: Modifications require verifying downstream dependent consumers.
"""


def generate_sequence_diagram(node_id: str, depends_on: List[str], imported_by: List[str]) -> str:
    """Generate a sequence flow diagram in Mermaid format."""
    caller = os.path.basename(imported_by[0]) if imported_by else "Client"
    target = os.path.basename(node_id)
    dep = os.path.basename(depends_on[0]) if depends_on else "Database / External API"

    return f"""sequenceDiagram
    autonumber
    participant Caller as {caller}
    participant Target as {target}
    participant Dep as {dep}

    Caller->>Target: Invoke Request / Action
    Target->>Dep: Query / Fetch Dependencies
    Dep-->>Target: Return Data Payload
    Target-->>Caller: Return Response / Result
"""
