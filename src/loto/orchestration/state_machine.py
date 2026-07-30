from __future__ import annotations

from dataclasses import dataclass

STAGES = ["INGEST", "VALIDATE", "CANONICALIZE", "BUILD_FEATURES", "TRAIN", "CALIBRATE", "DECODE", "EVALUATE", "SEAL_FORECAST", "REGISTER"]
TERMINAL = {"SUCCEEDED", "FAILED", "CANCELLED"}


@dataclass
class RunStateMachine:
    completed: set[str]

    def next_stage(self) -> str | None:
        for stage in STAGES:
            if stage not in self.completed:
                return stage
        return None

    def can_run(self, stage: str) -> bool:
        if stage not in STAGES:
            return False
        idx = STAGES.index(stage)
        return all(previous in self.completed for previous in STAGES[:idx])

    def mark_completed(self, stage: str) -> None:
        if not self.can_run(stage):
            raise RuntimeError(f"stage order violation: {stage}")
        self.completed.add(stage)
