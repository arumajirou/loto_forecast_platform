import asyncio

from loto.harness.contracts import HarnessStatus, LoopTask
from loto.harness.loop.controller import EngineeringLoop, LoopCallbacks


def callback(ok=True, failure_signature=None):
    async def inner(task, iteration):
        payload = {"ok": ok, "summary": f"{task.task_id}:{iteration}"}
        if failure_signature:
            payload["failure_signature"] = failure_signature
        return payload

    return inner


def test_loop_accepts_after_all_gates() -> None:
    callbacks = LoopCallbacks(
        observe=callback(),
        diagnose=callback(),
        plan=callback(),
        checkpoint=callback(),
        change=callback(),
        local_test=callback(),
        measure=callback(),
        review=callback(),
        judge=callback(),
        rollback=callback(),
    )
    task = LoopTask(task_id="t1", objective="test", repository="repo", worktree="tree")
    result = asyncio.run(EngineeringLoop(callbacks).run(task))
    assert result.status == HarnessStatus.VERIFIED
    assert result.final_phase == "ACCEPT"
    assert result.iterations == 1


def test_loop_rolls_back_after_repeated_same_failure() -> None:
    callbacks = LoopCallbacks(
        observe=callback(),
        diagnose=callback(),
        plan=callback(),
        checkpoint=callback(),
        change=callback(),
        local_test=callback(ok=False, failure_signature="same"),
        measure=callback(),
        review=callback(),
        judge=callback(),
        rollback=callback(),
    )
    task = LoopTask(task_id="t2", objective="test", repository="repo", worktree="tree")
    result = asyncio.run(EngineeringLoop(callbacks).run(task))
    assert result.status == HarnessStatus.FAILED
    assert result.final_phase == "ROLLBACK"
    assert result.iterations == 2
    assert result.failure_signature == "same"
