from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np
from numpy.typing import ArrayLike, NDArray

from loto.probabilistic.math.elementary_symmetric import log_elementary_symmetric
from loto.probabilistic.math.kdpp import PreparedKDPP, prepare_kdpp, sample_kdpp
from loto.probabilistic.models.kdpp_native import (
    MODEL_ID,
    MODEL_REVISION,
    KDPPChronologyEvidence,
    KDPPDegeneracyStatus,
    KDPPFixedKRequest,
    KDPPFixedKResponse,
    KDPPGame,
    KDPPKernelType,
    KDPPPointForecastSemantics,
    KDPPPSDRepairPolicy,
    KDPPTargetLayout,
    _validate_game_geometry,
)

RUNTIME_REVISION = "k_dpp_fixed_k_runtime_v1"
FloatArray = NDArray[np.float64]
FloatMatrix = NDArray[np.float64]


class KDPPKernelMode(StrEnum):
    HISTORICAL_RBF = "HISTORICAL_RBF"
    DIAGONAL_CONTROL = "DIAGONAL_CONTROL"
    PRECOMPUTED_TEST_ONLY = "PRECOMPUTED_TEST_ONLY"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def array_sha256(value: ArrayLike) -> str:
    array = np.ascontiguousarray(np.asarray(value))
    header = _json({"dtype": array.dtype.str, "shape": list(array.shape)})
    return _sha(header.encode() + array.tobytes(order="C"))


def feature_evidence_sha256(
    training_indicators: ArrayLike,
    item_features: ArrayLike | None = None,
) -> str:
    payload = {
        "training": array_sha256(training_indicators),
        "features": None if item_features is None else array_sha256(item_features),
    }
    return _sha(_json(payload).encode())


def _safe_root(root: str) -> None:
    path = PurePosixPath(root)
    if not root or path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise ValueError("artifact root must be a safe relative POSIX path")
    if "\\" in root:
        raise ValueError("artifact root must use POSIX separators")


@dataclass(frozen=True)
class KDPPSavedArtifacts:
    state_json: Path
    state_npz: Path
    manifest_json: Path
    sha256sums: Path

    @property
    def paths(self) -> tuple[Path, ...]:
        return self.state_json, self.state_npz, self.manifest_json, self.sha256sums

    def relative_paths(self, root: str = "runtime") -> tuple[str, ...]:
        _safe_root(root)
        return tuple(f"{root}/{path.name}" for path in self.paths)


@dataclass(frozen=True)
class KDPPState:
    model_id: str
    model_revision: str
    runtime_revision: str
    game: KDPPGame
    target_layout: KDPPTargetLayout
    item_ids: tuple[str, ...]
    cardinality: int
    context_length: int
    training_rows: int
    seed: int
    kernel_mode: KDPPKernelMode
    rbf_gamma: float | None
    quality_pseudocount: float
    psd_tolerance: float
    feature_cutoff: int
    training_matrix_sha256: str
    feature_matrix_sha256: str
    kernel_sha256: str
    kernel_shape: tuple[int, int]
    minimum_eigenvalue: float
    kernel_rank: int
    effective_rank: float
    log_normalizer: float
    kernel_off_diagonal_norm: float
    kernel_off_diagonal_ratio: float
    degeneracy_status: KDPPDegeneracyStatus
    state_sha256: str

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> KDPPState:
        expected = set(cls.__dataclass_fields__)
        if set(payload) != expected:
            raise ValueError("state metadata keys do not match the strict schema")
        payload = dict(payload)
        payload["game"] = KDPPGame(payload["game"])
        payload["target_layout"] = KDPPTargetLayout(payload["target_layout"])
        payload["kernel_mode"] = KDPPKernelMode(payload["kernel_mode"])
        payload["degeneracy_status"] = KDPPDegeneracyStatus(payload["degeneracy_status"])
        payload["item_ids"] = tuple(payload["item_ids"])
        payload["kernel_shape"] = tuple(payload["kernel_shape"])
        state = cls(**payload)
        state.validate()
        return state

    def validate(self) -> None:
        hashes = (
            self.training_matrix_sha256,
            self.feature_matrix_sha256,
            self.kernel_sha256,
            self.state_sha256,
        )
        if any(
            len(value) != 64 or not set(value) <= set("0123456789abcdef")
            for value in hashes
        ):
            raise ValueError("state hashes must be lowercase SHA-256")
        if self.model_id != MODEL_ID or self.model_revision != MODEL_REVISION:
            raise ValueError("state model identity mismatch")
        if self.runtime_revision != RUNTIME_REVISION:
            raise ValueError("state runtime revision mismatch")
        if self.kernel_shape != (len(self.item_ids), len(self.item_ids)):
            raise ValueError("state kernel shape mismatch")
        if self.kernel_rank < self.cardinality or self.cardinality < 1:
            raise ValueError("state rank/cardinality mismatch")
        _validate_game_geometry(
            game=self.game,
            target_layout=self.target_layout,
            item_ids=self.item_ids,
            cardinality=self.cardinality,
        )


