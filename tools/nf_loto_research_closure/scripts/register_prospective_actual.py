from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for block in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def atomic_write_text(
    path: Path,
    content: str,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
        text=True,
    )

    temporary = Path(temporary_name)

    try:
        with os.fdopen(
            fd,
            "w",
            encoding="utf-8",
        ) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())

        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def verify_lock_hash(lock_path: Path) -> str:
    sums_path = Path(f"{lock_path}.sha256")

    if not sums_path.is_file():
        raise FileNotFoundError(f"Missing lock checksum: {sums_path}")

    actual_hash = sha256_file(lock_path)
    first_line = sums_path.read_text(encoding="utf-8").splitlines()[0]

    expected_hash = first_line.split()[0]

    if actual_hash != expected_hash:
        raise RuntimeError(f"Lock SHA-256 mismatch: expected={expected_hash}, actual={actual_hash}")

    return actual_hash


def load_lock(
    lock_path: Path,
) -> dict[str, Any]:
    payload = json.loads(lock_path.read_text(encoding="utf-8"))

    if payload.get("schema_version") != "1.1":
        raise ValueError("Only schema 1.1 locks are valid for prospective evaluation")

    if payload.get("status") != ("LOCKED_BEFORE_ACTUAL"):
        raise ValueError("Lock status is not LOCKED_BEFORE_ACTUAL")

    if payload.get("actual") is not None:
        raise ValueError("Lock unexpectedly contains actual")

    models = payload.get("models")

    if not isinstance(models, dict):
        raise ValueError("Lock has no model dictionary")

    if not models:
        raise ValueError("Lock has no model predictions")

    return payload


def calculate_model_metrics(
    models: dict[str, Any],
    actual: int,
) -> list[dict[str, Any]]:
    rows = []

    for model_name, model in sorted(models.items()):
        prediction = int(model["prediction"])

        error = prediction - actual
        absolute_error = abs(error)
        squared_error = error**2

        rows.append(
            {
                "model": model_name,
                "prediction": prediction,
                "actual": actual,
                "error": error,
                "absolute_error": (absolute_error),
                "squared_error": (squared_error),
                "exact": int(absolute_error == 0),
                "hit_at_pm1": int(absolute_error <= 1),
            }
        )

    return rows


def read_registry(
    registry_path: Path,
) -> list[dict[str, str]]:
    if not registry_path.exists():
        return []

    with registry_path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        return list(csv.DictReader(handle))


def write_registry(
    registry_path: Path,
    rows: list[dict[str, Any]],
) -> None:
    fieldnames = [
        "evaluation_id",
        "evaluated_at_utc",
        "lock_file",
        "lock_sha256",
        "target_ds",
        "cutoff_ds",
        "model",
        "prediction",
        "actual",
        "error",
        "absolute_error",
        "squared_error",
        "exact",
        "hit_at_pm1",
    ]

    lines: list[str] = []

    with tempfile.TemporaryFile(
        mode="w+",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
        )
        writer.writeheader()
        writer.writerows(rows)
        handle.seek(0)
        lines = handle.readlines()

    atomic_write_text(
        registry_path,
        "".join(lines),
    )


