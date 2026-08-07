from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path.cwd()
STAMP = datetime.now().strftime("%Y%m%d-%H%M%S")

output = ROOT / "artifacts" / "environment_recovery" / f"main-recovered-{STAMP}"

output.mkdir(
    parents=True,
    exist_ok=True,
)


def run(
    name: str,
    command: list[str],
) -> int:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )

    (output / f"{name}.txt").write_text(
        completed.stdout,
        encoding="utf-8",
    )

    return completed.returncode


for filename in (
    "pyproject.toml",
    "uv.lock",
):
    shutil.copy2(
        ROOT / filename,
        output / filename,
    )


codes = {
    "uv_tree": run(
        "uv-tree",
        ["uv", "tree"],
    ),
    "package_list": run(
        "package-list",
        ["uv", "pip", "list"],
    ),
    "runtime": run(
        "runtime",
        [
            "uv",
            "run",
            "--frozen",
            "python",
            "-c",
            (
                "import sys, torch, neuralforecast;"
                "print('python=', sys.executable);"
                "print('torch=', torch.__version__);"
                "print('cuda=', torch.cuda.is_available());"
                "print('neuralforecast=', "
                "neuralforecast.__version__);"
                "assert torch.cuda.is_available();"
                "x=torch.ones(2, device='cuda');"
                "print('cuda_sum=', x.sum().item())"
            ),
        ],
    ),
    "selected_tests": run(
        "selected-tests",
        [
            "uv",
            "run",
            "--frozen",
            "python",
            "-m",
            "pytest",
            "-q",
            "-rs",
            "tests/test_nf_search_space_builder.py",
            "tests/test_experiment_feature_allowlist.py",
            "tests/test_feature_target_leakage.py",
        ],
    ),
    "model_smoke": run(
        "model-instantiation-smoke",
        [
            "uv",
            "run",
            "--frozen",
            "python",
            "scripts/experiments/smoke_instantiate_nf_models.py",
        ],
    ),
    "nvidia_smi": run(
        "nvidia-smi",
        ["nvidia-smi"],
    ),
}


required_success = {
    "uv_tree",
    "package_list",
    "runtime",
    "selected_tests",
    "model_smoke",
    "nvidia_smi",
}

failed = {name: code for name, code in codes.items() if (name in required_success and code != 0)}

status = "PASS" if not failed else "FAIL"

selected_tests_text = (output / "selected-tests.txt").read_text(encoding="utf-8")

database_test_status = (
    "SKIPPED_NOT_CONFIGURED"
    if (
        "skipped" in selected_tests_text.lower()
        and (
            "Database integration environment" in selected_tests_text
            or "1 skipped" in selected_tests_text
        )
    )
    else ("EXECUTED_PASS" if codes["selected_tests"] == 0 else "FAILED")
)

report = {
    "status": status,
    "output": str(output),
    "exit_codes": codes,
    "failed": failed,
    "database_integration_test": (database_test_status),
}

(output / "recovery-status.json").write_text(
    json.dumps(
        report,
        indent=2,
        ensure_ascii=False,
    )
    + "\n",
    encoding="utf-8",
)

print(
    json.dumps(
        report,
        indent=2,
        ensure_ascii=False,
    )
)

if failed:
    raise SystemExit(1)

print("MAIN_ENVIRONMENT_RECOVERY_EVIDENCE=PASS")
