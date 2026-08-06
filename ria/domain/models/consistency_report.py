"""ConsistencyReport domain value object.

Validates consistency across Repository, Knowledge Graph, Semantic Layer, and Parser Layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from ria.domain.models.twin_result import TwinDiagnostic

__all__ = ["ConsistencyReport"]


@dataclass(frozen=True)
class ConsistencyReport:
    """Consistency audit report across Digital Twin layers.

    Attributes:
        is_consistent: True if zero inconsistencies detected.
        repository_to_graph_consistent: True if Repository ↔ Graph matches.
        graph_to_semantic_consistent: True if Graph ↔ Semantic matches.
        semantic_to_parser_consistent: True if Semantic ↔ Parser matches.
        inconsistencies: Tuple of TwinDiagnostic messages explaining discrepancies.
    """

    is_consistent: bool = True
    repository_to_graph_consistent: bool = True
    graph_to_semantic_consistent: bool = True
    semantic_to_parser_consistent: bool = True
    inconsistencies: Tuple[TwinDiagnostic, ...] = ()
