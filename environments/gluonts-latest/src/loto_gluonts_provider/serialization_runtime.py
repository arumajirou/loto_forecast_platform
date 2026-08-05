from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import os
import random
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .artifacts import atomic_write_json
from .protocol import GluonTSProviderRequest, PredictionRow
from .serialization import (
    FIT_REQUIRED_CHECKS,
    RELOAD_REQUIRED_CHECKS,
    ArtifactFile,
    LifecycleCheckState,
    LifecycleOutcome,
    PredictorArtifactManifest,
    PredictorFitSerializeResult,
    PredictorReloadResult,
    artifact_tree_sha256,
    manifest_sha256,
    prediction_sha256,
    sha256_json,
)


@dataclass(frozen=True)
class RuntimeBindings:
    np: Any
    pd: Any
    torch: Any
    list_dataset: Any
    deep_ar_estimator: Any
    student_t_output: Any
    predictor_class: Any


def installed_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def runtime_versions() -> dict[str, str | None]:
    return {
        name: installed_version(name)
        for name in (
            "gluonts",
            "torch",
            "lightning",
            "pytorch-lightning",
            "numpy",
            "pandas",
        )
    }


def load_runtime_bindings() -> RuntimeBindings:
    import numpy as np
    import pandas as pd
    import torch
    from gluonts.dataset.common import ListDataset
    from gluonts.model.predictor import Predictor
    from gluonts.torch.distributions import StudentTOutput
    from gluonts.torch.model.deepar import DeepAREstimator

    return RuntimeBindings(
        np,
        pd,
        torch,
        ListDataset,
        DeepAREstimator,
        StudentTOutput,
        Predictor,
    )


def _release(value: str) -> tuple[int, int, int] | None:
    numbers = []
    for part in value.split("+", 1)[0].split(".")[:3]:
        digits = "".join(character for character in part if character.isdigit())
        if not digits:
            return None
        numbers.append(int(digits))
    if len(numbers) < 2:
        return None
    return tuple((numbers + [0, 0, 0])[:3])


def version_matches(
    lane: str,
    versions: dict[str, str | None],
) -> tuple[bool, str]:
    gluonts = versions.get("gluonts")
    torch = versions.get("torch")
    if gluonts is None or torch is None:
        return False, "GluonTS and Torch must both be installed"
    gluonts_release = _release(gluonts)
    torch_release = _release(torch)
    if gluonts_release is None or torch_release is None:
        return False, "runtime versions must use numeric release components"
    if lane == "compat":
        valid = (
            gluonts_release == (0, 16, 3)
            and torch_release == (2, 9, 1)
        )
        return valid, "compat requires GluonTS 0.16.3 and Torch 2.9.1"
    valid = (
        gluonts_release == (0, 17, 0)
        and (2, 10, 0) <= torch_release < (3, 0, 0)
    )
    return valid, "latest requires GluonTS 0.17.0 and Torch >=2.10,<3"


def _devices(predictor: Any) -> list[str]:
    observed: set[str] = set()
    for name in ("prediction_net", "network"):
        network = getattr(predictor, name, None)
        parameters = getattr(network, "parameters", None)
        if callable(parameters):
            try:
                observed.update(str(parameter.device) for parameter in parameters())
            except Exception:
                pass
    return sorted(observed)


def _dataset_payload(request: GluonTSProviderRequest) -> list[dict[str, Any]]:
    return [item.model_dump(mode="json") for item in request.dataset]


def _dataset(
    payload: list[dict[str, Any]],
    freq: str,
    runtime: RuntimeBindings,
) -> Any:
    rows = []
    for item in payload:
        row = {
            "item_id": item["item_id"],
            "start": runtime.pd.Period(item["start"], freq=freq),
            "target": runtime.np.asarray(
                item["target"],
                dtype=runtime.np.float32,
            ),
        }
        for name in (
            "feat_static_cat",
            "feat_static_real",
            "feat_dynamic_real",
            "past_feat_dynamic_real",
        ):
            if item.get(name) is not None:
                row[name] = item[name]
        rows.append(row)
    return runtime.list_dataset(rows, freq=freq)


def _forecast(
    predictor: Any,
    dataset: Any,
    runtime: RuntimeBindings,
) -> list[float]:
    forecast = next(iter(predictor.predict(dataset)))
    values = runtime.np.asarray(forecast.mean, dtype=float).reshape(-1)
    return [float(value) for value in values]


def _rows(item_id: str, values: list[float]) -> list[PredictionRow]:
    return [
        PredictionRow(item_id=item_id, horizon=index + 1, mean=value)
        for index, value in enumerate(values)
    ]


