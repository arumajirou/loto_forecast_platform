"""Build deterministic registry payloads from verified scoring artifacts."""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, unquote, urlsplit

import pandas as pd

from .persistence import sha256_file
from .prospective_registry_backends import redact_uri
from .prospective_registry_contract import (
    REGISTRY_MANIFEST,
    REGISTRY_SCHEMA_VERSION,
    RegistryOptions,
    _candidate_key,
    _canonical_sha256,
    _component,
    _json_safe,
    _read_json,
    _record_json,
    _seed_token,
)

_REQUIRED_SOURCE_FILES = (
    "ARTIFACT_MANIFEST.json",
    "SCORING_REPORT.json",
    "ACTUALS_LOCK.json",
    "SHA256SUMS",
    "RANKING.csv",
    "RANKING.parquet",
    "SEED_SUMMARY.csv",
    "SEED_SUMMARY.parquet",
    "PER_SEED_METRICS.csv",
    "PER_SEED_METRICS.parquet",
    "POSITION_METRICS.csv",
    "POSITION_METRICS.parquet",
    "BASELINE_COMPARISON.csv",
    "BASELINE_COMPARISON.parquet",
    "SOURCE_PREDICTION_MAP.json",
    "BASELINE_METADATA.json",
    "source_evidence/manifest.json",
    "source_evidence/campaign_config.json",
    "source_evidence/data_contract.json",
    "source_evidence/PREDICTION_LOCK.json",
    "source_evidence/VERIFICATION_SEAL.json",
)