def _training_matrix(
    value: ArrayLike,
    item_count: int,
) -> tuple[NDArray[np.int64], int]:
    raw = np.asarray(value)
    if raw.ndim != 2 or raw.shape[0] < 2 or raw.shape[1] != item_count:
        raise ValueError("training_indicators must have shape (rows >= 2, item_count)")
    if not np.isfinite(raw).all() or not np.isin(raw, (0, 1)).all():
        raise ValueError("training_indicators must contain finite 0/1 values")
    training = raw.astype(np.int64, copy=False)
    sums = training.sum(axis=1)
    cardinality = int(sums[0])
    if cardinality < 1 or cardinality >= item_count or not np.all(sums == cardinality):
        raise ValueError("training rows must share a valid fixed cardinality")
    return training, cardinality


def _features(
    training: NDArray[np.int64],
    supplied: ArrayLike | None,
) -> FloatMatrix:
    if supplied is not None:
        values = np.asarray(supplied, dtype=np.float64)
        if (
            values.ndim != 2
            or values.shape[0] != training.shape[1]
            or values.shape[1] < 1
        ):
            raise ValueError("item_features shape must be (item_count, feature_count >= 1)")
        if not np.isfinite(values).all():
            raise ValueError("item_features must be finite")
        return values
    rows = training.shape[0]
    cooccurrence = (training.T @ training).astype(np.float64) / rows
    frequency = training.sum(axis=0, dtype=np.float64)[:, None] / rows
    return np.concatenate([cooccurrence, frequency], axis=1)


def _quality(
    training: NDArray[np.int64],
    pseudocount: float,
) -> FloatArray:
    if not math.isfinite(pseudocount) or pseudocount <= 0.0:
        raise ValueError("quality_pseudocount must be finite and positive")
    weights = training.sum(axis=0, dtype=np.float64) + pseudocount
    log_weights = np.log(weights) - float(np.log(weights).mean())
    return np.exp(0.5 * log_weights).astype(np.float64)


def _rbf(item_features: FloatMatrix, gamma: float) -> FloatMatrix:
    if not math.isfinite(gamma) or gamma <= 0.0:
        raise ValueError("rbf_gamma must be finite and positive")
    scale = item_features.std(axis=0, keepdims=True)
    standardized = (
        item_features - item_features.mean(axis=0, keepdims=True)
    ) / np.where(scale > 0.0, scale, 1.0)
    norms = np.sum(standardized * standardized, axis=1)
    distances = np.maximum(
        norms[:, None] + norms[None, :] - 2.0 * standardized @ standardized.T,
        0.0,
    )
    similarity = np.exp(-distances / (2.0 * gamma * gamma))
    similarity = 0.5 * (similarity + similarity.T)
    np.fill_diagonal(similarity, 1.0)
    return similarity.astype(np.float64)


def _diagnostics(
    prepared: PreparedKDPP,
    tolerance: float,
) -> dict[str, Any]:
    positive = prepared.eigenvalues > tolerance
    rank = int(np.count_nonzero(positive))
    if rank < prepared.cardinality:
        raise ValueError("KERNEL_RANK_BELOW_CARDINALITY")
    mass = float(prepared.eigenvalues.sum())
    probabilities = prepared.eigenvalues[positive] / mass
    effective_rank = float(np.exp(-np.sum(probabilities * np.log(probabilities))))
    off_diagonal = prepared.kernel - np.diag(np.diag(prepared.kernel))
    off_norm = float(np.linalg.norm(off_diagonal, ord="fro"))
    total_norm = float(np.linalg.norm(prepared.kernel, ord="fro"))
    ratio = 0.0 if total_norm == 0.0 else off_norm / total_norm
    degeneracy = (
        KDPPDegeneracyStatus.DEGENERATE
        if off_norm == 0.0 or ratio == 0.0
        else KDPPDegeneracyStatus.DIVERSE_KERNEL
    )
    return {
        "minimum_eigenvalue": float(prepared.psd_evidence.min_eigenvalue_after),
        "kernel_rank": rank,
        "effective_rank": effective_rank,
        "log_normalizer": float(prepared.log_normalizer),
        "kernel_off_diagonal_norm": off_norm,
        "kernel_off_diagonal_ratio": ratio,
        "degeneracy_status": degeneracy,
    }


