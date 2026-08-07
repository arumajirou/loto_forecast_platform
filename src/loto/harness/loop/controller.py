from __future__ import annotations

import time
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from ..contracts import (
    HarnessStatus,
    LoopEvent,
    LoopPhase,
    LoopResult,
    LoopTask,
)
from ..errors import LoopLimitReached
from .state import LoopStateMachine

PhaseCallback = Callable[[LoopTask, int], Awaitable[dict]]


@dataclass
class LoopCallbacks:
    observe: PhaseCallback
    diagnose: PhaseCallback
    plan: PhaseCallback
    checkpoint: PhaseCallback
    change: PhaseCallback
    local_test: PhaseCallback
    measure: PhaseCallback
    review: PhaseCallback
    judge: PhaseCallback
    rollback: PhaseCallback


class EngineeringLoop:
    def __init__(self, callbacks: LoopCallbacks) -> None:
        self.callbacks = callbacks

    async def run(self, task: LoopTask) -> LoopResult:
        started = time.monotonic()
        state = LoopStateMachine()
        events: list[LoopEvent] = []
        sequence = 0
        iteration = 0
        signatures: Counter[str] = Counter()

        async def execute(phase: LoopPhase, callback: PhaseCallback) -> dict:
            nonlocal sequence
            payload = await callback(task, iteration)
            sequence += 1
            status_value = payload.get("status", HarnessStatus.VERIFIED)
            status = (
                status_value
                if isinstance(status_value, HarnessStatus)
                else HarnessStatus(str(status_value))
            )
            events.append(
                LoopEvent(
                    sequence=sequence,
                    phase=phase,
                    status=status,
                    summary=str(payload.get("summary", phase.value)),
                    evidence=dict(payload.get("evidence") or {}),
                )
            )
            return payload

        for phase, callback in [
            (LoopPhase.OBSERVE, self.callbacks.observe),
            (LoopPhase.DIAGNOSE, self.callbacks.diagnose),
            (LoopPhase.PLAN, self.callbacks.plan),
            (LoopPhase.CHECKPOINT, self.callbacks.checkpoint),
        ]:
            if state.phase != phase:
                state.transition(phase)
            payload = await execute(phase, callback)
            if payload.get("ok", True) is not True:
                return LoopResult(
                    task_id=task.task_id,
                    status=HarnessStatus.FAILED,
                    final_phase=LoopPhase.FAILED,
                    iterations=iteration,
                    events=events,
                )
            next_phase = {
                LoopPhase.OBSERVE: LoopPhase.DIAGNOSE,
                LoopPhase.DIAGNOSE: LoopPhase.PLAN,
                LoopPhase.PLAN: LoopPhase.CHECKPOINT,
                LoopPhase.CHECKPOINT: LoopPhase.CHANGE,
            }[phase]
            state.transition(next_phase)

        while iteration < task.limits.max_iterations:
            if time.monotonic() - started > task.limits.max_wall_seconds:
                raise LoopLimitReached("wall-clock limit reached")
            iteration += 1
            change = await execute(LoopPhase.CHANGE, self.callbacks.change)
            if change.get("ok", True) is not True:
                state.transition(LoopPhase.ROLLBACK)
                await execute(LoopPhase.ROLLBACK, self.callbacks.rollback)
                return LoopResult(
                    task_id=task.task_id,
                    status=HarnessStatus.FAILED,
                    final_phase=LoopPhase.ROLLBACK,
                    iterations=iteration,
                    events=events,
                    failure_signature=change.get("failure_signature"),
                )

            state.transition(LoopPhase.LOCAL_TEST)
            test = await execute(LoopPhase.LOCAL_TEST, self.callbacks.local_test)
            signature = str(test.get("failure_signature") or "")
            if signature:
                signatures[signature] += 1
            if test.get("ok", False) is not True:
                if signature and signatures[signature] >= task.limits.max_same_failure_repeats:
                    state.transition(LoopPhase.ROLLBACK)
                    await execute(LoopPhase.ROLLBACK, self.callbacks.rollback)
                    return LoopResult(
                        task_id=task.task_id,
                        status=HarnessStatus.FAILED,
                        final_phase=LoopPhase.ROLLBACK,
                        iterations=iteration,
                        events=events,
                        failure_signature=signature,
                    )
                state.transition(LoopPhase.REPAIR)
                sequence += 1
                events.append(
                    LoopEvent(
                        sequence=sequence,
                        phase=LoopPhase.REPAIR,
                        status=HarnessStatus.PENDING,
                        summary="repair requested after failed local test",
                        evidence={"failure_signature": signature},
                    )
                )
                state.transition(LoopPhase.CHANGE)
                continue

            state.transition(LoopPhase.MEASURE)
            await execute(LoopPhase.MEASURE, self.callbacks.measure)
            state.transition(LoopPhase.REVIEW)
            review = await execute(LoopPhase.REVIEW, self.callbacks.review)
            if review.get("ok", False) is not True:
                state.transition(LoopPhase.REPAIR)
                sequence += 1
                events.append(
                    LoopEvent(
                        sequence=sequence,
                        phase=LoopPhase.REPAIR,
                        status=HarnessStatus.PENDING,
                        summary="repair requested by reviewer",
                    )
                )
                state.transition(LoopPhase.CHANGE)
                continue

            state.transition(LoopPhase.JUDGE)
            judge = await execute(LoopPhase.JUDGE, self.callbacks.judge)
            if judge.get("ok", False) is True:
                state.transition(LoopPhase.ACCEPT)
                sequence += 1
                events.append(
                    LoopEvent(
                        sequence=sequence,
                        phase=LoopPhase.ACCEPT,
                        status=HarnessStatus.VERIFIED,
                        summary="all acceptance gates passed",
                    )
                )
                return LoopResult(
                    task_id=task.task_id,
                    status=HarnessStatus.VERIFIED,
                    final_phase=LoopPhase.ACCEPT,
                    iterations=iteration,
                    events=events,
                )
            state.transition(LoopPhase.REPAIR)
            sequence += 1
            events.append(
                LoopEvent(
                    sequence=sequence,
                    phase=LoopPhase.REPAIR,
                    status=HarnessStatus.PENDING,
                    summary="repair requested by judge",
                )
            )
            state.transition(LoopPhase.CHANGE)

        state.transition(LoopPhase.ROLLBACK)
        await execute(LoopPhase.ROLLBACK, self.callbacks.rollback)
        return LoopResult(
            task_id=task.task_id,
            status=HarnessStatus.FAILED,
            final_phase=LoopPhase.ROLLBACK,
            iterations=iteration,
            events=events,
        )
