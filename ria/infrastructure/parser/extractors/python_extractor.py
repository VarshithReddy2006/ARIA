"""Python syntax extractor.

Extracts functions, methods, classes, imports, comments, docstrings, decorators,
visibility, and parameters from Python syntax trees.
"""

from __future__ import annotations

from typing import FrozenSet, List, Optional, Tuple

from ria.domain.enums import DeclarationKind, ParserCapability, Visibility
from ria.domain.models.declaration import Annotation, DocComment, SyntaxDeclaration
from ria.domain.models.parser_identity import ComponentVersion
from ria.domain.models.syntax_facts import (
    CommentBlock,
    ExtractedSyntax,
    ImportedName,
    ImportStatement,
)
from ria.domain.models.syntax_tree import SyntaxNode, SyntaxTree
from ria.ports.parser import SyntaxExtractorPort

__all__ = ["PythonSyntaxExtractor"]

PYTHON_EXTRACTOR_CAPABILITIES: FrozenSet[ParserCapability] = frozenset(
    {
        ParserCapability.EXTRACT_FUNCTIONS,
        ParserCapability.EXTRACT_METHODS,
        ParserCapability.EXTRACT_CLASSES,
        ParserCapability.EXTRACT_IMPORTS,
        ParserCapability.EXTRACT_ANNOTATIONS,
        ParserCapability.EXTRACT_DECORATORS,
        ParserCapability.EXTRACT_COMMENTS,
        ParserCapability.EXTRACT_DOCUMENTATION,
        ParserCapability.EXTRACT_VISIBILITY,
        ParserCapability.EXTRACT_PARAMETERS,
    }
)


