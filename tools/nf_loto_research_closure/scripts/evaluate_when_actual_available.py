from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd


def load_actual(
    data_path: Path,
    target_ds: pd.Timestamp,
) -> int | None:
    if data_path.suffix.lower() == ".parquet":
        frame = pd.read_parquet(data_path)
    elif data_path.suffix.lower() == ".csv":
        frame = pd.read_csv(data_path)
    else:
        raise ValueError(f"Unsupported data format: {data_path.suffix}")

    required = {"ds", "y"}
    missing = required - set(frame.columns)

    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")

    frame = frame.loc[:, ["ds", "y"]].copy()
    frame["ds"] = pd.to_datetime(
        frame["ds"],
        errors="raise",
    ).dt.normalize()

    matches = frame.loc[frame["ds"] == target_ds.normalize()]

    if matches.empty:
        return None

    if len(matches) != 1:
        raise RuntimeError(
            f"Target date must have exactly one row: target={target_ds.date()}, rows={len(matches)}"
        )

    value = matches.iloc[0]["y"]

    if pd.isna(value):
        return None

    actual = int(value)

    if float(value) != float(actual):
        raise ValueError(f"Actual is not an integer: {value}")

    if not 0 <= actual <= 9:
        raise ValueError(f"Actual is outside 0..9: {actual}")

    return actual


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--lock",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--data",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--register-script",
        type=Path,
        required=True,
    )

    args = parser.parse_args()

    lock_path = args.lock.resolve()
    data_path = args.data.resolve()

    lock = json.loads(lock_path.read_text(encoding="utf-8"))

    target_ds = pd.Timestamp(lock["target_ds"])

    actual = load_actual(
        data_path,
        target_ds,
    )

    if actual is None:
        print(
            json.dumps(
                {
                    "status": ("WAITING_FOR_ACTUAL"),
                    "target_ds": str(target_ds),
                    "data": str(data_path),
                    "registered": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    command = [
        sys.executable,
        str(args.register_script.resolve()),
        "--lock",
        str(lock_path),
        "--actual",
        str(actual),
        "--output-dir",
        str(args.output_dir.resolve()),
    ]

    completed = subprocess.run(
        command,
        check=False,
        text=True,
        capture_output=True,
    )

    if completed.returncode != 0:
        combined = completed.stdout + "\n" + completed.stderr

        if "already been evaluated" in combined:
            print(
                json.dumps(
                    {
                        "status": ("ALREADY_REGISTERED"),
                        "target_ds": str(target_ds),
                        "actual": actual,
                        "registered": False,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        print(
            completed.stdout,
            end="",
        )
        print(
            completed.stderr,
            file=sys.stderr,
            end="",
        )
        return completed.returncode

    print(
        completed.stdout,
        end="",
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
