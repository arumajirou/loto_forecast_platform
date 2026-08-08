from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import numpy as np

from loto.probabilistic.models.kdpp_native import (
    MODEL_ID,
    MODEL_REVISION,
    SCHEMA_VERSION,
    KDPPChronologyEvidence,
    KDPPFixedKRequest,
    KDPPGame,
    KDPPKernelType,
    KDPPPSDRepairPolicy,
    KDPPTargetLayout,
)
from loto.probabilistic.models.kdpp_runtime import (
    KDPPFixedKPrivateRuntime,
    KDPPKernelMode,
    feature_evidence_sha256,
    prediction_sha256,
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run private CPU k-DPP fit/save/reload/predict certification."
    )
    parser.add_argument("--training-npz", type=Path, required=True)
    parser.add_argument("--item-ids-json", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--game",
        choices=[game.value for game in KDPPGame],
        required=True,
    )
    parser.add_argument(
        "--target-layout",
        choices=[layout.value for layout in KDPPTargetLayout],
        required=True,
    )
    parser.add_argument("--train-start", type=int, required=True)
    parser.add_argument("--train-end", type=int, required=True)
    parser.add_argument("--forecast-origin", type=int, required=True)
    parser.add_argument("--context-length", type=int, required=True)
    parser.add_argument(
        "--prediction-length",
        type=int,
        choices=[1, 2, 5],
        default=1,
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--config-sha256", required=True)
    parser.add_argument("--package-version", default="3.2.0")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--samples-per-horizon", type=int, default=128)
    parser.add_argument("--rbf-gamma", type=float, default=1.0)
    parser.add_argument("--quality-pseudocount", type=float, default=0.5)
    parser.add_argument("--psd-tolerance", type=float, default=1e-10)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=False)
    with np.load(args.training_npz, allow_pickle=False) as arrays:
        if "training_indicators" not in arrays:
            raise ValueError("training NPZ must contain training_indicators")
        training = np.asarray(arrays["training_indicators"])
        item_features = (
            np.asarray(arrays["item_features"], dtype=np.float64)
            if "item_features" in arrays
            else None
        )
    item_ids_payload = json.loads(args.item_ids_json.read_text(encoding="utf-8"))
    if not isinstance(item_ids_payload, list) or not all(
        isinstance(item, str) for item in item_ids_payload
    ):
        raise ValueError("item IDs JSON must be an array of strings")
    item_ids = tuple(item_ids_payload)
    feature_hash = feature_evidence_sha256(training, item_features)
    chronology = KDPPChronologyEvidence(
        train_start=args.train_start,
        train_end=args.train_end,
        validation_start=None,
        validation_end=None,
        forecast_origin=args.forecast_origin,
        future_actuals_available=False,
        known_future_covariates=(),
        feature_cutoff=args.train_end,
        feature_matrix_sha256=feature_hash,
    )
    runtime = KDPPFixedKPrivateRuntime.fit(
        training,
        item_ids=item_ids,
        game=KDPPGame(args.game),
        target_layout=KDPPTargetLayout(args.target_layout),
        context_length=args.context_length,
        chronology_evidence=chronology,
        seed=args.seed,
        item_features=item_features,
        kernel_mode=KDPPKernelMode.HISTORICAL_RBF,
        rbf_gamma=args.rbf_gamma,
        quality_pseudocount=args.quality_pseudocount,
        psd_tolerance=args.psd_tolerance,
    )
    state_dir = output_dir / "state"
    artifacts = runtime.save(state_dir)
    reloaded = KDPPFixedKPrivateRuntime.load(state_dir)
    relative_artifacts = (
        *artifacts.relative_paths("state"),
        "request.json",
        "response.json",
        "prediction.lock.json",
        "runtime_evidence.json",
    )
    request = KDPPFixedKRequest(
        schema_version=SCHEMA_VERSION,
        run_id=args.run_id,
        model_id=MODEL_ID,
        package_version=args.package_version,
        source_revision=args.source_revision,
        model_revision=MODEL_REVISION,
        config_sha256=args.config_sha256,
        weight_sha256=reloaded.metadata.state_sha256,
        license="MIT",
        game=reloaded.metadata.game,
        target_layout=reloaded.metadata.target_layout,
        context_length=reloaded.metadata.context_length,
        prediction_length=args.prediction_length,
        seed=args.seed,
        requested_device="cpu",
        chronology_evidence=chronology,
        actuals_used=False,
        kernel_type=KDPPKernelType.L_ENSEMBLE,
        kernel_shape=reloaded.metadata.kernel_shape,
        kernel_sha256=reloaded.metadata.kernel_sha256,
        item_ids=reloaded.metadata.item_ids,
        cardinality=reloaded.metadata.cardinality,
        psd_tolerance=reloaded.metadata.psd_tolerance,
        psd_repair_policy=KDPPPSDRepairPolicy.REJECT,
    )
    response = reloaded.predict(
        request,
        samples_per_horizon=args.samples_per_horizon,
        artifact_paths=relative_artifacts,
    )
    request_path = output_dir / "request.json"
    response_path = output_dir / "response.json"
    lock_path = output_dir / "prediction.lock.json"
    evidence_path = output_dir / "runtime_evidence.json"
    _write_json(request_path, request.model_dump(mode="json"))
    _write_json(response_path, response.model_dump(mode="json"))
    prediction_hash = prediction_sha256(response)
    _write_json(
        lock_path,
        {
            "schema_version": SCHEMA_VERSION,
            "model_id": MODEL_ID,
            "run_id": args.run_id,
            "prediction_sha256": prediction_hash,
            "actuals_used": False,
        },
    )
    _write_json(
        evidence_path,
        {
            "schema_version": SCHEMA_VERSION,
            "status": "PRIVATE_RUNTIME_EXECUTED",
            "formal_runtime_certification": False,
            "reason": ("Dataset provenance requires independent review before certification."),
            "runtime_pid": os.getpid(),
            "requested_device": "cpu",
            "effective_device": "cpu",
            "cpu_fallback": False,
            "gpu_not_applicable": True,
            "kernel_rank": reloaded.metadata.kernel_rank,
            "minimum_eigenvalue": reloaded.metadata.minimum_eigenvalue,
            "log_normalizer": reloaded.metadata.log_normalizer,
            "state_sha256": reloaded.metadata.state_sha256,
            "prediction_sha256": prediction_hash,
        },
    )
    inventory_paths = [
        *artifacts.paths,
        request_path,
        response_path,
        lock_path,
        evidence_path,
    ]
    certification_sums = output_dir / "CERTIFICATION_SHA256SUMS"
    certification_sums.write_text(
        "".join(
            f"{_sha256_file(path)}  {path.relative_to(output_dir).as_posix()}\n"
            for path in sorted(inventory_paths)
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "PRIVATE_RUNTIME_EXECUTED",
                "formal_runtime_certification": False,
                "run_id": args.run_id,
                "state_sha256": reloaded.metadata.state_sha256,
                "prediction_sha256": prediction_hash,
                "output_dir": str(output_dir),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
