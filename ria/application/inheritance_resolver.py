"""Inheritance and Override Resolver application service.

Resolves subtyping, inheritance, interface implementation, and method override relations.
Implements :class:`~ria.ports.semantic.InheritanceResolverPort`.
"""

from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

from ria.domain.enums import DeclarationKind, InheritanceKind
from ria.domain.models.inheritance import InheritanceRelation, OverrideRelation
from ria.domain.models.symbol import Symbol
from ria.domain.models.syntax_facts import ExtractedSyntax
from ria.ports.semantic import InheritanceResolverPort

__all__ = ["InheritanceResolverService"]


class InheritanceResolverService(InheritanceResolverPort):
    """Service for resolving inheritance and method override relationships."""

    def resolve_inheritance(
        self,
        extracted: ExtractedSyntax,
        symbols: Sequence[Symbol],
    ) -> Tuple[Tuple[InheritanceRelation, ...], Tuple[OverrideRelation, ...]]:
        """Resolve inheritance clauses and method overrides among class/interface symbols.

        Args:
            extracted: Extracted syntax facts.
            symbols: Known candidate type and method symbols.

        Returns:
            Tuple of:
            - Tuple of InheritanceRelation instances
            - Tuple of OverrideRelation instances
        """
        inheritance_relations: List[InheritanceRelation] = []
        override_relations: List[OverrideRelation] = []

        # Index symbols by qualified_name and name
        symbols_by_qual = {s.qualified_name: s for s in symbols}
        symbols_by_name: Dict[str, List[Symbol]] = {}
        for s in symbols:
            symbols_by_name.setdefault(s.name, []).append(s)

        # Index class/interface symbols and methods
        methods_by_class: Dict[str, List[Symbol]] = {}
        for s in symbols:
            if s.kind is DeclarationKind.METHOD and s.container_path:
                cls_path = ".".join(s.container_path)
                methods_by_class.setdefault(cls_path, []).append(s)

        # 1. Resolve Inheritance Relations from class declarations
        for decl in extracted.declarations:
            if decl.kind.is_type:
                child_sym = symbols_by_qual.get(decl.name) or (
                    symbols_by_name.get(decl.name, [None])[0]
                    if decl.name in symbols_by_name
                    else None
                )
                if child_sym is None:
                    continue

                # Inspect modifiers or signature/annotations for base class names
                # (Standard conventions: annotations / modifiers / container_path)
                for modifier in decl.modifiers:
                    parent_name = modifier
                    parent_sym = symbols_by_qual.get(parent_name) or (
                        symbols_by_name.get(parent_name, [None])[0]
                        if parent_name in symbols_by_name
                        else None
                    )
                    parent_id = parent_sym.symbol_id if parent_sym else None

                    rel = InheritanceRelation(
                        child_symbol_id=child_sym.symbol_id,
                        parent_name=parent_name,
                        kind=InheritanceKind.EXTENDS
                        if decl.kind is DeclarationKind.CLASS
                        else InheritanceKind.IMPLEMENTS,
                        span=decl.span,
                        parent_symbol_id=parent_id,
                    )
                    inheritance_relations.append(rel)

                    # 2. Resolve Method Overrides if parent class symbol is known
                    if parent_sym is not None:
                        child_methods = methods_by_class.get(child_sym.name, [])
                        parent_methods = methods_by_class.get(parent_sym.name, [])
                        parent_method_map = {m.name: m for m in parent_methods}

                        for cm in child_methods:
                            if cm.name in parent_method_map:
                                pm = parent_method_map[cm.name]
                                ovr = OverrideRelation(
                                    overriding_symbol_id=cm.symbol_id,
                                    overridden_symbol_id=pm.symbol_id,
                                    overridden_name=pm.name,
                                    span=cm.location,
                                )
                                override_relations.append(ovr)

        return tuple(inheritance_relations), tuple(override_relations)
