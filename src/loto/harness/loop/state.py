from __future__ import annotations

from ..contracts import LoopPhase

_ALLOWED: dict[LoopPhase, set[LoopPhase]] = {
    LoopPhase.OBSERVE: {LoopPhase.DIAGNOSE, LoopPhase.FAILED},
    LoopPhase.DIAGNOSE: {LoopPhase.PLAN, LoopPhase.FAILED},
    LoopPhase.PLAN: {LoopPhase.CHECKPOINT, LoopPhase.FAILED},
    LoopPhase.CHECKPOINT: {LoopPhase.CHANGE, LoopPhase.FAILED},
    LoopPhase.CHANGE: {LoopPhase.LOCAL_TEST, LoopPhase.ROLLBACK, LoopPhase.FAILED},
    LoopPhase.LOCAL_TEST: {LoopPhase.MEASURE, LoopPhase.REPAIR, LoopPhase.ROLLBACK},
    LoopPhase.MEASURE: {LoopPhase.REVIEW, LoopPhase.REPAIR, LoopPhase.ROLLBACK},
    LoopPhase.REVIEW: {LoopPhase.JUDGE, LoopPhase.REPAIR, LoopPhase.ROLLBACK},
    LoopPhase.JUDGE: {LoopPhase.ACCEPT, LoopPhase.REPAIR, LoopPhase.ROLLBACK},
    LoopPhase.REPAIR: {LoopPhase.CHANGE, LoopPhase.ROLLBACK, LoopPhase.FAILED},
    LoopPhase.ACCEPT: set(),
    LoopPhase.ROLLBACK: set(),
    LoopPhase.FAILED: set(),
}


class LoopStateMachine:
    def __init__(self, phase: LoopPhase = LoopPhase.OBSERVE) -> None:
        self.phase = phase

    def can_transition(self, target: LoopPhase) -> bool:
        return target in _ALLOWED[self.phase]

    def transition(self, target: LoopPhase) -> None:
        if not self.can_transition(target):
            raise ValueError(f"invalid loop transition: {self.phase} -> {target}")
        self.phase = target
