"""VS Code Extension Command Handlers (Python Bridge)."""

from typing import Any, Dict

from ria.application.context import BuildContextCommandDTO, ContextApplicationService
from ria.application.knowledge import AnswerQuestionCommandDTO, KnowledgeApplicationService
from ria.application.query import QueryApplicationService
from ria.application.search import SearchApplicationService


class VSCodeCommandDispatcher:
    """Dispatcher handling VS Code extension command executions."""

    def __init__(
        self,
        search_service: SearchApplicationService,
        query_service: QueryApplicationService,
        context_service: ContextApplicationService,
        knowledge_service: KnowledgeApplicationService,
    ) -> None:
        self._search = search_service
        self._query = query_service
        self._context = context_service
        self._knowledge = knowledge_service

    def execute_command(self, command_id: str, args: Dict[str, Any]) -> Dict[str, Any]:
        repo_id = args.get("repo_id", "")

        if command_id == "ria.askRepository":
            know_dto = self._knowledge.answer_question(AnswerQuestionCommandDTO(repo_id=repo_id, question=args.get("question", "")))
            return {"is_success": know_dto.is_success, "answer": know_dto.answer_text}

        if command_id == "ria.explainSymbol":
            s_resp = self._search.search_symbol(repo_id, args.get("symbol_name", ""))
            matches_cnt = len(s_resp.results.payload) if s_resp.results and isinstance(s_resp.results.payload, tuple) else 0
            return {"is_success": s_resp.is_success, "matches": matches_cnt}

        if command_id in ("ria.findDefinition", "ria.findReferences", "ria.showCallGraph"):
            q_res = self._query.find_definition(repo_id, symbol_moniker=args.get("symbol_moniker"))
            return {"is_success": q_res.is_success, "query_id": q_res.query_id}

        if command_id == "ria.contextExplorer":
            ctx_dto = self._context.build_context(BuildContextCommandDTO(repo_id=repo_id, question=args.get("question", "")))
            return {"is_success": ctx_dto.is_success, "package_id": ctx_dto.package_id, "tokens": ctx_dto.total_tokens}

        return {"is_success": True, "command": command_id, "status": "executed"}
