"""Resolution Context passed through resolution stages."""

from dataclasses import dataclass, field
from typing import Tuple

from ria.domain.common.base import ValueObject
from ria.domain.index.value_objects import FilePath, Language
from ria.domain.resolution.value_objects import ImportRelation, SymbolMoniker
from ria.domain.sync.value_objects import CommitReference, RepositoryIdentity


@dataclass(frozen=True, slots=True)
class ResolutionContext(ValueObject):
    """Immutable resolution context holding state during single-file or batch symbol resolution."""

    repo_id: RepositoryIdentity
    commit: CommitReference
    current_path: FilePath
    language: Language
    scope_chain: Tuple[str, ...] = field(default_factory=tuple)
    imported_symbols: Tuple[ImportRelation, ...] = field(default_factory=tuple)
    exported_symbols: Tuple[SymbolMoniker, ...] = field(default_factory=tuple)

    def with_scope(self, scope_name: str) -> "ResolutionContext":
        """Return a new ResolutionContext pushed with scope_name."""
        return ResolutionContext(
            repo_id=self.repo_id,
            commit=self.commit,
            current_path=self.current_path,
            language=self.language,
            scope_chain=self.scope_chain + (scope_name,),
            imported_symbols=self.imported_symbols,
            exported_symbols=self.exported_symbols,
        )

    def build_moniker(self, symbol_name: str) -> SymbolMoniker:
        """Construct a deterministic SymbolMoniker using repo, path, scope chain, and symbol name."""
        scope_str = ".".join(self.scope_chain) if self.scope_chain else "global"
        raw = f"{self.repo_id.repo_id.value}:{self.current_path.relative_path}:{scope_str}:{symbol_name}"
        return SymbolMoniker(value=raw)