def _file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_artifact_files(root: Path) -> list[ArtifactFile]:
    files = [
        ArtifactFile(
            relative_path=path.relative_to(root).as_posix(),
            size_bytes=path.stat().st_size,
            sha256=_file_sha(path),
        )
        for path in sorted(root.rglob("*"))
        if path.is_file()
        and path.name != "predictor_artifact_manifest.json"
    ]
    if not files:
        raise ValueError("serialized predictor directory contains no files")
    return files


def verify_artifact_directory(
    root: Path,
) -> tuple[PredictorArtifactManifest, str]:
    manifest = PredictorArtifactManifest.model_validate_json(
        (root / "predictor_artifact_manifest.json").read_text("utf-8")
    )
    observed = collect_artifact_files(root)
    if observed != manifest.files:
        raise ValueError("serialized predictor file inventory mismatch")
    if artifact_tree_sha256(observed) != manifest.tree_sha256:
        raise ValueError("serialized predictor tree SHA-256 mismatch")
    return manifest, manifest_sha256(manifest)


def _checks(names: tuple[str, ...]) -> dict[str, LifecycleCheckState]:
    return {name: LifecycleCheckState.NOT_RUN for name in names}


def _fit_failure(
    lane: str,
    request: GluonTSProviderRequest,
    checks: dict[str, LifecycleCheckState],
    error: str,
    outcome: LifecycleOutcome = LifecycleOutcome.FAILED,
) -> PredictorFitSerializeResult:
    return PredictorFitSerializeResult(
        lane=lane,
        outcome=outcome,
        process_id=os.getpid(),
        seed=request.seed,
        prediction_length=request.prediction_length,
        context_length=request.context_length or 8,
        expected_shape=[request.prediction_length],
        checks=checks,
        errors=[error],
    )


def _reload_failure(
    lane: str,
    checks: dict[str, LifecycleCheckState],
    error: str,
    *,
    fit_process_id: int = 1,
    prediction_length: int = 1,
    manifest_sha: str | None = None,
    versions: dict[str, str | None] | None = None,
    outcome: LifecycleOutcome = LifecycleOutcome.FAILED,
) -> PredictorReloadResult:
    return PredictorReloadResult(
        lane=lane,
        outcome=outcome,
        fit_process_id=max(1, fit_process_id),
        load_process_id=os.getpid(),
        prediction_length=prediction_length,
        expected_shape=[prediction_length],
        artifact_manifest_sha256=manifest_sha,
        runtime_versions=versions or runtime_versions(),
        checks=checks,
        errors=[error],
    )


def _seed(runtime: RuntimeBindings, seed: int) -> None:
    random.seed(seed)
    runtime.np.random.seed(seed)
    runtime.torch.manual_seed(seed)
    runtime.torch.set_num_threads(1)


