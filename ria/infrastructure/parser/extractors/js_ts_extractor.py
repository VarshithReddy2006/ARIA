"""JavaScript and TypeScript syntax extractor.

Extracts functions, methods, classes, interfaces, imports, exports, and comments from JS/TS trees.
"""

from __future__ import annotations

from typing import FrozenSet, List, Optional, Tuple

from ria.domain.enums import DeclarationKind, ParserCapability, Visibility
from ria.domain.models.declaration import SyntaxDeclaration
from ria.domain.models.parser_identity import ComponentVersion
from ria.domain.models.syntax_facts import (
    CommentBlock,
    ExportStatement,
    ExtractedSyntax,
    ImportedName,
    ImportStatement,
)
from ria.domain.models.syntax_tree import SyntaxNode, SyntaxTree
from ria.ports.parser import SyntaxExtractorPort

__all__ = ["JsTsSyntaxExtractor"]

JS_TS_EXTRACTOR_CAPABILITIES: FrozenSet[ParserCapability] = frozenset(
    {
        ParserCapability.EXTRACT_FUNCTIONS,
        ParserCapability.EXTRACT_METHODS,
        ParserCapability.EXTRACT_CLASSES,
        ParserCapability.EXTRACT_INTERFACES,
        ParserCapability.EXTRACT_IMPORTS,
        ParserCapability.EXTRACT_EXPORTS,
        ParserCapability.EXTRACT_COMMENTS,
        ParserCapability.EXTRACT_PARAMETERS,
    }
)


