"""Single-responsibility use cases for semantic queries."""

from ria.application.query.dto import (
    CallHierarchyQueryDTO,
    DependencyQueryDTO,
    FindDefinitionQueryDTO,
    FindReferencesQueryDTO,
    SearchSymbolQueryDTO,
)
from ria.application.query.service import QueryApplicationService
from ria.domain.query.entities import QueryResult


class SearchSymbolUseCase:
    """Use Case executing symbol or module search queries."""

    def __init__(self, service: QueryApplicationService) -> None:
        self._service = service

    def execute(self, dto: SearchSymbolQueryDTO) -> QueryResult:
        return self._service.search_symbols(
            dto.repo_id, dto.symbol_name, dto.max_results
        )


class FindDefinitionUseCase:
    """Use Case executing definition lookup queries."""

    def __init__(self, service: QueryApplicationService) -> None:
        self._service = service

    def execute(self, dto: FindDefinitionQueryDTO) -> QueryResult:
        return self._service.find_definition(
            dto.repo_id, dto.symbol_moniker, dto.symbol_name
        )


class FindReferencesUseCase:
    """Use Case executing reference lookup queries."""

    def __init__(self, service: QueryApplicationService) -> None:
        self._service = service

    def execute(self, dto: FindReferencesQueryDTO) -> QueryResult:
        return self._service.find_references(dto.repo_id, dto.symbol_moniker)


class FindCallHierarchyUseCase:
    """Use Case executing caller or callee hierarchy queries."""

    def __init__(self, service: QueryApplicationService) -> None:
        self._service = service

    def execute(self, dto: CallHierarchyQueryDTO) -> QueryResult:
        return self._service.find_call_hierarchy(
            dto.repo_id, dto.symbol_moniker, dto.is_callers
        )


class DependencyAnalysisUseCase:
    """Use Case executing dependency analysis queries."""

    def __init__(self, service: QueryApplicationService) -> None:
        self._service = service

    def execute(self, dto: DependencyQueryDTO) -> QueryResult:
        return self._service.analyze_dependencies(dto.repo_id, dto.file_path)
