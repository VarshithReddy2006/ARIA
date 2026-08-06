"""Unit tests for PromptContextBuilderService (Phase 9)."""

from __future__ import annotations


from ria.application.prompt_context_builder import PromptContextBuilderService
from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.context_evidence import ContextEvidence
from ria.domain.models.context_id import ContextId
from ria.domain.models.context_request import ContextRequest
from ria.domain.models.prompt_context import ContextCitation


def test_prompt_context_builder_service() -> None:
    svc = PromptContextBuilderService()

    repo_id = RepositoryId("repo1")
    sha = CommitSha("a" * 40)
    cid = ContextId.for_context("explain", "main")
    req = ContextRequest(
        context_id=cid, query_text="Explain main", repository_id=repo_id, commit_sha=sha
    )

    ev = ContextEvidence(
        id="main", kind="function", content="def main(): pass", location_path="main.py"
    )
    cit = ContextCitation(repository="repo1", file_path="main.py")

    prompt = svc.build_prompt(req, (ev,), (cit,))

    assert len(prompt.sections) == 3
    assert len(prompt.messages) == 2
    assert len(prompt.citations) == 1