def _copy_exact(source: Path, target: Path) -> dict[str, Any]:
    if source.is_symlink() or not source.is_file():
        raise ValueError(f"source evidence must be a regular file: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    source_sha = sha256_file(source)
    target_sha = sha256_file(target)
    if source_sha != target_sha:
        raise RuntimeError(f"source evidence copy SHA mismatch: {source}")
    return {
        "path": target.as_posix(),
        "sha256": target_sha,
        "size_bytes": target.stat().st_size,
    }


def _copy_source_evidence(
    scoring_root: Path,
    work: Path,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for relative_text in _REQUIRED_SOURCE_FILES:
        relative = Path(relative_text)
        source = scoring_root / relative
        target = work / "source_evidence" / relative
        record = _copy_exact(source, target)
        record["source_path"] = relative.as_posix()
        record["path"] = target.relative_to(work).as_posix()
        records.append(record)
    return records


def _read_registry_tables(scoring_root: Path) -> dict[str, pd.DataFrame]:
    names = {
        "ranking": "RANKING.parquet",
        "seed_summary": "SEED_SUMMARY.parquet",
        "seed_metrics": "PER_SEED_METRICS.parquet",
        "position_metrics": "POSITION_METRICS.parquet",
    }
    frames: dict[str, pd.DataFrame] = {}
    for name, filename in names.items():
        path = scoring_root / filename
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"required registry table missing: {filename}")
        try:
            frame = pd.read_parquet(path)
        except (OSError, ValueError) as exc:
            raise ValueError(
                f"registry table unreadable: {filename}: {type(exc).__name__}: {exc}"
            ) from exc
        if frame.empty:
            raise ValueError(f"required registry table is empty: {filename}")
        frames[name] = frame
    return frames


def _candidate_frame(
    seed_summary: pd.DataFrame,
    ranking: pd.DataFrame,
    registry_id: str,
) -> pd.DataFrame:
    required = {
        "source_type",
        "model_name",
        "baseline_name",
        "track",
        "seed_count",
        "hit_pm1_mean",
        "hit_pm1_var",
        "hit_pm1_min",
        "hit_pm1_max",
        "all_positions_hit_pm1_mean",
        "mae_mean",
        "mse_mean",
        "rmse_mean",
        "worst_seed_hit_pm1",
    }
    if not required.issubset(seed_summary.columns):
        raise ValueError(
            "SEED_SUMMARY.parquet missing required columns: "
            f"{sorted(required - set(seed_summary.columns))}"
        )
    rank_map: dict[str, int] = {}
    for row in ranking.to_dict(orient="records"):
        key = _candidate_key(row)
        rank_map[key] = int(row["rank"])
    rows: list[dict[str, Any]] = []
    for raw in seed_summary.to_dict(orient="records"):
        key = _candidate_key(raw)
        record = {
            "registry_id": registry_id,
            "candidate_key": key,
            "source_type": _component(raw.get("source_type")),
            "model_name": _json_safe(raw.get("model_name")),
            "baseline_name": _json_safe(raw.get("baseline_name")),
            "track": _json_safe(raw.get("track")),
            "seed_count": int(raw["seed_count"]),
            "hit_pm1_mean": float(raw["hit_pm1_mean"]),
            "hit_pm1_var": _optional_float(raw.get("hit_pm1_var")),
            "hit_pm1_min": float(raw["hit_pm1_min"]),
            "hit_pm1_max": float(raw["hit_pm1_max"]),
            "all_positions_hit_pm1_mean": _optional_float(raw.get("all_positions_hit_pm1_mean")),
            "mae_mean": float(raw["mae_mean"]),
            "mse_mean": float(raw["mse_mean"]),
            "rmse_mean": float(raw["rmse_mean"]),
            "worst_seed_hit_pm1": float(raw["worst_seed_hit_pm1"]),
            "rank": rank_map.get(key),
        }
        record["record_json"] = _record_json(raw)
        rows.append(record)
    frame = pd.DataFrame(rows)
    if frame["candidate_key"].duplicated().any():
        raise ValueError("candidate registry keys are not unique")
    return frame.sort_values(
        ["rank", "candidate_key"],
        na_position="last",
        kind="stable",
    ).reset_index(drop=True)


def _optional_float(value: Any) -> float | None:
    safe = _json_safe(value)
    return None if safe is None else float(safe)


def _seed_metric_frame(
    frame: pd.DataFrame,
    registry_id: str,
) -> pd.DataFrame:
    required = {
        "source_type",
        "model_name",
        "baseline_name",
        "track",
        "seed",
        "hit_pm1",
        "all_positions_hit_pm1",
        "mae",
        "mse",
        "rmse",
    }
    if not required.issubset(frame.columns):
        raise ValueError(
            "PER_SEED_METRICS.parquet missing required columns: "
            f"{sorted(required - set(frame.columns))}"
        )
    rows: list[dict[str, Any]] = []
    for raw in frame.to_dict(orient="records"):
        seed_value = _json_safe(raw.get("seed"))
        rows.append(
            {
                "registry_id": registry_id,
                "candidate_key": _candidate_key(raw),
                "seed_token": _seed_token(seed_value),
                "seed": None if seed_value is None else int(seed_value),
                "source_type": _component(raw.get("source_type")),
                "model_name": _json_safe(raw.get("model_name")),
                "baseline_name": _json_safe(raw.get("baseline_name")),
                "track": _json_safe(raw.get("track")),
                "hit_pm1": float(raw["hit_pm1"]),
                "all_positions_hit_pm1": _optional_float(raw.get("all_positions_hit_pm1")),
                "mae": float(raw["mae"]),
                "mse": float(raw["mse"]),
                "rmse": float(raw["rmse"]),
                "record_json": _record_json(raw),
            }
        )
    result = pd.DataFrame(rows)
    if result.duplicated(["candidate_key", "seed_token"]).any():
        raise ValueError("per-seed registry keys are not unique")
    return result.sort_values(
        ["candidate_key", "seed_token"],
        kind="stable",
    ).reset_index(drop=True)


def _position_metric_frame(
    frame: pd.DataFrame,
    registry_id: str,
) -> pd.DataFrame:
    required = {
        "source_type",
        "model_name",
        "baseline_name",
        "track",
        "seed",
        "unique_id",
        "variant",
        "hit_pm1",
        "exact_hit",
        "mae",
        "mse",
        "rmse",
    }
    if not required.issubset(frame.columns):
        raise ValueError(
            "POSITION_METRICS.parquet missing required columns: "
            f"{sorted(required - set(frame.columns))}"
        )
    rows: list[dict[str, Any]] = []
    for raw in frame.to_dict(orient="records"):
        normalized = {key: _json_safe(value) for key, value in raw.items()}
        seed_token = _seed_token(normalized.get("seed"))
        row_identity = {
            "candidate_key": _candidate_key(normalized),
            "candidate_id": normalized.get("candidate_id"),
            "backend": normalized.get("backend"),
            "config_index": normalized.get("config_index"),
            "position": normalized.get("position"),
            "seed_token": seed_token,
            "unique_id": normalized.get("unique_id"),
            "variant": normalized.get("variant"),
        }
        rows.append(
            {
                "registry_id": registry_id,
                "row_key": _canonical_sha256(row_identity),
                "candidate_key": row_identity["candidate_key"],
                "seed_token": seed_token,
                "unique_id": _component(normalized.get("unique_id")),
                "variant": _component(normalized.get("variant")),
                "hit_pm1": float(normalized["hit_pm1"]),
                "exact_hit": float(normalized["exact_hit"]),
                "mae": float(normalized["mae"]),
                "mse": float(normalized["mse"]),
                "rmse": float(normalized["rmse"]),
                "record_json": _record_json(normalized),
            }
        )
    result = pd.DataFrame(rows)
    if result["row_key"].duplicated().any():
        raise ValueError("position metric registry keys are not unique")
    return result.sort_values("row_key", kind="stable").reset_index(drop=True)


def _artifact_frame(
    scoring_root: Path,
    manifest: dict[str, Any],
    registry_id: str,
) -> pd.DataFrame:
    records = manifest.get("files")
    if not isinstance(records, list) or not records:
        raise ValueError("scoring artifact manifest file inventory is missing")
    rows: list[dict[str, Any]] = []
    for item in records:
        if not isinstance(item, Mapping):
            raise ValueError("scoring artifact inventory record is invalid")
        rows.append(
            {
                "registry_id": registry_id,
                "path": str(item["path"]),
                "size_bytes": int(item["size_bytes"]),
                "sha256": str(item["sha256"]),
            }
        )
    for name in (
        "ARTIFACT_MANIFEST.json",
        "SCORING_REPORT.json",
        "ACTUALS_LOCK.json",
        "SHA256SUMS",
    ):
        path = scoring_root / name
        rows.append(
            {
                "registry_id": registry_id,
                "path": name,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    result = pd.DataFrame(rows).drop_duplicates("path", keep="last")
    return result.sort_values("path", kind="stable").reset_index(drop=True)


def _build_payload(
    scoring_root: Path,
    options: RegistryOptions,
    tables: dict[str, pd.DataFrame],
) -> tuple[dict[str, Any], dict[str, pd.DataFrame]]:
    scoring_manifest = _read_json(
        scoring_root / "ARTIFACT_MANIFEST.json",
        "scoring artifact manifest",
    )
    scoring_report = _read_json(
        scoring_root / "SCORING_REPORT.json",
        "scoring report",
    )
    actuals_lock = _read_json(
        scoring_root / "ACTUALS_LOCK.json",
        "actuals lock",
    )
    source_manifest = _read_json(
        scoring_root / "source_evidence" / "manifest.json",
        "copied source manifest",
    )
    scoring_id = str(scoring_report.get("scoring_id") or "")
    if not scoring_id or scoring_manifest.get("scoring_id") != scoring_id:
        raise ValueError("scoring_id is missing or inconsistent")
    if actuals_lock.get("scoring_id") != scoring_id:
        raise ValueError("actuals lock scoring_id differs from scoring report")
    if scoring_report.get("priority_metric") != "hit_pm1":
        raise ValueError("Prospective registry priority metric must be hit_pm1")
    created_at = str(scoring_report.get("created_at") or "").strip()
    if not created_at:
        raise ValueError("scoring report created_at is missing")
    safe_mlflow_uri = redact_uri(options.mlflow_uri or os.getenv(options.mlflow_uri_env, ""))
    stable_identity = {
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "registry_namespace": options.registry_namespace,
        "scoring_id": scoring_id,
        "scoring_report_sha256": sha256_file(scoring_root / "SCORING_REPORT.json"),
        "artifact_manifest_sha256": sha256_file(scoring_root / "ARTIFACT_MANIFEST.json"),
        "scoring_sha256s_sha256": sha256_file(scoring_root / "SHA256SUMS"),
        "mlflow_tracking_uri": safe_mlflow_uri,
        "mlflow_experiment": options.mlflow_experiment,
        "artifact_mode": options.artifact_mode,
    }
    registry_id = f"prospective-registry-{_canonical_sha256(stable_identity)[:20]}"
    frames = {
        "candidates": _candidate_frame(
            tables["seed_summary"],
            tables["ranking"],
            registry_id,
        ),
        "seed_metrics": _seed_metric_frame(
            tables["seed_metrics"],
            registry_id,
        ),
        "position_metrics": _position_metric_frame(
            tables["position_metrics"],
            registry_id,
        ),
        "artifacts": _artifact_frame(
            scoring_root,
            scoring_manifest,
            registry_id,
        ),
    }
    source = {
        "scoring_root": str(scoring_root),
        "source_run_id": scoring_report.get("source_run_id"),
        "scoring_id": scoring_id,
        "prediction_lock_sha256": scoring_report["prediction_lock_sha256"],
        "verification_seal_sha256": scoring_report["verification_seal_sha256"],
        "history_sha256": scoring_report["history_sha256"],
        "actuals_sha256": scoring_report["actuals_sha256"],
        "scoring_code_sha256": scoring_report["scoring_code_sha256"],
        "scoring_report_sha256": stable_identity["scoring_report_sha256"],
        "artifact_manifest_sha256": stable_identity["artifact_manifest_sha256"],
        "scoring_sha256s_sha256": stable_identity["scoring_sha256s_sha256"],
        "actuals_lock_sha256": sha256_file(scoring_root / "ACTUALS_LOCK.json"),
        "source_code_sha256": source_manifest.get("code_sha256")
        or source_manifest.get("code_hash"),
        "source_data_sha256": source_manifest.get("data_sha256")
        or source_manifest.get("data_hash"),
        "source_lineage_chain_sha256": source_manifest.get("lineage_chain_sha256"),
        "source_git_commit": source_manifest.get("git_commit") or source_manifest.get("git_sha"),
    }
    payload: dict[str, Any] = {
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "registry_id": registry_id,
        "registry_namespace": options.registry_namespace,
        "scoring_id": scoring_id,
        "created_at": created_at,
        "source": source,
        "metric_policy": {
            "priority_metric": "hit_pm1",
            "secondary_metrics": [
                "all_positions_hit_pm1",
                "mae",
                "mse",
                "rmse",
            ],
            "aggregation": [
                "per_seed",
                "mean",
                "variance",
                "minimum",
                "maximum",
                "worst_seed",
            ],
            "best_seed_only_selection": False,
        },
        "backend_policy": {
            "required_backends": ["postgres", "mlflow"],
            "postgres_dsn_env": options.postgres_dsn_env,
            "mlflow_tracking_uri": safe_mlflow_uri,
            "mlflow_uri_env": options.mlflow_uri_env,
            "mlflow_experiment": options.mlflow_experiment,
            "artifact_mode": options.artifact_mode,
        },
        "counts": {
            "candidate_count": len(frames["candidates"]),
            "seed_metric_rows": len(frames["seed_metrics"]),
            "position_metric_rows": len(frames["position_metrics"]),
            "artifact_rows": len(frames["artifacts"]),
        },
        "scoring_report": scoring_report,
    }
    payload["payload_sha256"] = _canonical_sha256(payload)
    return payload, frames


def _redaction_tokens(values: tuple[str, ...]) -> list[str]:
    tokens: set[str] = set()
    sensitive_query_keys = {
        "access_token",
        "api_key",
        "apikey",
        "credential",
        "password",
        "secret",
        "token",
    }
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        tokens.add(text)
        try:
            parsed = urlsplit(text)
        except ValueError:
            continue
        if parsed.password:
            tokens.add(unquote(parsed.password))
        for key, item in parse_qsl(parsed.query, keep_blank_values=False):
            if key.casefold() in sensitive_query_keys and item:
                tokens.add(unquote(item))
    return sorted(tokens, key=len, reverse=True)


def _safe_error(
    exc: BaseException,
    *,
    secrets: tuple[str, ...],
    phase: str,
) -> dict[str, Any]:
    detail = str(exc)
    for secret in _redaction_tokens(secrets):
        detail = detail.replace(secret, "<redacted>")
    return {
        "phase": phase,
        "error_type": type(exc).__name__,
        "error": detail[:1000],
    }


def _registry_file_inventory(root: Path) -> list[dict[str, Any]]:
    excluded = {REGISTRY_MANIFEST, "SHA256SUMS"}
    rows: list[dict[str, Any]] = []
    for path in sorted(
        (item for item in root.rglob("*") if item.is_file()),
        key=lambda item: item.relative_to(root).as_posix(),
    ):
        relative = path.relative_to(root).as_posix()
        if relative in excluded:
            continue
        rows.append(
            {
                "path": relative,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return rows
