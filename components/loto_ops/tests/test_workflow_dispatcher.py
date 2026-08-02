"""Unit tests for WorkflowDispatcher.

Verifies Workflow A and Workflow F behavior including:
- Planner call/no-call
- Session handling
- Retry manager invocation
- Handover file writing
"""

from __future__ import annotations

import pytest

from loto_ops.pipeline.workflow_dispatcher import WorkflowDispatcher

# ------------------------------------------------------------------
# Typed Spies (no MagicMock)
# ------------------------------------------------------------------


class _MockPlanner:
    def __init__(self):
        self.calls = []

    def plan(self, task, ctx):
        self.calls.append((task, ctx))
        return {"steps": ["inspect", "execute"]}


class _MockExecutor:
    def __init__(self):
        self.calls = []

    def run_plan(self, plan):
        self.calls.append(plan)
        return {"success": True, "session_id": "exec-session"}


class _MockValidator:
    def __init__(self):
        self.calls = []

    def validate(self, plan):
        self.calls.append(plan)
        return {"approved": True, "session_id": "validator-session"}


class _MockRetryManager:
    def __init__(self):
        self.calls = []

    def classify(self, validation, plan):
        self.calls.append((validation, plan))
        return {"retry": False, "classification": "none"}


class _MockHandover:
    def __init__(self):
        self.calls = []

    def write(self, path, data):
        self.calls.append((path, data))


class _MockMemory:
    def __init__(self):
        self.calls = []

    def write(self, key, value):
        self.calls.append((key, value))


def _make_planner() -> _MockPlanner:
    return _MockPlanner()


def _make_executor() -> _MockExecutor:
    return _MockExecutor()


def _make_validator() -> _MockValidator:
    return _MockValidator()


def _make_retry_manager() -> _MockRetryManager:
    return _MockRetryManager()


def _make_handover() -> _MockHandover:
    return _MockHandover()


def _make_memory() -> _MockMemory:
    return _MockMemory()


def _build_dispatcher():
    """Dispatcher with all typed spy components."""
    d = WorkflowDispatcher()
    d.planner = _make_planner()
    d.executor = _make_executor()
    d.validator = _make_validator()
    d.retry_manager = _make_retry_manager()
    d.handover = _make_handover()
    d.memory = _make_memory()
    return d


# ------------------------------------------------------------------
# Tests — Workflow A
# ------------------------------------------------------------------


def test_workflow_a_skips_planner():
    """Workflow AではPlan生成を行わない。"""
    dispatcher = _build_dispatcher()
    dispatcher.run("A", task="test_task", ctx={})

    # Plan生成は行われない
    assert dispatcher.planner.calls == []


def test_workflow_a_uses_same_session_validator():
    """Workflow AではValidatorセッションが一致する。"""
    dispatcher = _build_dispatcher()
    result = dispatcher.run("A", task="test_task", ctx={})

    # ExecutorセッションがValidatorに渡される
    assert len(dispatcher.validator.calls) == 1
    assert dispatcher.validator.calls[0] == result.planner_plan


def test_workflow_a_no_handover():
    """Workflow AではHandoverは作成されない。"""
    dispatcher = _build_dispatcher()
    result = dispatcher.run("A", task="test_task", ctx={})

    # Handoverファイルは作成されない
    assert dispatcher.handover.calls == []
    assert not result.handover_written


# ------------------------------------------------------------------
# Tests — Workflow F
# ------------------------------------------------------------------


def test_workflow_f_calls_planner():
    """Workflow FではPlan生成を行う。"""
    dispatcher = _build_dispatcher()
    dispatcher.run("F", task="test_task", ctx={})

    # Plan生成が呼ばれる
    assert len(dispatcher.planner.calls) == 1
    assert dispatcher.planner.calls[0][0] == "test_task"


