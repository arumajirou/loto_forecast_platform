from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import inspect
import os
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .p6_contract import (
    ArtifactFile,
    DistributionMode,
    FailureCategory,
    P6CheckState,
    P6DatasetItem,
    P6PredictorManifest,
    P6ProviderRequest,
    P6StageEvidence,
    P6Status,
    artifact_tree_sha256,
    manifest_sha256,
    sha256_json,
)
from .p6_registry import LIGHTNING_TRAINER, get_model_spec


@dataclass(frozen=True)
class RuntimeBindings:
    np: Any
    pd: Any
    torch: Any
    list_dataset: Any
    predictor_class: Any
    estimators: dict[str, Any]
    student_t_output: Any


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

    estimators = {}
    for model_class in (
        "DeepNPTSEstimator",
        "DeepAREstimator",
        "TiDEEstimator",
        "SimpleFeedForwardEstimator",
        "TemporalFusionTransformerEstimator",
        "WaveNetEstimator",
        "DLinearEstimator",
        "PatchTSTEstimator",
        "LagTSTEstimator",
    ):
        spec = get_model_spec(model_class)
        module = importlib.import_module(spec.module_path)
        estimators[model_class] = getattr(module, model_class)
    return RuntimeBindings(
        np=np,
        pd=pd,
        torch=torch,
        list_dataset=ListDataset,
        predictor_class=Predictor,
        estimators=estimators,
        student_t_output=StudentTOutput,
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
        valid = gluonts_release == (0, 16, 3) and torch_release == (2, 9, 1)
        return valid, "compat requires GluonTS 0.16.3 and Torch 2.9.1"
    valid = gluonts_release == (0, 17, 0) and (2, 10, 0) <= torch_release < (3, 0, 0)
    return valid, "latest requires GluonTS 0.17.0 and Torch >=2.10,<3"


def _checks(names: tuple[str, ...]) -> dict[str, P6CheckState]:
    return {name: P6CheckState.NOT_RUN for name in names}


def _failure(
    request: P6ProviderRequest,
    checks: dict[str, P6CheckState],
    category: FailureCategory,
    error: str,
    *,
    status: P6Status = P6Status.FAILED,
    fit_process_id: int | None = None,
    manifest_sha: str | None = None,
    distribution_output: str | None = None,
) -> P6StageEvidence:
    return P6StageEvidence(
        lane=request.lane,
        operation=request.operation,
        model_class=request.model_class,
        distribution_output=distribution_output or request.distribution_output or "UNRESOLVED",
        status=status,
        process_id=os.getpid(),
        fit_process_id=fit_process_id,
        prediction_length=request.prediction_length,
        expected_shape=[request.prediction_length],
        artifact_manifest_sha256=manifest_sha,
        failure_category=category,
        checks=checks,
        errors=[error],
    )


def _default_distribution(spec: Any) -> str:
    return spec.certified_distributions[0]


def _resolve_distribution(
    request: P6ProviderRequest,
    spec: Any,
    runtime: RuntimeBindings,
) -> tuple[str, Any | None]:
    requested = request.distribution_output or _default_distribution(spec)
    if requested not in spec.certified_distributions:
        raise ValueError(
            f"distribution {requested!r} is not certified for {spec.model_class}"
        )
    if spec.distribution_mode is DistributionMode.STUDENT_T:
        return requested, runtime.student_t_output()
    return requested, None


def _replace_tokens(value: Any, replacements: dict[str, Any]) -> Any:
    if isinstance(value, str) and value in replacements:
        return replacements[value]
    if isinstance(value, list):
        return [_replace_tokens(item, replacements) for item in value]
    if isinstance(value, dict):
        return {key: _replace_tokens(item, replacements) for key, item in value.items()}
    return value


def constructor_arguments(
    request: P6ProviderRequest,
    spec: Any,
    distribution: Any | None,
) -> dict[str, Any]:
    if not spec.supports_context_length and request.context_length is not None:
        raise ValueError(f"{spec.model_class} derives context length and rejects overrides")
    context_length = request.context_length or spec.default_context_length
    replacements = {
        "$freq": request.freq,
        "$prediction_length": request.prediction_length,
        "$context_length": context_length,
        "$trainer_kwargs": dict(LIGHTNING_TRAINER),
        "$distribution": distribution,
    }
    arguments = _replace_tokens(spec.constructor_profile, replacements)
    unknown = sorted(set(request.constructor_overrides) - set(arguments))
    if unknown:
        raise KeyError(f"unsupported constructor override keys: {unknown}")

    def bounded(default: Any, override: Any, path: str) -> Any:
        if isinstance(default, bool):
            if not isinstance(override, bool):
                raise OverflowError(f"{path} must remain boolean")
            return override
        if isinstance(default, (int, float)) and not isinstance(default, bool):
            if not isinstance(override, (int, float)) or isinstance(override, bool):
                raise OverflowError(f"{path} must remain numeric")
            if override < 0 or override > default:
                raise OverflowError(f"{path} exceeds the bounded certification profile")
            return override
        if isinstance(default, str):
            if override != default:
                raise OverflowError(f"{path} cannot change in certification mode")
            return override
        if isinstance(default, list):
            if not isinstance(override, list) or len(override) != len(default):
                raise OverflowError(f"{path} list shape cannot change")
            return [
                bounded(default_value, override_value, f"{path}[{index}]")
                for index, (default_value, override_value) in enumerate(
                    zip(default, override)
                )
            ]
        if isinstance(default, dict):
            if not isinstance(override, dict):
                raise OverflowError(f"{path} must remain a mapping")
            extra = sorted(set(override) - set(default))
            if extra:
                raise OverflowError(f"{path} contains unsupported keys: {extra}")
            merged = dict(default)
            for key, value in override.items():
                merged[key] = bounded(default[key], value, f"{path}.{key}")
            return merged
        if override != default:
            raise OverflowError(f"{path} cannot change in certification mode")
        return override

    for key, value in request.constructor_overrides.items():
        arguments[key] = bounded(arguments[key], value, key)
    limits = spec.resource_limits
    if arguments.get("epochs", 1) > limits.max_epochs:
        raise OverflowError("epochs exceed the P6 certification limit")
    if arguments.get("num_batches_per_epoch", 1) > limits.max_batches_per_epoch:
        raise OverflowError("num_batches_per_epoch exceeds the P6 certification limit")
    if arguments.get("batch_size", 1) > limits.max_batch_size:
        raise OverflowError("batch_size exceeds the P6 certification limit")
    if arguments.get("num_parallel_samples", 1) > limits.max_parallel_samples:
        raise OverflowError("num_parallel_samples exceeds the P6 certification limit")
    if request.threads_per_job != limits.threads_per_job:
        raise OverflowError("threads_per_job violates the P6 certification limit")
    return arguments


def validate_signature(estimator_class: Any, spec: Any, arguments: dict[str, Any]) -> str:
    signature = inspect.signature(estimator_class)
    parameters = signature.parameters
    accepts_kwargs = any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )
    unsupported = sorted(
        key for key in arguments if key not in parameters and not accepts_kwargs
    )
    if unsupported:
        raise TypeError(f"constructor signature rejects arguments: {unsupported}")
    missing_contract = sorted(
        key for key in spec.required_constructor_parameters if key not in parameters
    )
    if missing_contract and not accepts_kwargs:
        raise TypeError(f"constructor signature is missing required parameters: {missing_contract}")
    return str(signature)


