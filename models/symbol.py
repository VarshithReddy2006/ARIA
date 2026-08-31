"""Symbol data models for PH2-002 — Symbol Intelligence Layer.

These Pydantic models represent the Symbol data structures used for
persistence (data/symbols/) and API response serialisation.

Kept in a dedicated module (separate from models/schemas.py) to isolate
the Symbol Intelligence domain and avoid touching existing model definitions.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class Symbol(BaseModel):
    """A single named symbol extracted from a source file via Tree-sitter AST.

    Attributes:
        name:         Identifier as it appears in the source (e.g. "chat_streamer").
        type:         Symbol category: function | class | method | interface |
                      enum | variable.
        file_path:    Relative file path within the repository.
        line_number:  1-indexed line of the definition (from AST start_point).
        language:     Source language: python | javascript | typescript | tsx.
        parent_class: Enclosing class name for method symbols; None otherwise.
    """

    name: str = Field(..., description="Symbol identifier name.")
    type: str = Field(
        ...,
        description=(
            "Symbol type: function | class | method | interface | enum | variable"
        ),
    )
    file_path: str = Field(
        ...,
        description="Relative file path within the repository.",
    )
    line_number: int = Field(
        ...,
        ge=1,
        description="1-indexed line number of the symbol definition.",
    )
    language: str = Field(
        ...,
        description="Source language: python | javascript | typescript | tsx",
    )
    parent_class: Optional[str] = Field(
        None,
        description=(
            "Enclosing class name for method symbols; "
            "None for top-level functions, classes, interfaces, and enums."
        ),
    )


class SymbolIndex(BaseModel):
    """Persisted symbol index for an entire repository.

    Written to data/symbols/{owner}_{repo}.json by SymbolService.build().

    Attributes:
        repo:          Repository identifier (owner/repo).
        generated_at:  ISO-8601 UTC timestamp of index generation.
        symbol_count:  Total number of symbols (convenience field).
        symbols:       Flat list of all extracted Symbol objects.
    """

    repo: str = Field(..., description="Repository identifier (owner/repo).")
    generated_at: str = Field(
        ...,
        description="ISO-8601 UTC timestamp of index generation.",
    )
    symbol_count: int = Field(
        ...,
        ge=0,
        description="Total number of symbols in the index.",
    )
    symbols: List[Symbol] = Field(
        default_factory=list,
        description="All symbols extracted from all supported source files.",
    )

    @property
    def file_symbol_map(self) -> dict[str, List[Symbol]]:
        """Return cached O(1) mapping from normalized file path to symbols."""
        if not hasattr(self, "_file_symbol_map_cache"):
            mapping: dict[str, List[Symbol]] = {}
            for s in self.symbols:
                norm_p = s.file_path.replace("\\", "/").lower()
                if norm_p not in mapping:
                    mapping[norm_p] = []
                mapping[norm_p].append(s)
            object.__setattr__(self, "_file_symbol_map_cache", mapping)
        return getattr(self, "_file_symbol_map_cache")

    @property
    def name_symbol_map(self) -> dict[str, List[Symbol]]:
        """Return cached O(1) mapping from lowercase symbol name to symbols."""
        if not hasattr(self, "_name_symbol_map_cache"):
            mapping: dict[str, List[Symbol]] = {}
            for s in self.symbols:
                name_key = s.name.lower()
                if name_key not in mapping:
                    mapping[name_key] = []
                mapping[name_key].append(s)
            object.__setattr__(self, "_name_symbol_map_cache", mapping)
        return getattr(self, "_name_symbol_map_cache")
