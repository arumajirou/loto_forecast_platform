from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_sundial_provider_v2_final_gate.sh"


def test_final_gate_shell_syntax() -> None:
    proc = subprocess.run(
        ["bash", "-n", str(SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr


def test_final_gate_order_is_fail_closed() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    stages = (
        "run_logged ruff",
        "run_logged mypy",
        "run_logged focused-pytest",
        "run_logged semantic-snapshot-preflight",
        "run_logged certification",
        "run_logged semantic-output-verification",
        "run_logged evidence-verification",
        "run_logged full-pytest",
    )
    offsets = [text.index(stage) for stage in stages]
    assert offsets == sorted(offsets)
    assert "git status --porcelain=v1" in text
    assert "SUNDIAL_PROVIDER_V2_FINAL_GATE=" in text
    assert "SKIPPED_BY_CONFIGURATION" not in text


def test_final_gate_requires_fixed_identity_and_evidence() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    required = (
        "EXPECTED_COMMIT",
        "EXPECTED_BRANCH",
        "3212e42564493f520593e5414af4367fc4b49226",
        "UV_FROZEN=1",
        "SUNDIAL_PROVIDER_V2_CERTIFICATION=PASS",
        "verify_sundial_provider_v2_semantics.py",
        "SEMANTIC_REPORT",
        "VERIFICATION_REPORT.json",
        "evidence.zip",
        '"$ARCHIVE.sha256"',
    )
    for marker in required:
        assert marker in text