def _seed(runtime: RuntimeBindings, seed: int) -> None:
    random.seed(seed)
    runtime.np.random.seed(seed)
    runtime.torch.manual_seed(seed)
    runtime.torch.set_num_threads(1)


def _dataset_payload(items: list[P6DatasetItem]) -> list[dict[str, Any]]:
    return [item.model_dump(mode="json") for item in items]


def _dataset(payload: list[dict[str, Any]], freq: str, runtime: RuntimeBindings) -> Any:
    rows = []
    for item in payload:
        row = {
            "item_id": item["item_id"],
            "start": runtime.pd.Period(item["start"], freq=freq),
            "target": runtime.np.asarray(item["target"], dtype=runtime.np.float32),
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


def _forecast(predictor: Any, dataset: Any, runtime: RuntimeBindings) -> list[float]:
    forecast = next(iter(predictor.predict(dataset)))
    values = runtime.np.asarray(forecast.mean, dtype=float).reshape(-1)
    return [float(value) for value in values]


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
        if path.is_file() and path.name != "p6_predictor_manifest.json"
    ]
    if not files:
        raise ValueError("serialized predictor directory contains no files")
    return files


def verify_artifact_directory(root: Path) -> tuple[P6PredictorManifest, str]:
    manifest = P6PredictorManifest.model_validate_json(
        (root / "p6_predictor_manifest.json").read_text("utf-8")
    )
    observed = collect_artifact_files(root)
    if observed != manifest.files:
        raise ValueError("serialized predictor file inventory mismatch")
    if artifact_tree_sha256(observed) != manifest.tree_sha256:
        raise ValueError("serialized predictor tree SHA-256 mismatch")
    return manifest, manifest_sha256(manifest)
