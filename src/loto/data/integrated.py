from __future__ import annotations

import json
import shutil
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from loto.data.canonical import canonicalize_loto7, to_candidate_table, to_position_table
from loto.data.datasets import copy_bundle_to_postgres, write_dataset_bundle
from loto.data.fetcher import PoliteHttpClient
from loto.data.lineage import (
    StageManifest,
    artifact_descriptor,
    atomic_write_frame_csv,
    atomic_write_json,
    frame_fingerprint,
    utc_now_iso,
)
from loto.data.lotteries import LotterySpec, get_lottery_spec, select_lottery_specs
from loto.data.parser import parse_file
from loto.features.legacy import make_draw_features, make_occurrence_features
from loto.features.pipeline import build_candidate_features


def _append_event(path: Path, event: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(dict(event), ensure_ascii=False, default=str) + "\n")


def _quality_report(frame: pd.DataFrame, spec: LotterySpec) -> dict[str, Any]:
    issues: list[str] = []
    if frame.empty:
        issues.append("empty_frame")
    duplicate_draws = int(frame.duplicated(subset=["draw_no"]).sum()) if "draw_no" in frame else 0
    if duplicate_draws:
        issues.append(f"duplicate_draw_no:{duplicate_draws}")
    date_invalid = int(pd.to_datetime(frame.get("draw_date"), errors="coerce").isna().sum()) if "draw_date" in frame else len(frame)
    if date_invalid:
        issues.append(f"invalid_draw_date:{date_invalid}")
    number_columns = [c for c in frame.columns if c.startswith("n") and c[1:].isdigit()]
    range_violations = 0
    missing_numbers = 0
    for col in number_columns:
        values = pd.to_numeric(frame[col], errors="coerce")
        missing_numbers += int(values.isna().sum())
        range_violations += int(((values < spec.number_min) | (values > spec.number_max)).fillna(False).sum())
    if missing_numbers:
        issues.append(f"missing_numbers:{missing_numbers}")
    if range_violations:
        issues.append(f"number_range_violations:{range_violations}")
    unordered_rows = 0
    if spec.kind == "lotto" and number_columns:
        ordered = frame[number_columns].apply(pd.to_numeric, errors="coerce")
        unordered_rows = int((ordered.diff(axis=1).iloc[:, 1:] <= 0).any(axis=1).sum())
        if unordered_rows:
            issues.append(f"unordered_or_duplicate_main_numbers:{unordered_rows}")
    return {
        "status": "PASS" if not issues else "FAIL",
        "rows": int(len(frame)),
        "columns": list(frame.columns),
        "frame_sha256": frame_fingerprint(frame),
        "duplicate_draws": duplicate_draws,
        "invalid_draw_dates": date_invalid,
        "missing_numbers": missing_numbers,
        "range_violations": range_violations,
        "unordered_rows": unordered_rows,
        "issues": issues,
    }


def _materialize_source_file(source_file: str | Path, raw_dir: Path, game: str) -> tuple[Path, dict[str, Any]]:
    source = Path(source_file)
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(source)
    target = raw_dir / f"{game}.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != target.resolve():
        tmp = target.with_suffix(".csv.tmp")
        shutil.copy2(source, tmp)
        tmp.replace(target)
    return target, {"game": game, "source": str(source), "raw_path": str(target), "mode": "local-file", **artifact_descriptor(target)}


