"""Immutable Index Units for C1 Index Core."""

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from ria.domain.common.base import ValueObject
from ria.domain.common.value_objects import Timestamp, UUIDv4
from ria.domain.index.value_objects import ASTNode, ContentHash, FilePath, Language
from ria.domain.sync.value_objects import CommitReference, RepositoryIdentity


@dataclass(frozen=True, slots=True)
class FileUnit(ValueObject):
    """Immutable unit representing a discovered file in a repository."""

    path: FilePath
    language: Language
    content_hash: ContentHash
    size_bytes: int

    def _validate_invariants(self) -> None:
        if self.size_bytes < 0:
            raise ValueError("File size_bytes cannot be negative.")


@dataclass(frozen=True, slots=True)
class ASTUnit(ValueObject):
    """Immutable unit representing a generated AST for a single file."""

    path: FilePath
    language: Language
    root_node: ASTNode
    total_nodes: int

    def _validate_invariants(self) -> None:
        if self.total_nodes < 1:
            raise ValueError("total_nodes must be at least 1.")


@dataclass(frozen=True, slots=True)
class ParserResult(ValueObject):
    """Immutable result of executing a Tree-sitter parser plugin."""

    ast_root_node: Optional[ASTNode]
    is_success: bool
    total_nodes: int
    has_syntax_errors: bool
    error_message: Optional[str] = None


@dataclass(frozen=True, slots=True)
class ParseUnit(ValueObject):
    """Immutable composite parse unit combining FileUnit, ASTUnit, and parse metrics."""

    file_unit: FileUnit
    ast_unit: Optional[ASTUnit]
    parse_duration_ms: float
    is_truncated: bool = False

    def _validate_invariants(self) -> None:
        if self.parse_duration_ms < 0.0:
            raise ValueError("parse_duration_ms cannot be negative.")


@dataclass(frozen=True, slots=True)
class DirectoryUnit(ValueObject):
    """Immutable unit representing a directory node in a scanned repository."""

    path: FilePath
    child_directories: Tuple[FilePath, ...] = field(default_factory=tuple)
    child_files: Tuple[FileUnit, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class RepositoryUnit(ValueObject):
    """Immutable unit representing the entire scanned directory hierarchy of a repository."""

    identity: RepositoryIdentity
    commit: CommitReference
    directories: Tuple[DirectoryUnit, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class IndexBatch(ValueObject):
    """Immutable batch of parsed units produced by Index Core."""

    batch_id: UUIDv4
    repo_id: RepositoryIdentity
    commit: CommitReference
    parse_units: Tuple[ParseUnit, ...]
    created_at: Timestamp

    def _validate_invariants(self) -> None:
        if not self.parse_units:
            raise ValueError("IndexBatch must contain at least one ParseUnit.")


@dataclass(frozen=True, slots=True)
class IndexManifest(ValueObject):
    """Immutable manifest summarizing an IndexBatch."""

    batch_id: UUIDv4
    total_files: int
    total_parsed: int
    total_failed: int
    language_counts: Tuple[Tuple[str, int], ...]

    def _validate_invariants(self) -> None:
        if self.total_files < 0 or self.total_parsed < 0 or self.total_failed < 0:
            raise ValueError("Manifest counts cannot be negative.")