class JsTsSyntaxExtractor(SyntaxExtractorPort):
    """Tree-sitter based extractor for JavaScript and TypeScript syntax."""

    def extractor_version(self) -> ComponentVersion:
        return ComponentVersion(name="jsts-extractor", version="1.0.0")

    def capabilities(self) -> FrozenSet[ParserCapability]:
        return JS_TS_EXTRACTOR_CAPABILITIES

    def extract(self, tree: SyntaxTree, source_bytes: bytes) -> ExtractedSyntax:
        """Extract syntactic facts from JS/TS SyntaxTree."""
        declarations: List[SyntaxDeclaration] = []
        imports: List[ImportStatement] = []
        exports: List[ExportStatement] = []
        comments: List[CommentBlock] = []

        self._walk_and_extract(
            node=tree.root,
            source_bytes=source_bytes,
            container_path=(),
            declarations=declarations,
            imports=imports,
            exports=exports,
            comments=comments,
        )

        return ExtractedSyntax(
            declarations=tuple(declarations),
            imports=tuple(imports),
            exports=tuple(exports),
            comments=tuple(comments),
        )

    def _walk_and_extract(
        self,
        node: SyntaxNode,
        source_bytes: bytes,
        container_path: Tuple[str, ...],
        declarations: List[SyntaxDeclaration],
        imports: List[ImportStatement],
        exports: List[ExportStatement],
        comments: List[CommentBlock],
    ) -> None:
        """Recursive walk over SyntaxNodes."""
        for child in node.children:
            kind = child.kind

            if kind in ("comment", "line_comment", "block_comment"):
                c_text = child.span.text_of(source_bytes)
                comments.append(
                    CommentBlock(
                        text=c_text,
                        span=child.span,
                        node_kind=kind,
                        is_block=kind == "block_comment" or c_text.startswith("/*"),
                    )
                )
                continue

            if kind == "import_statement":
                imp = self._extract_import_statement(child, source_bytes)
                if imp is not None:
                    imports.append(imp)
                continue

            if kind == "export_statement":
                exp, decl = self._extract_export_statement(
                    child, source_bytes, container_path
                )
                if exp is not None:
                    exports.append(exp)
                if decl is not None:
                    declarations.append(decl)
                continue

            if kind in (
                "function_declaration",
                "class_declaration",
                "interface_declaration",
            ):
                decl = self._extract_declaration(child, source_bytes, container_path)
                if decl is not None:
                    declarations.append(decl)
                    new_container = container_path + (decl.name,)
                    body = child.child_by_field("body")
                    if body is not None:
                        self._walk_and_extract(
                            body,
                            source_bytes,
                            new_container,
                            declarations,
                            imports,
                            exports,
                            comments,
                        )
                continue

            if kind == "method_definition":
                decl = self._extract_declaration(child, source_bytes, container_path)
                if decl is not None:
                    declarations.append(decl)
                continue

            if child.children:
                self._walk_and_extract(
                    child,
                    source_bytes,
                    container_path,
                    declarations,
                    imports,
                    exports,
                    comments,
                )

    def _extract_import_statement(
        self, node: SyntaxNode, source_bytes: bytes
    ) -> Optional[ImportStatement]:
        module_text = ""
        is_relative = False
        names: List[ImportedName] = []

        for child in node.children:
            if child.kind == "string":
                module_text = child.span.text_of(source_bytes).strip("'\"` ")
                if module_text.startswith(".") or module_text.startswith("/"):
                    is_relative = True

            elif child.kind == "import_clause":
                for clause_child in child.children:
                    if clause_child.kind == "identifier":
                        names.append(
                            ImportedName(name=clause_child.span.text_of(source_bytes))
                        )
                    elif clause_child.kind == "named_imports":
                        for spec in clause_child.children:
                            if spec.kind == "import_specifier":
                                n_node = spec.child_by_field("name") or (
                                    spec.children[0] if spec.children else None
                                )
                                a_node = spec.child_by_field("alias")
                                if n_node is not None:
                                    n_str = n_node.span.text_of(source_bytes)
                                    a_str = (
                                        a_node.span.text_of(source_bytes)
                                        if a_node
                                        else None
                                    )
                                    names.append(ImportedName(name=n_str, alias=a_str))

        if not module_text:
            return None

        return ImportStatement(
            module_text=module_text,
            span=node.span,
            node_kind=node.kind,
            names=tuple(names),
            is_relative=is_relative,
        )

    def _extract_export_statement(
        self,
        node: SyntaxNode,
        source_bytes: bytes,
        container_path: Tuple[str, ...],
    ) -> Tuple[Optional[ExportStatement], Optional[SyntaxDeclaration]]:
        module_text: Optional[str] = None
        names: List[ImportedName] = []
        is_default = False
        is_wildcard = False
        decl: Optional[SyntaxDeclaration] = None

        for child in node.children:
            if child.kind == "string":
                module_text = child.span.text_of(source_bytes).strip("'\"` ")

            if child.kind == "default":
                is_default = True

            if child.kind == "*":
                is_wildcard = True

            if child.kind in (
                "function_declaration",
                "class_declaration",
                "interface_declaration",
            ):
                decl = self._extract_declaration(
                    child, source_bytes, container_path, is_exported=True
                )

        exp = ExportStatement(
            span=node.span,
            node_kind=node.kind,
            names=tuple(names),
            module_text=module_text,
            is_default=is_default,
            is_wildcard=is_wildcard,
        )

        return exp, decl

    def _extract_declaration(
        self,
        node: SyntaxNode,
        source_bytes: bytes,
        container_path: Tuple[str, ...],
        is_exported: bool = False,
    ) -> Optional[SyntaxDeclaration]:
        name_node = node.child_by_field("name")
        if name_node is None:
            for child in node.children:
                if child.kind in (
                    "identifier",
                    "property_identifier",
                    "type_identifier",
                ):
                    name_node = child
                    break

        if name_node is None:
            return None

        name = name_node.span.text_of(source_bytes)
        kind_map = {
            "function_declaration": DeclarationKind.FUNCTION,
            "class_declaration": DeclarationKind.CLASS,
            "interface_declaration": DeclarationKind.INTERFACE,
            "method_definition": DeclarationKind.METHOD,
        }
        decl_kind = kind_map.get(node.kind, DeclarationKind.FUNCTION)

        return SyntaxDeclaration(
            kind=decl_kind,
            name=name,
            span=node.span,
            name_span=name_node.span,
            node_kind=node.kind,
            container_path=container_path,
            visibility=Visibility.PUBLIC,
            is_exported=is_exported,
        )
