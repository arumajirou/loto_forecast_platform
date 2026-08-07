from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from loto.toto2_campaign.raw_history_export import (
    FORMAL_GAMES,
    parse_checksum_lines,
    sha256_file,
)

_EXPECTED_FILES = {
    "DATABASE_SNAPSHOT.json",
    "EXPORT_MANIFEST.json",
    "RAW_QUERY.sql",
    "SHA256SUMS",
    *{f"{game}.json" for game in FORMAL_GAMES},
    *{f"{game}.parquet" for game in FORMAL_GAMES},
}


def _load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _verify_safe_files(root: Path) -> None:
    actual = {path.name for path in root.iterdir() if path.is_file()}
    if actual != _EXPECTED_FILES:
        raise ValueError(
            f"export file set mismatch: missing={sorted(_EXPECTED_FILES - actual)} "
            f"extra={sorted(actual - _EXPECTED_FILES)}"
        )
    for path in root.iterdir():
        if path.is_symlink():
            raise ValueError(f"symlinks are forbidden in export root: {path.name}")
        if path.is_dir():
            raise ValueError(f"subdirectories are forbidden in export root: {path.name}")


def _verify_checksums(root: Path) -> None:
    checksums = parse_checksum_lines((root / "SHA256SUMS").read_text().splitlines())
    expected = _EXPECTED_FILES - {"SHA256SUMS"}
    if set(checksums) != expected:
        raise ValueError("SHA256SUMS coverage differs from the export file set")
    for relative, expected_digest in checksums.items():
        actual = sha256_file(root / relative)
        if actual != expected_digest:
            raise ValueError(f"SHA-256 mismatch: {relative}")


def _verify_game(root: Path, game_id: str, manifest: dict[str, Any]) -> dict[str, Any]:
    payload = _load_object(root / f"{game_id}.json")
    game_manifest = manifest["games"][game_id]
    if payload.get("schema_version") != 1 or payload.get("game_id") != game_id:
        raise ValueError(f"invalid history JSON identity: {game_id}")
    columns = payload.get("position_columns")
    rows = payload.get("rows")
    if not isinstance(columns, list) or not isinstance(rows, list):
        raise ValueError(f"invalid history JSON structure: {game_id}")
    if len(rows) != game_manifest["draw_count"]:
        raise ValueError(f"history row count differs from manifest: {game_id}")

    parquet = pd.read_parquet(root / f"{game_id}.parquet", engine="pyarrow")
    expected_columns = ["game_id", "draw_no", "ds", *columns]
    if list(parquet.columns) != expected_columns:
        raise ValueError(f"Parquet columns differ from JSON: {game_id}")
    if len(parquet) != len(rows):
        raise ValueError(f"Parquet row count differs from JSON: {game_id}")
    if parquet["game_id"].astype(str).unique().tolist() != [game_id]:
        raise ValueError(f"Parquet game identity mismatch: {game_id}")
    expected_draws = list(range(1, len(rows) + 1))
    if parquet["draw_no"].astype(int).tolist() != expected_draws:
        raise ValueError(f"Parquet draw_no is not gap-free: {game_id}")

    for index, row in enumerate(rows):
        if row.get("draw_no") != index + 1:
            raise ValueError(f"JSON draw_no is not gap-free: {game_id}")
        values = row.get("values")
        if not isinstance(values, dict) or list(values) != columns:
            raise ValueError(f"JSON values do not match position columns: {game_id}")
        parquet_row = parquet.iloc[index]
        for column in columns:
            if int(parquet_row[column]) != int(values[column]):
                raise ValueError(f"JSON/Parquet value mismatch: {game_id}/{column}")

    if str(parquet.iloc[0]["ds"]) != game_manifest["first_ds"]:
        raise ValueError(f"first_ds differs from manifest: {game_id}")
    if str(parquet.iloc[-1]["ds"]) != game_manifest["last_ds"]:
        raise ValueError(f"last_ds differs from manifest: {game_id}")
    return {
        "game_id": game_id,
        "draw_count": len(rows),
        "json_sha256": sha256_file(root / f"{game_id}.json"),
        "parquet_sha256": sha256_file(root / f"{game_id}.parquet"),
    }


def verify_export_bundle(root: Path) -> dict[str, Any]:
    if not root.is_dir() or root.is_symlink():
        raise ValueError(f"export root is missing or unsafe: {root}")
    _verify_safe_files(root)
    _verify_checksums(root)
    manifest = _load_object(root / "EXPORT_MANIFEST.json")
    snapshot = _load_object(root / "DATABASE_SNAPSHOT.json")

    if manifest.get("schema_version") != 1:
        raise ValueError("export manifest schema_version must be 1")
    if manifest.get("source_schema") != "dataset":
        raise ValueError("export manifest source_schema mismatch")
    if manifest.get("source_table") != "loto_y_ts_unified":
        raise ValueError("export manifest source_table mismatch")
    if manifest.get("source_ts_type") != "raw":
        raise ValueError("export manifest source_ts_type mismatch")
    if manifest.get("source_mode") != "repeatable_read_read_only":
        raise ValueError("export manifest source_mode mismatch")
    if manifest.get("future_actuals_used") is not False:
        raise ValueError("export manifest must not claim future actual usage")
    if snapshot.get("transaction_read_only") is not True:
        raise ValueError("database snapshot is not read-only")
    if snapshot.get("transaction_isolation") != "repeatable read":
        raise ValueError("database snapshot isolation is not repeatable read")
    if set(manifest.get("games", {})) != set(FORMAL_GAMES):
        raise ValueError("export manifest does not cover the formal games")

    results = [_verify_game(root, game_id, manifest) for game_id in FORMAL_GAMES]
    primary = manifest.get("primary_files")
    if not isinstance(primary, list) or manifest.get("primary_file_count") != len(primary):
        raise ValueError("primary-file manifest is invalid")
    for entry in primary:
        relative = entry["path"]
        path = root / relative
        if path.stat().st_size != entry["size_bytes"]:
            raise ValueError(f"primary file size mismatch: {relative}")
        if sha256_file(path) != entry["sha256"]:
            raise ValueError(f"primary file hash mismatch: {relative}")

    return {
        "schema_version": 1,
        "status": "VERIFIED",
        "export_root": str(root.resolve()),
        "file_count": len(_EXPECTED_FILES),
        "games": results,
        "future_actuals_used": False,
        "raw_data_modified": False,
    }
