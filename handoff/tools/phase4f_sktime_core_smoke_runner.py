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
TEMPLATE = HANDOFF_WT / "handoff/tools/phase4e_sktime_classic_smoke_runner.py"
EXPECTED_TEMPLATE_BLOB = "ceddabed1639be11434fec6419488aa20aa2b981"
GENERATED = Path(f"/tmp/loto-phase4f-sktime-core-generated-{os.getpid()}.py")
PYCACHE = Path(f"/tmp/loto-phase4f-pycache-{os.getpid()}")


def fail(message: str, rc: int = 2) -> int:
    print("=" * 60)
    print("PHASE4F_SKTIME_CORE_LAUNCHER=FAILED")
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


def replace_required(text: str, old: str, new: str) -> str:
    if old not in text:
        raise RuntimeError(f"TEMPLATE_TOKEN_MISSING:{old}")
    return text.replace(old, new)


def generate() -> str:
    if not TEMPLATE.is_file():
        raise RuntimeError(f"PHASE4E_TEMPLATE_MISSING:{TEMPLATE}")
    observed_blob = git_blob(TEMPLATE)
    if observed_blob != EXPECTED_TEMPLATE_BLOB:
        raise RuntimeError(
            "PHASE4E_TEMPLATE_BLOB_MISMATCH:"
            f"expected={EXPECTED_TEMPLATE_BLOB}:actual={observed_blob}"
        )

    text = TEMPLATE.read_text(encoding="utf-8")

    # Convert the already-verified Phase 4E lifecycle harness into the Phase 4F
    # sktime core Python 3.13 lane while preserving all fail-closed evidence gates.
    replacements = (
        ("PHASE4E", "PHASE4F"),
        ("phase4e", "phase4f"),
        ("sktime-classic-py312", "sktime-core-py313"),
        ("sktime-classic", "sktime-core"),
        ("sktime classic", "sktime core"),
        ("SKTIME_CLASSIC", "SKTIME_CORE"),
        ("PY312", "PY313"),
        ("Python 3.12", "Python 3.13"),
        (">=3.12,<3.13", ">=3.13,<3.14"),
        ('EXPECTED_PYTHON_PREFIX = "3.12."', 'EXPECTED_PYTHON_PREFIX = "3.13."'),
        ('MODEL_STRATEGY = "drift"', 'MODEL_STRATEGY = "last"'),
        ('strategy="drift"', 'strategy="last"'),
        ('"strategy": "drift"', '"strategy": "last"'),
        ("classic CPU", "core CPU"),
        ("classic-runtime", "core-runtime"),
    )
    for old, new in replacements:
        text = replace_required(text, old, new)

    # Phase 4F must depend on the just-published Phase 4E evidence, not Phase 4D.
    prerequisite_replacements = (
        ('phase4d_path = HANDOFF / "phase4d/summary.json"', 'phase4e_path = HANDOFF / "phase4e/summary.json"'),
        ('if not phase4d_path.exists():', 'if not phase4e_path.exists():'),
        ('phase4d = json.loads(phase4d_path.read_text("utf-8"))', 'phase4e = json.loads(phase4e_path.read_text("utf-8"))'),
        ('if phase4d.get("status") != "VERIFIED":', 'if phase4e.get("status") != "VERIFIED":'),
        ('PHASE4D_SUMMARY_MISSING', 'PHASE4E_SUMMARY_MISSING'),
        ('PHASE4D_NOT_VERIFIED', 'PHASE4E_NOT_VERIFIED'),
    )
    for old, new in prerequisite_replacements:
        text = replace_required(text, old, new)

    text = replace_required(
        text,
        '"phase4f_sktime_classic_verified_phase4f_next"',
        '"phase4f_sktime_core_verified_phase4g_next"',
    )
    text = replace_required(
        text,
        'Continue with `environments/sktime-core-py313`, then `environments/statsforecast-py313`, and finally `environments/toto2-4m-py312` from the Phase 4 ready queue.',
        'Continue with `environments/statsforecast-py313`, then `environments/toto2-4m-py312` from the Phase 4 ready queue.',
    )

    transformed_status_line = '- Phase 4F sktime core Python 3.13 CPU lifecycle: `VERIFIED`'
    if transformed_status_line not in text:
        raise RuntimeError("PHASE4F_CURRENT_STATUS_LINE_MISSING_AFTER_TRANSFORM")
    text = text.replace(
        f'                "{transformed_status_line}",',
        '                "- Phase 4E sktime classic Python 3.12 CPU lifecycle: `VERIFIED`",\n'
        f'                "{transformed_status_line}",',
        1,
    )

    required_final_tokens = (
        'ENV_NAME = "environments/sktime-core-py313"',
        'EXPECTED_PYTHON_PREFIX = "3.13."',
        'MODEL_STRATEGY = "last"',
        'phase4e_path = HANDOFF / "phase4e/summary.json"',
        'HANDOFF_OUT = HANDOFF / "phase4f"',
        '"phase4f_sktime_core_verified_phase4g_next"',
        '- Phase 4E sktime classic Python 3.12 CPU lifecycle: `VERIFIED`',
        '- Phase 4F sktime core Python 3.13 CPU lifecycle: `VERIFIED`',
        'Continue with `environments/statsforecast-py313`, then `environments/toto2-4m-py312` from the Phase 4 ready queue.',
    )
    missing = [token for token in required_final_tokens if token not in text]
    if missing:
        raise RuntimeError(f"PHASE4F_TRANSFORM_INCOMPLETE:{missing}")

    forbidden = (
        'ENV_NAME = "environments/sktime-classic-py312"',
        'MODEL_STRATEGY = "drift"',
        'strategy="drift"',
        '"strategy": "drift"',
        'phase4d_path = HANDOFF / "phase4d/summary.json"',
        '"phase4f_sktime_classic_verified_phase4f_next"',
    )
    leaked = [token for token in forbidden if token in text]
    if leaked:
        raise RuntimeError(f"PHASE4F_TRANSFORM_OLD_TOKEN_LEAK:{leaked}")

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
            return fail("GENERATED_PHASE4F_PY_COMPILE_FAILED", compile_proc.returncode or 2)
        print("PHASE4F_GENERATED_RUNNER_SYNTAX=PASS")
        print(f"PHASE4F_TEMPLATE_BLOB={EXPECTED_TEMPLATE_BLOB}")
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