def kdpp_marginal_inclusion_probabilities(
    prepared: PreparedKDPP,
) -> FloatArray:
    eigenvalues = prepared.eigenvalues
    logs = np.full(eigenvalues.shape, -np.inf, dtype=np.float64)
    logs[eigenvalues > 0.0] = np.log(eigenvalues[eigenvalues > 0.0])
    coefficients = np.zeros_like(eigenvalues)
    for index, eigenvalue in enumerate(eigenvalues):
        if eigenvalue > 0.0:
            excluding = log_elementary_symmetric(
                np.delete(logs, index),
                prepared.cardinality - 1,
            )
            coefficients[index] = math.exp(
                math.log(float(eigenvalue))
                + excluding
                - prepared.log_normalizer
            )
    marginal_kernel = (
        prepared.eigenvectors * coefficients
    ) @ prepared.eigenvectors.T
    marginals = np.clip(
        np.diag(marginal_kernel),
        0.0,
        1.0,
    ).astype(np.float64)
    if not np.isfinite(marginals).all() or not np.isclose(
        marginals.sum(),
        prepared.cardinality,
        atol=1e-8,
        rtol=1e-8,
    ):
        raise RuntimeError("k-DPP marginals failed finite or sum-to-k checks")
    return marginals


def _state_hash(
    payload: dict[str, Any],
    kernel: FloatMatrix,
    quality: FloatArray,
    features: FloatMatrix,
) -> str:
    material = {
        "metadata": payload,
        "kernel": array_sha256(kernel),
        "quality": array_sha256(quality),
        "features": array_sha256(features),
    }
    return _sha(_json(material).encode())


