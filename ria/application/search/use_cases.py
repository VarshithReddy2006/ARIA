"""Single-responsibility use cases for search subsystem."""

from ria.application.search.dto import AutocompleteDTO, SearchFileDTO, SearchModuleDTO, SearchSymbolDTO
from ria.application.search.service import SearchApplicationService
from ria.domain.search.entities import SearchResponse


class SearchSymbolUseCase:
    """Use Case executing symbol search queries."""

    def __init__(self, service: SearchApplicationService) -> None:
        self._service = service

    def execute(self, dto: SearchSymbolDTO) -> SearchResponse:
        return self._service.search_symbol(dto.repo_id, dto.query_text, dto.query_type, dto.max_results)


class SearchFileUseCase:
    """Use Case executing file path search queries."""

    def __init__(self, service: SearchApplicationService) -> None:
        self._service = service

    def execute(self, dto: SearchFileDTO) -> SearchResponse:
        return self._service.search_file(dto.repo_id, dto.query_text, dto.max_results)


class SearchModuleUseCase:
    """Use Case executing module search queries."""

    def __init__(self, service: SearchApplicationService) -> None:
        self._service = service

    def execute(self, dto: SearchModuleDTO) -> SearchResponse:
        return self._service.search_module(dto.repo_id, dto.query_text, dto.max_results)


class AutocompleteUseCase:
    """Use Case executing autocomplete query suggestions."""

    def __init__(self, service: SearchApplicationService) -> None:
        self._service = service

    def execute(self, dto: AutocompleteDTO) -> SearchResponse:
        return self._service.autocomplete(dto.repo_id, dto.prefix, dto.max_suggestions)
