"""CLI Entry Point & Command Executor."""

from typing import Sequence

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
from ria.interfaces.cli.console import ConsoleFormatter
from ria.interfaces.cli.parser import create_cli_parser


class CLIRunner:
    """CLI Runner dispatching commands to Application Services."""

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

    def run(self, args: Sequence[str]) -> int:
        parser = create_cli_parser()
        parsed = parser.parse_args(args)

        if parsed.command == "init":
            reg_dto = self._sync.register_repository(
                RegisterRepositoryCommand(
                    remote_url=parsed.remote_url, name=parsed.name
                )
            )
            ConsoleFormatter.print_success(
                f"Registered repo {reg_dto.repo_id} ({reg_dto.status})"
            )
            return 0

        if parsed.command in ("index", "update"):
            upd_dto = self._sync.synchronize_repository(
                SynchronizeRepositoryCommand(repo_id=parsed.repo_id)
            )
            ConsoleFormatter.print_success(
                f"Synchronized repo {upd_dto.repo_id} ({upd_dto.current_commit_sha})"
            )
            return 0 if upd_dto.is_success else 1

        if parsed.command == "search":
            s_resp = self._search.search_symbol(parsed.repo_id, parsed.query)
            matches_cnt = (
                len(s_resp.results.payload)
                if s_resp.results and isinstance(s_resp.results.payload, tuple)
                else 0
            )
            ConsoleFormatter.print_success(f"Search found {matches_cnt} matches")
            return 0 if s_resp.is_success else 1

        if parsed.command == "query":
            q_res = self._query.find_definition(
                parsed.repo_id, symbol_moniker=parsed.symbol
            )
            ConsoleFormatter.print_success(f"Query returned ID {q_res.query_id}")
            return 0 if q_res.is_success else 1

        if parsed.command == "context":
            ctx_dto = self._context.build_context(
                BuildContextCommandDTO(
                    repo_id=parsed.repo_id,
                    question=parsed.question,
                    max_tokens=parsed.max_tokens,
                )
            )
            ConsoleFormatter.print_success(
                f"Context package {ctx_dto.package_id} built with {ctx_dto.total_tokens} tokens"
            )
            return 0 if ctx_dto.is_success else 1

        if parsed.command == "ask":
            know_dto = self._knowledge.answer_question(
                AnswerQuestionCommandDTO(
                    repo_id=parsed.repo_id, question=parsed.question
                )
            )
            ConsoleFormatter.print_success(f"Answer: {know_dto.answer_text}")
            return 0 if know_dto.is_success else 1

        if parsed.command == "version":
            ConsoleFormatter.print_info("RIA v2 Platform CLI v2.0.0")
            return 0

        if parsed.command in ("doctor", "config", "status"):
            ConsoleFormatter.print_info(
                f"Command '{parsed.command}' executed successfully."
            )
            return 0

        return 1
