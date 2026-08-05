"""Shared contracts and integrity helpers for Prospective actual scoring."""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from .persistence import sha256_file, verify_sha256s
from .prediction_lock import PREDICTION_LOCK_PATH, verify_prediction_lock
from .verification_seal import verify_verification_seal

SCORING_SCHEMA_VERSION = "all-auto-prospective-scoring-v1"
ACTUALS_LOCK_SCHEMA_VERSION = "all-auto-actuals-lock-v1"
ARTIFACT_MANIFEST = "ARTIFACT_MANIFEST.json"
ACTUALS_LOCK = "ACTUALS_LOCK.json"
SCORING_REPORT = "SCORING_REPORT.json"
LOWER_BOUND = 1
UPPER_BOUND = 31


class ScoringOptions(BaseModel):
    """Validated operator inputs that affect reproducible scoring."""

    random_seed: int = Field(default=1, ge=0)
    actual_source_label: str = Field(default="UNSPECIFIED", min_length=1, max_length=500)
    actual_published_at: str | None = None


def _read_json(path: Path, failures: list[str], label: str) -> dict[str, Any]:
    if not path.is_file():
        failures.append(f"{label} missing: {path}")
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        failures.append(f"{label} unreadable: {type(exc).__name__}: {exc}")
        return {}
    if not isinstance(payload, dict) or not payload:
        failures.append(f"{label} must be a non-empty JSON object: {path}")
        return {}
    return payload


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=repr,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _parse_utc(value: Any, failures: list[str], label: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        failures.append(f"{label} missing")
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        failures.append(f"{label} is not ISO-8601: {text}")
        return None
    if parsed.tzinfo is None:
        failures.append(f"{label} must include a timezone")
        return None
    return parsed.astimezone(UTC)


def _safe_relative(value: str, failures: list[str], label: str) -> Path | None:
    if "\\" in value:
        failures.append(f"{label} contains a backslash: {value}")
        return None
    pure = PurePosixPath(value)
    if pure.is_absolute() or not pure.parts or ".." in pure.parts or "." in pure.parts:
        failures.append(f"{label} is unsafe: {value}")
        return None
    return Path(*pure.parts)


def _reject_symlinks(root: Path, label: str) -> list[str]:
    if root.is_symlink():
        return [f"{label} must not be a symlink: {root}"]
    if not root.is_dir():
        return [f"{label} is not a directory: {root}"]
    failures: list[str] = []
    try:
        paths = list(root.rglob("*"))
    except OSError as exc:
        return [f"{label} traversal failed: {type(exc).__name__}: {exc}"]
    for path in paths:
        if path.is_symlink():
            failures.append(f"{label} contains symlink: {path.relative_to(root).as_posix()}")
    return failures


def _verify_scoring_sha256s(root: Path) -> list[str]:
    failures: list[str] = []
    manifest = root / "SHA256SUMS"
    if not manifest.is_file():
        return ["SHA256SUMS missing"]
    listed: set[str] = set()
    try:
        lines = manifest.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return [f"SHA256SUMS unreadable: {type(exc).__name__}: {exc}"]
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            expected, relative_text = line.split("  ", 1)
        except ValueError:
            failures.append(f"SHA256SUMS malformed line: {line_number}")
            continue
        relative_failures: list[str] = []
        relative = _safe_relative(
            relative_text,
            relative_failures,
            f"SHA256SUMS line {line_number}",
        )
        failures.extend(relative_failures)
        if relative is None:
            continue
        normalized = relative.as_posix()
        if normalized in listed:
            failures.append(f"SHA256SUMS duplicate path: {normalized}")
            continue
        listed.add(normalized)
        path = root / relative
        if path.is_symlink() or not path.is_file():
            failures.append(f"SHA256SUMS missing regular file: {normalized}")
        elif sha256_file(path) != expected:
            failures.append(f"SHA256SUMS mismatch: {normalized}")
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink() and path.name != "SHA256SUMS"
    }
    failures.extend(f"SHA256SUMS unlisted: {item}" for item in sorted(actual - listed))
    failures.extend(
        f"SHA256SUMS listed-but-missing: {item}" for item in sorted(listed - actual)
    )
    return failures


