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
SOURCE_WT = Path(
    os.environ.get(
        "LOTO_SOURCE_WT", "/mnt/e/env/ts/worktrees/loto-runtime-audit-20260826-121248"
    )
)

V3 = HANDOFF_WT / "handoff/tools/phase5b_runtime_family_effectiveness_runner_v3.py"
EXPECTED_V3_BLOB = "aae836966df6520b1477c1ef661983beb08bf0b8"
EXPECTED_SOURCE_SHA = "03c366ed929d897e80f6541c26132ba5419f440d"

RUN_ID = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
OUT = ROOT / "artifacts" / f"phase5b-v4-generated-{RUN_ID}"
GENERATED = OUT / "phase5b_runtime_family_effectiveness_runner_v3_fixed.py"

OLD = '''        if generated.count(NEW_EXEC) != 1 or OLD_EXEC in generated:
            raise RuntimeError("PHASE5B_V3_TRANSFORM_VERIFY_FAILED")'''

NEW = '''        if generated.count(NEW_EXEC) != 1:
            raise RuntimeError("PHASE5B_V3_TRANSFORM_VERIFY_FAILED")'''


def run(cmd: list[str], *, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def git_blob(path: Path) -> str:
    p = run(["git", "-C", str(HANDOFF_WT), "hash-object", str(path)], timeout=60)
    if p.returncode != 0:
        raise RuntimeError(f"HASH_OBJECT_FAILED:{p.stderr.strip()}")
    return p.stdout.strip()


def source_head() -> str:
    p = run(["git", "-C", str(SOURCE_WT), "rev-parse", "HEAD"], timeout=60)
    if p.returncode != 0:
        raise RuntimeError(f"SOURCE_HEAD_FAILED:{p.stderr.strip()}")
    return p.stdout.strip()


def main() -> int:
    try:
        if not V3.is_file():
            raise RuntimeError(f"PHASE5B_V3_MISSING:{V3}")

        actual_blob = git_blob(V3)
        if actual_blob != EXPECTED_V3_BLOB:
            raise RuntimeError(
                f"PHASE5B_V3_BLOB_MISMATCH:expected={EXPECTED_V3_BLOB}:actual={actual_blob}"
            )

        actual_source = source_head()
        if actual_source != EXPECTED_SOURCE_SHA:
            raise RuntimeError(
                f"PHASE5B_V4_SOURCE_SHA_MISMATCH:expected={EXPECTED_SOURCE_SHA}:actual={actual_source}"
            )

        text = V3.read_text(encoding="utf-8")
        if text.count(OLD) != 1:
            raise RuntimeError(f"PHASE5B_V4_TRANSFORM_TARGET_COUNT:{text.count(OLD)}")

        generated = text.replace(OLD, NEW, 1)
        if generated.count(NEW) != 1:
            raise RuntimeError("PHASE5B_V4_TRANSFORM_VERIFY_FAILED")
        if OLD in generated:
            raise RuntimeError("PHASE5B_V4_OLD_SELF_CHECK_REMAINS")

        OUT.mkdir(parents=True, exist_ok=False)
        GENERATED.write_text(generated, encoding="utf-8")

        pyc = run([sys.executable, "-m", "py_compile", str(GENERATED)], timeout=60)
        if pyc.returncode != 0:
            raise RuntimeError(f"PHASE5B_V4_GENERATED_SYNTAX_FAILED:{pyc.stderr.strip()}")

        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        executed = subprocess.run(
            [sys.executable, str(GENERATED)],
            env=env,
            text=True,
            timeout=3600,
            check=False,
        )
        if executed.returncode != 0:
            raise RuntimeError(f"PHASE5B_V4_GENERATED_RUNNER_FAILED:rc={executed.returncode}")

        print("=" * 80)
        print("PHASE5B_V4_TRANSFORM_SELF_CHECK_FIX=VERIFIED")
        print(f"PHASE5B_V3_BLOB={actual_blob}")
        print(f"SOURCE_SHA={actual_source}")
        print(f"GENERATED_RUNNER={GENERATED}")
        print("NEXT=VERIFY_PHASE5B_PUBLISHED_SUMMARY")
        print("=" * 80)
        return 0
    except Exception as exc:
        print("=" * 80)
        print("PHASE5B_V4_TRANSFORM_SELF_CHECK_FIX=FAILED")
        print(f"ERROR={type(exc).__name__}:{exc}")
        print("GITHUB_PUBLISH=SKIPPED_FAIL_CLOSED")
        print("=" * 80)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
