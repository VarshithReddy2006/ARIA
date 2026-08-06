"""Digital Twin result and metadata value objects.

Defines TwinMetadata, TwinStatistics, and TwinDiagnostic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from ria.domain.enums import DiagnosticSeverity

__all__ = ["TwinMetadata", "TwinStatistics", "TwinDiagnostic"]


@dataclass(frozen=True)
class TwinMetadata:
    """Provenance metadata for a constructed Digital Twin.

    Attributes:
        repository_id: Identity of the repository.
        commit_sha: Identity of the commit snapshot.
        created_at_iso: UTC timestamp when the twin was constructed.
        builder_version: Version of the twin builder.
        schema_version: Version of the twin schema.
    """

    repository_id: str
    commit_sha: str
    created_at_iso: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    builder_version: str = "1.0.0"
    schema_version: str = "1.0.0"


@dataclass(frozen=True)
class TwinStatistics:
    """Quantitative summary statistics of a Digital Twin.

    Attributes:
        files_total: Total files count.
        modules_total: Total modules count.
        symbols_total: Total symbols count.
        nodes_total: Total graph nodes count.
        edges_total: Total graph edges count.
    """

    files_total: int = 0
    modules_total: int = 0
    symbols_total: int = 0
    nodes_total: int = 0
    edges_total: int = 0


@dataclass(frozen=True)
class TwinDiagnostic:
    """Diagnostic message emitted during twin construction or synchronization.

    Attributes:
        severity: DiagnosticSeverity level.
        message: Text explanation.
        code: Error/warning code.
        component: Associated component name.
    """

    severity: DiagnosticSeverity
    message: str
    code: str = "TWIN_DIAGNOSTIC"
    component: Optional[str] = None
