from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def create_lock(
    directory: Path,
) -> Path:
    lock = {
        "schema_version": "1.1",
        "status": "LOCKED_BEFORE_ACTUAL",
        "actual": None,
        "target_ds": "2026-08-03 00:00:00",
        "cutoff_ds": "2026-07-31 00:00:00",
        "models": {
            "constant": {
                "prediction": 8,
            },
            "tree": {
                "prediction": 1,
            },
        },
    }

    path = directory / "lock.json"

    path.write_text(
        json.dumps(lock),
        encoding="utf-8",
    )

    Path(f"{path}.sha256").write_text(
        f"{sha256_file(path)}  {path.name}\n",
        encoding="utf-8",
    )

    return path


def test_register_actual(
    tmp_path: Path,
) -> None:
    lock = create_lock(tmp_path)
    output = tmp_path / "results"

    script = Path(__file__).parents[2] / "scripts" / "register_prospective_actual.py"

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--lock",
            str(lock),
            "--actual",
            "2",
            "--output-dir",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)

    assert payload["status"] == "PASS"

    metrics = {row["model"]: row for row in payload["metrics"]}

    assert metrics["tree"]["hit_at_pm1"] == 1
    assert metrics["tree"]["absolute_error"] == 1
    assert metrics["constant"]["hit_at_pm1"] == 0
    assert metrics["constant"]["squared_error"] == 36

    assert (output / "PROSPECTIVE_EVALUATION_REGISTRY.csv").is_file()

    assert (output / "PROSPECTIVE_CUMULATIVE_METRICS.csv").is_file()


def test_duplicate_rejected(
    tmp_path: Path,
) -> None:
    lock = create_lock(tmp_path)
    output = tmp_path / "results"

    script = Path(__file__).parents[2] / "scripts" / "register_prospective_actual.py"

    command = [
        sys.executable,
        str(script),
        "--lock",
        str(lock),
        "--actual",
        "2",
        "--output-dir",
        str(output),
    ]

    subprocess.run(
        command,
        check=True,
    )

    duplicate = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )

    assert duplicate.returncode != 0
    assert "already been evaluated" in duplicate.stderr
