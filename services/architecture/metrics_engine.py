"""Advanced Architecture Software Metrics Engine.

Computes deterministic software metrics for files, modules, and directories:
  - Afferent Coupling (Ca): Incoming dependencies
  - Efferent Coupling (Ce): Outgoing dependencies
  - Instability (I = Ce / (Ca + Ce))
  - Abstractness (A = Abstract / Total)
  - Distance from Main Sequence (D = |A + I - 1|)
  - Cyclomatic Complexity (v(G))
  - Maintainability Index (MI = 171 - 5.2*ln(V) - 0.23*v(G) - 16.2*ln(LOC))
  - Dependency Depth, Import/Export Counts, Public Symbols, Line Counts
"""

from __future__ import annotations

import math
import re
from typing import Dict, Any, List


def compute_metrics(
    node_id: str,
    content: str = "",
    depends_on: List[str] | None = None,
    imported_by: List[str] | None = None,
) -> Dict[str, Any]:
    """Compute complete software metrics suite for a node."""
    depends_on = depends_on or []
    imported_by = imported_by or []

    ca = len(imported_by)
    ce = len(depends_on)
    instability = round(ce / (ca + ce), 3) if (ca + ce) > 0 else 0.0

    lines = content.splitlines() if content else []
    loc = max(len(lines), 1)
    comment_lines = sum(
        1 for line in lines if line.strip().startswith(("#", "//", "/*", "*"))
    )
    comment_density = round((comment_lines / loc) * 100, 1)

    # Cyclomatic complexity heuristic (decision keywords)
    decision_keywords = [
        "if ",
        "elif ",
        "else:",
        "for ",
        "while ",
        "except ",
        "catch ",
        "case ",
        "&&",
        "||",
        " and ",
        " or ",
    ]
    cyclomatic_complexity = 1 + sum(content.count(kw) for kw in decision_keywords)

    # Functions, classes, public symbols
    functions_count = len(re.findall(r"\b(def|function|const|let|var)\s+\w+", content))
    classes_count = len(re.findall(r"\b(class|interface|struct|enum)\s+\w+", content))
    public_symbols_count = len(
        re.findall(r"\b(export\s+|def\s+[a-zA-Z0-9]+|class\s+[a-zA-Z0-9]+)", content)
    )

    abstract_count = len(
        re.findall(r"\b(ABC|abstractclass|interface|abstract)\b", content)
    )
    abstractness = (
        round(abstract_count / max(classes_count, 1), 3) if classes_count > 0 else 0.0
    )
    distance_main_sequence = round(abs(abstractness + instability - 1.0), 3)

    # Maintainability Index calculation
    halstead_volume = max(loc * 5.0, 1.0)
    mi_raw = (
        171.0
        - 5.2 * math.log(halstead_volume)
        - 0.23 * cyclomatic_complexity
        - 16.2 * math.log(loc)
    )
    maintainability_index = max(0.0, min(100.0, round(mi_raw * 100 / 171.0, 1)))

    return {
        "fan_in": ca,
        "fan_out": ce,
        "afferent_coupling": ca,
        "efferent_coupling": ce,
        "instability": instability,
        "abstractness": abstractness,
        "distance_main_sequence": distance_main_sequence,
        "cyclomatic_complexity": cyclomatic_complexity,
        "maintainability_index": maintainability_index,
        "dependency_depth": len(depends_on) + 1,
        "import_count": len(depends_on),
        "export_count": max(public_symbols_count, 1),
        "public_symbols_count": public_symbols_count,
        "classes_count": classes_count,
        "functions_count": functions_count,
        "avg_function_length": round(loc / max(functions_count, 1), 1),
        "lines_of_code": loc,
        "comment_density": comment_density,
    }
