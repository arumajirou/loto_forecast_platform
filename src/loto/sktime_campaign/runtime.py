from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import tempfile
import traceback
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from loto.sktime_campaign.inventory import (
    SELECTED_TAGS,
    discover_forecasters,
    installed_sktime_version,
    summarize_inventory,
)
from loto.sktime_campaign.matrix import run_smoke_matrix
from loto.sktime_campaign.protocol import (
    ProviderOperation,
    ProviderRequest,
    ProviderResponse,
    ProviderStatus,
)


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        text=True,
    )
    os.close(descriptor)
    temporary_path = Path(temporary)
    try:
        temporary_path.write_text(text, encoding="utf-8")
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _write_json(path: Path, payload: Any) -> None:
    _atomic_write_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_inventory_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "name",
        "class_path",
        "constructor_signature",
        "package_version",
        "dependency_state",
        "import_status",
        "construct_status",
        "fit_status",
        "predict_status",
        "save_load_status",
        "tags_json",
    ]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                **{field: row[field] for field in fields if field != "tags_json"},
                "tags_json": json.dumps(row["tags"], sort_keys=True),
            }
        )
    _atomic_write_text(path, buffer.getvalue())


def _selected_instance_tags(forecaster: Any) -> dict[str, Any]:
    tags = forecaster.get_tags()
    selected: dict[str, Any] = {}
    for name in SELECTED_TAGS:
        if name not in tags:
            continue
        value = tags[name]
        if value is None or isinstance(value, (bool, int, float, str)):
            selected[name] = value
        elif isinstance(value, (list, tuple, set, frozenset)):
            selected[name] = [str(item) for item in value]
        else:
            selected[name] = repr(value)
    return selected


def _validate_prediction(
    prediction: pd.Series,
    *,
    expected_index: list[int],
) -> np.ndarray:
    values = prediction.to_numpy(dtype=float)
    if values.shape != (len(expected_index),):
        raise RuntimeError(
            f"prediction shape mismatch: expected {(len(expected_index),)}, got {values.shape}"
        )
    if not np.isfinite(values).all():
        raise RuntimeError("prediction contains NaN or Inf")
    actual_index = [int(value) for value in prediction.index.tolist()]
    if actual_index != expected_index:
        raise RuntimeError(
            f"prediction index mismatch: expected {expected_index}, got {actual_index}"
        )
    return values


def run_naive_smoke(request: ProviderRequest, output_dir: Path) -> dict[str, Any]:
    """Fit, predict, save, load, and re-predict a core NaiveForecaster."""

    try:
        from sktime.forecasting.naive import NaiveForecaster
    except Exception as exc:
        raise RuntimeError(f"unable to import NaiveForecaster: {exc}") from exc

    index = pd.RangeIndex(
        start=1,
        stop=len(request.series) + 1,
        step=1,
        name="draw_no",
    )
    target = pd.Series(request.series, index=index, name="y", dtype=float)
    expected_index = [len(target) + step for step in request.forecast_horizon]

    forecaster = NaiveForecaster(strategy=request.strategy)
    class_tags = _selected_instance_tags(forecaster)
    forecaster.fit(target, fh=request.forecast_horizon)
    prediction = forecaster.predict(fh=request.forecast_horizon)
    values_before = _validate_prediction(prediction, expected_index=expected_index)

    save_load: dict[str, Any] = {"requested": request.save_load}
    values_after = values_before.copy()
    if request.save_load:
        model_base = output_dir / "naive_forecaster"
        archive = forecaster.save(model_base)
        archive.close()
        model_archive = output_dir / "naive_forecaster.zip"
        if not model_archive.is_file() or model_archive.stat().st_size <= 0:
            raise RuntimeError("NaiveForecaster save did not create a non-empty zip")
        loaded = type(forecaster).load_from_path(model_archive)
        prediction_after = loaded.predict(fh=request.forecast_horizon)
        values_after = _validate_prediction(
            prediction_after,
            expected_index=expected_index,
        )
        if not np.array_equal(values_before, values_after):
            raise RuntimeError("save/load/re-predict values changed")
        save_load = {
            "requested": True,
            "status": "PASS",
            "artifact": model_archive.name,
            "artifact_sha256": _sha256(model_archive),
            "exact_prediction_match": True,
        }

    return {
        "model_name": request.model_name,
        "strategy": request.strategy,
        "device": "cpu",
        "cpu_fallback": False,
        "input_rows": len(target),
        "input_index_kind": "RangeIndex",
        "forecast_horizon": request.forecast_horizon,
        "expected_prediction_index": expected_index,
        "prediction_shape": list(values_before.shape),
        "prediction_finite": True,
        "prediction_before_save": values_before.tolist(),
        "prediction_after_load": values_after.tolist(),
        "instance_tags": class_tags,
        "fit_status": "PASS",
        "predict_status": "PASS",
        "save_load": save_load,
    }