class PythonSyntaxExtractor(SyntaxExtractorPort):
    """Tree-sitter based extractor for Python syntax."""

    def extractor_version(self) -> ComponentVersion:
        return ComponentVersion(name="python-extractor", version="1.0.0")

    def capabilities(self) -> FrozenSet[ParserCapability]:
        return PYTHON_EXTRACTOR_CAPABILITIES

    def extract(self, tree: SyntaxTree, source_bytes: bytes) -> ExtractedSyntax:
        """Extract declarations, imports, comments from Python SyntaxTree."""
        declarations: List[SyntaxDeclaration] = []
        imports: List[ImportStatement] = []
        comments: List[CommentBlock] = []

        self._walk_and_extract(
            node=tree.root,
            source_bytes=source_bytes,
            container_path=(),
            declarations=declarations,
            imports=imports,
            comments=comments,
        )

        return ExtractedSyntax(
            declarations=tuple(declarations),
            imports=tuple(imports),
            exports=(),
            comments=tuple(comments),
        )

    def _walk_and_extract(
        self,
        node: SyntaxNode,
        source_bytes: bytes,
        container_path: Tuple[str, ...],
        declarations: List[SyntaxDeclaration],
        imports: List[ImportStatement],
        comments: List[CommentBlock],
    ) -> None:
        """Recursive walk over SyntaxNodes to extract syntactic facts."""
        i = 0
        children = node.children
        while i < len(children):
            child = children[i]
            kind = child.kind

            if kind == "comment":
                comment_text = child.span.text_of(source_bytes)
                comments.append(
                    CommentBlock(
                        text=comment_text,
                        span=child.span,
                        node_kind=kind,
                        is_block=comment_text.startswith("'''")
                        or comment_text.startswith('"""'),
                    )
                )
                i += 1
                continue

            if kind == "import_statement":
                imports.extend(self._extract_import_statement(child, source_bytes))
                i += 1
                continue

            if kind == "import_from_statement":
                imports.extend(self._extract_import_from_statement(child, source_bytes))
                i += 1
                continue

            if kind in ("function_definition", "class_definition"):
                decl = self._extract_declaration(
                    child,
                    source_bytes,
                    container_path,
                    annotations=(),
                )
                if decl is not None:
                    declarations.append(decl)
                    # Recurse into body with updated container path if class or function
                    new_container = container_path + (decl.name,)
                    body_node = child.child_by_field("body")
                    if body_node is not None:
                        self._walk_and_extract(
                            body_node,
                            source_bytes,
                            new_container,
                            declarations,
                            imports,
                            comments,
                        )
                i += 1
                continue

            if kind == "decorated_definition":
                annotations, def_node = self._extract_decorated_definition(
                    child, source_bytes
                )
                if def_node is not None and def_node.kind in (
                    "function_definition",
                    "class_definition",
                ):
                    decl = self._extract_declaration(
                        def_node,
                        source_bytes,
                        container_path,
                        annotations=tuple(annotations),
                    )
                    if decl is not None:
                        declarations.append(decl)
                        new_container = container_path + (decl.name,)
                        body_node = def_node.child_by_field("body")
                        if body_node is not None:
                            self._walk_and_extract(
                                body_node,
                                source_bytes,
                                new_container,
                                declarations,
                                imports,
                                comments,
                            )
                i += 1
                continue

            # Fall through for general containers/modules
            if child.children:
                self._walk_and_extract(
                    child,
                    source_bytes,
                    container_path,
                    declarations,
                    imports,
                    comments,
                )
            i += 1

    # -- Imports -----------------------------------------------------------

    def _extract_import_statement(
        self, node: SyntaxNode, source_bytes: bytes
    ) -> List[ImportStatement]:
        results = []
        for child in node.children:
            if child.kind == "dotted_name":
                mod_name = child.span.text_of(source_bytes)
                results.append(
                    ImportStatement(
                        module_text=mod_name,
                        span=node.span,
                        node_kind=node.kind,
                        names=(ImportedName(name=mod_name),),
                        is_relative=False,
                    )
                )
            elif child.kind == "aliased_import":
                name_child = child.child_by_field("name")
                alias_child = child.child_by_field("alias")
                if name_child is not None:
                    mod_name = name_child.span.text_of(source_bytes)
                    alias = (
                        alias_child.span.text_of(source_bytes) if alias_child else None
                    )
                    results.append(
                        ImportStatement(
                            module_text=mod_name,
                            span=node.span,
                            node_kind=node.kind,
                            names=(ImportedName(name=mod_name, alias=alias),),
                        )
                    )
        return results

    def _extract_import_from_statement(
        self, node: SyntaxNode, source_bytes: bytes
    ) -> List[ImportStatement]:
        module_name = ""
        is_relative = False

        for child in node.children:
            if child.kind in ("dotted_name", "relative_import"):
                module_name = child.span.text_of(source_bytes)
                if child.kind == "relative_import" or module_name.startswith("."):
                    is_relative = True

        names: List[ImportedName] = []
        for child in node.children:
            if child.kind == "dotted_name" and child.field_name == "name":
                name_str = child.span.text_of(source_bytes)
                names.append(ImportedName(name=name_str))
            elif child.kind == "aliased_import":
                name_child = child.child_by_field("name")
                alias_child = child.child_by_field("alias")
                if name_child is not None:
                    n_str = name_child.span.text_of(source_bytes)
                    a_str = (
                        alias_child.span.text_of(source_bytes) if alias_child else None
                    )
                    names.append(ImportedName(name=n_str, alias=a_str))
            elif child.kind == "wildcard_import":
                names.append(ImportedName(name="*"))

        if not module_name:
            module_name = "."

        return [
            ImportStatement(
                module_text=module_name,
                span=node.span,
                node_kind=node.kind,
                names=tuple(names),
                is_relative=is_relative,
            )
        ]

    # -- Declarations ------------------------------------------------------

    def _extract_decorated_definition(
        self, node: SyntaxNode, source_bytes: bytes
    ) -> Tuple[List[Annotation], Optional[SyntaxNode]]:
        annotations: List[Annotation] = []
        def_node: Optional[SyntaxNode] = None

        for child in node.children:
            if child.kind == "decorator":
                name_str = ""
                args_str: Optional[str] = None
                for sub in child.children:
                    if sub.kind in ("identifier", "dotted_name", "attribute"):
                        name_str = sub.span.text_of(source_bytes)
                    elif sub.kind == "argument_list":
                        args_str = sub.span.text_of(source_bytes)

                if not name_str:
                    name_str = child.span.text_of(source_bytes).lstrip("@").strip()

                annotations.append(
                    Annotation(
                        name=name_str,
                        span=child.span,
                        arguments_text=args_str,
                    )
                )
            elif child.kind in ("function_definition", "class_definition"):
                def_node = child

        return annotations, def_node

    def _extract_declaration(
        self,
        node: SyntaxNode,
        source_bytes: bytes,
        container_path: Tuple[str, ...],
        annotations: Tuple[Annotation, ...],
    ) -> Optional[SyntaxDeclaration]:
        name_node = node.child_by_field("name")
        if name_node is None:
            # Fallback for identifier child if field_name missing
            for child in node.children:
                if child.kind == "identifier":
                    name_node = child
                    break

        if name_node is None:
            return None

        name = name_node.span.text_of(source_bytes)
        kind = (
            DeclarationKind.CLASS
            if node.kind == "class_definition"
            else (
                DeclarationKind.METHOD if container_path else DeclarationKind.FUNCTION
            )
        )

        # Visibility inference (Python convention: leading _ is private/internal)
        visibility = Visibility.PUBLIC
        if name.startswith("__") and not name.endswith("__"):
            visibility = Visibility.PRIVATE
        elif name.startswith("_"):
            visibility = Visibility.INFERRED

        # Docstring extraction
        doc: Optional[DocComment] = None
        body_node = node.child_by_field("body")
        if body_node is None:
            for child in node.children:
                if child.kind == "block":
                    body_node = child
                    break

        if body_node is not None and body_node.children:
            first_stmt = body_node.children[0]
            string_node = None
            if first_stmt.kind == "expression_statement" and first_stmt.children:
                string_node = first_stmt.children[0]
            elif first_stmt.kind == "string":
                string_node = first_stmt

            if string_node is not None and string_node.kind == "string":
                doc_text = string_node.span.text_of(source_bytes).strip("\"'")
                doc = DocComment(
                    text=doc_text,
                    span=string_node.span,
                    is_leading=False,
                )

        # Signature text for functions / methods
        sig_text: Optional[str] = None
        params_node = node.child_by_field("parameters")
        if params_node is not None:
            sig_text = params_node.span.text_of(source_bytes)

        return SyntaxDeclaration(
            kind=kind,
            name=name,
            span=node.span,
            name_span=name_node.span,
            node_kind=node.kind,
            container_path=container_path,
            visibility=visibility,
            annotations=annotations,
            documentation=doc,
            signature_text=sig_text,
        )
