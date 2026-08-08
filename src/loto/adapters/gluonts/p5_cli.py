from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .lifecycle import certify_predictor_lifecycle
from .protocol import (
    DatasetItem,
    DeviceRequest,
    EnvironmentLane,
    GluonTSProviderRequest,
    ProviderOperation,
    ResourcePolicy,
)
from .serialization import LifecycleOutcome


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run cross-process GluonTS Predictor lifecycle certification"
    )
    parser.add_argument("--lane", choices=["compat", "latest"], required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--predictor-artifact-dir", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=600.0)
    return parser


def _request(lane: str, run_id: str) -> GluonTSProviderRequest:
    target = [float((index % 9) + (index / 50.0)) for index in range(48)]
    return GluonTSProviderRequest(
        request_id=f"{run_id}-fit-serialize",
        run_id=run_id,
        lane=EnvironmentLane(lane),
        operation=ProviderOperation.FIT_PREDICT,
        model_class="DeepAREstimator",
        distribution_output="StudentTOutput",
        prediction_length=1,
        context_length=8,
        seed=1,
        device=DeviceRequest.CPU,
        freq="D",
        dataset=[
            DatasetItem(
                item_id="deepar-p5-lifecycle",
                start="2000-01-01",
                target=target,
            )
        ],
        arguments={"p5_lifecycle_certification": True},
        resource_policy=ResourcePolicy(
            outer_workers=8,
            max_gpu_jobs=1,
            threads_per_job=1,
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    request = _request(args.lane, args.run_id)
    lifecycle = certify_predictor_lifecycle(
        request,
        [sys.executable, "-m", "loto_gluonts_provider"],
        args.artifact_root,
        args.predictor_artifact_dir,
        timeout_seconds=args.timeout_seconds,
    )
    print(
        json.dumps(
            {
                "lane": args.lane,
                "run_id": args.run_id,
                "outcome": lifecycle.result.outcome.value,
                "fit_process_id": lifecycle.result.fit.process_id,
                "load_process_id": (
                    lifecycle.result.reload.load_process_id
                    if lifecycle.result.reload is not None
                    else None
                ),
                "predictor_lifecycle_path": str(lifecycle.result_path),
                "predictor_lifecycle_sha256": lifecycle.result_sha256,
                "lifecycle_manifest_path": str(lifecycle.manifest_path),
                "lifecycle_manifest_sha256": lifecycle.manifest_sha256,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    if lifecycle.result.outcome is LifecycleOutcome.VERIFIED:
        return 0
    if lifecycle.result.outcome is LifecycleOutcome.BLOCKED:
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
