from __future__ import annotations

import hashlib
import json
import math
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

FORMAL_GAMES = ("numbers3", "numbers4", "miniloto", "loto6", "loto7")
MIN_HISTORY_ROWS = 512
SOURCE_SCHEMA = "dataset"
SOURCE_TABLE = "loto_y_ts_unified"
SOURCE_TS_TYPE = "raw"

_GAME_SPECS: dict[str, tuple[int, int, int, bool]] = {
    "numbers3": (3, 0, 9, False),
    "numbers4": (4, 0, 9, False),
    "miniloto": (5, 1, 31, True),
    "loto6": (6, 1, 43, True),
    "loto7": (7, 1, 37, True),
}
_POSITION_RE = re.compile(r"(?:^|::)n([1-9][0-9]*)$", re.IGNORECASE)


@dataclass(frozen=True)
class GameExport:
    game_id: str
    json_payload: dict[str, Any]
    audit_frame: pd.DataFrame
    statistics: dict[str, Any]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_bytes(path, canonical_json_bytes(payload))


def position_number(unique_id: str) -> int:
    match = _POSITION_RE.search(unique_id.strip())
    if match is None:
        raise ValueError(f"unsupported unique_id format: {unique_id!r}")
    return int(match.group(1))


def _required_columns(frame: pd.DataFrame) -> None:
    required = {"game_id", "ds", "unique_id", "y"}
    missing = sorted(required - set(frame.columns))
    extra = sorted(set(frame.columns) - required)
    if missing:
        raise ValueError(f"source frame is missing columns: {missing}")
    if extra:
        raise ValueError(f"source frame contains unexpected columns: {extra}")


def _integer_values(series: pd.Series, *, game_id: str) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.isna().any():
        raise ValueError(f"{game_id} contains null or non-numeric y values")
    values = numeric.to_numpy(dtype=float)
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError(f"{game_id} contains non-finite y values")
    rounded = numeric.round()
    if not (numeric == rounded).all():
        raise ValueError(f"{game_id} contains non-integer y values")
    return rounded.astype("int64")


def build_game_export(game_id: str, source: pd.DataFrame) -> GameExport:
    if game_id not in _GAME_SPECS:
        raise ValueError(f"unsupported game: {game_id}")
    _required_columns(source)
    position_count, candidate_min, candidate_max, strictly_increasing = _GAME_SPECS[game_id]

    frame = source.copy()
    frame["game_id"] = frame["game_id"].astype(str).str.lower()
    if set(frame["game_id"].unique()) != {game_id}:
        raise ValueError(f"source frame does not contain only {game_id}")
    parsed_ds = pd.to_datetime(frame["ds"], errors="coerce", utc=True)
    if parsed_ds.isna().any():
        raise ValueError(f"{game_id} contains invalid ds values")
    frame["ds"] = parsed_ds.dt.strftime("%Y-%m-%d")
    frame["unique_id"] = frame["unique_id"].astype(str)
    frame["position_no"] = frame["unique_id"].map(position_number)
    frame["y"] = _integer_values(frame["y"], game_id=game_id)

    expected_positions = set(range(1, position_count + 1))
    actual_positions = set(int(value) for value in frame["position_no"].unique())
    if actual_positions != expected_positions:
        raise ValueError(
            f"{game_id} position set mismatch: expected={sorted(expected_positions)} "
            f"actual={sorted(actual_positions)}"
        )
    duplicate_mask = frame.duplicated(subset=["ds", "position_no"], keep=False)
    if duplicate_mask.any():
        raise ValueError(f"{game_id} contains duplicate ds/position rows")

    counts = frame.groupby("ds", sort=True)["position_no"].nunique()
    incomplete = counts[counts != position_count]
    if not incomplete.empty:
        raise ValueError(f"{game_id} contains incomplete draws: {len(incomplete)}")

    if (frame["y"] < candidate_min).any() or (frame["y"] > candidate_max).any():
        raise ValueError(f"{game_id} contains y outside [{candidate_min}, {candidate_max}]")

    pivot = frame.pivot(index="ds", columns="position_no", values="y").sort_index()
    pivot = pivot.reindex(columns=range(1, position_count + 1))
    if pivot.isna().any().any():
        raise ValueError(f"{game_id} pivot contains missing values")
    if len(pivot) < MIN_HISTORY_ROWS:
        raise ValueError(
            f"{game_id} requires at least {MIN_HISTORY_ROWS} complete draws, got {len(pivot)}"
        )
    if strictly_increasing:
        values = pivot.to_numpy(dtype=int)
        if not ((values[:, 1:] - values[:, :-1]) > 0).all():
            raise ValueError(f"{game_id} positions are not strictly increasing")

    position_columns = [f"N{index}" for index in range(1, position_count + 1)]
    rows: list[dict[str, Any]] = []
    audit = pivot.reset_index()
    audit.insert(0, "draw_no", range(1, len(audit) + 1))
    audit.insert(0, "game_id", game_id)
    audit.columns = ["game_id", "draw_no", "ds", *position_columns]

    for row in audit.itertuples(index=False):
        values = {column: int(getattr(row, column)) for column in position_columns}
        rows.append({"draw_no": int(row.draw_no), "values": values})

    payload = {
        "schema_version": 1,
        "game_id": game_id,
        "position_columns": position_columns,
        "rows": rows,
    }
    statistics = {
        "game_id": game_id,
        "source_rows": int(len(frame)),
        "draw_count": int(len(audit)),
        "position_count": position_count,
        "first_ds": str(audit.iloc[0]["ds"]),
        "last_ds": str(audit.iloc[-1]["ds"]),
        "first_draw_no": 1,
        "last_draw_no": int(len(audit)),
        "candidate_min": candidate_min,
        "candidate_max": candidate_max,
        "observed_min": int(frame["y"].min()),
        "observed_max": int(frame["y"].max()),
        "duplicate_keys": 0,
        "incomplete_draws": 0,
        "null_y": 0,
        "strictly_increasing": strictly_increasing,
        "draw_no_semantics": "one_based_ordinal_over_ds",
    }
    return GameExport(
        game_id=game_id,
        json_payload=payload,
        audit_frame=audit,
        statistics=statistics,
    )


