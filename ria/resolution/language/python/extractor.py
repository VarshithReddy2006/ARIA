"""Python AST Symbol Extractor."""

from ria.domain.index.value_objects import ASTNode, Location
from ria.domain.resolution.entities import ResolvedFactSet, SemanticSymbol
from ria.domain.resolution.value_objects import (
    CallRelation,
    ImportRelation,
    InheritanceRelation,
    RelationKind,
    SemanticDefinition,
    SemanticReference,
    SemanticRelation,
    SymbolKind,
    SymbolModifiers,
    SymbolMoniker,
    Visibility,
)
from ria.resolution.context import ResolutionContext
from ria.resolution.extractors.ast_symbol_extractor import ASTSymbolExtractor
from ria.resolution.extractors.relationship_resolver import RelationshipResolver


class PythonExtractor:
    """Extractor traversing Python AST structures to extract definitions, calls, imports, and inheritance."""

    def __init__(self) -> None:
        self._symbol_extractor = ASTSymbolExtractor()
        self._rel_resolver = RelationshipResolver()

    def extract_unit(self, root_ast: ASTNode, context: ResolutionContext) -> ResolvedFactSet:
        symbols: list[SemanticSymbol] = []
        definitions: list[SemanticDefinition] = []
        references: list[SemanticReference] = []
        calls: list[CallRelation] = []
        imports: list[ImportRelation] = []
        inheritance: list[InheritanceRelation] = []
        relations: list[SemanticRelation] = []

        def _walk(node: ASTNode, curr_ctx: ResolutionContext) -> None:
            nonlocal symbols, definitions, references, calls, imports, inheritance, relations

            ntype = node.type

            if ntype == "function_definition":
                # Find function name
                fn_name = "func"
                for child in node.children:
                    if child.type == "identifier":
                        fn_name = child.attributes[0][1] if child.attributes else "func"
                        break

                is_method = len(curr_ctx.scope_chain) > 0
                kind = SymbolKind.METHOD if is_method else SymbolKind.FUNCTION
                vis = Visibility.PRIVATE if fn_name.startswith("_") and not fn_name.startswith("__") else Visibility.PUBLIC

                sym, defn = self._symbol_extractor.extract_symbol(node, fn_name, kind, curr_ctx, visibility=vis)
                symbols.append(sym)
                definitions.append(defn)

                next_ctx = curr_ctx.with_scope(fn_name)
                for child in node.children:
                    _walk(child, next_ctx)
                return

            elif ntype == "class_definition":
                class_name = "Class"
                for child in node.children:
                    if child.type == "identifier":
                        class_name = child.attributes[0][1] if child.attributes else "Class"
                        break

                sym, defn = self._symbol_extractor.extract_symbol(node, class_name, SymbolKind.CLASS, curr_ctx)
                symbols.append(sym)
                definitions.append(defn)

                next_ctx = curr_ctx.with_scope(class_name)
                for child in node.children:
                    _walk(child, next_ctx)
                return

            elif ntype in ("import_statement", "import_from_statement"):
                imp_name = "module"
                for child in node.children:
                    if child.type in ("dotted_name", "identifier", "aliased_import"):
                        imp_name = child.attributes[0][1] if child.attributes else "module"
                        break
                imp_moniker = curr_ctx.build_moniker(imp_name)
                imp_rel = self._rel_resolver.build_import_relation(curr_ctx, imp_moniker)
                imports.append(imp_rel)

            elif ntype == "call":
                callee_name = "callee"
                for child in node.children:
                    if child.type in ("identifier", "attribute"):
                        callee_name = child.attributes[0][1] if child.attributes else "callee"
                        break

                caller_moniker = curr_ctx.build_moniker(curr_ctx.scope_chain[-1] if curr_ctx.scope_chain else "global")
                callee_moniker = curr_ctx.build_moniker(callee_name)
                loc = Location(node.start_line, node.start_col, node.end_line, node.end_col)
                call_rel = self._rel_resolver.build_call_relation(caller_moniker, callee_moniker, loc)
                calls.append(call_rel)

            for child in node.children:
                _walk(child, curr_ctx)

        _walk(root_ast, context)

        return ResolvedFactSet(
            symbols=tuple(symbols),
            definitions=tuple(definitions),
            references=tuple(references),
            calls=tuple(calls),
            imports=tuple(imports),
            inheritance=tuple(inheritance),
            relations=tuple(relations),
        )
