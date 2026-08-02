"""Workflow A/F 統合試験 — type-safe spy pattern."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# ------------------------------------------------------------------
# Typed Spies (no MagicMock)
# ------------------------------------------------------------------


class MockPlanner:
    """Planner Spy — records calls and returns a deterministic plan."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.result: dict[str, Any] = {}
        self.call_count: int = 0

    def plan(self, task: str, ctx: Any = None) -> dict[str, Any]:
        self.calls.append((task, ctx))
        self.call_count += 1
        self.result = {
            "plan_id": "workflow-f-plan",
            "steps": ["execute", "validate"],
        }
        return self.result


class MockExecutor:
    """Executor Spy — records calls and returns a session-identified result."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.received_plan: dict[str, Any] | None = None

    def run_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(plan)
        self.received_plan = plan
        return {
            "session_id": "executor-session-001",
            "status": "completed",
        }


class MockValidator:
    """Validator Spy — records calls and returns a fixed validation."""

    def __init__(self) -> None:
        self.calls: list[Any] = []

    def validate(self, data: Any) -> dict[str, Any]:
        self.calls.append(data)
        return {
            "session_id": "validator-session-001",
            "valid": False,
            "status": "retryable",
        }


class MockRetryManager:
    """RetryManager Spy — records calls and returns a fixed decision."""

    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, Any], Any]] = []

    def classify(self, validation: dict[str, Any], plan: Any) -> dict[str, str]:
        self.calls.append((validation, plan))
        return {
            "action": "retry",
            "reason": "validator_requested_retry",
        }


class HandoverSpy:
    """Spy that records path and data, and writes the actual file."""

    def __init__(self) -> None:
        self.call_count = 0
        self.written_path: Path | None = None
        self.written_data: Any = None

    def write(self, path: str | Path, data: Any) -> None:
        self.call_count += 1
        self.written_path = Path(path)
        self.written_data = data

        # Actually write the file
        self.written_path.parent.mkdir(parents=True, exist_ok=True)
        self.written_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


# ------------------------------------------------------------------
# Test Cases
# ------------------------------------------------------------------


def test_workflow_a_no_planner() -> None:
    """Workflow A does not call Planner."""
    from loto_ops.pipeline.workflow_dispatcher import WorkflowDispatcher

    planner_spy = MockPlanner()
    executor_spy = MockExecutor()
    validator_spy = MockValidator()
    retry_manager_spy = MockRetryManager()
    handover_spy = HandoverSpy()

    dispatcher = WorkflowDispatcher(
        planner=planner_spy,
        executor=executor_spy,
        validator=validator_spy,
        retry_manager=retry_manager_spy,
        handover=handover_spy,
        workflow="A",
    )

    result = dispatcher.dispatch(task="test-task-a", plan={"steps": ["inspect"]})

    assert planner_spy.call_count == 0
    assert result.planner_called is False
    assert result.planner_plan is None


def test_workflow_f_planner_called() -> None:
    """Workflow F calls Planner once and passes its result to Executor."""
    from loto_ops.pipeline.workflow_dispatcher import WorkflowDispatcher

    planner_spy = MockPlanner()
    executor_spy = MockExecutor()
    validator_spy = MockValidator()
    retry_manager_spy = MockRetryManager()
    handover_spy = HandoverSpy()

    dispatcher = WorkflowDispatcher(
        planner=planner_spy,
        executor=executor_spy,
        validator=validator_spy,
        retry_manager=retry_manager_spy,
        handover=handover_spy,
        workflow="F",
    )

    result = dispatcher.dispatch(task="test-task-f", plan=None)

    assert planner_spy.call_count == 1
    assert result.planner_called is True
    assert result.planner_plan == planner_spy.result
    assert executor_spy.received_plan == planner_spy.result


def test_workflow_f_session_ids_differ() -> None:
    """Workflow F: Executor and Validator session IDs must differ."""
    from loto_ops.pipeline.workflow_dispatcher import WorkflowDispatcher

    planner_spy = MockPlanner()
    executor_spy = MockExecutor()
    validator_spy = MockValidator()
    retry_manager_spy = MockRetryManager()
    handover_spy = HandoverSpy()

    dispatcher = WorkflowDispatcher(
        planner=planner_spy,
        executor=executor_spy,
        validator=validator_spy,
        retry_manager=retry_manager_spy,
        handover=handover_spy,
        workflow="F",
    )

    result = dispatcher.dispatch(task="test-task-session", plan=None)

    # Executorが受け取ったPlanからsession_idを抽出
    executor_plan = executor_spy.calls[-1]
    executor_id = executor_plan.get("session_id", "executor-session-001")

    validator_id = result.validator_result.get("session_id")

    assert executor_id is not None
    assert validator_id is not None
    assert executor_id != validator_id
    assert result.validator_fresh is True


def test_workflow_f_handover(tmp_path: Path) -> None:
    """Handover writes an actual JSON file at output_dir."""
    from loto_ops.pipeline.workflow_dispatcher import WorkflowDispatcher

    planner_spy = MockPlanner()
    executor_spy = MockExecutor()
    validator_spy = MockValidator()
    retry_manager_spy = MockRetryManager()
    handover_spy = HandoverSpy()

    dispatcher = WorkflowDispatcher(
        planner=planner_spy,
        executor=executor_spy,
        validator=validator_spy,
        retry_manager=retry_manager_spy,
        handover=handover_spy,
        workflow="F",
        output_dir=str(tmp_path),
    )

    result = dispatcher.dispatch(task="test-task-handover", plan=None)

    assert result.handover_written is True
    assert handover_spy.call_count == 1
    assert handover_spy.written_path is not None
    assert handover_spy.written_path.is_file()

    loaded = json.loads(handover_spy.written_path.read_text(encoding="utf-8"))
    assert loaded == handover_spy.written_data


def test_workflow_a_handover() -> None:
    """Workflow A also writes Handover file."""
    from loto_ops.pipeline.workflow_dispatcher import WorkflowDispatcher

    planner_spy = MockPlanner()
    executor_spy = MockExecutor()
    validator_spy = MockValidator()
    retry_manager_spy = MockRetryManager()
    handover_spy = HandoverSpy()

    dispatcher = WorkflowDispatcher(
        planner=planner_spy,
        executor=executor_spy,
        validator=validator_spy,
        retry_manager=retry_manager_spy,
        handover=handover_spy,
        workflow="A",
        output_dir="/tmp",
    )

    result = dispatcher.dispatch(task="test-task-a-handover", plan={"steps": ["inspect"]})

    assert result.handover_written is True
    assert handover_spy.call_count == 1
    assert handover_spy.written_path is not None
    assert handover_spy.written_path.is_file()
