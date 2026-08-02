from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd
import psycopg


@dataclass(frozen=True)
class SyncResult:
    status: str
    source_rows: int
    output_rows: int
    min_ds: str
    max_ds: str
    duplicate_ds: int
    null_ds: int
    null_y: int
    changed: bool
    output_sha256: str
    target_path: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def load_numbers3_n1(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
) -> pd.DataFrame:
    query = """
        SELECT
            ds,
            y
        FROM dataset.loto_y_ts
        WHERE loto = 'numbers3'
          AND unique_id = 'N1'
          AND ts_type = 'raw'
        ORDER BY ds
    """

    with psycopg.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        dbname=database,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

    return pd.DataFrame(
        rows,
        columns=["ds", "y"],
    )


def validate(frame: pd.DataFrame) -> None:
    required = {"ds", "y"}

    if set(frame.columns) != required:
        raise ValueError(f"Unexpected columns: {frame.columns.tolist()}")

    if frame.empty:
        raise ValueError("Numbers3 N1 dataset is empty")

    frame["ds"] = pd.to_datetime(
        frame["ds"],
        errors="raise",
    )

    frame["y"] = pd.to_numeric(
        frame["y"],
        errors="raise",
    )

    non_integer = frame["y"].notna() & (frame["y"] % 1 != 0)

    if non_integer.any():
        invalid = frame.loc[
            non_integer,
            "y",
        ].tolist()

        raise ValueError(f"Non-integer Numbers3 N1 values detected: {invalid[:20]}")

    if frame["ds"].isna().any():
        raise ValueError("Null ds detected")

    if frame["y"].isna().any():
        raise ValueError("Null y detected")

    if frame["ds"].duplicated().any():
        duplicates = (
            frame.loc[
                frame["ds"].duplicated(keep=False),
                "ds",
            ]
            .astype(str)
            .tolist()
        )

        raise ValueError(f"Duplicate ds detected: {duplicates[:20]}")

    if not frame["ds"].is_monotonic_increasing:
        raise ValueError("ds is not monotonically increasing")

    if not frame["y"].between(0, 9).all():
        invalid = frame.loc[
            ~frame["y"].between(0, 9),
            "y",
        ].tolist()

        raise ValueError(f"Numbers3 N1 value outside 0..9: {invalid[:20]}")

    if len(frame) < 7000:
        raise ValueError(f"Unexpectedly small row count: {len(frame)}")


def atomic_write_parquet(
    frame: pd.DataFrame,
    target: Path,
) -> tuple[bool, str]:
    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    before_hash = sha256_file(target) if target.is_file() else None

    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
    )

    os.close(fd)
    temporary = Path(temporary_name)

    try:
        frame.to_parquet(
            temporary,
            index=False,
        )

        verification = pd.read_parquet(
            temporary,
            columns=["ds", "y"],
        )

        validate(verification)

        after_hash = sha256_file(temporary)

        if target.is_file():
            current = pd.read_parquet(
                target,
                columns=["ds", "y"],
            )

            validate(current)

            current = current.loc[:, ["ds", "y"]].copy()
            current["ds"] = pd.to_datetime(current["ds"])
            current["y"] = pd.to_numeric(
                current["y"],
                errors="raise",
            ).astype(int)

            candidate = verification.loc[:, ["ds", "y"]].copy()
            candidate["ds"] = pd.to_datetime(candidate["ds"])
            candidate["y"] = pd.to_numeric(
                candidate["y"],
                errors="raise",
            ).astype(int)

            current.sort_values(
                "ds",
                inplace=True,
            )
            candidate.sort_values(
                "ds",
                inplace=True,
            )

            current.reset_index(
                drop=True,
                inplace=True,
            )
            candidate.reset_index(
                drop=True,
                inplace=True,
            )

            if current.equals(candidate):
                return False, before_hash or after_hash

        os.replace(
            temporary,
            target,
        )

        return True, after_hash

    finally:
        temporary.unlink(
            missing_ok=True,
        )


def run(
    *,
    target: Path,
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
) -> SyncResult:
    frame = load_numbers3_n1(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
    )

    validate(frame)

    frame = frame.loc[:, ["ds", "y"]].copy()
    frame["ds"] = pd.to_datetime(frame["ds"])
    frame["y"] = frame["y"].astype(int)

    changed, output_hash = atomic_write_parquet(
        frame,
        target,
    )

    return SyncResult(
        status="PASS",
        source_rows=len(frame),
        output_rows=len(frame),
        min_ds=str(frame["ds"].min()),
        max_ds=str(frame["ds"].max()),
        duplicate_ds=int(
            frame["ds"]
            .duplicated(
                keep=False,
            )
            .sum()
        ),
        null_ds=int(frame["ds"].isna().sum()),
        null_y=int(frame["y"].isna().sum()),
        changed=changed,
        output_sha256=output_hash,
        target_path=str(target),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--target",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--host",
        default=os.getenv(
            "PGHOST",
            "127.0.0.1",
        ),
    )

    parser.add_argument(
        "--port",
        type=int,
        default=int(
            os.getenv(
                "PGPORT",
                "5432",
            )
        ),
    )

    parser.add_argument(
        "--user",
        default=os.getenv(
            "PGUSER",
            "loto",
        ),
    )

    parser.add_argument(
        "--password",
        default=os.getenv(
            "PGPASSWORD",
            "",
        ),
    )

    parser.add_argument(
        "--database",
        default=os.getenv(
            "PGDATABASE",
            "loto",
        ),
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    result = run(
        target=args.target,
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.database,
    )

    print(
        json.dumps(
            asdict(result),
            ensure_ascii=False,
            indent=2,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
