from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for block in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def run_command(
    command: list[str],
) -> tuple[int, str]:
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )

    output = completed.stdout.strip() or completed.stderr.strip()

    return completed.returncode, output


def systemd_property(
    unit: str,
    property_name: str,
) -> str | None:
    code, output = run_command(
        [
            "systemctl",
            "--user",
            "show",
            unit,
            f"--property={property_name}",
            "--value",
        ]
    )

    if code != 0:
        return None

    value = output.strip()

    if not value or value == "n/a":
        return None

    return value


def systemd_state(
    command: str,
    unit: str,
) -> str:
    _, output = run_command(
        [
            "systemctl",
            "--user",
            command,
            unit,
        ]
    )

    return output or "unknown"


def read_lock(
    lock_path: Path,
) -> dict[str, Any]:
    payload = json.loads(lock_path.read_text(encoding="utf-8"))

    return {
        "path": str(lock_path),
        "file": lock_path.name,
        "sha256": sha256_file(lock_path),
        "schema_version": payload.get("schema_version"),
        "status": payload.get("status"),
        "target_ds": payload.get("target_ds"),
        "cutoff_ds": payload.get("cutoff_ds"),
        "actual": payload.get("actual"),
        "predictions": {
            name: model.get("prediction")
            for name, model in payload.get(
                "models",
                {},
            ).items()
        },
    }


def read_data_status(
    data_path: Path,
    target_ds: str,
) -> dict[str, Any]:
    if data_path.suffix.lower() == ".parquet":
        frame = pd.read_parquet(
            data_path,
            columns=["ds", "y"],
        )
    elif data_path.suffix.lower() == ".csv":
        frame = pd.read_csv(
            data_path,
            usecols=["ds", "y"],
        )
    else:
        raise ValueError(f"Unsupported data file: {data_path}")

    frame = frame.copy()

    frame["ds"] = pd.to_datetime(
        frame["ds"],
        errors="raise",
    ).dt.normalize()

    target = pd.Timestamp(target_ds).normalize()

    matches = frame.loc[
        frame["ds"] == target,
        "y",
    ]

    actual_available = len(matches) == 1 and not pd.isna(matches.iloc[0])

    actual = int(matches.iloc[0]) if actual_available else None

    return {
        "path": str(data_path),
        "sha256": sha256_file(data_path),
        "row_count": int(len(frame)),
        "min_ds": str(frame["ds"].min()),
        "max_ds": str(frame["ds"].max()),
        "target_row_count": int(len(matches)),
        "actual_available": (actual_available),
        "actual": actual,
    }


