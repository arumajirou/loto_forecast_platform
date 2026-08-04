from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator

from loto.probabilistic._tracking_backends import (
    write_duckdb,
    write_mlflow,
    write_parquet,
    write_postgres,
)
from loto.probabilistic.artifact_store import ProbabilisticArtifactStore
from loto.probabilistic.config import stable_hash
from loto.probabilistic.dataset import DatasetBundle
from loto.probabilistic.subset_evaluation import (
    SubsetEvaluationResult,
    evaluate_conditional_bernoulli,
    verify_fixed_prediction,
)

BackendName = Literal["parquet", "duckdb", "postgres", "mlflow"]
_METRICS = (
    "hit_at_1",
    "all_positions_hit_at_1",
    "mae",
    "mse",
    "rmse",
    "candidate_brier",
    "candidate_ece",
    "candidate_log_loss",
    "expected_overlap",
    "joint_log_loss",
)


class ExperimentTrackingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    required_backends: list[BackendName] = Field(default_factory=lambda: ["parquet"])
    optional_backends: list[BackendName] = Field(default_factory=list)
    fail_closed: bool = True
    duckdb_path: str | None = None
    postgres_dsn: str | None = None
    postgres_dsn_env: str = "LOTO_POSTGRES_DSN"
    mlflow_uri: str | None = None
    mlflow_experiment: str = "loto-probabilistic-ppl02"
    model_revision: str = "conditional_bernoulli_fixed_k_v1"

    @model_validator(mode="after")
    def validate_backends(self) -> ExperimentTrackingConfig:
        self.required_backends = list(dict.fromkeys(self.required_backends))
        self.optional_backends = list(dict.fromkeys(self.optional_backends))
        overlap = sorted(set(self.required_backends) & set(self.optional_backends))
        if overlap:
            raise ValueError(f"tracking backends cannot be both required and optional: {overlap}")
        if self.enabled and not self.required_backends and not self.optional_backends:
            raise ValueError("enabled tracking requires at least one backend")
        return self


@dataclass(frozen=True)
class TrackingBackendResult:
    backend: str
    status: str
    required: bool
    uri: str | None
    records: int
    detail: str = ""


@dataclass(frozen=True)
class ExperimentTrackingReport:
    run_id: str
    status: str
    created_at: str
    model_id: str
    model_revision: str
    config_hash: str
    data_hash: str
    code_hash: str
    git_commit: str
    prediction_payload_sha256: str
    artifact_uri: str
    device: dict[str, Any]
    backends: tuple[TrackingBackendResult, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["backends"] = [asdict(item) for item in self.backends]
        return payload


class ExperimentPersistenceError(RuntimeError):
    def __init__(self, report: ExperimentTrackingReport):
        self.report = report
        failed = [
            item.backend for item in report.backends if item.required and item.status != "PASS"
        ]
        super().__init__(f"required tracking backends failed: {failed}")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def dataset_hash(bundle: DatasetBundle) -> str:
    digest = hashlib.sha256()
    metadata = {
        "game": bundle.game,
        "geometry": {
            "key": bundle.geometry.key,
            "family": bundle.geometry.family,
            "positions": bundle.geometry.positions,
            "value_min": bundle.geometry.value_min,
            "value_max": bundle.geometry.value_max,
        },
        "draw_ids": list(bundle.draw_ids),
        "data_version": bundle.data_version,
        "feature_set_hash": bundle.feature_set_hash,
        "draw_order_verified": bundle.draw_order_verified,
    }
    digest.update(_json(metadata).encode())
    digest.update(np.ascontiguousarray(bundle.values).tobytes())
    for array in (bundle.candidate_indicator, bundle.draw_order):
        if array is not None:
            digest.update(np.ascontiguousarray(array).tobytes())
    return digest.hexdigest()


def code_hash(repo_root: str | Path | None = None) -> str:
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[3]
    package = root / "src" / "loto" / "probabilistic"
    digest = hashlib.sha256()
    paths = sorted(package.rglob("*.py")) if package.exists() else [Path(__file__)]
    for path in paths:
        digest.update(
            path.relative_to(root).as_posix().encode() if package.exists() else path.name.encode()
        )
        digest.update(path.read_bytes())
    return digest.hexdigest()


def git_commit(repo_root: str | Path | None = None) -> str:
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[3]
    try:
        value = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
        if len(value) == 40:
            return value
    except (FileNotFoundError, subprocess.SubprocessError):
        pass
    return os.getenv("GITHUB_SHA", "UNAVAILABLE")


def device_evidence() -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "python": sys.version,
        "platform": platform.platform(),
        "pid": os.getpid(),
        "cpu_count": os.cpu_count(),
        "torch_available": False,
        "cuda_available": False,
        "cuda_device_count": 0,
        "cuda_device_names": [],
        "cuda_version": None,
    }
    try:
        import torch

        evidence.update(
            torch_available=True,
            torch_version=str(torch.__version__),
            cuda_available=bool(torch.cuda.is_available()),
            cuda_device_count=int(torch.cuda.device_count()),
            cuda_version=torch.version.cuda,
        )
        if evidence["cuda_available"]:
            evidence["cuda_device_names"] = [
                torch.cuda.get_device_name(index) for index in range(evidence["cuda_device_count"])
            ]
    except (ImportError, RuntimeError) as exc:
        evidence["torch_probe_error"] = f"{type(exc).__name__}:{str(exc)[:200]}"
    return evidence


