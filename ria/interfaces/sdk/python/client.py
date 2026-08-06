"""Python SDK Client."""

from typing import Optional

from ria.application.context import BuildContextCommandDTO, ContextApplicationService
from ria.application.knowledge import (
    AnswerQuestionCommandDTO,
    KnowledgeApplicationService,
)
from ria.application.query import QueryApplicationService
from ria.application.search import SearchApplicationService
from ria.application.sync import RepositorySyncService, SynchronizeRepositoryCommand
from ria.interfaces.sdk.python.models import SDKResponse


class RIAClient:
    """Python SDK Client exposing platform capabilities."""

    def __init__(
        self,
        sync_service: RepositorySyncService,
        search_service: SearchApplicationService,
        query_service: QueryApplicationService,
        context_service: ContextApplicationService,
        knowledge_service: KnowledgeApplicationService,
    ) -> None:
        self._sync = sync_service
        self._search = search_service
        self._query = query_service
        self._context = context_service
        self._knowledge = knowledge_service

    def search(self, repo_id: str, query_text: str) -> SDKResponse:
        s_resp = self._search.search_symbol(repo_id, query_text)
        matches_cnt = (
            len(s_resp.results.payload)
            if s_resp.results and isinstance(s_resp.results.payload, tuple)
            else 0
        )
        return SDKResponse(
            is_success=s_resp.is_success, data={"total_matches": matches_cnt}
        )

    def query(
        self, repo_id: str, query_type: str, symbol_moniker: Optional[str] = None
    ) -> SDKResponse:
        q_res = self._query.find_definition(repo_id, symbol_moniker=symbol_moniker)
        return SDKResponse(
            is_success=q_res.is_success, data={"query_id": q_res.query_id}
        )

    def context(self, repo_id: str, question: str) -> SDKResponse:
        ctx_dto = self._context.build_context(
            BuildContextCommandDTO(repo_id=repo_id, question=question)
        )
        return SDKResponse(
            is_success=ctx_dto.is_success,
            data={"package_id": ctx_dto.package_id, "content": ctx_dto.content},
        )

    def ask(self, repo_id: str, question: str) -> SDKResponse:
        know_dto = self._knowledge.answer_question(
            AnswerQuestionCommandDTO(repo_id=repo_id, question=question)
        )
        return SDKResponse(
            is_success=know_dto.is_success,
            data={"answer": know_dto.answer_text, "grounded": know_dto.is_grounded},
        )

    def update(self, repo_id: str) -> SDKResponse:
        upd_dto = self._sync.synchronize_repository(
            SynchronizeRepositoryCommand(repo_id=repo_id)
        )
        return SDKResponse(
            is_success=upd_dto.is_success,
            data={"commit_sha": upd_dto.current_commit_sha},
        )

    def status(self, repo_id: str) -> SDKResponse:
        return SDKResponse(
            is_success=True, data={"repo_id": repo_id, "status": "active"}
        )