def _write_response_bundle(output_dir: Path, response: ProviderResponse) -> None:
    response.artifacts.setdefault("response", "response.json")
    response.artifacts.setdefault("manifest", "ARTIFACT_MANIFEST.json")
    response.artifacts.setdefault("sha256sums", "SHA256SUMS")
    response_path = output_dir / "response.json"
    _write_json(response_path, response.model_dump(mode="json"))

    existing = sorted(
        path
        for path in output_dir.iterdir()
        if path.is_file() and path.name not in {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
    )
    manifest = {
        "schema_version": "1.0",
        "status": response.status.value,
        "operation": response.operation.value,
        "files": [
            {
                "path": path.name,
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
            for path in existing
        ],
    }
    manifest_path = output_dir / "ARTIFACT_MANIFEST.json"
    _write_json(manifest_path, manifest)

    hashed = sorted(
        path for path in output_dir.iterdir() if path.is_file() and path.name != "SHA256SUMS"
    )
    lines = [f"{_sha256(path)}  {path.name}" for path in hashed]
    _atomic_write_text(output_dir / "SHA256SUMS", "\n".join(lines) + "\n")


def execute_request(request: ProviderRequest) -> ProviderResponse:
    """Execute one fail-closed provider request and persist durable evidence."""

    output_dir = Path(request.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    actual_version: str | None = None
    try:
        actual_version = installed_sktime_version()
        if actual_version != request.expected_sktime_version:
            raise RuntimeError(
                "sktime version mismatch: "
                f"expected {request.expected_sktime_version}, got {actual_version}"
            )

        if request.operation is ProviderOperation.INVENTORY:
            rows = discover_forecasters()
            _write_json(output_dir / "FORECASTER_INVENTORY.json", rows)
            _write_inventory_csv(output_dir / "FORECASTER_INVENTORY.csv", rows)
            summary = summarize_inventory(rows)
            _write_json(output_dir / "INVENTORY_SUMMARY.json", summary)
            response = ProviderResponse(
                status=ProviderStatus.PASS,
                operation=request.operation,
                environment_lane=request.environment_lane,
                expected_sktime_version=request.expected_sktime_version,
                actual_sktime_version=actual_version,
                inventory=summary,
                artifacts={
                    "inventory_json": "FORECASTER_INVENTORY.json",
                    "inventory_csv": "FORECASTER_INVENTORY.csv",
                    "inventory_summary": "INVENTORY_SUMMARY.json",
                },
            )
        elif request.operation is ProviderOperation.NAIVE_SMOKE:
            smoke = run_naive_smoke(request, output_dir)
            _write_json(output_dir / "NAIVE_SMOKE.json", smoke)
            response = ProviderResponse(
                status=ProviderStatus.PASS,
                operation=request.operation,
                environment_lane=request.environment_lane,
                expected_sktime_version=request.expected_sktime_version,
                actual_sktime_version=actual_version,
                smoke=smoke,
                artifacts={"naive_smoke": "NAIVE_SMOKE.json"},
            )
        elif request.operation is ProviderOperation.SMOKE_MATRIX:
            matrix = run_smoke_matrix(request, output_dir)
            _write_json(output_dir / "SMOKE_MATRIX.json", matrix)
            response = ProviderResponse(
                status=ProviderStatus(matrix["status"]),
                operation=request.operation,
                environment_lane=request.environment_lane,
                expected_sktime_version=request.expected_sktime_version,
                actual_sktime_version=actual_version,
                matrix=matrix,
                artifacts={"smoke_matrix": "SMOKE_MATRIX.json"},
            )
        else:  # pragma: no cover - enum validation prevents this path
            raise RuntimeError(f"unsupported operation: {request.operation}")
    except Exception as exc:
        unavailable = "not installed" in str(exc) or "unable to import" in str(exc)
        response = ProviderResponse(
            status=(ProviderStatus.UNAVAILABLE if unavailable else ProviderStatus.FAILED),
            operation=request.operation,
            environment_lane=request.environment_lane,
            expected_sktime_version=request.expected_sktime_version,
            actual_sktime_version=actual_version,
            error={
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            },
        )

    _write_response_bundle(output_dir, response)
    return response