def build_exports(source: pd.DataFrame) -> dict[str, GameExport]:
    _required_columns(source)
    normalized_games = source["game_id"].astype(str).str.lower()
    actual_games = set(normalized_games.unique())
    if actual_games != set(FORMAL_GAMES):
        raise ValueError(
            f"source games must exactly equal {list(FORMAL_GAMES)}, got {sorted(actual_games)}"
        )
    exports: dict[str, GameExport] = {}
    for game_id in FORMAL_GAMES:
        game_source = source.loc[normalized_games == game_id].copy()
        exports[game_id] = build_game_export(game_id, game_source)
    return exports


def _parquet_metadata() -> dict[str, str]:
    try:
        import pyarrow  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "pyarrow is required to write the immutable audit Parquet files"
        ) from exc
    return {"pyarrow_version": str(pyarrow.__version__)}


def write_export_bundle(
    exports: dict[str, GameExport],
    *,
    output_root: Path,
    database_snapshot: dict[str, Any],
    query_text: str,
) -> dict[str, Any]:
    if set(exports) != set(FORMAL_GAMES):
        raise ValueError("exports must exactly cover all formal games")
    if output_root.exists():
        raise FileExistsError(f"output root already exists: {output_root}")
    output_root.mkdir(parents=True)

    atomic_write_bytes(output_root / "RAW_QUERY.sql", query_text.encode("utf-8"))
    atomic_write_json(output_root / "DATABASE_SNAPSHOT.json", database_snapshot)
    runtime = _parquet_metadata()
    game_entries: dict[str, Any] = {}

    for game_id in FORMAL_GAMES:
        export = exports[game_id]
        json_path = output_root / f"{game_id}.json"
        parquet_path = output_root / f"{game_id}.parquet"
        atomic_write_json(json_path, export.json_payload)
        export.audit_frame.to_parquet(
            parquet_path,
            engine="pyarrow",
            compression="zstd",
            index=False,
        )
        game_entries[game_id] = {
            **export.statistics,
            "json_path": json_path.name,
            "json_sha256": sha256_file(json_path),
            "json_size_bytes": json_path.stat().st_size,
            "parquet_path": parquet_path.name,
            "parquet_sha256": sha256_file(parquet_path),
            "parquet_size_bytes": parquet_path.stat().st_size,
        }

    primary_files = [
        output_root / "RAW_QUERY.sql",
        output_root / "DATABASE_SNAPSHOT.json",
        *[output_root / f"{game}.json" for game in FORMAL_GAMES],
        *[output_root / f"{game}.parquet" for game in FORMAL_GAMES],
    ]
    manifest = {
        "schema_version": 1,
        "status": "EXPORTED_UNVERIFIED",
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "source_schema": SOURCE_SCHEMA,
        "source_table": SOURCE_TABLE,
        "source_ts_type": SOURCE_TS_TYPE,
        "source_mode": "repeatable_read_read_only",
        "future_actuals_used": False,
        "draw_no_semantics": "one_based_ordinal_over_ds",
        "runtime": runtime,
        "query_sha256": sha256_file(output_root / "RAW_QUERY.sql"),
        "database_snapshot_sha256": sha256_file(output_root / "DATABASE_SNAPSHOT.json"),
        "games": game_entries,
        "primary_file_count": len(primary_files),
        "primary_files": [
            {
                "path": path.name,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in sorted(primary_files, key=lambda item: item.name)
        ],
    }
    manifest_path = output_root / "EXPORT_MANIFEST.json"
    atomic_write_json(manifest_path, manifest)

    checksum_paths = [*primary_files, manifest_path]
    checksum_lines = [
        f"{sha256_file(path)}  {path.name}"
        for path in sorted(checksum_paths, key=lambda item: item.name)
    ]
    atomic_write_bytes(
        output_root / "SHA256SUMS",
        ("\n".join(checksum_lines) + "\n").encode("utf-8"),
    )
    return manifest


def parse_checksum_lines(lines: Iterable[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    pattern = re.compile(r"^([0-9a-f]{64})  ([A-Za-z0-9_.-]+)$")
    for line in lines:
        match = pattern.fullmatch(line.rstrip("\n"))
        if match is None:
            raise ValueError(f"invalid SHA256SUMS line: {line!r}")
        digest, relative = match.groups()
        if relative in result:
            raise ValueError(f"duplicate SHA256SUMS path: {relative}")
        result[relative] = digest
    return result
