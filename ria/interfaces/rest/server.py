"""REST API Server & Endpoint Dispatcher."""

import time
from typing import Any

from ria.application.context import BuildContextCommandDTO, ContextApplicationService
from ria.application.knowledge import (
    AnswerQuestionCommandDTO,
    KnowledgeApplicationService,
)
from ria.application.query import QueryApplicationService
from ria.application.search import SearchApplicationService
from ria.application.sync import (
    RegisterRepositoryCommand,
    RepositorySyncService,
    SynchronizeRepositoryCommand,
)
from ria.interfaces.rest.exceptions import RESTAPIException
from ria.interfaces.rest.schemas import (
    APIResponse,
    AskQuestionRequest,
    ContextRequestSchema,
    QueryRequest,
    RegisterRepositoryRequest,
    SearchRequest,
    UpdateRepositoryRequest,
)


class RESTAPIServer:
    """REST API Server dispatching endpoints strictly to Application Services."""

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

    def handle_request(self, method: str, path: str, body: Any = None) -> APIResponse:
        try:
            m = method.upper()
            if m == "GET" and path == "/health":
                return APIResponse(
                    is_success=True,
                    data={"status": "healthy", "timestamp": time.time()},
                )
            if m == "GET" and path == "/version":
                return APIResponse(
                    is_success=True,
                    data={"version": "2.0.0", "subsystem": "RIA v2 Platform"},
                )
            if m == "GET" and path == "/metrics":
                return APIResponse(
                    is_success=True, data={"total_requests": 1, "active_sessions": 1}
                )

            if m == "POST" and path == "/repositories":
                reg_req = RegisterRepositoryRequest(**(body or {}))
                reg_dto = self._sync.register_repository(
                    RegisterRepositoryCommand(
                        remote_url=reg_req.remote_url, name=reg_req.name
                    )
                )
                return APIResponse(
                    is_success=True,
                    data={"repo_id": reg_dto.repo_id, "state": reg_dto.status},
                )

            if m == "POST" and path == "/update":
                upd_req = UpdateRepositoryRequest(**(body or {}))
                upd_dto = self._sync.synchronize_repository(
                    SynchronizeRepositoryCommand(repo_id=upd_req.repo_id)
                )
                return APIResponse(
                    is_success=upd_dto.is_success,
                    data={
                        "repo_id": upd_dto.repo_id,
                        "commit_sha": upd_dto.current_commit_sha,
                    },
                )

            if m == "POST" and path == "/search":
                srch_req = SearchRequest(**(body or {}))
                s_resp = self._search.search_symbol(
                    srch_req.repo_id, srch_req.query_text
                )
                matches_cnt = (
                    len(s_resp.results.payload)
                    if s_resp.results and isinstance(s_resp.results.payload, tuple)
                    else 0
                )
                return APIResponse(
                    is_success=s_resp.is_success, data={"total_matches": matches_cnt}
                )

            if m == "POST" and path == "/query":
                q_req = QueryRequest(**(body or {}))
                q_res = self._query.find_definition(
                    q_req.repo_id, symbol_moniker=q_req.symbol_moniker
                )
                return APIResponse(
                    is_success=q_res.is_success, data={"query_id": q_res.query_id}
                )

            if m == "POST" and path == "/context":
                ctx_req = ContextRequestSchema(**(body or {}))
                ctx_dto = self._context.build_context(
                    BuildContextCommandDTO(
                        repo_id=ctx_req.repo_id,
                        question=ctx_req.question,
                        max_tokens=ctx_req.max_tokens,
                        format=ctx_req.format,
                    )
                )
                return APIResponse(
                    is_success=ctx_dto.is_success,
                    data={
                        "package_id": ctx_dto.package_id,
                        "tokens": ctx_dto.total_tokens,
                        "content": ctx_dto.content,
                    },
                )

            if m == "POST" and path == "/ask":
                ask_req = AskQuestionRequest(**(body or {}))
                know_dto = self._knowledge.answer_question(
                    AnswerQuestionCommandDTO(
                        repo_id=ask_req.repo_id,
                        question=ask_req.question,
                        conversation_id=ask_req.conversation_id,
                        provider_name=ask_req.provider_name,
                    )
                )
                return APIResponse(
                    is_success=know_dto.is_success,
                    data={
                        "answer": know_dto.answer_text,
                        "grounded": know_dto.is_grounded,
                        "score": know_dto.grounding_score,
                    },
                )

            raise RESTAPIException(
                f"Endpoint '{method} {path}' not found.", status_code=404
            )

        except RESTAPIException as err:
            return APIResponse(is_success=False, error_message=err.message)
        except Exception as err:
            return APIResponse(is_success=False, error_message=str(err))
