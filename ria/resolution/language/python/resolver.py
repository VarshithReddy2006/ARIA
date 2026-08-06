"""Python Language Resolver implementing LanguageResolverPort."""

from typing import Any

from ria.domain.index.units import ParseUnit
from ria.domain.index.value_objects import Language
from ria.domain.resolution.entities import ResolvedFactSet
from ria.ports.resolution.language_resolver import LanguageResolverPort
from ria.resolution.context import ResolutionContext
from ria.resolution.language.python.extractor import PythonExtractor


class PythonLanguageResolver(LanguageResolverPort):
    """Language resolver implementation for Python code."""

    def __init__(self) -> None:
        self._extractor = PythonExtractor()

    def can_resolve(self, language: Language) -> bool:
        return language == Language.PYTHON

    def resolve_unit(self, parse_unit: ParseUnit, context: Any) -> ResolvedFactSet:
        if not parse_unit.ast_unit or not parse_unit.ast_unit.root_node:
            return ResolvedFactSet()

        if isinstance(context, ResolutionContext):
            ctx = context
        else:
            ctx = ResolutionContext(
                repo_id=context.repo_id,
                commit=context.commit,
                current_path=parse_unit.file_unit.path,
                language=Language.PYTHON,
            )

        return self._extractor.extract_unit(parse_unit.ast_unit.root_node, ctx)
