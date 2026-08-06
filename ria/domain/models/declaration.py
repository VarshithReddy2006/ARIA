"""Syntactic declarations extracted from a syntax tree.

A declaration is a *syntactic observation*: a named form appearing at a span. It makes
no claim about what the name refers to, what type it has, or whether anything uses it.

Why this is not a Symbol
-----------------------
Twin Spec section 3.2 defines ``Symbol`` with a moniker, a container reference, a
resolved ``type_ref`` and a provenance triple. Every one of those requires resolution,
which is Milestone 4. Naming this type ``Symbol`` would invite Milestone 4 to treat a
syntactic observation as a resolved entity, and the resulting edges would be name
matches wearing the label of bindings — the exact failure the foundation documents
identify as the previous architecture's central defect.

Accordingly a declaration has:

* a ``name`` as written, never a qualified or resolved name;
* a ``container_path`` of enclosing declaration names, which is lexical nesting
  observed from spans, not a resolved parent;
* no type, no references, no monikers, no confidence.

Confidence is absent on purpose. Every field here is either read directly from the
grammar or absent, so there is nothing to be uncertain about. Uncertainty enters in
Milestone 4 when these observations are bound to each other, and that is where the
provenance triple belongs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from ria.domain.enums import DeclarationKind, Visibility
from ria.domain.models.span import SourceSpan

__all__ = ["Annotation", "DocComment", "SyntaxDeclaration"]


@dataclass(frozen=True)
class Annotation:
    """A decorator or annotation attached to a declaration.

    Covers Python decorators, Java and Kotlin annotations, TypeScript decorators and
    Rust attributes. All are the same syntactic shape: a name, optional arguments, and a
    span attached to a following declaration.

    Arguments are captured as raw source text, not parsed values. Interpreting
    ``@app.get("/users")`` as a route requires framework knowledge, which is a
    Milestone 4 framework descriptor concern. Recording the text means that descriptor
    has something to work from without the parser having pretended to understand it.

    Attributes:
        name: Annotation name as written, for example ``staticmethod`` or ``app.get``.
        span: Where the annotation appears.
        arguments_text: Raw argument text including delimiters, or ``None`` when the
            annotation takes no arguments. An empty string means arguments were present
            but empty, which is a different observation from their absence.
    """

    name: str
    span: SourceSpan
    arguments_text: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("annotation name must be non-empty")

    @property
    def has_arguments(self) -> bool:
        """Whether an argument list was present, even if empty."""
        return self.arguments_text is not None

    def __str__(self) -> str:
        return f"@{self.name}{self.arguments_text or ''}"


@dataclass(frozen=True)
class DocComment:
    """Documentation attached to a declaration.

    Attributes:
        text: Documentation text with comment delimiters removed and indentation
            stripped uniformly. The raw form is recoverable from the span, so keeping
            only the cleaned text here avoids storing the same bytes twice.
        span: Where the documentation appears in the source.
        is_leading: Whether the documentation precedes the declaration, as in a
            JavaDoc or JSDoc block, rather than following it, as in a Python docstring.
            Recorded because it is the only way to tell an orphaned trailing comment
            from documentation of the next declaration.
    """

    text: str
    span: SourceSpan
    is_leading: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "text", self.text.strip())

    @property
    def is_empty(self) -> bool:
        """Whether the documentation has no content after cleaning."""
        return not self.text

    @property
    def summary(self) -> str:
        """First paragraph of the documentation.

        The part a hover or a citation shows. Split on a blank line rather than a
        sentence boundary, because sentence splitting is language-dependent and would
        be wrong for the many docstrings that are not prose.
        """
        for block in self.text.split("\n\n"):
            cleaned = block.strip()
            if cleaned:
                return cleaned
        return ""


@dataclass(frozen=True)
class SyntaxDeclaration:
    """One named form observed in a source file.

    Attributes:
        kind: Syntactic category.
        name: Name exactly as written. Never qualified: qualification requires knowing
            the module's identity, which is resolution.
        span: Full extent of the declaration, including its body.
        name_span: Extent of the name alone. Kept separately because a citation should
            point at the identifier, not at a two-hundred-line body, and because
            Milestone 4 binds references to the name's position.
        container_path: Names of the enclosing declarations, outermost first. Lexical
            nesting observed from span containment. ``("Repository", "save")`` means the
            declaration appeared inside a member named ``save`` inside one named
            ``Repository`` — it does not assert that either resolves to anything.
        visibility: Declared or conventionally inferred visibility.
        annotations: Decorators and annotations attached to the declaration.
        documentation: Attached documentation, if any.
        signature_text: Raw signature text for a callable form, delimiters included, or
            ``None``. Text rather than a parsed parameter model, because parameter
            grammars differ enough between languages that a shared model would either
            lose information or become a union of every language's shape.
        modifiers: Grammar keywords present on the declaration, for example ``static``,
            ``async`` or ``abstract``, in source order.
        is_exported: Whether an export keyword appeared on the declaration itself.
            Distinct from a separate export statement, which is recorded as an
            :class:`~ria.domain.models.syntax_facts.ExportStatement`.
        node_kind: Grammar node type the declaration was extracted from. Retained so a
            plugin author can tell which grammar rule produced a wrong result without
            re-parsing.
    """

    kind: DeclarationKind
    name: str
    span: SourceSpan
    name_span: SourceSpan
    node_kind: str
    container_path: Tuple[str, ...] = ()
    visibility: Visibility = Visibility.NOT_APPLICABLE
    annotations: Tuple[Annotation, ...] = ()
    documentation: Optional[DocComment] = None
    signature_text: Optional[str] = None
    modifiers: Tuple[str, ...] = ()
    is_exported: bool = False

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("declaration name must be non-empty")
        if not self.node_kind:
            raise ValueError("node_kind must be non-empty")
        if not self.span.contains(self.name_span):
            raise ValueError(
                f"the name span {self.name_span} of {self.name!r} lies outside its "
                f"declaration span {self.span}"
            )
        if any(not part for part in self.container_path):
            raise ValueError("container_path entries must be non-empty")
        object.__setattr__(self, "container_path", tuple(self.container_path))
        object.__setattr__(self, "annotations", tuple(self.annotations))
        object.__setattr__(self, "modifiers", tuple(self.modifiers))

    # -- derived -----------------------------------------------------------

    @property
    def lexical_path(self) -> Tuple[str, ...]:
        """Container path with this declaration's own name appended.

        The lexical address of the declaration within its file. Not a moniker: a moniker
        is scheme-qualified and globally stable (Twin Spec section 3.1), and producing
        one requires knowing the module's identity.
        """
        return self.container_path + (self.name,)

    @property
    def qualified_name(self) -> str:
        """Dotted lexical path, for display and logging only.

        Deliberately not an identity. Two files in one repository can produce the same
        qualified name, which is precisely why Milestone 4 introduces monikers.
        """
        return ".".join(self.lexical_path)

    @property
    def is_nested(self) -> bool:
        """Whether the declaration appears inside another declaration."""
        return bool(self.container_path)

    @property
    def is_top_level(self) -> bool:
        """Whether the declaration appears at file scope."""
        return not self.container_path

    @property
    def annotation_names(self) -> Tuple[str, ...]:
        """Names of the attached annotations, in source order.

        The input to framework entry-point detection in Milestone 4, which is why the
        names are surfaced separately from the annotation objects.
        """
        return tuple(annotation.name for annotation in self.annotations)

    def has_modifier(self, modifier: str) -> bool:
        """Whether a grammar keyword is present on the declaration.

        Args:
            modifier: Keyword to test, for example ``async``.
        """
        return modifier in self.modifiers

    def has_annotation(self, name: str) -> bool:
        """Whether an annotation with a given name is attached.

        Args:
            name: Annotation name as written.
        """
        return name in self.annotation_names

    def sort_key(self) -> Tuple[int, int, str]:
        """Deterministic ordering key: position, then name.

        Position alone is not total — a zero-width span can coincide with another — so
        the name breaks the tie and keeps serialised extraction output stable.
        """
        return (self.span.start.byte, -self.span.end.byte, self.name)

    def __str__(self) -> str:
        return f"{self.kind} {self.qualified_name} @{self.span}"
