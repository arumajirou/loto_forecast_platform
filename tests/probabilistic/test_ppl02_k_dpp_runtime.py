from __future__ import annotations

import itertools
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from loto.probabilistic.math.elementary_symmetric import fixed_cardinality_marginals
from loto.probabilistic.models.kdpp_native import (
    MODEL_ID,
    MODEL_REVISION,
    SCHEMA_VERSION,
    KDPPChronologyEvidence,
    KDPPDegeneracyStatus,
    KDPPFixedKRequest,
    KDPPGame,
    KDPPKernelType,
    KDPPPSDRepairPolicy,
    KDPPTargetLayout,
)
from loto.probabilistic.models.kdpp_runtime import (
    KDPPFixedKPrivateRuntime,
    KDPPKernelMode,
    array_sha256,
    feature_evidence_sha256,
    kdpp_marginal_inclusion_probabilities,
    prediction_sha256,
)

SHA = "a" * 64
GIT_SHA = "b" * 40


def miniloto_training(rows: int = 64) -> np.ndarray:
    values = np.zeros((rows, 31), dtype=np.int64)
    for row in range(rows):
        chosen = [(row + offset * 6) % 31 for offset in range(5)]
        values[row, chosen] = 1
    return values


def chronology(training: np.ndarray) -> KDPPChronologyEvidence:
    return KDPPChronologyEvidence(
        train_start=0,
        train_end=len(training) - 1,
        validation_start=None,
        validation_end=None,
        forecast_origin=len(training),
        future_actuals_available=False,
        known_future_covariates=(),
        feature_cutoff=len(training) - 1,
        feature_matrix_sha256=feature_evidence_sha256(training),
    )


def fit_runtime(
    *,
    kernel_mode: KDPPKernelMode = KDPPKernelMode.HISTORICAL_RBF,
) -> tuple[KDPPFixedKPrivateRuntime, np.ndarray, KDPPChronologyEvidence]:
    training = miniloto_training()
    evidence = chronology(training)
    runtime = KDPPFixedKPrivateRuntime.fit(
        training,
        item_ids=tuple(str(index) for index in range(1, 32)),
        game=KDPPGame.MINILOTO,
        target_layout=KDPPTargetLayout.UNORDERED_FIXED_CARDINALITY,
        context_length=len(training),
        chronology_evidence=evidence,
        seed=7,
        kernel_mode=kernel_mode,
        rbf_gamma=1.25,
        quality_pseudocount=0.5,
        psd_tolerance=1e-10,
    )
    return runtime, training, evidence


def prediction_request(
    runtime: KDPPFixedKPrivateRuntime,
    evidence: KDPPChronologyEvidence,
    *,
    prediction_length: int = 5,
    seed: int = 123,
) -> KDPPFixedKRequest:
    return KDPPFixedKRequest(
        schema_version=SCHEMA_VERSION,
        run_id="kdpp-runtime-test",
        model_id=MODEL_ID,
        package_version="3.2.0",
        source_revision=GIT_SHA,
        model_revision=MODEL_REVISION,
        config_sha256=SHA,
        weight_sha256=runtime.metadata.state_sha256,
        license="MIT",
        game=runtime.metadata.game,
        target_layout=runtime.metadata.target_layout,
        context_length=runtime.metadata.context_length,
        prediction_length=prediction_length,
        seed=seed,
        requested_device="cpu",
        chronology_evidence=evidence,
        actuals_used=False,
        kernel_type=KDPPKernelType.L_ENSEMBLE,
        kernel_shape=runtime.metadata.kernel_shape,
        kernel_sha256=runtime.metadata.kernel_sha256,
        item_ids=runtime.metadata.item_ids,
        cardinality=runtime.metadata.cardinality,
        psd_tolerance=runtime.metadata.psd_tolerance,
        psd_repair_policy=KDPPPSDRepairPolicy.REJECT,
    )


def test_historical_fit_is_psd_finite_and_train_only() -> None:
    runtime, training, evidence = fit_runtime()
    metadata = runtime.metadata
    assert metadata.kernel_mode is KDPPKernelMode.HISTORICAL_RBF
    assert metadata.feature_cutoff == len(training) - 1
    assert metadata.feature_matrix_sha256 == evidence.feature_matrix_sha256
    assert metadata.kernel_sha256 == array_sha256(runtime.kernel)
    assert metadata.kernel_rank >= metadata.cardinality
    assert np.isfinite(metadata.log_normalizer)
    assert metadata.minimum_eigenvalue >= -metadata.psd_tolerance
    assert metadata.degeneracy_status is KDPPDegeneracyStatus.DIVERSE_KERNEL
    assert np.allclose(runtime.kernel, runtime.kernel.T, atol=1e-12, rtol=0.0)


