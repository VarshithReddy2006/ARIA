"""Relationship Resolver extracting Calls, Imports, and Inheritance."""

from ria.domain.index.value_objects import Location
from ria.domain.resolution.value_objects import (
    CallRelation,
    ImportRelation,
    InheritanceRelation,
    RelationKind,
    SemanticRelation,
    SymbolMoniker,
)
from ria.resolution.context import ResolutionContext


class RelationshipResolver:
    """Resolver constructing CallRelation, ImportRelation, InheritanceRelation, and SemanticRelation value objects."""

    def build_call_relation(
        self,
        caller_moniker: SymbolMoniker,
        callee_moniker: SymbolMoniker,
        location: Location,
    ) -> CallRelation:
        return CallRelation(
            caller_moniker=caller_moniker,
            callee_moniker=callee_moniker,
            location=location,
        )

    def build_import_relation(
        self,
        context: ResolutionContext,
        imported_moniker: SymbolMoniker,
        alias: str | None = None,
        is_relative: bool = False,
    ) -> ImportRelation:
        return ImportRelation(
            importer_path=context.current_path,
            imported_symbol_moniker=imported_moniker,
            alias=alias,
            is_relative=is_relative,
        )

    def build_inheritance_relation(
        self,
        subclass_moniker: SymbolMoniker,
        superclass_moniker: SymbolMoniker,
        is_interface: bool = False,
    ) -> InheritanceRelation:
        return InheritanceRelation(
            subclass_moniker=subclass_moniker,
            superclass_moniker=superclass_moniker,
            is_interface=is_interface,
        )

    def build_generic_relation(
        self,
        source: SymbolMoniker,
        target: SymbolMoniker,
        kind: RelationKind,
        location: Location,
    ) -> SemanticRelation:
        return SemanticRelation(
            source=source,
            target=target,
            kind=kind,
            location=location,
        )
