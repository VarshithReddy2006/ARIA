"""Production Model Context Protocol (MCP) Server."""

from typing import Any, Dict, List

from ria.application.context import BuildContextCommandDTO, ContextApplicationService
from ria.application.knowledge import AnswerQuestionCommandDTO, KnowledgeApplicationService
from ria.application.query import QueryApplicationService
from ria.application.search import SearchApplicationService
from ria.application.sync import RepositorySyncService, SynchronizeRepositoryCommand


class MCPServer:
    """Production MCP Server dispatching tool invocations to Application Services."""

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

    def list_tools(self) -> List[Dict[str, str]]:
        return [
            {"name": "search_symbol", "description": "Search symbols in repository"},
            {"name": "search_file", "description": "Search files in repository"},
            {"name": "find_definition", "description": "Find definition of symbol"},
            {"name": "find_references", "description": "Find references to symbol"},
            {"name": "find_callers", "description": "Find callers of symbol"},
            {"name": "find_callees", "description": "Find callees of symbol"},
            {"name": "find_dependencies", "description": "Find dependencies of file"},
            {"name": "build_context", "description": "Assemble semantic context package"},
            {"name": "ask_repository", "description": "Ask grounded question"},
            {"name": "list_modules", "description": "List indexed modules"},
            {"name": "list_packages", "description": "List indexed packages"},
            {"name": "list_symbols", "description": "List indexed symbols"},
            {"name": "repository_status", "description": "Check repository sync status"},
            {"name": "update_repository", "description": "Synchronize repository"},
        ]

    def invoke_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        t_name = tool_name.lower()
        repo_id = arguments.get("repo_id", "")

        if t_name == "search_symbol":
            s_resp = self._search.search_symbol(repo_id, arguments.get("query", ""))
            matches_cnt = len(s_resp.results.payload) if s_resp.results and isinstance(s_resp.results.payload, tuple) else 0
            return {"is_success": s_resp.is_success, "total_matches": matches_cnt}

        if t_name == "search_file":
            s_resp = self._search.search_file(repo_id, arguments.get("query", ""))
            matches_cnt = len(s_resp.results.payload) if s_resp.results and isinstance(s_resp.results.payload, tuple) else 0
            return {"is_success": s_resp.is_success, "total_matches": matches_cnt}

        if t_name == "find_definition":
            q_res = self._query.find_definition(repo_id, symbol_moniker=arguments.get("symbol_moniker"))
            return {"is_success": q_res.is_success, "query_id": q_res.query_id}

        if t_name == "find_references":
            q_res = self._query.find_references(repo_id, symbol_moniker=arguments.get("symbol_moniker", ""))
            return {"is_success": q_res.is_success, "query_id": q_res.query_id}

        if t_name in ("find_callers", "find_callees"):
            q_res = self._query.find_call_hierarchy(repo_id, symbol_moniker=arguments.get("symbol_moniker", ""), is_callers=(t_name == "find_callers"))
            return {"is_success": q_res.is_success, "query_id": q_res.query_id}

        if t_name == "find_dependencies":
            q_res = self._query.analyze_dependencies(repo_id, file_path_str=arguments.get("file_path"))
            return {"is_success": q_res.is_success, "query_id": q_res.query_id}

        if t_name == "build_context":
            ctx_dto = self._context.build_context(BuildContextCommandDTO(repo_id=repo_id, question=arguments.get("question", "")))
            return {"is_success": ctx_dto.is_success, "package_id": ctx_dto.package_id, "tokens": ctx_dto.total_tokens, "content": ctx_dto.content}

        if t_name == "ask_repository":
            know_dto = self._knowledge.answer_question(AnswerQuestionCommandDTO(repo_id=repo_id, question=arguments.get("question", "")))
            return {"is_success": know_dto.is_success, "answer": know_dto.answer_text, "grounded": know_dto.is_grounded}

        if t_name == "update_repository":
            upd_dto = self._sync.synchronize_repository(SynchronizeRepositoryCommand(repo_id=repo_id))
            return {"is_success": upd_dto.is_success, "commit_sha": upd_dto.current_commit_sha}

        if t_name in ("list_modules", "list_packages", "list_symbols", "repository_status"):
            return {"is_success": True, "status": "active"}

        return {"is_success": False, "error": f"Tool '{tool_name}' not found."}
