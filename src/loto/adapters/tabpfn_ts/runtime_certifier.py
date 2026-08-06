from __future__ import annotations

from pathlib import Path

from .hash_gate import CheckpointGateSpec, verify_checkpoint_before_load
from .manifests import CheckpointLane, require_executable_lane
from .runtime_gpu import (
    parse_nvidia_compute_apps,
    query_nvidia_compute_apps,
    validate_provider_response,
)
from .runtime_models import (
    GPUProcessSample,
    ProviderRunEvidence,
    RuntimeCertificationConfig,
    RuntimeCertificationError,
    RuntimeCertificationReport,
    build_sha256_inventory,
    canonical_prediction_sha256,
    load_json,
    utc_now,
    write_json_atomic,
)
from .runtime_process import (
    build_formal_provider_request,
    compare_process_replays,
    run_provider_process,
)

__all__ = [
    "GPUProcessSample",
    "ProviderRunEvidence",
    "RuntimeCertificationConfig",
    "RuntimeCertificationError",
    "RuntimeCertificationReport",
    "build_formal_provider_request",
    "canonical_prediction_sha256",
    "certify_runtime",
    "compare_process_replays",
    "parse_nvidia_compute_apps",
    "query_nvidia_compute_apps",
    "run_provider_process",
    "validate_provider_response",
    "write_json_atomic",
]


def certify_runtime(
    config: RuntimeCertificationConfig,
    *,
    gpu_probe=query_nvidia_compute_apps,
) -> RuntimeCertificationReport:
    manifest = require_executable_lane(CheckpointLane.V2_REG_LEGACY)
    if not config.provider_python.is_file():
        raise RuntimeCertificationError(f"provider Python does not exist: {config.provider_python}")
    if not config.provider_script.is_file():
        raise RuntimeCertificationError(f"provider script does not exist: {config.provider_script}")
    source_request = load_json(config.request_path)
    formal_request = build_formal_provider_request(
        source_request,
        snapshot_path=config.snapshot_path,
        device=config.device,
        seed=config.seed,
    )
    checkpoint_path = config.snapshot_path / manifest.filename
    checkpoint_evidence = verify_checkpoint_before_load(
        checkpoint_path=checkpoint_path,
        snapshot_path=config.snapshot_path,
        repository_cache_root=config.repository_cache_root,
        spec=CheckpointGateSpec(
            expected_filename=manifest.filename,
            expected_sha256=str(manifest.sha256),
            expected_revision=str(manifest.revision),
            local_files_only=True,
        ),
    )

    process_runs = [
        run_provider_process(
            config,
            run_index=index,
            formal_request=formal_request,
            gpu_probe=gpu_probe,
        )
        for index in range(1, config.repeats + 1)
    ]
    deterministic, maximum_difference = compare_process_replays(
        process_runs,
        absolute_tolerance=config.prediction_tolerance,
    )
    if not deterministic:
        raise RuntimeCertificationError(
            "separate-process predictions differ: "
            f"max_abs_diff={maximum_difference}, tolerance={config.prediction_tolerance}"
        )

    report = RuntimeCertificationReport(
        run_id=config.run_id,
        status="PASS",
        certification_class="GPU_FORMAL" if config.device == "cuda" else "CPU_SMOKE",
        created_at_utc=utc_now(),
        checkpoint_evidence=checkpoint_evidence,
        process_runs=process_runs,
        separate_process_reload=True,
        deterministic_replay=True,
        max_absolute_prediction_difference=maximum_difference,
        prediction_locked_before_actuals=True,
    )
    report_dir = config.output_root / config.run_id
    report_path = report_dir / "runtime-certification-report.json"
    write_json_atomic(report_path, report.model_dump(mode="json"))
    evidence_paths = [report_path]
    for run in process_runs:
        evidence_paths.extend(
            [
                Path(run.request_path),
                Path(run.response_path),
                Path(run.stdout_path),
                Path(run.stderr_path),
            ]
        )
    (report_dir / "SHA256SUMS").write_text(
        build_sha256_inventory(report_dir, evidence_paths), encoding="utf-8"
    )
    return report