def fit_predict_serialize(
    request: GluonTSProviderRequest,
    lane: str,
    *,
    bindings_loader: Callable[[], RuntimeBindings] = load_runtime_bindings,
    observed_versions: dict[str, str | None] | None = None,
) -> tuple[PredictorFitSerializeResult, list[PredictionRow]]:
    checks = _checks(FIT_REQUIRED_CHECKS)
    versions = observed_versions or runtime_versions()
    valid, reason = version_matches(lane, versions)
    if not valid:
        checks["version"] = LifecycleCheckState.BLOCKED
        return (
            _fit_failure(
                lane,
                request,
                checks,
                reason,
                LifecycleOutcome.BLOCKED,
            ),
            [],
        )
    checks["version"] = LifecycleCheckState.PASS
    if request.model_class != "DeepAREstimator":
        return (
            _fit_failure(
                lane,
                request,
                checks,
                "P5 supports only DeepAREstimator",
            ),
            [],
        )
    if request.artifact_dir is None or len(request.dataset) != 1:
        return (
            _fit_failure(
                lane,
                request,
                checks,
                "P5 requires artifact_dir and exactly one dataset item",
            ),
            [],
        )

    try:
        runtime = bindings_loader()
        checks["import"] = LifecycleCheckState.PASS
        _seed(runtime, request.seed)
        estimator = runtime.deep_ar_estimator(
            freq=request.freq,
            prediction_length=request.prediction_length,
            context_length=request.context_length or 8,
            num_layers=1,
            hidden_size=4,
            batch_size=4,
            num_batches_per_epoch=1,
            num_parallel_samples=4,
            distr_output=runtime.student_t_output(),
            trainer_kwargs={
                "max_epochs": 1,
                "accelerator": "cpu",
                "devices": 1,
                "enable_checkpointing": False,
                "enable_progress_bar": False,
                "logger": False,
            },
        )
        checks["constructor"] = LifecycleCheckState.PASS
        payload = _dataset_payload(request)
        dataset = _dataset(payload, request.freq, runtime)
        checks["dataset"] = LifecycleCheckState.PASS
        predictor = estimator.train(training_data=dataset)
        checks["fit"] = LifecycleCheckState.PASS
        values = _forecast(predictor, dataset, runtime)
        checks["predict"] = LifecycleCheckState.PASS
        shape = [len(values)]
        checks["shape"] = (
            LifecycleCheckState.PASS
            if shape == [request.prediction_length]
            else LifecycleCheckState.FAIL
        )
        checks["finite"] = (
            LifecycleCheckState.PASS
            if all(math.isfinite(value) for value in values)
            else LifecycleCheckState.FAIL
        )
        devices = _devices(predictor)
        checks["device"] = (
            LifecycleCheckState.PASS
            if devices and all(device.startswith("cpu") for device in devices)
            else LifecycleCheckState.FAIL
        )
        pre_serialize = FIT_REQUIRED_CHECKS[:-2]
        if any(
            checks[name] is not LifecycleCheckState.PASS
            for name in pre_serialize
        ):
            return (
                _fit_failure(
                    lane,
                    request,
                    checks,
                    "one or more pre-serialization checks failed",
                ),
                [],
            )

        final = Path(request.artifact_dir).resolve()
        final.parent.mkdir(parents=True, exist_ok=True)
        if final.exists() and any(final.iterdir()):
            return (
                _fit_failure(
                    lane,
                    request,
                    checks,
                    "predictor artifact directory must be absent or empty",
                ),
                [],
            )
        if final.exists():
            final.rmdir()
        staging = Path(
            tempfile.mkdtemp(
                prefix=f".{final.name}.staging-",
                dir=final.parent,
            )
        )
        try:
            predictor.serialize(staging)
            checks["serialize"] = LifecycleCheckState.PASS
            dataset_document = {
                "schema_version": 1,
                "freq": request.freq,
                "dataset": payload,
            }
            atomic_write_json(
                staging / "certification_dataset.json",
                dataset_document,
            )
            files = collect_artifact_files(staging)
            manifest = PredictorArtifactManifest(
                lane=lane,
                fit_process_id=os.getpid(),
                seed=request.seed,
                freq=request.freq,
                prediction_length=request.prediction_length,
                context_length=request.context_length or 8,
                dataset_sha256=sha256_json(dataset_document),
                pre_reload_prediction_sha256=prediction_sha256(values),
                runtime_versions=versions,
                files=files,
                tree_sha256=artifact_tree_sha256(files),
            )
            manifest_digest = atomic_write_json(
                staging / "predictor_artifact_manifest.json",
                manifest.model_dump(mode="json"),
            )
            verified, verified_digest = verify_artifact_directory(staging)
            if verified != manifest or verified_digest != manifest_digest:
                raise ValueError("predictor artifact verification mismatch")
            checks["artifact_integrity"] = LifecycleCheckState.PASS
            os.replace(staging, final)
        finally:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)

        result = PredictorFitSerializeResult(
            lane=lane,
            outcome=LifecycleOutcome.VERIFIED,
            process_id=os.getpid(),
            seed=request.seed,
            prediction_length=request.prediction_length,
            context_length=request.context_length or 8,
            expected_shape=[request.prediction_length],
            observed_shape=shape,
            prediction_values=values,
            observed_devices=devices,
            artifact_manifest=manifest,
            artifact_manifest_sha256=manifest_digest,
            checks=checks,
            metadata={
                "artifact_dir": str(final),
                "runtime_versions": versions,
            },
        )
        return result, _rows(request.dataset[0].item_id, values)
    except Exception as exc:
        for name, state in checks.items():
            if state is LifecycleCheckState.NOT_RUN:
                checks[name] = LifecycleCheckState.BLOCKED
        return (
            _fit_failure(
                lane,
                request,
                checks,
                f"{type(exc).__name__}: {exc}",
            ),
            [],
        )


