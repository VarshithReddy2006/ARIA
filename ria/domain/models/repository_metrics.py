"""RepositoryMetrics domain value object.

Calculates and stores deterministic quantitative repository software metrics.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["RepositoryMetrics"]


@dataclass(frozen=True)
class RepositoryMetrics:
    """Quantitative software engineering metrics derived from the Digital Twin.

    Attributes:
        repository_size_bytes: Total source bytes across all files.
        files_count: Total file count.
        packages_count: Total package count.
        modules_count: Total module count.
        classes_count: Total class count.
        functions_count: Total function count.
        methods_count: Total method count.
        symbols_count: Total extracted symbol count.
        references_count: Total symbol reference count.
        graph_density: Graph edge to node ratio.
        dependency_count: Total import/dependency edge count.
        inheritance_count: Total subtyping edge count.
        cyclomatic_complexity_average: Average estimated complexity per callable.
    """

    repository_size_bytes: int = 0
    files_count: int = 0
    packages_count: int = 0
    modules_count: int = 0
    classes_count: int = 0
    functions_count: int = 0
    methods_count: int = 0
    symbols_count: int = 0
    references_count: int = 0
    graph_density: float = 0.0
    dependency_count: int = 0
    inheritance_count: int = 0
    cyclomatic_complexity_average: float = 1.0

    def __post_init__(self) -> None:
        for attr in (
            "repository_size_bytes",
            "files_count",
            "packages_count",
            "modules_count",
            "classes_count",
            "functions_count",
            "methods_count",
            "symbols_count",
            "references_count",
            "dependency_count",
            "inheritance_count",
        ):
            val = getattr(self, attr)
            if not isinstance(val, int) or val < 0:
                raise ValueError(f"{attr} must be a non-negative integer, got {val}")
        if self.graph_density < 0.0:
            raise ValueError(
                f"graph_density must be non-negative, got {self.graph_density}"
            )
        if self.cyclomatic_complexity_average < 0.0:
            raise ValueError(
                f"cyclomatic_complexity_average must be non-negative, got {self.cyclomatic_complexity_average}"
            )