def test_chronology_hash_mismatch_fails_closed() -> None:
    training = miniloto_training()
    evidence = chronology(training).model_copy(
        update={"feature_matrix_sha256": "c" * 64}
    )
    with pytest.raises(ValueError, match="feature_matrix_sha256"):
        KDPPFixedKPrivateRuntime.fit(
            training,
            item_ids=tuple(str(index) for index in range(1, 32)),
            game=KDPPGame.MINILOTO,
            target_layout=KDPPTargetLayout.UNORDERED_FIXED_CARDINALITY,
            context_length=len(training),
            chronology_evidence=evidence,
            seed=7,
        )


def test_shared_position_runtime_fails_closed_until_partition_sampler_exists() -> None:
    training = np.zeros((12, 30), dtype=np.int64)
    for row in range(12):
        training[row, row % 10] = 1
        training[row, 10 + ((row + 1) % 10)] = 1
        training[row, 20 + ((row + 2) % 10)] = 1
    item_ids = tuple(
        f"n{position}:{digit}"
        for position in range(1, 4)
        for digit in range(10)
    )
    evidence = KDPPChronologyEvidence(
        train_start=0,
        train_end=11,
        validation_start=None,
        validation_end=None,
        forecast_origin=12,
        future_actuals_available=False,
        known_future_covariates=(),
        feature_cutoff=11,
        feature_matrix_sha256=feature_evidence_sha256(training),
    )
    with pytest.raises(ValueError, match="partition-constrained"):
        KDPPFixedKPrivateRuntime.fit(
            training,
            item_ids=item_ids,
            game=KDPPGame.NUMBERS3,
            target_layout=KDPPTargetLayout.POSITION_QUALIFIED_SHARED,
            context_length=12,
            chronology_evidence=evidence,
            seed=1,
        )


def test_diagonal_control_matches_conditional_bernoulli_marginals() -> None:
    runtime, _, _ = fit_runtime(kernel_mode=KDPPKernelMode.DIAGONAL_CONTROL)
    diagonal = np.diag(runtime.kernel)
    expected = fixed_cardinality_marginals(
        np.log(diagonal), runtime.metadata.cardinality
    )
    assert runtime.metadata.degeneracy_status is KDPPDegeneracyStatus.DEGENERATE
    assert runtime.metadata.kernel_off_diagonal_norm == 0.0
    assert np.allclose(runtime.marginals, expected, atol=1e-10, rtol=1e-10)


def test_exact_marginals_match_exhaustive_enumeration() -> None:
    kernel = np.asarray(
        [
            [2.0, 0.2, 0.1, 0.0, 0.0, 0.0],
            [0.2, 1.8, 0.2, 0.1, 0.0, 0.0],
            [0.1, 0.2, 1.6, 0.2, 0.1, 0.0],
            [0.0, 0.1, 0.2, 1.4, 0.2, 0.1],
            [0.0, 0.0, 0.1, 0.2, 1.2, 0.2],
            [0.0, 0.0, 0.0, 0.1, 0.2, 1.0],
        ],
        dtype=np.float64,
    )
    runtime = KDPPFixedKPrivateRuntime.from_precomputed_kernel(
        kernel,
        item_ids=tuple(str(index) for index in range(1, 7)),
        game=KDPPGame.MINILOTO,
        target_layout=KDPPTargetLayout.UNORDERED_FIXED_CARDINALITY,
        cardinality=5,
        context_length=10,
        feature_cutoff=9,
        feature_matrix_sha256=SHA,
        seed=1,
    )
    determinants: list[tuple[tuple[int, ...], float]] = []
    for subset in itertools.combinations(range(6), 5):
        determinant = float(np.linalg.det(kernel[np.ix_(subset, subset)]))
        determinants.append((subset, determinant))
    normalizer = sum(value for _, value in determinants)
    expected = np.zeros(6, dtype=np.float64)
    for subset, value in determinants:
        for index in subset:
            expected[index] += value / normalizer
    actual = kdpp_marginal_inclusion_probabilities(runtime.prepared)
    assert np.allclose(actual, expected, atol=1e-10, rtol=1e-10)
    assert np.isclose(actual.sum(), 5.0)


def test_non_psd_and_rank_below_k_are_rejected() -> None:
    with pytest.raises(ValueError, match="PSD_VIOLATION"):
        KDPPFixedKPrivateRuntime.from_precomputed_kernel(
            np.asarray([[1.0, 2.0], [2.0, 1.0]]),
            item_ids=("n1:0", "n1:1"),
            game=KDPPGame.NUMBERS3,
            target_layout=KDPPTargetLayout.POSITION_LOCAL,
            cardinality=1,
            context_length=10,
            feature_cutoff=9,
            feature_matrix_sha256=SHA,
            seed=1,
        )
    with pytest.raises(ValueError, match="normalizer|RANK"):
        KDPPFixedKPrivateRuntime.from_precomputed_kernel(
            np.diag([1.0, 1.0, 1.0, 1.0, 0.0, 0.0]),
            item_ids=tuple(str(index) for index in range(1, 7)),
            game=KDPPGame.MINILOTO,
            target_layout=KDPPTargetLayout.UNORDERED_FIXED_CARDINALITY,
            cardinality=5,
            context_length=10,
            feature_cutoff=9,
            feature_matrix_sha256=SHA,
            seed=1,
        )