def acquire_and_build(
    *,
    game: str,
    output_dir: str | Path,
    source_file: str | Path | None = None,
    force: bool = False,
    postgres_dsn: str | None = None,
    windows: tuple[int, ...] = (5, 10, 20, 30, 50, 100),
    require_parquet: bool = False,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Acquire, parse, validate and feature-engineer one configured game."""
    run_id = run_id or f"data-{uuid.uuid4().hex[:12]}"
    out = Path(output_dir)
    raw_dir = out / "raw"
    normalized_dir = out / "normalized"
    feature_dir = out / "features"
    manifest_dir = out / "manifests"
    event_path = out / "events.jsonl"
    for path in (raw_dir, normalized_dir, feature_dir, manifest_dir):
        path.mkdir(parents=True, exist_ok=True)
    spec = get_lottery_spec(game)
    stages: list[dict[str, Any]] = []

    def run_stage(name: str, operation):
        started_at = utc_now_iso()
        started = time.perf_counter()
        _append_event(event_path, {"run_id": run_id, "game": game, "stage": name, "status": "STARTED", "timestamp": started_at})
        try:
            value, inputs, outputs, metrics, warnings = operation()
            manifest = StageManifest(
                run_id=run_id,
                stage=name,
                status="SUCCEEDED",
                started_at=started_at,
                finished_at=utc_now_iso(),
                inputs=inputs,
                outputs=outputs,
                metrics={**metrics, "duration_seconds": time.perf_counter() - started},
                warnings=warnings,
            )
        except Exception as exc:
            manifest = StageManifest(
                run_id=run_id,
                stage=name,
                status="FAILED",
                started_at=started_at,
                finished_at=utc_now_iso(),
                metrics={"duration_seconds": time.perf_counter() - started},
                error=f"{type(exc).__name__}: {exc}",
            )
            path = atomic_write_json(manifest_dir / f"{name}.json", manifest.to_dict())
            stages.append({**manifest.to_dict(), "manifest_path": str(path)})
            _append_event(event_path, {"run_id": run_id, "game": game, "stage": name, "status": "FAILED", "timestamp": manifest.finished_at, "error": manifest.error})
            raise
        path = atomic_write_json(manifest_dir / f"{name}.json", manifest.to_dict())
        stages.append({**manifest.to_dict(), "manifest_path": str(path)})
        _append_event(event_path, {"run_id": run_id, "game": game, "stage": name, "status": "SUCCEEDED", "timestamp": manifest.finished_at, **manifest.metrics})
        return value

    def fetch_stage():
        if source_file:
            raw_path, fetch_meta = _materialize_source_file(source_file, raw_dir, game)
        else:
            fetched = PoliteHttpClient().fetch_one(spec, raw_dir, force=force)
            raw_path = Path(fetched.raw_path)
            fetch_meta = asdict(fetched)
        return (raw_path, fetch_meta), [], [artifact_descriptor(raw_path, role="raw")], {"bytes": raw_path.stat().st_size}, []

    raw_path, fetch_meta = run_stage("fetch", fetch_stage)

    def parse_stage():
        normalized, parse_meta = parse_file(raw_path, spec)
        normalized_path = atomic_write_frame_csv(normalized, normalized_dir / f"{game}.csv")
        quality = _quality_report(normalized, spec)
        atomic_write_json(normalized_dir / f"{game}.quality.json", quality)
        if quality["status"] != "PASS":
            raise ValueError("normalized data quality failed: " + ",".join(quality["issues"]))
        return (normalized, parse_meta, normalized_path, quality), [artifact_descriptor(raw_path, role="raw")], [artifact_descriptor(normalized_path, role="normalized")], {"rows": len(normalized), "columns": len(normalized.columns)}, []

    normalized, parse_meta, normalized_path, quality = run_stage("parse_validate", parse_stage)

    def feature_stage():
        draw_features = make_draw_features(normalized, spec, windows=list(windows))
        occurrence_features = make_occurrence_features(normalized, spec, windows=list(windows))
        tables: dict[str, pd.DataFrame] = {"normalized_draws": normalized, "draw_features": draw_features}
        if not occurrence_features.empty:
            tables["occurrence_features"] = occurrence_features
        canonical_manifest = None
        if game == "loto7":
            canonical, canonical_manifest = canonicalize_loto7(normalized, source=str(raw_path))
            tables.update({
                "canonical_loto7": canonical,
                "position_loto7": to_position_table(canonical),
                "candidate_loto7": to_candidate_table(canonical),
                "candidate_features_v2": build_candidate_features(canonical, windows=windows),
            })
        bundle = write_dataset_bundle(tables, feature_dir, require_parquet=require_parquet)
        outputs = [artifact_descriptor(bundle["sqlite"], role="sqlite"), artifact_descriptor(bundle["manifest"], role="bundle_manifest")]
        metrics = {"table_count": len(tables), "total_rows": sum(len(v) for v in tables.values()), "parquet_failures": len(bundle["parquet_errors"])}
        warnings = list(bundle["parquet_errors"])
        return (tables, bundle, canonical_manifest), [artifact_descriptor(normalized_path, role="normalized")], outputs, metrics, warnings

    tables, bundle, canonical_manifest = run_stage("features_persist", feature_stage)

    postgres = None
    if postgres_dsn:
        def postgres_stage():
            written = copy_bundle_to_postgres(tables, postgres_dsn)
            return written, [artifact_descriptor(bundle["manifest"], role="bundle_manifest")], [], {"tables_written": len(written), "rows_written": sum(written.values())}, []
        postgres = run_stage("postgres", postgres_stage)

    report = {
        "schema_version": "2.1.0",
        "run_id": run_id,
        "game": game,
        "spec": asdict(spec),
        "status": "SUCCEEDED",
        "fetch": fetch_meta,
        "parse": parse_meta,
        "quality": quality,
        "normalized": str(normalized_path),
        "bundle": bundle,
        "postgres": postgres,
        "canonical_manifest": canonical_manifest.model_dump(mode="json") if canonical_manifest else None,
        "stages": stages,
        "events": str(event_path),
    }
    report_path = atomic_write_json(out / "acquisition_report.json", report)
    report["report_path"] = str(report_path)
    return report


def acquire_and_build_many(
    *,
    games: str | list[str] | tuple[str, ...] | None,
    output_dir: str | Path,
    source_files: Mapping[str, str | Path] | None = None,
    force: bool = False,
    postgres_dsn: str | None = None,
    windows: tuple[int, ...] = (5, 10, 20, 30, 50, 100),
    require_parquet: bool = False,
    continue_on_error: bool = True,
) -> dict[str, Any]:
    """Run the complete data path for several or all games with isolation."""
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    run_id = f"data-all-{uuid.uuid4().hex[:12]}"
    selected = select_lottery_specs(games)
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for spec in selected:
        try:
            result = acquire_and_build(
                game=spec.key,
                output_dir=root / spec.key,
                source_file=(source_files or {}).get(spec.key),
                force=force,
                postgres_dsn=postgres_dsn,
                windows=windows,
                require_parquet=require_parquet,
                run_id=f"{run_id}-{spec.key}",
            )
            results.append(result)
        except Exception as exc:
            failure = {"game": spec.key, "status": "FAILED", "reason": f"{type(exc).__name__}: {exc}"}
            failures.append(failure)
            if not continue_on_error:
                raise
    summary = {
        "schema_version": "2.1.0",
        "run_id": run_id,
        "status": "SUCCEEDED" if not failures else "PARTIAL" if results else "FAILED",
        "requested_games": [s.key for s in selected],
        "successful_games": [r["game"] for r in results],
        "failed_games": failures,
        "results": results,
    }
    summary_path = atomic_write_json(root / "multi_game_summary.json", summary)
    summary["summary_path"] = str(summary_path)
    return summary