def issue_run_id(
    *, model_id: str, created_at: str, config_hash_value: str, data_hash_value: str
) -> str:
    timestamp = datetime.fromisoformat(created_at.replace("Z", "+00:00")).astimezone(UTC)
    suffix = stable_hash(
        {
            "model_id": model_id,
            "created_at": created_at,
            "config_hash": config_hash_value,
            "data_hash": data_hash_value,
        }
    )[:10]
    return f"ppl02-{timestamp.strftime('%Y%m%d-%H%M%S')}-{suffix}"


def _config_payload(config: Any) -> dict[str, Any]:
    if hasattr(config, "model_dump"):
        return dict(config.model_dump(mode="json"))
    return dict(vars(config))


def _metric_frame(result: SubsetEvaluationResult, run_id: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    sources = [("model", None, result.model_rows)] + [
        ("baseline", name, [row for row in result.baseline_rows if row["baseline"] == name])
        for name in result.baseline_summary
    ]
    for kind, baseline, records in sources:
        for record in records:
            for key, value in record.items():
                if (
                    isinstance(value, (int, float))
                    and not isinstance(value, bool)
                    and key not in {"seed", "cutoff"}
                ):
                    rows.append(
                        {
                            "run_id": run_id,
                            "row_kind": kind,
                            "baseline": baseline,
                            "seed": int(record["seed"]),
                            "cutoff": int(record["cutoff"]),
                            "draw_id": str(record["draw_id"]),
                            "metric_name": key,
                            "metric_value": float(value),
                        }
                    )
    return pd.DataFrame(rows)


def _prediction_frame(result: SubsetEvaluationResult, run_id: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for kind, baseline, records in (
        ("model", None, result.model_rows),
        ("baseline", "*", result.baseline_rows),
    ):
        for record in records:
            rows.append(
                {
                    "run_id": run_id,
                    "row_kind": kind,
                    "baseline": record.get("baseline") if baseline == "*" else baseline,
                    "seed": int(record["seed"]),
                    "cutoff": int(record["cutoff"]),
                    "draw_id": str(record["draw_id"]),
                    "prediction_json": _json(record["prediction"]),
                    "actual_json": _json(record["actual"]),
                    "candidate_marginals_json": _json(record["candidate_marginals"]),
                    "actual_known": True,
                    "prediction_payload_sha256": None,
                }
            )
    sealed = result.prospective_prediction
    rows.append(
        {
            "run_id": run_id,
            "row_kind": "prospective",
            "baseline": None,
            "seed": None,
            "cutoff": None,
            "draw_id": sealed["payload"]["forecast_draw_id"],
            "prediction_json": _json(sealed["payload"]["prediction"]),
            "actual_json": None,
            "candidate_marginals_json": _json(sealed["payload"]["candidate_marginals"]),
            "actual_known": False,
            "prediction_payload_sha256": sealed["payload_sha256"],
        }
    )
    return pd.DataFrame(rows)


def _artifact_frame(root: Path, run_id: str) -> pd.DataFrame:
    rows = []
    for path in sorted(
        item for item in root.rglob("*") if item.is_file() and not item.name.endswith(".tmp")
    ):
        if path.name in {"ARTIFACT_MANIFEST.json", "SHA256SUMS.json"}:
            continue
        rows.append(
            {
                "run_id": run_id,
                "path": path.relative_to(root).as_posix(),
                "size": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return pd.DataFrame(rows)


def _run_record(
    result: SubsetEvaluationResult,
    bundle: DatasetBundle,
    config: Any,
    tracking: ExperimentTrackingConfig,
    *,
    created_at: str,
    repo_root: str | Path | None,
) -> dict[str, Any]:
    config_hash_value = stable_hash(_config_payload(config))
    data_hash_value = dataset_hash(bundle)
    run_id = getattr(config, "run_id", None) or issue_run_id(
        model_id=result.model_id,
        created_at=created_at,
        config_hash_value=config_hash_value,
        data_hash_value=data_hash_value,
    )
    sealed = result.prospective_prediction
    if not verify_fixed_prediction(sealed) or sealed["payload"].get("actual_known") is not False:
        raise ValueError("prospective prediction seal is invalid")
    return {
        "run_id": run_id,
        "created_at": created_at,
        "model_id": result.model_id,
        "model_revision": tracking.model_revision,
        "game": result.game,
        "status": result.status,
        "config_hash": config_hash_value,
        "data_hash": data_hash_value,
        "code_hash": code_hash(repo_root),
        "git_commit": git_commit(repo_root),
        "prediction_payload_sha256": sealed["payload_sha256"],
        "artifact_uri": Path(result.artifact_dir).resolve().as_uri(),
        "device": device_evidence(),
        "seeds": list(result.seeds),
        "cutoffs": list(result.cutoffs),
        "promotion": result.promotion,
        "actual_known": False,
    }


def persist_experiment_tracking(
    result: SubsetEvaluationResult,
    bundle: DatasetBundle,
    config: Any,
    tracking: ExperimentTrackingConfig,
    *,
    created_at: str | None = None,
    repo_root: str | Path | None = None,
) -> ExperimentTrackingReport:
    if not tracking.enabled:
        raise ValueError("tracking.enabled must be true")
    if not result.artifact_dir:
        raise ValueError("evaluation artifacts are required before persistence")
    root = Path(result.artifact_dir).resolve()
    timestamp = created_at or datetime.now(UTC).isoformat()
    record = _run_record(
        result, bundle, config, tracking, created_at=timestamp, repo_root=repo_root
    )
    store = ProbabilisticArtifactStore(root)
    store.write_json("tracking/run_record.json", record)
    frames = {
        "metrics": _metric_frame(result, record["run_id"]),
        "predictions": _prediction_frame(result, record["run_id"]),
        "artifacts": _artifact_frame(root, record["run_id"]),
    }
    outcomes: list[TrackingBackendResult] = []
    configured = [*tracking.required_backends, *tracking.optional_backends]
    for backend in configured:
        required = backend in tracking.required_backends
        try:
            if backend == "parquet":
                uri, count = write_parquet(root, record, frames)
            elif backend == "duckdb":
                path = Path(tracking.duckdb_path or root / "tracking" / "experiments.duckdb")
                uri, count = write_duckdb(path, record, frames)
            elif backend == "postgres":
                dsn = tracking.postgres_dsn or os.getenv(tracking.postgres_dsn_env)
                if not dsn:
                    raise ValueError(
                        f"PostgreSQL DSN is missing; set {tracking.postgres_dsn_env} or postgres_dsn"
                    )
                uri, count = write_postgres(dsn, record, frames)
            elif backend == "mlflow":
                if not tracking.mlflow_uri:
                    raise ValueError("mlflow_uri is required for MLflow tracking")
                summary = result.model_summary["metrics"]
                metrics = {key: float(summary[key]["mean"]) for key in _METRICS if key in summary}
                uri, count = write_mlflow(
                    tracking.mlflow_uri,
                    tracking.mlflow_experiment,
                    record,
                    metrics,
                    root,
                )
            else:  # pragma: no cover
                raise KeyError(backend)
            outcomes.append(TrackingBackendResult(backend, "PASS", required, uri, int(count)))
        except Exception as exc:  # noqa: BLE001
            outcomes.append(
                TrackingBackendResult(
                    backend,
                    "BLOCKED",
                    required,
                    None,
                    0,
                    f"{type(exc).__name__}:{str(exc)[:500]}",
                )
            )
    required_failed = any(item.required and item.status != "PASS" for item in outcomes)
    optional_failed = any(not item.required and item.status != "PASS" for item in outcomes)
    status = "BLOCKED" if required_failed else "PARTIAL" if optional_failed else "PASS"
    report = ExperimentTrackingReport(
        run_id=record["run_id"],
        status=status,
        created_at=timestamp,
        model_id=result.model_id,
        model_revision=tracking.model_revision,
        config_hash=record["config_hash"],
        data_hash=record["data_hash"],
        code_hash=record["code_hash"],
        git_commit=record["git_commit"],
        prediction_payload_sha256=record["prediction_payload_sha256"],
        artifact_uri=record["artifact_uri"],
        device=record["device"],
        backends=tuple(outcomes),
    )
    store.write_json("tracking/persistence_report.json", report.to_dict())
    store.manifest(
        metadata={
            "model_id": result.model_id,
            "game": result.game,
            "status": result.status,
            "tracking_status": status,
            "run_id": report.run_id,
            "prediction_payload_sha256": report.prediction_payload_sha256,
            "config_hash": report.config_hash,
            "data_hash": report.data_hash,
            "code_hash": report.code_hash,
            "git_commit": report.git_commit,
        }
    )
    if required_failed and tracking.fail_closed:
        raise ExperimentPersistenceError(report)
    return report


def evaluate_and_persist_conditional_bernoulli(
    bundle: DatasetBundle,
    config: Any,
    tracking: ExperimentTrackingConfig,
    *,
    output_dir: str | Path,
    fixed_at: str | None = None,
    created_at: str | None = None,
    repo_root: str | Path | None = None,
) -> tuple[SubsetEvaluationResult, ExperimentTrackingReport]:
    result = evaluate_conditional_bernoulli(
        bundle, config, output_dir=output_dir, fixed_at=fixed_at
    )
    return result, persist_experiment_tracking(
        result, bundle, config, tracking, created_at=created_at, repo_root=repo_root
    )


def query_duckdb_runs(
    path: str | Path,
    *,
    model_id: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    if not 1 <= limit <= 10000:
        raise ValueError("limit must be in [1, 10000]")
    import duckdb

    clauses, parameters = [], []
    if model_id is not None:
        clauses.append("model_id = ?")
        parameters.append(model_id)
    if status is not None:
        clauses.append("status = ?")
        parameters.append(status)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    connection = duckdb.connect(str(path), read_only=True)
    try:
        frame = connection.execute(
            "SELECT * FROM ppl02_runs" + where + " ORDER BY created_at DESC LIMIT ?",
            [*parameters, limit],
        ).fetchdf()
    finally:
        connection.close()
    return frame.to_dict(orient="records")


__all__ = [
    "ExperimentPersistenceError",
    "ExperimentTrackingConfig",
    "ExperimentTrackingReport",
    "TrackingBackendResult",
    "code_hash",
    "dataset_hash",
    "device_evidence",
    "evaluate_and_persist_conditional_bernoulli",
    "git_commit",
    "issue_run_id",
    "persist_experiment_tracking",
    "query_duckdb_runs",
]
