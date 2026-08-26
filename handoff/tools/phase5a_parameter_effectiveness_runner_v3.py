#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.dont_write_bytecode = True
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

ROOT = Path(os.environ.get("LOTO_ROOT", "/mnt/e/env/ts/loto_forecast_platform"))
HANDOFF_WT = Path(
    os.environ.get("LOTO_HANDOFF_WT", "/mnt/e/env/ts/worktrees/loto-runtime-handoff")
)
V2 = HANDOFF_WT / "handoff/tools/phase5a_parameter_effectiveness_runner_v2.py"
EXPECTED_V2_BLOB = "a587d04c77631a3dd100209bb15591b75b6c2ec9"
RUN_ID = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
OUT = ROOT / "artifacts" / f"phase5a-v3-generated-{RUN_ID}"
GENERATED = OUT / "phase5a_parameter_effectiveness_runner_v2_crlf.py"

OLD = '''    chk = run(["git", "-C", str(HANDOFF_WT), "diff", "--cached", "--check"], timeout=120)'''
NEW = '''    chk = run(["git", "-c", "core.whitespace=cr-at-eol", "-C", str(HANDOFF_WT), "diff", "--cached", "--check"], timeout=120)'''


def run(cmd: list[str], *, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def git_blob(path: Path) -> str:
    p = run(["git", "-C", str(HANDOFF_WT), "hash-object", str(path)], timeout=60)
    if p.returncode != 0:
        raise RuntimeError(f"HASH_OBJECT_FAILED:{p.stderr.strip()}")
    return p.stdout.strip()


def main() -> int:
    try:
        if not V2.is_file():
            raise RuntimeError(f"PHASE5A_V2_MISSING:{V2}")

        actual_blob = git_blob(V2)
        if actual_blob != EXPECTED_V2_BLOB:
            raise RuntimeError(
                f"PHASE5A_V2_BLOB_MISMATCH:expected={EXPECTED_V2_BLOB}:actual={actual_blob}"
            )

        text = V2.read_text(encoding="utf-8")
        if text.count(OLD) != 1:
            raise RuntimeError(f"PHASE5A_V3_TRANSFORM_TARGET_COUNT:{text.count(OLD)}")
        if NEW in text:
            raise RuntimeError("PHASE5A_V3_TARGET_ALREADY_PATCHED")

        generated = text.replace(OLD, NEW, 1)
        if generated.count(NEW) != 1 or OLD in generated:
            raise RuntimeError("PHASE5A_V3_TRANSFORM_VERIFY_FAILED")

        OUT.mkdir(parents=True, exist_ok=False)
        GENERATED.write_text(generated, encoding="utf-8")

        pyc = run([sys.executable, "-m", "py_compile", str(GENERATED)], timeout=60)
        if pyc.returncode != 0:
            raise RuntimeError(f"PHASE5A_V3_GENERATED_SYNTAX_FAILED:{pyc.stderr.strip()}")

        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        p = subprocess.run(
            [sys.executable, str(GENERATED)],
            env=env,
            text=True,
            timeout=2400,
            check=False,
        )
        if p.returncode != 0:
            raise RuntimeError(f"PHASE5A_V3_GENERATED_RUNNER_FAILED:rc={p.returncode}")

        print("=" * 72)
        print("PHASE5A_V3_CRLF_DIFF_GATE=VERIFIED")
        print(f"PHASE5A_V2_BLOB={actual_blob}")
        print("GIT_WHITESPACE_POLICY=cr-at-eol")
        print(f"GENERATED_RUNNER={GENERATED}")
        print("NEXT=VERIFY_PHASE5A_PUBLISHED_SUMMARY")
        print("=" * 72)
        return 0
    except Exception as exc:
        print("=" * 72)
        print("PHASE5A_V3_CRLF_DIFF_GATE=FAILED")
        print(f"ERROR={type(exc).__name__}:{exc}")
        print("GITHUB_PUBLISH=SKIPPED_FAIL_CLOSED")
        print("=" * 72)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