def test_zero_probability_item_has_zero_marginal() -> None:
    runtime = KDPPFixedKPrivateRuntime.from_precomputed_kernel(
        np.diag([1.0, 2.0, 0.0]),
        item_ids=("n1:0", "n1:1", "n1:2"),
        game=KDPPGame.NUMBERS3,
        target_layout=KDPPTargetLayout.POSITION_LOCAL,
        cardinality=1,
        context_length=10,
        feature_cutoff=9,
        feature_matrix_sha256=SHA,
        seed=1,
    )
    assert runtime.marginals[2] == 0.0
    assert np.isclose(runtime.marginals.sum(), 1.0)


@pytest.mark.parametrize("prediction_length", [1, 2, 5])
def test_prediction_is_exact_seeded_cpu_only_and_replayable(
    tmp_path: Path,
    prediction_length: int,
) -> None:
    runtime, _, evidence = fit_runtime()
    artifacts = runtime.save(tmp_path / "state")
    request = prediction_request(
        runtime,
        evidence,
        prediction_length=prediction_length,
        seed=2026,
    )
    relative_paths = artifacts.relative_paths("runtime")
    first = runtime.predict(
        request,
        samples_per_horizon=16,
        artifact_paths=relative_paths,
    )
    second = runtime.predict(
        request,
        samples_per_horizon=16,
        artifact_paths=relative_paths,
    )
    assert prediction_sha256(first) == prediction_sha256(second)
    assert first.runtime_pid == os.getpid()
    assert first.effective_device == "cpu"
    assert first.cpu_fallback is False
    assert first.gpu_uuid is None
    assert first.gpu_process_vram_mb is None
    assert first.gpu_not_applicable is True
    assert first.actuals_used is False
    assert first.quantiles is None
    for subset in first.point_forecast:
        assert len(subset) == runtime.metadata.cardinality
        assert len(set(subset)) == runtime.metadata.cardinality
    for horizon_samples in first.samples:
        assert len(horizon_samples) == 16
        for subset in horizon_samples:
            assert len(subset) == runtime.metadata.cardinality
            assert len(set(subset)) == runtime.metadata.cardinality


def test_save_reload_inventory_and_separate_process_replay(
    tmp_path: Path,
) -> None:
    runtime, _, evidence = fit_runtime()
    state_dir = tmp_path / "state"
    artifacts = runtime.save(state_dir)
    loaded = KDPPFixedKPrivateRuntime.load(state_dir)
    request = prediction_request(
        runtime,
        evidence,
        prediction_length=2,
        seed=77,
    )
    paths = artifacts.relative_paths("runtime")
    local_response = loaded.predict(
        request,
        samples_per_horizon=8,
        artifact_paths=paths,
    )
    request_path = tmp_path / "request.json"
    request_path.write_text(request.model_dump_json(), encoding="utf-8")
    code = """
import json
import sys
from pathlib import Path
from loto.probabilistic.models.kdpp_native import KDPPFixedKRequest
from loto.probabilistic.models.kdpp_runtime import (
    KDPPFixedKPrivateRuntime,
    prediction_sha256,
)
state_dir = Path(sys.argv[1])
request = KDPPFixedKRequest.model_validate_json(Path(sys.argv[2]).read_text())
runtime = KDPPFixedKPrivateRuntime.load(state_dir)
response = runtime.predict(
    request,
    samples_per_horizon=8,
    artifact_paths=(
        "runtime/kdpp_state.json",
        "runtime/kdpp_state.npz",
        "runtime/artifact_manifest.json",
        "runtime/SHA256SUMS",
    ),
)
print(json.dumps({"pid": response.runtime_pid, "sha256": prediction_sha256(response)}))
"""
    environment = dict(os.environ)
    source_root = str(Path(__file__).parents[2] / "src")
    environment["PYTHONPATH"] = source_root
    completed = subprocess.run(
        [sys.executable, "-c", code, str(state_dir), str(request_path)],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    remote = json.loads(completed.stdout)
    assert remote["pid"] != os.getpid()
    assert remote["sha256"] == prediction_sha256(local_response)
    assert all(path.is_file() for path in artifacts.paths)
    assert artifacts.sha256sums.read_text(encoding="utf-8").count("\n") == 3


def test_tampered_state_is_rejected(tmp_path: Path) -> None:
    runtime, _, _ = fit_runtime()
    artifacts = runtime.save(tmp_path / "state")
    with artifacts.state_json.open("a", encoding="utf-8") as handle:
        handle.write(" ")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        KDPPFixedKPrivateRuntime.load(tmp_path / "state")