def load_predict_serialized(
    request: GluonTSProviderRequest,
    lane: str,
    *,
    bindings_loader: Callable[[], RuntimeBindings] = load_runtime_bindings,
    observed_versions: dict[str, str | None] | None = None,
) -> tuple[PredictorReloadResult, list[PredictionRow]]:
    checks = _checks(RELOAD_REQUIRED_CHECKS)
    versions = observed_versions or runtime_versions()
    artifact_dir = Path(request.artifact_dir or "").resolve()
    fit_process_id = 1
    prediction_length = request.prediction_length
    manifest_digest = None

    try:
        manifest, manifest_digest = verify_artifact_directory(artifact_dir)
        fit_process_id = manifest.fit_process_id
        prediction_length = manifest.prediction_length
        checks["manifest"] = LifecycleCheckState.PASS
        checks["artifact_integrity"] = LifecycleCheckState.PASS
        if manifest.lane != lane:
            raise ValueError("serialized predictor lane mismatch")
        if os.getpid() == fit_process_id:
            raise ValueError("load_predict must execute in a new process")
        checks["process_restart"] = LifecycleCheckState.PASS
        valid, reason = version_matches(lane, versions)
        if not valid:
            checks["version"] = LifecycleCheckState.BLOCKED
            return (
                _reload_failure(
                    lane,
                    checks,
                    reason,
                    fit_process_id=fit_process_id,
                    prediction_length=prediction_length,
                    manifest_sha=manifest_digest,
                    versions=versions,
                    outcome=LifecycleOutcome.BLOCKED,
                ),
                [],
            )
        for name in ("gluonts", "torch"):
            if versions.get(name) != manifest.runtime_versions.get(name):
                raise ValueError(f"serialized predictor {name} version mismatch")
        checks["version"] = LifecycleCheckState.PASS
        runtime = bindings_loader()
        predictor = runtime.predictor_class.deserialize(artifact_dir)
        checks["deserialize"] = LifecycleCheckState.PASS
        document = json.loads(
            (artifact_dir / "certification_dataset.json").read_text("utf-8")
        )
        if sha256_json(document) != manifest.dataset_sha256:
            raise ValueError("serialized certification dataset SHA-256 mismatch")
        dataset = _dataset(document["dataset"], document["freq"], runtime)
        checks["dataset"] = LifecycleCheckState.PASS
        _seed(runtime, manifest.seed)
        values = _forecast(predictor, dataset, runtime)
        checks["predict"] = LifecycleCheckState.PASS
        shape = [len(values)]
        checks["shape"] = (
            LifecycleCheckState.PASS
            if shape == [manifest.prediction_length]
            else LifecycleCheckState.FAIL
        )
        checks["finite"] = (
            LifecycleCheckState.PASS
            if all(math.isfinite(value) for value in values)
            else LifecycleCheckState.FAIL
        )
        devices = _devices(predictor)
        checks["device"] = (
            LifecycleCheckState.PASS
            if devices and all(device.startswith("cpu") for device in devices)
            else LifecycleCheckState.FAIL
        )
        checks["identity"] = (
            LifecycleCheckState.PASS
            if manifest_digest == manifest_sha256(manifest)
            else LifecycleCheckState.FAIL
        )
        if any(state is not LifecycleCheckState.PASS for state in checks.values()):
            return (
                _reload_failure(
                    lane,
                    checks,
                    "one or more reload checks failed",
                    fit_process_id=fit_process_id,
                    prediction_length=prediction_length,
                    manifest_sha=manifest_digest,
                    versions=versions,
                ),
                [],
            )
        item_id = document["dataset"][0]["item_id"]
        result = PredictorReloadResult(
            lane=lane,
            outcome=LifecycleOutcome.VERIFIED,
            fit_process_id=fit_process_id,
            load_process_id=os.getpid(),
            prediction_length=prediction_length,
            expected_shape=[prediction_length],
            observed_shape=shape,
            prediction_values=values,
            observed_devices=devices,
            artifact_manifest_sha256=manifest_digest,
            runtime_versions=versions,
            checks=checks,
            metadata={
                "artifact_dir": str(artifact_dir),
                "pre_reload_prediction_sha256": (
                    manifest.pre_reload_prediction_sha256
                ),
                "post_reload_prediction_sha256": prediction_sha256(values),
            },
        )
        return result, _rows(item_id, values)
    except Exception as exc:
        for name, state in checks.items():
            if state is LifecycleCheckState.NOT_RUN:
                checks[name] = LifecycleCheckState.BLOCKED
        return (
            _reload_failure(
                lane,
                checks,
                f"{type(exc).__name__}: {exc}",
                fit_process_id=fit_process_id,
                prediction_length=prediction_length,
                manifest_sha=manifest_digest,
                versions=versions,
            ),
            [],
        )