def newest_log(
    log_dir: Path,
) -> dict[str, Any] | None:
    logs = sorted(
        log_dir.glob("check-*.log"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    if not logs:
        return None

    path = logs[0]

    lines = path.read_text(
        encoding="utf-8",
        errors="replace",
    ).splitlines()

    status_lines = [line for line in lines if line.startswith("STATUS=")]

    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "modified_at_utc": datetime.fromtimestamp(
            path.stat().st_mtime,
            tz=UTC,
        ).isoformat(),
        "status": (
            status_lines[-1].split(
                "=",
                1,
            )[1]
            if status_lines
            else None
        ),
        "tail": lines[-20:],
    }


def build_markdown(
    payload: dict[str, Any],
) -> str:
    timer = payload["timer"]
    lock = payload["lock"]
    data = payload["data"]
    evaluation = payload["evaluation"]

    predictions = "\n".join(
        (f"| {name} | {prediction} |") for name, prediction in sorted(lock["predictions"].items())
    )

    if not predictions:
        predictions = "| — | — |"

    return f"""# Numbers3 N1 Prospective Status

- Generated at UTC: `{payload["generated_at_utc"]}`
- Overall status: **{payload["overall_status"]}**
- Recommended action: **{payload["recommended_action"]}**

## Timer

| Item | Value |
|---|---|
| Enabled | `{timer["enabled"]}` |
| Active | `{timer["active"]}` |
| Next trigger | `{timer["next_trigger"]}` |
| Last trigger | `{timer["last_trigger"]}` |
| Service result | `{timer["service_result"]}` |

## Current Lock

| Item | Value |
|---|---|
| File | `{lock["file"]}` |
| SHA-256 | `{lock["sha256"]}` |
| Schema | `{lock["schema_version"]}` |
| Status | `{lock["status"]}` |
| Target | `{lock["target_ds"]}` |
| Cutoff | `{lock["cutoff_ds"]}` |
| Actual in lock | `{lock["actual"]}` |

### Predictions

| Model | Prediction |
|---|---:|
{predictions}

## Data

| Item | Value |
|---|---|
| Rows | `{data["row_count"]}` |
| Minimum date | `{data["min_ds"]}` |
| Maximum date | `{data["max_ds"]}` |
| Target row count | `{data["target_row_count"]}` |
| Actual available | `{data["actual_available"]}` |
| Actual | `{data["actual"]}` |
| SHA-256 | `{data["sha256"]}` |

## Evaluation

| Item | Value |
|---|---|
| Registered | `{evaluation["registered"]}` |
| Completion marker | `{evaluation["completion_marker"]}` |
| Completion hash valid | `{evaluation["completion_hash_valid"]}` |
"""


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--project-root",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
    )

    args = parser.parse_args()

    project_root = args.project_root.resolve()

    output_dir = args.output_dir.resolve()

    lock_link = project_root / "prospective" / "numbers3-n1" / "locks" / "CURRENT.json"

    data_path = project_root / "data" / "exports" / "numbers3" / "numbers3_n1.parquet"

    evaluation_dir = project_root / "prospective" / "numbers3-n1" / "evaluations"

    completion_file = evaluation_dir / "completion" / "CURRENT_ACTUAL_EVALUATION_COMPLETE.json"

    registry_path = evaluation_dir / "PROSPECTIVE_EVALUATION_REGISTRY.csv"

    log_dir = project_root / "logs" / "prospective-actual-watch"

    if not lock_link.exists():
        raise FileNotFoundError(lock_link)

    if not data_path.exists():
        raise FileNotFoundError(data_path)

    lock_path = lock_link.resolve()
    lock = read_lock(lock_path)

    data = read_data_status(
        data_path,
        lock["target_ds"],
    )

    completion_hash_valid = False

    completion_hash_path = Path(f"{completion_file}.sha256")

    if completion_file.is_file() and completion_hash_path.is_file():
        expected = completion_hash_path.read_text(encoding="utf-8").splitlines()[0].split()[0]

        completion_hash_valid = expected == sha256_file(completion_file)

    registered = registry_path.is_file()

    timer_unit = "loto-numbers3-n1-actual-check.timer"

    service_unit = "loto-numbers3-n1-actual-check.service"

    timer = {
        "enabled": systemd_state(
            "is-enabled",
            timer_unit,
        ),
        "active": systemd_state(
            "is-active",
            timer_unit,
        ),
        "next_trigger": systemd_property(
            timer_unit,
            "NextElapseUSecRealtime",
        ),
        "last_trigger": systemd_property(
            timer_unit,
            "LastTriggerUSec",
        ),
        "service_result": systemd_property(
            service_unit,
            "Result",
        ),
    }

    if registered and completion_hash_valid:
        overall_status = "COMPLETED"
        recommended_action = "NO_ACTION_REQUIRED"
    elif data["actual_available"]:
        overall_status = "ACTUAL_AVAILABLE_NOT_REGISTERED"
        recommended_action = "RUN_MONITOR_SERVICE_NOW"
    elif timer["enabled"] == "enabled" and timer["active"] == "active":
        overall_status = "WAITING_WITH_ACTIVE_MONITOR"
        recommended_action = "CONTINUE_MONITORING"
    else:
        overall_status = "WAITING_WITHOUT_ACTIVE_MONITOR"
        recommended_action = "ENABLE_AND_START_TIMER"

    payload = {
        "schema_version": "1.0",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "overall_status": overall_status,
        "recommended_action": (recommended_action),
        "timer": timer,
        "lock": lock,
        "data": data,
        "evaluation": {
            "registered": registered,
            "registry_path": str(registry_path),
            "completion_marker": (completion_file.is_file()),
            "completion_marker_path": str(completion_file),
            "completion_hash_valid": (completion_hash_valid),
        },
        "latest_log": newest_log(log_dir),
    }

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    json_path = output_dir / "CURRENT_PROSPECTIVE_STATUS.json"

    markdown_path = output_dir / "CURRENT_PROSPECTIVE_STATUS.md"

    json_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    markdown_path.write_text(
        build_markdown(payload),
        encoding="utf-8",
    )

    for path in [
        json_path,
        markdown_path,
    ]:
        Path(f"{path}.sha256").write_text(
            (f"{sha256_file(path)}  {path.name}\n"),
            encoding="utf-8",
        )

    print(
        json.dumps(
            {
                "status": "PASS",
                "overall_status": (overall_status),
                "recommended_action": (recommended_action),
                "json": str(json_path),
                "markdown": str(markdown_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
