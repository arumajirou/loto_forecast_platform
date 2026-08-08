from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from loto.orchestration.pipeline_ledger import PipelineLedgerRecorder

EXPECTED_PIPELINE_BLOB_SHA = "98a323f91577f17292b474d566f9c1e58139c799"


class StagedPipelineError(RuntimeError):
    """Base error for staged trusted-vertical-slice execution."""


class StagedPipelinePreflightError(StagedPipelineError):
    """Raised before computation when the audited lane cannot be guaranteed."""


class StagedPipelineBlocked(StagedPipelineError):
    """Raised when computation completed but governance evidence did not pass."""


@dataclass(frozen=True)
class PipelineComponents:
    np: Any
    pd: Any
    canonicalize_loto7: Callable[..., Any]
    save_manifest: Callable[..., None]
    to_candidate_table: Callable[..., Any]
    build_candidate_features: Callable[..., Any]
    build_next_candidate_features: Callable[..., Any]
    feature_manifest: Callable[..., Any]
    UniformCandidateAdapter: Any
    FrequencyCandidateAdapter: Any
    PositionFrequencyAdapter: Any
    decode_hybrid: Callable[..., Any]
    evaluate_draws: Callable[..., dict[str, float]]
    brier_score: Callable[..., float]
    log_loss: Callable[..., float]
    ForecastPackage: Any
    CandidateProbability: Any
    seal_payload: Callable[..., dict[str, Any]]
    verify_seal: Callable[..., bool]
    collect_gpu_evidence: Callable[..., dict[str, Any]]


Clock = Callable[[], datetime]
RecorderFactory = Callable[..., PipelineLedgerRecorder]


def _default_components() -> PipelineComponents:
    import numpy as np
    import pandas as pd

    from loto.contracts import CandidateProbability, ForecastPackage
    from loto.data.canonical import canonicalize_loto7, save_manifest, to_candidate_table
    from loto.decoding.hybrid import decode_hybrid
    from loto.evaluation.metrics import brier_score, evaluate_draws, log_loss
    from loto.features.pipeline import (
        build_candidate_features,
        build_next_candidate_features,
        feature_manifest,
    )
    from loto.models.baselines import FrequencyCandidateAdapter, UniformCandidateAdapter
    from loto.models.position import PositionFrequencyAdapter
    from loto.observability.gpu import collect_gpu_evidence
    from loto.sealing.manifest import seal_payload, verify_seal

    return PipelineComponents(
        np=np,
        pd=pd,
        canonicalize_loto7=canonicalize_loto7,
        save_manifest=save_manifest,
        to_candidate_table=to_candidate_table,
        build_candidate_features=build_candidate_features,
        build_next_candidate_features=build_next_candidate_features,
        feature_manifest=feature_manifest,
        UniformCandidateAdapter=UniformCandidateAdapter,
        FrequencyCandidateAdapter=FrequencyCandidateAdapter,
        PositionFrequencyAdapter=PositionFrequencyAdapter,
        decode_hybrid=decode_hybrid,
        evaluate_draws=evaluate_draws,
        brier_score=brier_score,
        log_loss=log_loss,
        ForecastPackage=ForecastPackage,
        CandidateProbability=CandidateProbability,
        seal_payload=seal_payload,
        verify_seal=verify_seal,
        collect_gpu_evidence=collect_gpu_evidence,
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC)


def git_blob_sha(path: Path) -> str:
    content = path.read_bytes()
    header = f"blob {len(content)}\0".encode("ascii")
    return hashlib.sha1(header + content).hexdigest()  # noqa: S324 - Git object identity


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(path.expanduser()))


def _reject_symlink_components(path: Path, *, label: str) -> None:
    absolute = _absolute(path)
    for candidate in (absolute, *absolute.parents):
        if candidate.exists() and candidate.is_symlink():
            raise StagedPipelinePreflightError(
                f"{label} must not contain a symlink component: {candidate}"
            )


def _require_regular_file(path: Path, *, label: str) -> None:
    _reject_symlink_components(path, label=label)
    if not path.is_file():
        raise StagedPipelinePreflightError(f"{label} is not a regular file: {path}")


def _require_empty_output(path: Path) -> None:
    _reject_symlink_components(path, label="output")
    if path.exists() and not path.is_dir():
        raise StagedPipelinePreflightError(f"output is not a directory: {path}")
    if path.exists() and any(path.iterdir()):
        raise StagedPipelinePreflightError("staged pipeline requires an empty output directory")
    path.mkdir(parents=True, exist_ok=True)


def _atomic_write_json(path: Path, payload: Any) -> None:
    if path.is_symlink():
        raise StagedPipelineBlocked(f"artifact path is a symlink: {path}")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    if temporary.exists() or temporary.is_symlink():
        temporary.unlink()
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            handle.write(text)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _candidate_targets(numbers: list[int], np: Any) -> Any:
    target = np.zeros(37, dtype=float)
    target[np.asarray(numbers) - 1] = 1
    return target


def _metric_bundle(
    *,
    actual: Any,
    predicted: Any,
    targets: Any,
    probabilities: Any,
    components: PipelineComponents,
) -> dict[str, float]:
    result = components.evaluate_draws(actual, predicted)
    result.update(
        {
            "brier": components.brier_score(targets, probabilities),
            "log_loss": components.log_loss(targets, probabilities),
        }
    )
    return result


def _manifest_value(manifest: Any, name: str) -> Any:
    if hasattr(manifest, name):
        return getattr(manifest, name)
    if isinstance(manifest, dict):
        return manifest[name]
    raise TypeError(f"manifest does not expose {name}")


def _model_dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return value
    raise TypeError(f"artifact does not support model_dump: {type(value).__name__}")
