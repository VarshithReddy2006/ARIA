"""Base AST Symbol Extractor walking domain ASTNode trees."""

from ria.domain.index.value_objects import ASTNode, Location
from ria.domain.resolution.entities import SemanticSymbol
from ria.domain.resolution.value_objects import (
    QualifiedName,
    SemanticDefinition,
    SymbolKind,
    SymbolModifiers,
    Visibility,
)
from ria.resolution.context import ResolutionContext


class ASTSymbolExtractor:
    """Base extractor traversing domain ASTNode objects to construct SemanticSymbols and SemanticDefinitions."""

    def extract_symbol(
        self,
        node: ASTNode,
        name: str,
        kind: SymbolKind,
        context: ResolutionContext,
        visibility: Visibility = Visibility.PUBLIC,
        modifiers: SymbolModifiers = SymbolModifiers(),
    ) -> tuple[SemanticSymbol, SemanticDefinition]:
        """Construct immutable SemanticSymbol and SemanticDefinition for an AST node."""
        moniker = context.build_moniker(name)
        scope_prefix = ".".join(context.scope_chain)
        dotted_name = f"{scope_prefix}.{name}" if scope_prefix else name
        qname = QualifiedName(dotted_path=dotted_name)
        loc = Location(
            start_line=node.start_line,
            start_col=node.start_col,
            end_line=node.end_line,
            end_col=node.end_col,
        )

        symbol = SemanticSymbol(
            moniker=moniker,
            name=name,
            qualified_name=qname,
            kind=kind,
            visibility=visibility,
            path=context.current_path,
            location=loc,
            modifiers=modifiers,
        )

        definition = SemanticDefinition(
            moniker=moniker,
            qualified_name=qname,
            path=context.current_path,
            location=loc,
        )

        return symbol, definition
