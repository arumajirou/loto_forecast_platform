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
V1 = HANDOFF_WT / "handoff/tools/phase5b_runtime_family_effectiveness_runner.py"
EXPECTED_V1_BLOB = "98f861a15fb5ef34f33bc53be4cea66c07cbc3ce"
RUN_ID = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
OUT = ROOT / "artifacts" / f"phase5b-v2-generated-{RUN_ID}"
GENERATED = OUT / "phase5b_runtime_family_effectiveness_runner_fixed.py"

OLD = '''    script.write_text(
        """from pathlib import Path\\n"
        "import sys\\n"
        "from loto.parameter_effectiveness.contracts import ParameterSuiteSpec\\n"
        "from loto.parameter_effectiveness.core import AdapterRegistry, run_suite\\n"
        "from loto.parameter_effectiveness.toto2_adapter import Toto2MinimalParameterAdapter\\n"
        "spec = ParameterSuiteSpec.model_validate_json(Path(sys.argv[1]).read_text(encoding='utf-8'))\\n"
        "registry = AdapterRegistry()\\n"
        "registry.register(Toto2MinimalParameterAdapter(), 'toto')\\n"
        "results = run_suite(spec, registry, Path(sys.argv[2]))\\n"
        "print([item.model_dump(mode='json') for item in results])\\n"
        "raise SystemExit(0 if all(item.outcome.value == 'effective' for item in results) else 2)\\n"
        """,
        encoding="utf-8",
    )'''

NEW = '''    script.write_text(
        "\\n".join(
            [
                "from pathlib import Path",
                "import sys",
                "from loto.parameter_effectiveness.contracts import ParameterSuiteSpec",
                "from loto.parameter_effectiveness.core import AdapterRegistry, run_suite",
                "from loto.parameter_effectiveness.toto2_adapter import Toto2MinimalParameterAdapter",
                "spec = ParameterSuiteSpec.model_validate_json(Path(sys.argv[1]).read_text(encoding='utf-8'))",
                "registry = AdapterRegistry()",
                "registry.register(Toto2MinimalParameterAdapter(), 'toto')",
                "results = run_suite(spec, registry, Path(sys.argv[2]))",
                "print([item.model_dump(mode='json') for item in results])",
                "raise SystemExit(0 if all(item.outcome.value == 'effective' for item in results) else 2)",
            ]
        )
        + "\\n",
        encoding="utf-8",
    )'''


def run(cmd: list[str], *, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def git_blob(path: Path) -> str:
    p = run(["git", "-C", str(HANDOFF_WT), "hash-object", str(path)], timeout=60)
    if p.returncode != 0:
        raise RuntimeError(f"HASH_OBJECT_FAILED:{p.stderr.strip()}")
    return p.stdout.strip()


def main() -> int:
    try:
        if not V1.is_file():
            raise RuntimeError(f"PHASE5B_V1_MISSING:{V1}")
        actual_blob = git_blob(V1)
        if actual_blob != EXPECTED_V1_BLOB:
            raise RuntimeError(
                f"PHASE5B_V1_BLOB_MISMATCH:expected={EXPECTED_V1_BLOB}:actual={actual_blob}"
            )

        text = V1.read_text(encoding="utf-8")
        if text.count(OLD) != 1:
            raise RuntimeError(f"PHASE5B_V2_TRANSFORM_TARGET_COUNT:{text.count(OLD)}")
        if NEW in text:
            raise RuntimeError("PHASE5B_V2_TARGET_ALREADY_PATCHED")

        generated = text.replace(OLD, NEW, 1)
        if generated.count(NEW) != 1 or OLD in generated:
            raise RuntimeError("PHASE5B_V2_TRANSFORM_VERIFY_FAILED")

        OUT.mkdir(parents=True, exist_ok=False)
        GENERATED.write_text(generated, encoding="utf-8")

        pyc = run([sys.executable, "-m", "py_compile", str(GENERATED)], timeout=60)
        if pyc.returncode != 0:
            raise RuntimeError(f"PHASE5B_V2_GENERATED_SYNTAX_FAILED:{pyc.stderr.strip()}")

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
            raise RuntimeError(
                f"PHASE5B_V2_GENERATED_RUNNER_FAILED:rc={executed.returncode}"
            )

        print("=" * 80)
        print("PHASE5B_V2_TOTO_GENERATED_RUNNER_FIX=VERIFIED")
        print(f"PHASE5B_V1_BLOB={actual_blob}")
        print(f"GENERATED_RUNNER={GENERATED}")
        print("NEXT=VERIFY_PHASE5B_PUBLISHED_SUMMARY")
        print("=" * 80)
        return 0
    except Exception as exc:
        print("=" * 80)
        print("PHASE5B_V2_TOTO_GENERATED_RUNNER_FIX=FAILED")
        print(f"ERROR={type(exc).__name__}:{exc}")
        print("GITHUB_PUBLISH=SKIPPED_FAIL_CLOSED")
        print("=" * 80)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
