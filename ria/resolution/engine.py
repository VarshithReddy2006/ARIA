"""Semantic Resolution Engine implementing ResolutionEnginePort."""

from ria.domain.index.units import IndexBatch
from ria.domain.resolution import (
    CallRelation,
    ImportRelation,
    InheritanceRelation,
    ResolvedFactSet,
    SemanticDefinition,
    SemanticReference,
    SemanticRelation,
    SemanticSymbol,
)
from ria.ports.resolution.registry import LanguageResolverRegistryPort
from ria.ports.resolution.resolver import ResolutionEnginePort
from ria.resolution.context import ResolutionContext


class ResolutionEngine(ResolutionEnginePort):
    """Pure Semantic Resolution Engine transforming an immutable IndexBatch into an immutable ResolvedFactSet."""

    def __init__(self, resolver_registry: LanguageResolverRegistryPort) -> None:
        self._registry = resolver_registry

    def resolve_batch(self, batch: IndexBatch) -> ResolvedFactSet:
        """Resolve all symbols, definitions, references, calls, imports, and inheritance across an IndexBatch."""
        all_symbols: list[SemanticSymbol] = []
        all_definitions: list[SemanticDefinition] = []
        all_references: list[SemanticReference] = []
        all_calls: list[CallRelation] = []
        all_imports: list[ImportRelation] = []
        all_inheritance: list[InheritanceRelation] = []
        all_relations: list[SemanticRelation] = []

        for parse_unit in batch.parse_units:
            resolver = self._registry.get_resolver(parse_unit.file_unit.language)
            if resolver is None:
                continue

            ctx = ResolutionContext(
                repo_id=batch.repo_id,
                commit=batch.commit,
                current_path=parse_unit.file_unit.path,
                language=parse_unit.file_unit.language,
            )

            fact_set = resolver.resolve_unit(parse_unit, ctx)

            all_symbols.extend(fact_set.symbols)
            all_definitions.extend(fact_set.definitions)
            all_references.extend(fact_set.references)
            all_calls.extend(fact_set.calls)
            all_imports.extend(fact_set.imports)
            all_inheritance.extend(fact_set.inheritance)
            all_relations.extend(fact_set.relations)

        return ResolvedFactSet(
            symbols=tuple(all_symbols),
            definitions=tuple(all_definitions),
            references=tuple(all_references),
            calls=tuple(all_calls),
            imports=tuple(all_imports),
            inheritance=tuple(all_inheritance),
            relations=tuple(all_relations),
        )
