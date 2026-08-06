"""Unit tests for VerificationPipelineService (Phase 7)."""

from __future__ import annotations


from ria.application.verification_pipeline import VerificationPipelineService
from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.workflow_definition import (
    WorkflowAction,
    WorkflowDefinition,
    WorkflowStep,
)
from ria.domain.models.workflow_execution import WorkflowContext, WorkflowExecution
from ria.domain.models.workflow_id import WorkflowId


def test_verification_pipeline_service() -> None:
    svc = VerificationPipelineService()

    wfid = WorkflowId.for_workflow("wf", "1")
    act = WorkflowAction("inspection", "main.py")
    step = WorkflowStep("step1", "Title", act)
    defn = WorkflowDefinition(wfid, "Name", "Desc", (step,))

    ctx = WorkflowContext(RepositoryId("repo1"), CommitSha("a" * 40), "s1")
    exec_rec = WorkflowExecution(wfid, defn, ctx)

    res = svc.verify_execution(exec_rec, "Valid output text")
    assert res.is_verified
    assert res.tool_success
