"""Module-level and free-standing syntactic facts.

Three shapes that are not named declarations and would need meaningless nullable fields
if forced into :class:`~ria.domain.models.declaration.SyntaxDeclaration`: import
statements, export statements, and comments.

Imports and exports carry no resolution
---------------------------------------
An :class:`ImportStatement` records the module specifier *as written* — ``"../utils"``,
``"os.path"``, ``"@scope/pkg"`` — and never a resolved path. Turning a specifier into a
file requires the module resolution algorithm of the language and build system, which is
Milestone 4's Resolution layer. The foundation documents identify name-matched edges
presented as bindings as the previous architecture's central defect, so the syntax layer
records the text and stops.

The consequence is deliberate and worth stating: nothing in Milestone 3 can answer "what
does this file depend on". It can only answer "what does this file say it imports".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

from ria.domain.models.declaration import SyntaxDeclaration
from ria.domain.models.span import SourceSpan

__all__ = [
    "ImportedName",
    "ImportStatement",
    "ExportStatement",
    "CommentBlock",
    "ExtractedSyntax",
]


@dataclass(frozen=True)
class ImportedName:
    """One name brought into scope by an import statement.

    Attributes:
        name: Name as it appears in the source module, or ``*`` for a wildcard import.
        alias: Local name it is bound to, when renamed. ``None`` when no alias is
            present, which is a different observation from an alias equal to the name.
    """

    name: str
    alias: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("imported name must be non-empty")
        if self.alias is not None and not self.alias:
            raise ValueError("alias must be non-empty when present")

    @property
    def local_name(self) -> str:
        """The name visible in the importing file."""
        return self.alias or self.name

    @property
    def is_wildcard(self) -> bool:
        """Whether the import brings in everything from the module."""
        return self.name == "*"

    def __str__(self) -> str:
        return f"{self.name} as {self.alias}" if self.alias else self.name


@dataclass(frozen=True)
class ImportStatement:
    """An import as written in the source.

    Attributes:
        module_text: Module specifier exactly as written, delimiters removed. Never
            resolved to a path.
        span: Where the statement appears.
        names: Names brought into scope. Empty for a whole-module import such as
            ``import os``, where the module itself is the binding.
        is_relative: Whether the specifier is relative, for example ``./x`` or ``..y``.
            Recorded because it is decidable from syntax and is the first thing
            Milestone 4's resolver needs, whereas resolving it is not.
        is_type_only: Whether the import is erased at runtime, as in TypeScript's
            ``import type``. A type-only import is a real dependency for analysis and
            no dependency at runtime, and conflating the two would misreport both.
        is_side_effect_only: Whether the statement binds nothing, as in ``import
            "./polyfill"``. Such an import cannot be dead-code eliminated, so recording
            it prevents a later milestone reporting it as unused.
        node_kind: Grammar node type the statement was extracted from.
    """

    module_text: str
    span: SourceSpan
    node_kind: str
    names: Tuple[ImportedName, ...] = ()
    is_relative: bool = False
    is_type_only: bool = False
    is_side_effect_only: bool = False

    def __post_init__(self) -> None:
        if not self.module_text:
            raise ValueError("module_text must be non-empty")
        if not self.node_kind:
            raise ValueError("node_kind must be non-empty")
        if self.is_side_effect_only and self.names:
            raise ValueError(
                "a side-effect-only import binds no names, but "
                f"{len(self.names)} were recorded"
            )
        object.__setattr__(self, "names", tuple(self.names))

    @property
    def local_names(self) -> Tuple[str, ...]:
        """Names visible in the importing file, in source order."""
        return tuple(name.local_name for name in self.names)

    @property
    def has_wildcard(self) -> bool:
        """Whether the statement imports everything from the module."""
        return any(name.is_wildcard for name in self.names)

    def sort_key(self) -> Tuple[int, str]:
        """Deterministic ordering key: position, then specifier."""
        return (self.span.start.byte, self.module_text)

    def __str__(self) -> str:
        return f"import {self.module_text} ({len(self.names)} names)"


@dataclass(frozen=True)
class ExportStatement:
    """An export as written in the source.

    Covers both re-exports, which name a source module, and local exports, which do not.
    A declaration carrying an inline export keyword is recorded on the declaration
    itself as ``is_exported`` rather than here, so that one export is never counted
    twice.

    Attributes:
        span: Where the statement appears.
        node_kind: Grammar node type the statement was extracted from.
        names: Names exported. Empty for a wildcard re-export.
        module_text: Source module for a re-export, as written, or ``None`` for a local
            export.
        is_default: Whether this is a default export.
        is_wildcard: Whether the statement re-exports everything from the module.
    """

    span: SourceSpan
    node_kind: str
    names: Tuple[ImportedName, ...] = ()
    module_text: Optional[str] = None
    is_default: bool = False
    is_wildcard: bool = False

    def __post_init__(self) -> None:
        if not self.node_kind:
            raise ValueError("node_kind must be non-empty")
        if self.is_wildcard and not self.module_text:
            raise ValueError(
                "a wildcard export must name the module it re-exports from"
            )
        if self.module_text is not None and not self.module_text:
            raise ValueError("module_text must be non-empty when present")
        object.__setattr__(self, "names", tuple(self.names))

    @property
    def is_reexport(self) -> bool:
        """Whether the statement re-exports from another module."""
        return self.module_text is not None

    def sort_key(self) -> Tuple[int, str]:
        """Deterministic ordering key: position, then module specifier."""
        return (self.span.start.byte, self.module_text or "")

    def __str__(self) -> str:
        target = f" from {self.module_text}" if self.module_text else ""
        return f"export {len(self.names)} names{target}"


@dataclass(frozen=True)
class CommentBlock:
    """A comment not attached to any declaration.

    Comments that document a declaration are recorded on it as a
    :class:`~ria.domain.models.declaration.DocComment`. What remains — licence headers,
    section banners, commented-out code, and the annotations engineers leave for each
    other — is recorded here.

    Free-standing comments are worth keeping rather than discarding: a file's licence
    header, and the notes engineers leave to explain a workaround they were not happy
    about, are among the few places intent is written down at all. Twin Spec section 5.2
    identifies unrecorded intent as a hard ceiling on comprehension, so discarding these
    at the syntax layer would close a door no later milestone could reopen.

    Attributes:
        text: Comment text with delimiters removed.
        span: Where the comment appears.
        is_block: Whether the comment used block delimiters rather than line ones.
        node_kind: Grammar node type the comment was extracted from.
    """

    text: str
    span: SourceSpan
    node_kind: str
    is_block: bool = False

    def __post_init__(self) -> None:
        if not self.node_kind:
            raise ValueError("node_kind must be non-empty")
        object.__setattr__(self, "text", self.text.strip())

    @property
    def is_empty(self) -> bool:
        """Whether the comment has no content after cleaning."""
        return not self.text

    def sort_key(self) -> Tuple[int, int]:
        """Deterministic ordering key by position."""
        return self.span.sort_key()

    def __str__(self) -> str:
        head = self.text.split("\n", 1)[0]
        clipped = head if len(head) <= 40 else head[:37] + "..."
        return f"comment@{self.span}: {clipped}"


@dataclass(frozen=True)
class ExtractedSyntax:
    """Everything the extractors found in one file.

    A single value object rather than four collections passed around together, so that a
    parse result cannot carry declarations from one file and imports from another.

    Every collection is sorted by position at construction. Extraction order depends on
    tree walk order, which is deterministic, but sorting here means the invariant holds
    regardless of how a future plugin chooses to walk — and the milestone's determinism
    requirement covers the extraction output, not only the tree.

    Attributes:
        declarations: Named forms found, in source order.
        imports: Import statements, in source order.
        exports: Export statements, in source order.
        comments: Free-standing comments, in source order.
    """

    declarations: Tuple[SyntaxDeclaration, ...] = ()
    imports: Tuple[ImportStatement, ...] = ()
    exports: Tuple[ExportStatement, ...] = ()
    comments: Tuple[CommentBlock, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "declarations",
            tuple(sorted(self.declarations, key=lambda item: item.sort_key())),
        )
        object.__setattr__(
            self,
            "imports",
            tuple(sorted(self.imports, key=lambda item: item.sort_key())),
        )
        object.__setattr__(
            self,
            "exports",
            tuple(sorted(self.exports, key=lambda item: item.sort_key())),
        )
        object.__setattr__(
            self,
            "comments",
            tuple(sorted(self.comments, key=lambda item: item.sort_key())),
        )

    # -- selection ---------------------------------------------------------

    def declarations_of_kind(self, *kinds) -> Tuple[SyntaxDeclaration, ...]:
        """Declarations matching any of the given kinds, in source order.

        Args:
            *kinds: :class:`~ria.domain.enums.DeclarationKind` members to match.
        """
        wanted = frozenset(kinds)
        return tuple(
            declaration
            for declaration in self.declarations
            if declaration.kind in wanted
        )

    def top_level_declarations(self) -> Tuple[SyntaxDeclaration, ...]:
        """Declarations at file scope, in source order."""
        return tuple(
            declaration for declaration in self.declarations if declaration.is_top_level
        )

    def declarations_within(
        self, container_path: Tuple[str, ...]
    ) -> Tuple[SyntaxDeclaration, ...]:
        """Declarations directly inside a lexical container.

        Args:
            container_path: Lexical path of the container.
        """
        return tuple(
            declaration
            for declaration in self.declarations
            if declaration.container_path == container_path
        )

    # -- measures ----------------------------------------------------------

    @property
    def is_empty(self) -> bool:
        """Whether nothing at all was extracted.

        True for an empty file, and also for a file whose language has no extractor
        installed. The two are distinguished by the parse result's capabilities, not
        here, which is why a consumer must consult those rather than infer from
        emptiness.
        """
        return not (self.declarations or self.imports or self.exports or self.comments)

    @property
    def total(self) -> int:
        """Total facts extracted."""
        return (
            len(self.declarations)
            + len(self.imports)
            + len(self.exports)
            + len(self.comments)
        )

    def counts(self) -> Mapping[str, int]:
        """Count per fact category, omitting empty categories.

        Suitable directly as progress detail and bounded-cardinality metric labels.
        """
        counts = {
            "declarations": len(self.declarations),
            "imports": len(self.imports),
            "exports": len(self.exports),
            "comments": len(self.comments),
        }
        return {name: value for name, value in counts.items() if value}

    def declaration_kind_counts(self) -> Mapping[str, int]:
        """Count of declarations per kind, omitting empty kinds.

        Feeds the per-language coverage report of Twin Spec section 9.
        """
        counts: dict = {}
        for declaration in self.declarations:
            counts[declaration.kind.value] = counts.get(declaration.kind.value, 0) + 1
        return counts

    def __str__(self) -> str:
        rendered = ", ".join(
            f"{name}={value}" for name, value in sorted(self.counts().items())
        )
        return f"extracted({rendered or 'nothing'})"