def build_summary(
    registry_rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
    grouped: dict[
        str,
        list[dict[str, str]],
    ] = {}

    for row in registry_rows:
        grouped.setdefault(
            row["model"],
            [],
        ).append(row)

    summary = []

    for model, rows in sorted(grouped.items()):
        n = len(rows)

        exact_sum = sum(int(row["exact"]) for row in rows)

        hit_sum = sum(int(row["hit_at_pm1"]) for row in rows)

        absolute_error_sum = sum(float(row["absolute_error"]) for row in rows)

        squared_error_sum = sum(float(row["squared_error"]) for row in rows)

        mae = absolute_error_sum / n
        mse = squared_error_sum / n

        summary.append(
            {
                "model": model,
                "prospective_rows": n,
                "exact_rate": exact_sum / n,
                "hit_at_pm1": hit_sum / n,
                "mae": mae,
                "mse": mse,
                "rmse": math.sqrt(mse),
            }
        )

    return summary


def write_summary(
    path: Path,
    rows: list[dict[str, Any]],
) -> None:
    fieldnames = [
        "model",
        "prospective_rows",
        "exact_rate",
        "hit_at_pm1",
        "mae",
        "mse",
        "rmse",
    ]

    with tempfile.TemporaryFile(
        mode="w+",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
        )
        writer.writeheader()
        writer.writerows(rows)
        handle.seek(0)

        atomic_write_text(
            path,
            handle.read(),
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=("Register an actual value for a previously locked prospective prediction.")
    )

    parser.add_argument(
        "--lock",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--actual",
        type=int,
        required=True,
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
    )

    args = parser.parse_args()

    if not 0 <= args.actual <= 9:
        parser.error("--actual must be from 0 to 9")

    lock_path = args.lock.resolve()
    output_dir = args.output_dir.resolve()

    if not lock_path.is_file():
        raise FileNotFoundError(lock_path)

    lock_sha256 = verify_lock_hash(lock_path)

    lock = load_lock(lock_path)

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    registry_path = output_dir / "PROSPECTIVE_EVALUATION_REGISTRY.csv"

    existing_rows = read_registry(registry_path)

    duplicate = any(row["lock_sha256"] == lock_sha256 for row in existing_rows)

    if duplicate:
        raise RuntimeError("This lock has already been evaluated")

    evaluated_at = datetime.now(UTC).isoformat()

    evaluation_id = datetime.now(UTC).strftime("%Y%m%d-%H%M%S") + "-" + lock_sha256[:12]

    model_metrics = calculate_model_metrics(
        lock["models"],
        args.actual,
    )

    result = {
        "schema_version": "1.0",
        "evaluation_id": evaluation_id,
        "evaluated_at_utc": evaluated_at,
        "source_lock": {
            "path": str(lock_path),
            "file": lock_path.name,
            "sha256": lock_sha256,
            "schema_version": (lock["schema_version"]),
            "target_ds": lock["target_ds"],
            "cutoff_ds": lock["cutoff_ds"],
        },
        "actual": args.actual,
        "primary_metric": "Hit@±1",
        "model_metrics": model_metrics,
    }

    result_path = output_dir / f"prospective-evaluation-{evaluation_id}.json"

    atomic_write_text(
        result_path,
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )

    result_sha256 = sha256_file(result_path)

    atomic_write_text(
        Path(f"{result_path}.sha256"),
        (f"{result_sha256}  {result_path.name}\n"),
    )

    new_rows = []

    for row in model_metrics:
        new_rows.append(
            {
                "evaluation_id": evaluation_id,
                "evaluated_at_utc": evaluated_at,
                "lock_file": lock_path.name,
                "lock_sha256": lock_sha256,
                "target_ds": lock["target_ds"],
                "cutoff_ds": lock["cutoff_ds"],
                **row,
            }
        )

    all_rows: list[dict[str, Any]] = [dict(row) for row in existing_rows]

    all_rows.extend(new_rows)

    write_registry(
        registry_path,
        all_rows,
    )

    registry_sha256 = sha256_file(registry_path)

    atomic_write_text(
        Path(f"{registry_path}.sha256"),
        (f"{registry_sha256}  {registry_path.name}\n"),
    )

    normalized_registry_rows = read_registry(registry_path)

    summary_rows = build_summary(normalized_registry_rows)

    summary_path = output_dir / "PROSPECTIVE_CUMULATIVE_METRICS.csv"

    write_summary(
        summary_path,
        summary_rows,
    )

    summary_sha256 = sha256_file(summary_path)

    atomic_write_text(
        Path(f"{summary_path}.sha256"),
        (f"{summary_sha256}  {summary_path.name}\n"),
    )

    print(
        json.dumps(
            {
                "status": "PASS",
                "evaluation_id": evaluation_id,
                "result_file": str(result_path),
                "result_sha256": result_sha256,
                "registry": str(registry_path),
                "summary": str(summary_path),
                "target_ds": lock["target_ds"],
                "actual": args.actual,
                "metrics": model_metrics,
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
