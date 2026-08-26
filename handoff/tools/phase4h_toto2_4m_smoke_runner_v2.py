#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

HANDOFF_WT = Path(
    os.environ.get(
        "LOTO_HANDOFF_WT",
        "/mnt/e/env/ts/worktrees/loto-runtime-handoff",
    )
)
TEMPLATE = HANDOFF_WT / "handoff/tools/phase4h_toto2_4m_smoke_runner.py"
EXPECTED_TEMPLATE_BLOB = "128c5c9c600fd4b61c0d147dd46f2d51230a38ff"
GENERATED = Path(f"/tmp/loto-phase4h-toto2-generated-{os.getpid()}.py")
PYCACHE = Path(f"/tmp/loto-phase4h-toto2-pycache-{os.getpid()}")


def fail(message: str, rc: int = 2) -> int:
    print("=" * 60)
    print("PHASE4H_TOTO2_4M_LAUNCHER=FAILED")
    print(f"ERROR={message}")
    print("GITHUB_PUBLISH=SKIPPED_FAIL_CLOSED")
    print("=" * 60)
    return rc


def git_blob(path: Path) -> str:
    proc = subprocess.run(
        ["git", "-C", str(HANDOFF_WT), "hash-object", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"GIT_HASH_OBJECT_FAILED:{proc.stderr.strip()}")
    return proc.stdout.strip()


def replace_once(text: str, old: str, new: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"EXPECTED_EXACTLY_ONE_TOKEN:count={count}:token={old}")
    return text.replace(old, new, 1)


def generate() -> str:
    if not TEMPLATE.is_file():
        raise RuntimeError(f"PHASE4H_TEMPLATE_MISSING:{TEMPLATE}")
    observed_blob = git_blob(TEMPLATE)
    if observed_blob != EXPECTED_TEMPLATE_BLOB:
        raise RuntimeError(
            "PHASE4H_TEMPLATE_BLOB_MISMATCH:"
            f"expected={EXPECTED_TEMPLATE_BLOB}:actual={observed_blob}"
        )

    text = TEMPLATE.read_text(encoding="utf-8")
    text = replace_once(
        text,
        'proc = run([str(RUNTIME), "-I", "-c", code], timeout=120, env=offline_env())',
        'proc = run([str(RUNTIME), "-c", code], timeout=120, env=offline_env())',
    )
    text = replace_once(
        text,
        '[str(RUNTIME), "-I", "-c", code, str(candidate)],',
        '[str(RUNTIME), "-c", code, str(candidate)],',
    )

    required = (
        'PYTHONPATH": str(SOURCE_WT / "src")',
        'proc = run([str(RUNTIME), "-c", code], timeout=120, env=offline_env())',
        '[str(RUNTIME), "-c", code, str(candidate)],',
        'PHASE4H_TOTO2_4M_SMOKE=VERIFIED',
        'TOTO2_LIFECYCLE_VALIDATION_FAILED',
        'gpu_execution_claimed": True',
        'cpu_fallback": False',
    )
    missing = [token for token in required if token not in text]
    if missing:
        raise RuntimeError(f"PHASE4H_TRANSFORM_INCOMPLETE:{missing}")

    forbidden = (
        'proc = run([str(RUNTIME), "-I", "-c", code], timeout=120, env=offline_env())',
        '[str(RUNTIME), "-I", "-c", code, str(candidate)],',
    )
    leaked = [token for token in forbidden if token in text]
    if leaked:
        raise RuntimeError(f"PHASE4H_OLD_ISOLATED_MODE_TOKEN_LEAK:{leaked}")
    return text


def main() -> int:
    try:
        generated = generate()
        GENERATED.write_text(generated, encoding="utf-8")
        env = os.environ.copy()
        env.update(
            {
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONPYCACHEPREFIX": str(PYCACHE),
            }
        )
        compile_proc = subprocess.run(
            [sys.executable, "-m", "py_compile", str(GENERATED)],
            env=env,
            check=False,
        )
        if compile_proc.returncode != 0:
            return fail("GENERATED_PHASE4H_PY_COMPILE_FAILED", compile_proc.returncode or 2)
        print("PHASE4H_GENERATED_RUNNER_SYNTAX=PASS")
        print(f"PHASE4H_TEMPLATE_BLOB={EXPECTED_TEMPLATE_BLOB}")
        proc = subprocess.run([sys.executable, str(GENERATED)], env=env, check=False)
        return proc.returncode
    except Exception as exc:
        return fail(f"{type(exc).__name__}:{exc}")
    finally:
        try:
            GENERATED.unlink(missing_ok=True)
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