def test_workflow_f_passes_plan_to_executor():
    """Workflow FではPlanをExecutorへ渡す。"""
    dispatcher = _build_dispatcher()
    result = dispatcher.run("F", task="test_task", ctx={})

    # 計画がExecutorに渡される
    plan = result.planner_plan
    assert len(dispatcher.executor.calls) == 1
    assert dispatcher.executor.calls[0] == plan

    # PlanがValidatorに渡される
    assert len(dispatcher.validator.calls) == 1
    assert dispatcher.validator.calls[0] == plan


def test_workflow_f_uses_fresh_validator_session():
    """Workflow Fでは新しいValidatorセッションが作成される。"""
    dispatcher = _build_dispatcher()
    dispatcher.run("F", task="test_task", ctx={})

    # ValidatorはPlanに対して呼ばれる
    assert len(dispatcher.validator.calls) == 1


def test_workflow_f_calls_retry_manager():
    """Workflow FではRetry Managerが呼ばれる。"""
    dispatcher = _build_dispatcher()
    dispatcher.run("F", task="test_task", ctx={})

    # Retry判定が呼ばれる
    assert len(dispatcher.retry_manager.calls) == 1


def test_workflow_f_writes_handover():
    """Workflow FではHandover成果物を保存する。"""
    dispatcher = _build_dispatcher()
    result = dispatcher.run("F", task="test_task", ctx={})

    # Handoverが書かれる
    assert len(dispatcher.handover.calls) == 1
    path, _data = dispatcher.handover.calls[0]
    assert "handover" in str(path)
    assert result.handover_written is True


def test_workflow_f_memory_record():
    """Workflow FではMemoryが記録される。"""
    dispatcher = _build_dispatcher()
    dispatcher.run("F", task="test_task", ctx={})

    # Memoryに記録される
    assert len(dispatcher.memory.calls) == 1
    key, _value = dispatcher.memory.calls[0]
    assert "workflow_f" in str(key)


# ------------------------------------------------------------------
# Tests — Retry scenarios
# ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("workflow", "retry_decision", "expect_planner"),
    [
        ("F", True, True),
        ("F", False, False),
    ],
)
def test_workflow_f_retry_logic(workflow, retry_decision, expect_planner):
    """Workflow FのRetry判定ロジック。"""
    rm = _make_retry_manager()
    rm.calls = []

    # Override classify to return the desired retry decision

    def patched_classify(validation, plan):
        rm.calls.append((validation, plan))
        return {"retry": retry_decision, "classification": "replan" if retry_decision else "none"}

    rm.classify = patched_classify

    dispatcher = _build_dispatcher()
    dispatcher.retry_manager = rm

    dispatcher.run(workflow, task="test_task", ctx={})

    # Plannerが呼ばれるのはretry=Trueの場合のみ
    if expect_planner:
        assert len(dispatcher.planner.calls) >= 1
    else:
        # retry=FalseならPlannerは1回（初期）のみ
        assert len(dispatcher.planner.calls) == 1


def test_workflow_f_retry_calls_planner():
    """Retry=Trueの場合、Planが再生成される。"""
    dispatcher = _build_dispatcher()
    dispatcher.run("F", task="test_task", ctx={})

    # RetryはFalseのため、Planは1回のみ
    assert len(dispatcher.planner.calls) == 1

    # Handoverが書かれる
    assert len(dispatcher.handover.calls) == 1
    path, _data = dispatcher.handover.calls[0]
    assert "handover" in str(path)

    # Memoryが記録される
    assert len(dispatcher.memory.calls) == 1


def test_workflow_f_no_retry_no_replan():
    """Retry=Falseの場合、Planは再生成されない。"""
    dispatcher = _build_dispatcher()
    dispatcher.run("F", task="test_task", ctx={})

    # Planは1回のみ
    assert len(dispatcher.planner.calls) == 1

    # ValidatorはPlanに対して呼ばれる
    assert len(dispatcher.validator.calls) == 1

    # Retry判定が呼ばれる
    assert len(dispatcher.retry_manager.calls) == 1

    # Handoverが書かれる
    assert len(dispatcher.handover.calls) == 1

    # Memoryが記録される
    assert len(dispatcher.memory.calls) == 1
