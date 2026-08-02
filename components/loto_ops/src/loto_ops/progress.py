from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def make_bar(percent: float, *, width: int = 28) -> str:
    percent = max(0.0, min(100.0, float(percent)))
    filled = round(width * percent / 100.0)
    return "█" * filled + "░" * (width - filled)


@dataclass
class StepState:
    index: int
    name: str
    status: str = "pending"
    started_at: str | None = None
    finished_at: str | None = None
    seconds: float | None = None
    message: str = ""


@dataclass
class ProgressReporter:
    """Small dependency-free progress reporter for CLI, cron logs, and Streamlit polling.

    It writes a JSON state file and prints a compact textual progress bar.  The JSON file
    is intentionally simple so cron/systemd jobs, Streamlit, and shell scripts can all read it.
    """

    title: str
    steps: list[str]
    state_path: Path | None = None
    stream: TextIO | None = sys.stdout
    run_id: str | None = None
    reason: str | None = None
    enabled: bool = True
    _started_monotonic: float = field(default_factory=time.perf_counter, init=False)
    _step_started_monotonic: float | None = field(default=None, init=False)
    _states: list[StepState] = field(init=False)
    _current_index: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self._states = [StepState(index=i + 1, name=name) for i, name in enumerate(self.steps)]
        if self.state_path is not None:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.write(status="running", message="started", percent=0.0)
        self.print_line(0.0, "started")

    @property
    def total(self) -> int:
        return max(1, len(self.steps))

    def start_step(self, name: str | None = None) -> None:
        if name is not None and name in self.steps:
            self._current_index = self.steps.index(name) + 1
        elif self._current_index < len(self.steps):
            self._current_index += 1
        else:
            self._current_index = len(self.steps)

        state = self._states[self._current_index - 1]
        state.status = "running"
        state.started_at = utc_now_iso()
        state.message = "running"
        self._step_started_monotonic = time.perf_counter()
        self.write(status="running", message=f"running: {state.name}")
        self.print_line(self.percent_in_step(0.0), f"RUN {state.index}/{self.total} {state.name}")

    def complete_step(self, message: str = "done") -> None:
        if self._current_index <= 0:
            return
        state = self._states[self._current_index - 1]
        state.status = "success"
        state.finished_at = utc_now_iso()
        state.message = message
        if self._step_started_monotonic is not None:
            state.seconds = round(time.perf_counter() - self._step_started_monotonic, 3)
        self.write(status="running", message=f"done: {state.name}")
        self.print_line(
            self.percent_completed_steps(), f"OK  {state.index}/{self.total} {state.name}"
        )

    def fail_step(self, message: str) -> None:
        if self._current_index <= 0:
            self._current_index = 1
        state = self._states[self._current_index - 1]
        state.status = "failed"
        state.finished_at = utc_now_iso()
        state.message = message
        if self._step_started_monotonic is not None:
            state.seconds = round(time.perf_counter() - self._step_started_monotonic, 3)
        self.write(status="failed", message=message)
        self.print_line(
            self.percent_completed_steps(),
            f"FAIL {state.index}/{self.total} {state.name}: {message}",
        )

    def finish(self, status: str = "success", message: str = "finished") -> None:
        percent = 100.0 if status == "success" else self.percent_completed_steps()
        self.write(status=status, message=message, percent=percent)
        self.print_line(percent, message)

    def percent_completed_steps(self) -> float:
        done = sum(1 for s in self._states if s.status == "success")
        return 100.0 * done / self.total

    def percent_in_step(self, step_fraction: float) -> float:
        completed = max(0, self._current_index - 1)
        return 100.0 * (completed + max(0.0, min(1.0, step_fraction))) / self.total

    def write(self, *, status: str, message: str = "", percent: float | None = None) -> None:
        if not self.enabled:
            return
        percent = self.percent_completed_steps() if percent is None else percent
        payload: dict[str, Any] = {
            "title": self.title,
            "run_id": self.run_id,
            "reason": self.reason,
            "status": status,
            "message": message,
            "percent": round(float(percent), 2),
            "bar": make_bar(float(percent)),
            "current_index": self._current_index,
            "total_steps": self.total,
            "current_step": self._states[self._current_index - 1].name
            if self._current_index
            else None,
            "started_at": datetime.fromtimestamp(
                time.time() - (time.perf_counter() - self._started_monotonic), UTC
            ).isoformat(timespec="seconds"),
            "updated_at": utc_now_iso(),
            "elapsed_seconds": round(time.perf_counter() - self._started_monotonic, 3),
            "steps": [s.__dict__ for s in self._states],
        }
        if self.state_path is not None:
            tmp = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.state_path)

    def print_line(self, percent: float, message: str) -> None:
        if not self.enabled or self.stream is None:
            return
        bar = make_bar(percent)
        print(f"[progress] {bar} {percent:6.2f}% | {message}", file=self.stream, flush=True)


def run_step(reporter: ProgressReporter, name: str, func, *args, **kwargs):
    reporter.start_step(name)
    try:
        result = func(*args, **kwargs)
    except Exception as exc:
        reporter.fail_step(f"{type(exc).__name__}: {exc}")
        raise
    reporter.complete_step()
    return result
