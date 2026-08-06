"""Architectural Rule Engine (ArchUnit Style).

Enforces layer boundary integrity and architectural rules across repository imports:
  - Rule 1: Layer Flow (Presentation -> Application -> Domain -> Infrastructure)
  - Rule 2: Domain Cleanliness (Domain layer must NEVER import Presentation or Infrastructure)
  - Rule 3: Direct Database Access (Presentation Controllers/Routers must NOT access Data/Database directly)
"""

from __future__ import annotations

from typing import Dict, List, Any
from .layer_classifier import classify_layer


def evaluate_rules(graph_edges: List[Dict[str, str]]) -> Dict[str, Any]:
    """Evaluate ArchUnit-style rules across all dependency edges."""
    violations: List[Dict[str, Any]] = []

    for edge in graph_edges:
        src = edge.get("source") or edge.get("src")
        tgt = edge.get("target") or edge.get("dst")
        if not src or not tgt:
            continue

        src_layer = classify_layer(src)
        tgt_layer = classify_layer(tgt)

        # Rule 2: Domain must never import Presentation or Infrastructure
        if src_layer == "Domain" and tgt_layer in ("Presentation", "Infrastructure"):
            violations.append({
                "rule_id": "ARCH-001",
                "rule_name": "Domain Cleanliness Violation",
                "severity": "CRITICAL",
                "source_node": src,
                "target_node": tgt,
                "description": f"Domain module '{src}' illegally depends on {tgt_layer} module '{tgt}'.",
            })

        # Rule 3: Presentation cannot directly access Data / Infrastructure / Database
        if src_layer == "Presentation" and (tgt_layer in ("Data", "Infrastructure") or "db" in tgt.lower() or "repository" in tgt.lower()):
            violations.append({
                "rule_id": "ARCH-002",
                "rule_name": "Direct Infrastructure Access Violation",
                "severity": "MAJOR",
                "source_node": src,
                "target_node": tgt,
                "description": f"Presentation module '{src}' directly accesses Data/Infrastructure module '{tgt}' bypassing Application layer.",
            })

        # Rule 1: Backward layer import (Infrastructure calling Presentation)
        if src_layer == "Infrastructure" and tgt_layer == "Presentation":
            violations.append({
                "rule_id": "ARCH-003",
                "rule_name": "Upward Layer Dependency Violation",
                "severity": "CRITICAL",
                "source_node": src,
                "target_node": tgt,
                "description": f"Infrastructure module '{src}' imports Presentation layer module '{tgt}'.",
            })

    return {
        "violation_count": len(violations),
        "critical_count": sum(1 for v in violations if v["severity"] == "CRITICAL"),
        "major_count": sum(1 for v in violations if v["severity"] == "MAJOR"),
        "minor_count": sum(1 for v in violations if v["severity"] == "MINOR"),
        "violations": violations,
    }
