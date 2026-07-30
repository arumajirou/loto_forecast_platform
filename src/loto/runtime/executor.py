from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ExecutionResult:
    status: str
    returncode: int | None
    elapsed_seconds: float
    stdout_path: str
    stderr_path: str
    timed_out: bool = False


class IsolatedExecutor:
    def __init__(self, *, timeout_seconds: int = 1800, env: dict[str, str] | None = None):
        self.timeout_seconds = timeout_seconds
        self.env = env or {}

    def run_python_module(self, module: str, args: list[str], output_dir: str | Path) -> ExecutionResult:
        root = Path(output_dir)
        root.mkdir(parents=True, exist_ok=True)
        stdout_path = root / "stdout.log"
        stderr_path = root / "stderr.log"
        started = time.perf_counter()
        command = [sys.executable, "-m", module, *args]
        with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
            try:
                proc = subprocess.run(command, stdout=stdout, stderr=stderr, timeout=self.timeout_seconds,
                                      check=False, env=os.environ | self.env)
                timed_out = False
                code = proc.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
                code = None
        result = ExecutionResult(
            status="TIMEOUT" if timed_out else ("SUCCEEDED" if code == 0 else "FAILED"),
            returncode=code, elapsed_seconds=time.perf_counter() - started,
            stdout_path=str(stdout_path), stderr_path=str(stderr_path), timed_out=timed_out,
        )
        (root / "execution.json").write_text(json.dumps(result.__dict__, indent=2), encoding="utf-8")
        return result