class KDPPFixedKPrivateRuntime:
    public_registration = False
    runtime_status = "PRIVATE_RUNTIME_IMPLEMENTED"

    def __init__(
        self,
        state: KDPPState,
        kernel: ArrayLike,
        quality: ArrayLike,
        item_features: ArrayLike,
    ) -> None:
        state.validate()
        self.metadata = state
        self.kernel = np.asarray(kernel, dtype=np.float64)
        self.quality_scores = np.asarray(quality, dtype=np.float64)
        self.item_features = np.asarray(item_features, dtype=np.float64)
        if array_sha256(self.kernel) != state.kernel_sha256:
            raise ValueError("loaded kernel hash mismatch")
        self.prepared = prepare_kdpp(
            self.kernel,
            state.cardinality,
            tolerance=state.psd_tolerance,
            repair_psd=False,
        )
        if self.prepared.psd_evidence.symmetrized:
            raise ValueError("loaded kernel required forbidden symmetrization")
        if self.prepared.psd_evidence.repaired:
            raise ValueError("loaded kernel required forbidden PSD repair")
        current = _diagnostics(self.prepared, state.psd_tolerance)
        for key, actual in current.items():
            expected = getattr(state, key)
            if isinstance(actual, float):
                if not math.isclose(
                    actual,
                    float(expected),
                    rel_tol=1e-10,
                    abs_tol=1e-10,
                ):
                    raise ValueError(f"loaded {key} mismatch")
            elif actual != expected:
                raise ValueError(f"loaded {key} mismatch")

    @classmethod
    def fit(
        cls,
        training_indicators: ArrayLike,
        *,
        item_ids: tuple[str, ...],
        game: KDPPGame,
        target_layout: KDPPTargetLayout,
        context_length: int,
        chronology_evidence: KDPPChronologyEvidence,
        seed: int,
        item_features: ArrayLike | None = None,
        kernel_mode: KDPPKernelMode = KDPPKernelMode.HISTORICAL_RBF,
        rbf_gamma: float = 1.0,
        quality_pseudocount: float = 0.5,
        psd_tolerance: float = 1e-10,
    ) -> KDPPFixedKPrivateRuntime:
        if target_layout is KDPPTargetLayout.POSITION_QUALIFIED_SHARED:
            raise ValueError(
                "shared layout requires a partition-constrained sampler"
            )
        training, cardinality = _training_matrix(
            training_indicators,
            len(item_ids),
        )
        _validate_game_geometry(
            game=game,
            target_layout=target_layout,
            item_ids=item_ids,
            cardinality=cardinality,
        )
        expected_rows = chronology_evidence.train_end - chronology_evidence.train_start + 1
        if expected_rows != len(training):
            raise ValueError("chronology train range must exactly match training rows")
        feature_hash = feature_evidence_sha256(training, item_features)
        if chronology_evidence.feature_matrix_sha256 != feature_hash:
            raise ValueError(
                "chronology feature_matrix_sha256 does not match fit inputs"
            )
        features = _features(training, item_features)
        quality = _quality(training, quality_pseudocount)
        if kernel_mode is KDPPKernelMode.HISTORICAL_RBF:
            similarity = _rbf(features, rbf_gamma)
            stored_gamma: float | None = rbf_gamma
        elif kernel_mode is KDPPKernelMode.DIAGONAL_CONTROL:
            similarity = np.eye(len(item_ids), dtype=np.float64)
            stored_gamma = None
        else:
            raise ValueError("PRECOMPUTED_TEST_ONLY is not accepted by fit")
        kernel = np.outer(quality, quality) * similarity
        return cls._build(
            kernel,
            quality,
            features,
            item_ids=item_ids,
            game=game,
            target_layout=target_layout,
            cardinality=cardinality,
            context_length=context_length,
            training_rows=len(training),
            seed=seed,
            kernel_mode=kernel_mode,
            rbf_gamma=stored_gamma,
            quality_pseudocount=quality_pseudocount,
            psd_tolerance=psd_tolerance,
            feature_cutoff=chronology_evidence.feature_cutoff,
            training_hash=array_sha256(training),
            feature_hash=feature_hash,
        )

    @classmethod
    def from_precomputed_kernel(
        cls,
        kernel: ArrayLike,
        *,
        item_ids: tuple[str, ...],
        game: KDPPGame,
        target_layout: KDPPTargetLayout,
        cardinality: int,
        context_length: int,
        feature_cutoff: int,
        feature_matrix_sha256: str,
        seed: int,
        psd_tolerance: float = 1e-10,
    ) -> KDPPFixedKPrivateRuntime:
        if target_layout is KDPPTargetLayout.POSITION_QUALIFIED_SHARED:
            raise ValueError(
                "shared layout requires a partition-constrained sampler"
            )
        values = np.asarray(kernel, dtype=np.float64)
        if values.shape != (len(item_ids), len(item_ids)):
            raise ValueError("precomputed kernel shape must match item_ids")
        _validate_game_geometry(
            game=game,
            target_layout=target_layout,
            item_ids=item_ids,
            cardinality=cardinality,
        )
        features = np.empty((len(item_ids), 0), dtype=np.float64)
        quality = np.sqrt(np.clip(np.diag(values), 0.0, None))
        return cls._build(
            values,
            quality,
            features,
            item_ids=item_ids,
            game=game,
            target_layout=target_layout,
            cardinality=cardinality,
            context_length=context_length,
            training_rows=1,
            seed=seed,
            kernel_mode=KDPPKernelMode.PRECOMPUTED_TEST_ONLY,
            rbf_gamma=None,
            quality_pseudocount=1.0,
            psd_tolerance=psd_tolerance,
            feature_cutoff=feature_cutoff,
            training_hash=array_sha256(values),
            feature_hash=feature_matrix_sha256,
        )

    @classmethod
    def _build(
        cls,
        kernel: FloatMatrix,
        quality: FloatArray,
        features: FloatMatrix,
        **values: Any,
    ) -> KDPPFixedKPrivateRuntime:
        prepared = prepare_kdpp(
            kernel,
            int(values["cardinality"]),
            tolerance=float(values["psd_tolerance"]),
            repair_psd=False,
        )
        if prepared.psd_evidence.symmetrized:
            raise ValueError("kernel failed strict symmetry policy")
        if prepared.psd_evidence.repaired:
            raise ValueError("kernel failed strict PSD repair policy")
        payload = {
            "model_id": MODEL_ID,
            "model_revision": MODEL_REVISION,
            "runtime_revision": RUNTIME_REVISION,
            "game": values["game"],
            "target_layout": values["target_layout"],
            "item_ids": values["item_ids"],
            "cardinality": values["cardinality"],
            "context_length": values["context_length"],
            "training_rows": values["training_rows"],
            "seed": values["seed"],
            "kernel_mode": values["kernel_mode"],
            "rbf_gamma": values["rbf_gamma"],
            "quality_pseudocount": values["quality_pseudocount"],
            "psd_tolerance": values["psd_tolerance"],
            "feature_cutoff": values["feature_cutoff"],
            "training_matrix_sha256": values["training_hash"],
            "feature_matrix_sha256": values["feature_hash"],
            "kernel_sha256": array_sha256(kernel),
            "kernel_shape": kernel.shape,
            **_diagnostics(prepared, float(values["psd_tolerance"])),
        }
        state_hash = _state_hash(
            payload,
            kernel,
            quality,
            features,
        )
        state = KDPPState.from_dict(
            {**payload, "state_sha256": state_hash}
        )
        return cls(state, kernel, quality, features)

    @property
    def marginals(self) -> FloatArray:
        return kdpp_marginal_inclusion_probabilities(self.prepared)

    def predict(
        self,
        request: KDPPFixedKRequest,
        *,
        samples_per_horizon: int,
        artifact_paths: tuple[str, ...],
    ) -> KDPPFixedKResponse:
        state = self.metadata
        checks = {
            request.game == state.game,
            request.target_layout == state.target_layout,
            request.item_ids == state.item_ids,
            request.cardinality == state.cardinality,
            request.context_length == state.context_length,
            request.kernel_sha256 == state.kernel_sha256,
            request.kernel_shape == state.kernel_shape,
            request.chronology_evidence.feature_matrix_sha256
            == state.feature_matrix_sha256,
            request.chronology_evidence.feature_cutoff == state.feature_cutoff,
            request.weight_sha256 in {None, state.state_sha256},
        }
        if False in checks:
            raise ValueError("predict request does not match fitted state")
        if samples_per_horizon < 1 or samples_per_horizon > 100_000:
            raise ValueError("samples_per_horizon must be in [1, 100000]")
        marginal_row = tuple(float(value) for value in self.marginals)
        points: list[tuple[str, ...]] = []
        all_samples: list[tuple[tuple[str, ...], ...]] = []
        for horizon in range(request.prediction_length):
            seed_sequence = np.random.SeedSequence([request.seed, horizon])
            rng = np.random.default_rng(seed_sequence)
            samples = tuple(
                tuple(
                    state.item_ids[index]
                    for index in sample_kdpp(self.prepared, rng=rng)
                )
                for _ in range(samples_per_horizon)
            )
            points.append(samples[0])
            all_samples.append(samples)
        return KDPPFixedKResponse(
            schema_version=request.schema_version,
            run_id=request.run_id,
            model_id=request.model_id,
            package_version=request.package_version,
            source_revision=request.source_revision,
            model_revision=request.model_revision,
            config_sha256=request.config_sha256,
            weight_sha256=state.state_sha256,
            license=request.license,
            game=request.game,
            target_layout=request.target_layout,
            context_length=request.context_length,
            prediction_length=request.prediction_length,
            seed=request.seed,
            requested_device="cpu",
            effective_device="cpu",
            cpu_fallback=False,
            input_shape=state.kernel_shape,
            output_shape=(request.prediction_length, state.cardinality),
            point_forecast=tuple(points),
            quantiles=None,
            samples=tuple(all_samples),
            finite_check=True,
            chronology_evidence=request.chronology_evidence,
            actuals_used=False,
            runtime_pid=os.getpid(),
            gpu_uuid=None,
            gpu_process_vram_mb=None,
            gpu_not_applicable=True,
            artifact_paths=artifact_paths,
            kernel_type=KDPPKernelType.L_ENSEMBLE,
            kernel_shape=state.kernel_shape,
            kernel_sha256=state.kernel_sha256,
            item_ids=state.item_ids,
            cardinality=state.cardinality,
            psd_tolerance=state.psd_tolerance,
            psd_repair_policy=KDPPPSDRepairPolicy.REJECT,
            symmetry_check=True,
            psd_check=True,
            minimum_eigenvalue=state.minimum_eigenvalue,
            kernel_rank=state.kernel_rank,
            effective_rank=state.effective_rank,
            log_normalizer=state.log_normalizer,
            kernel_off_diagonal_norm=state.kernel_off_diagonal_norm,
            kernel_off_diagonal_ratio=state.kernel_off_diagonal_ratio,
            degeneracy_status=state.degeneracy_status,
            marginal_inclusion_probabilities=tuple(
                marginal_row
                for _ in range(request.prediction_length)
            ),
            exact_cardinality_check=True,
            duplicate_check=True,
            point_forecast_semantics=(
                KDPPPointForecastSemantics.SEEDED_EXACT_SAMPLE
            ),
        )

    def save(self, directory: str | Path) -> KDPPSavedArtifacts:
        root = Path(directory)
        root.mkdir(parents=True, exist_ok=True)
        artifacts = KDPPSavedArtifacts(
            root / "kdpp_state.json",
            root / "kdpp_state.npz",
            root / "artifact_manifest.json",
            root / "SHA256SUMS",
        )
        artifacts.state_json.write_text(
            json.dumps(asdict(self.metadata), sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        np.savez_compressed(
            artifacts.state_npz,
            kernel=self.kernel,
            quality=self.quality_scores,
            item_features=self.item_features,
        )
        core = {
            artifacts.state_json.name: _file_sha(artifacts.state_json),
            artifacts.state_npz.name: _file_sha(artifacts.state_npz),
        }
        artifacts.manifest_json.write_text(
            json.dumps(
                {
                    "state_sha256": self.metadata.state_sha256,
                    "files": core,
                },
                sort_keys=True,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        records = {
            **core,
            artifacts.manifest_json.name: _file_sha(artifacts.manifest_json),
        }
        artifacts.sha256sums.write_text(
            "".join(
                f"{value}  {name}\n"
                for name, value in sorted(records.items())
            ),
            encoding="utf-8",
        )
        _verify_inventory(artifacts)
        return artifacts

    @classmethod
    def load(cls, directory: str | Path) -> KDPPFixedKPrivateRuntime:
        root = Path(directory)
        artifacts = KDPPSavedArtifacts(
            root / "kdpp_state.json",
            root / "kdpp_state.npz",
            root / "artifact_manifest.json",
            root / "SHA256SUMS",
        )
        _verify_inventory(artifacts)
        payload = json.loads(artifacts.state_json.read_text(encoding="utf-8"))
        state = KDPPState.from_dict(payload)
        with np.load(artifacts.state_npz, allow_pickle=False) as arrays:
            kernel = np.asarray(arrays["kernel"], dtype=np.float64)
            quality = np.asarray(arrays["quality"], dtype=np.float64)
            features = np.asarray(arrays["item_features"], dtype=np.float64)
        hash_payload = asdict(state)
        saved_hash = hash_payload.pop("state_sha256")
        if _state_hash(hash_payload, kernel, quality, features) != saved_hash:
            raise ValueError("loaded state SHA-256 verification failed")
        return cls(state, kernel, quality, features)


def _verify_inventory(artifacts: KDPPSavedArtifacts) -> None:
    if not all(path.is_file() for path in artifacts.paths):
        raise ValueError("state artifact set is incomplete")
    records: dict[str, str] = {}
    for line in artifacts.sha256sums.read_text(encoding="utf-8").splitlines():
        digest, separator, name = line.partition("  ")
        if not separator or name in records:
            raise ValueError("invalid SHA256SUMS record")
        records[name] = digest
    expected = {
        artifacts.state_json.name,
        artifacts.state_npz.name,
        artifacts.manifest_json.name,
    }
    if set(records) != expected:
        raise ValueError("SHA256SUMS inventory mismatch")
    for name, digest in records.items():
        if _file_sha(artifacts.state_json.parent / name) != digest:
            raise ValueError(f"SHA-256 mismatch for {name}")


def prediction_sha256(response: KDPPFixedKResponse) -> str:
    payload = response.model_dump(mode="json")
    payload.pop("runtime_pid", None)
    return _sha(_json(payload).encode())