def _require_regular_file(path: Path, label: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular file: {path}")


def _read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.casefold()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    raise ValueError(f"unsupported table format: {path.suffix}; use CSV or Parquet")


def _normalized_name(value: object) -> str:
    return "".join(character for character in str(value).casefold() if character.isalnum())


def _resolve_column(
    columns: list[str],
    candidates: list[str],
    *,
    label: str,
) -> str:
    exact = {column: column for column in columns}
    folded = {column.casefold(): column for column in columns}
    normalized = {_normalized_name(column): column for column in columns}
    for candidate in candidates:
        if candidate in exact:
            return exact[candidate]
        if candidate.casefold() in folded:
            return folded[candidate.casefold()]
        key = _normalized_name(candidate)
        if key in normalized:
            return normalized[key]
    raise ValueError(f"{label} column not found; candidates={candidates}, columns={columns}")


def _normalize_input_table(
    path: Path,
    *,
    contract: Mapping[str, Any],
    campaign_config: Mapping[str, Any],
    label: str,
) -> pd.DataFrame:
    frame = _read_table(path)
    columns = [str(column) for column in frame.columns]
    number_columns = [str(value) for value in contract.get("number_columns") or []]
    if not number_columns:
        raise ValueError("data contract number_columns missing")

    draw_id_name = str(contract.get("draw_id_column") or "draw_id")
    draw_index_name = str(contract.get("draw_index_column") or "draw_index")
    draw_id_candidates = [
        draw_id_name,
        *[str(value) for value in campaign_config.get("draw_id_candidates") or []],
    ]
    draw_index_candidates = [
        draw_index_name,
        *[str(value) for value in campaign_config.get("draw_index_candidates") or []],
    ]
    draw_id_source = _resolve_column(columns, draw_id_candidates, label=f"{label} draw_id")
    draw_index_source = _resolve_column(
        columns,
        draw_index_candidates,
        label=f"{label} draw_index",
    )
    number_sources = [
        _resolve_column(columns, [name], label=f"{label} {name}")
        for name in number_columns
    ]

    normalized = pd.DataFrame(
        {
            "draw_id": frame[draw_id_source].astype("string"),
            "draw_index": pd.to_numeric(frame[draw_index_source], errors="raise"),
            **{
                name: pd.to_numeric(frame[source], errors="raise")
                for name, source in zip(number_columns, number_sources, strict=True)
            },
        }
    )
    numeric_columns = ["draw_index", *number_columns]
    if normalized[numeric_columns].isna().any().any():
        raise ValueError(f"{label} contains missing numeric values")
    values = normalized[numeric_columns].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError(f"{label} contains non-finite values")
    if not np.equal(values, np.rint(values)).all():
        raise ValueError(f"{label} contains non-integer draw values")
    normalized[numeric_columns] = normalized[numeric_columns].astype("int64")
    if normalized["draw_id"].isna().any() or normalized["draw_id"].eq("").any():
        raise ValueError(f"{label} contains missing draw_id values")
    if normalized["draw_id"].duplicated().any():
        raise ValueError(f"{label} contains duplicate draw_id values")
    if normalized["draw_index"].duplicated().any():
        raise ValueError(f"{label} contains duplicate draw_index values")
    number_matrix = normalized[number_columns].to_numpy(dtype=int)
    if np.any(number_matrix < LOWER_BOUND) or np.any(number_matrix > UPPER_BOUND):
        raise ValueError(
            f"{label} values must be within Mini Loto bounds "
            f"[{LOWER_BOUND}, {UPPER_BOUND}]"
        )
    if np.any(np.diff(number_matrix, axis=1) <= 0):
        raise ValueError(f"{label} number positions must be strictly increasing")
    normalized = normalized.sort_values("draw_index", kind="stable").reset_index(drop=True)
    if not normalized["draw_index"].is_monotonic_increasing:
        raise ValueError(f"{label} draw_index order violation")
    return normalized


def _source_verification(run_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    failures = _reject_symlinks(run_root, "source prospective run")
    manifest = _read_json(run_root / "manifest.json", failures, "source manifest")
    lock = _read_json(run_root / PREDICTION_LOCK_PATH, failures, "prediction lock")
    prediction_result = verify_prediction_lock(run_root, manifest)
    seal_result = verify_verification_seal(run_root)
    failures.extend(f"prediction-lock:{item}" for item in prediction_result.get("failures", []))
    failures.extend(f"verification-seal:{item}" for item in seal_result.get("failures", []))
    failures.extend(f"source-sha256:{item}" for item in verify_sha256s(run_root))
    if manifest.get("status") != "PASS":
        failures.append(f"source manifest status is not PASS: {manifest.get('status')}")
    if manifest.get("stage") != "prospective":
        failures.append(f"source stage is not prospective: {manifest.get('stage')}")
    if manifest.get("prediction_lock_status") != "LOCKED":
        failures.append("source manifest prediction_lock_status must be LOCKED")
    if prediction_result.get("status") != "PASS":
        failures.append("source prediction lock verification is not PASS")
    if seal_result.get("status") != "PASS":
        failures.append("source verification seal is not PASS")
    if failures:
        raise ValueError("; ".join(failures))
    return manifest, lock


def _copy_exact(source: Path, target: Path) -> dict[str, Any]:
    _require_regular_file(source, "source evidence")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    source_sha = sha256_file(source)
    target_sha = sha256_file(target)
    if source_sha != target_sha:
        raise RuntimeError(f"copied evidence hash mismatch: {source} -> {target}")
    return {
        "path": target.as_posix(),
        "sha256": target_sha,
        "size_bytes": target.stat().st_size,
    }


def _copy_source_evidence(run_root: Path, output: Path) -> dict[str, Any]:
    records: dict[str, Any] = {}
    for name in (
        "manifest.json",
        PREDICTION_LOCK_PATH,
        "VERIFICATION_SEAL.json",
        "VERIFICATION_REPORT.json",
        "SHA256SUMS",
    ):
        target = output / "source_evidence" / name
        _copy_exact(run_root / name, target)
        records[name] = {
            "path": target.relative_to(output).as_posix(),
            "sha256": sha256_file(target),
            "size_bytes": target.stat().st_size,
        }
    return records


def _file_inventory(root: Path) -> list[dict[str, Any]]:
    excluded = {ARTIFACT_MANIFEST, "SHA256SUMS"}
    records: list[dict[str, Any]] = []
    for path in sorted(
        (item for item in root.rglob("*") if item.is_file()),
        key=lambda item: item.relative_to(root).as_posix(),
    ):
        relative = path.relative_to(root).as_posix()
        if relative in excluded:
            continue
        records.append(
            {
                "path": relative,
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
        )
    return records


def _source_fingerprint(run_root: Path) -> dict[str, str]:
    return {
        name: sha256_file(run_root / name)
        for name in (
            "manifest.json",
            PREDICTION_LOCK_PATH,
            "VERIFICATION_SEAL.json",
            "SHA256SUMS",
        )
    }
