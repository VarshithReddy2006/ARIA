"""Unit tests for Iteration 10 Agent Runtime domain models, goal interpreter, planner, task graph, execution engine, reflection, verification, checkpoint manager, and runtime."""

import pytest
from ria.agent import (
    AgentEvent,
    AgentRuntime,
    CheckpointManager,
    EventPublisher,
    ExecutionContextManager,
    ExecutionEngine,
    GoalInterpreter,
    Planner,
    ReflectionEngine,
    TaskGraphEngine,
    TaskScheduler,
    ToolRegistry,
    ToolSelector,
    VerificationEngine,
)
from ria.domain.agent import (
    Goal,
    GoalType,
    InvalidGoalError,
    TaskId,
    TaskStatus,
)


def test_agent_domain_value_objects() -> None:
    goal = Goal(
        goal_id="g1",
        description="Explain auth",
        goal_type=GoalType.REPOSITORY_EXPLANATION,
        repo_id="r1",
    )
    assert goal.goal_id == "g1"

    with pytest.raises(InvalidGoalError):
        Goal(
            goal_id="g1",
            description="",
            goal_type=GoalType.REPOSITORY_EXPLANATION,
            repo_id="r1",
        )

    with pytest.raises(InvalidGoalError):
        Goal(
            goal_id="g1",
            description="desc",
            goal_type=GoalType.REPOSITORY_EXPLANATION,
            repo_id="",
        )


def test_goal_interpreter_all_types() -> None:
    interpreter = GoalInterpreter()
    assert (
        interpreter.interpret_goal("Explain the architecture", "r1").goal_type
        == GoalType.ARCHITECTURE_ANALYSIS
    )
    assert (
        interpreter.interpret_goal("Show call sequence", "r1").goal_type
        == GoalType.CALL_FLOW_ANALYSIS
    )
    assert (
        interpreter.interpret_goal("Analyze module imports", "r1").goal_type
        == GoalType.DEPENDENCY_INVESTIGATION
    )
    assert (
        interpreter.interpret_goal("Investigate bug in login", "r1").goal_type
        == GoalType.BUG_INVESTIGATION
    )
    assert (
        interpreter.interpret_goal("Generate docstring for auth", "r1").goal_type
        == GoalType.DOCUMENTATION_GENERATION
    )
    assert (
        interpreter.interpret_goal("Refactor user module", "r1").goal_type
        == GoalType.REFACTORING_ANALYSIS
    )
    assert (
        interpreter.interpret_goal("Check impact of user_id change", "r1").goal_type
        == GoalType.IMPACT_ANALYSIS
    )
    assert (
        interpreter.interpret_goal("Find symbol definition", "r1").goal_type
        == GoalType.CODE_NAVIGATION
    )
    assert (
        interpreter.interpret_goal("Check repository health status", "r1").goal_type
        == GoalType.REPOSITORY_HEALTH
    )
    assert (
        interpreter.interpret_goal("General repository explanation", "r1").goal_type
        == GoalType.REPOSITORY_EXPLANATION
    )


def test_planner_and_task_graph() -> None:
    goal = Goal(
        goal_id="g1",
        description="Explain auth",
        goal_type=GoalType.REPOSITORY_EXPLANATION,
        repo_id="r1",
    )
    planner = Planner()
    plan = planner.create_plan(goal)

    assert len(plan.steps) == 4

    graph_engine = TaskGraphEngine()
    graph = graph_engine.build_graph(plan)
    assert len(graph.tasks) == 4
    assert graph.tasks[0].status == TaskStatus.PENDING

    scheduler = TaskScheduler()
    ready = scheduler.get_ready_tasks(graph)
    assert len(ready) == 1
    assert ready[0].task_id.value == "task_1"


def test_tool_registry_and_selector() -> None:
    registry = ToolRegistry()
    registry.register_tool("mock_tool", lambda params: {"result": "ok"})

    exec_res = registry.invoke_tool("mock_tool", {"param": 1})
    assert exec_res.is_success
    assert exec_res.output["result"] == "ok"

    selector = ToolSelector()
    tools = selector.select_tools_for_goal(GoalType.CALL_FLOW_ANALYSIS)
    assert "find_callers" in tools


def test_reflection_verification_and_checkpoints() -> None:
    goal = Goal(
        goal_id="g1",
        description="Explain auth",
        goal_type=GoalType.REPOSITORY_EXPLANATION,
        repo_id="r1",
    )
    ctx_mgr = ExecutionContextManager()
    ctx = ctx_mgr.create_context(goal)

    ref_engine = ReflectionEngine()
    ver_engine = VerificationEngine()
    cp_mgr = CheckpointManager()

    # Initial empty state
    ref1 = ref_engine.reflect(ctx)
    assert not ref1.is_sufficient

    ver1 = ver_engine.verify(ctx)
    assert not ver1.is_verified

    # Add task
    ctx = ctx_mgr.update_context(ctx, TaskId(value="t1"), {"out": "ok"})
    cp = cp_mgr.create_checkpoint(ctx)
    assert cp_mgr.restore_checkpoint(cp.checkpoint_id) == cp

    ref2 = ref_engine.reflect(ctx)
    assert ref2.is_sufficient

    ver2 = ver_engine.verify(ctx)
    assert ver2.is_verified


def test_event_publisher() -> None:
    publisher = EventPublisher()
    events: list[AgentEvent] = []
    publisher.subscribe(events.append)

    evt = AgentEvent(event_type="GoalStarted", goal_id="g1", details="Started")
    publisher.publish(evt)
    assert len(events) == 1
    assert events[0].event_type == "GoalStarted"


def test_agent_runtime_end_to_end() -> None:
    goal = Goal(
        goal_id="g1",
        description="Explain auth",
        goal_type=GoalType.REPOSITORY_EXPLANATION,
        repo_id="r1",
    )

    planner = Planner()
    graph_engine = TaskGraphEngine()
    scheduler = TaskScheduler()
    ctx_mgr = ExecutionContextManager()
    executor = ExecutionEngine(graph_engine, scheduler, ctx_mgr)
    registry = ToolRegistry()
    ref_engine = ReflectionEngine()
    ver_engine = VerificationEngine()
    cp_mgr = CheckpointManager()

    runtime = AgentRuntime(planner, executor, registry, ref_engine, ver_engine, cp_mgr)
    result = runtime.execute_goal(goal)

    assert result.is_success
    assert "executed successfully" in result.answer_text
