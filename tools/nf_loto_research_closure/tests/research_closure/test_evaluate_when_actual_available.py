from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd


def test_waits_when_actual_missing(
    tmp_path: Path,
) -> None:
    lock = tmp_path / "lock.json"
    data = tmp_path / "data.parquet"
    output = tmp_path / "output"
    register = tmp_path / "register.py"

    lock.write_text(
        json.dumps({"target_ds": ("2026-08-03 00:00:00")}),
        encoding="utf-8",
    )

    pd.DataFrame(
        {
            "ds": ["2026-07-31"],
            "y": [8],
        }
    ).to_parquet(data)

    register.write_text(
        "raise RuntimeError('must not run')\n",
        encoding="utf-8",
    )

    script = Path(__file__).parents[2] / "scripts" / "evaluate_when_actual_available.py"

    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--lock",
            str(lock),
            "--data",
            str(data),
            "--output-dir",
            str(output),
            "--register-script",
            str(register),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)

    assert payload["status"] == "WAITING_FOR_ACTUAL"
    assert payload["registered"] is False
