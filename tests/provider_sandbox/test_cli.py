from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from loto.provider_sandbox import SandboxArgvPlan, SandboxBackend

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/run_provider_sandbox.py"


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run(
        [sys.executable, str(SCRIPT), *arguments],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


def test_validate_default_policy_cli() -> None:
    result = _run(
        "validate-policy",
        "--policy",
        str(ROOT / "configs/provider_sandbox/default_policy.json"),
    )
    assert result.returncode == 0
    assert json.loads(result.stdout)["status"] == "PASS"


def test_execute_plan_requires_explicit_test_only_acknowledgment(tmp_path: Path) -> None:
    plan = SandboxArgvPlan.create(
        backend=SandboxBackend.NONE,
        argv=(sys.executable, "-c", "print('fixture')"),
        environment_keys=(),
    )
    path = tmp_path / "plan.json"
    path.write_text(
        json.dumps(plan.model_dump(mode="json"), sort_keys=True),
        encoding="utf-8",
    )
    blocked = _run(
        "execute-plan",
        "--plan",
        str(path),
        "--timeout-seconds",
        "2",
        "--output-limit-bytes",
        "1024",
    )
    assert blocked.returncode == 2
    allowed = _run(
        "execute-plan",
        "--plan",
        str(path),
        "--timeout-seconds",
        "2",
        "--output-limit-bytes",
        "1024",
        "--test-only-confirm-no-security-certification",
    )
    assert allowed.returncode == 0
    assert json.loads(allowed.stdout)["outcome"] == "SUCCEEDED"
