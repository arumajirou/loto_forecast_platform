from __future__ import annotations

from loto.adapters.timesfm25.contracts import GPUExecutionEvidence, RuntimeEvidence
from loto.timesfm25_campaign.certification import judge_gpu_certification


def test_cpu_numpy_outputs_prevent_strict_gpu_pass() -> None:
    runtime = RuntimeEvidence(
        provider_pid=1,
        model_parameter_device="cuda:0",
        input_device="cpu_numpy_staging",
        mean_output_device="cpu_numpy",
        quantile_output_device="cpu_numpy",
        cpu_fallback=False,
        load_time_seconds=0,
        compile_time_seconds=0,
        inference_time_seconds=0,
        compile_requested=False,
        compile_effective=False,
    )
    gpu = GPUExecutionEvidence(
        requested=True,
        cuda_available=True,
        gpu_used=True,
        provider_pid=1,
        external_pid_match=True,
        gpu_uuid="GPU-test",
        vram_before_bytes=0,
        vram_peak_bytes=1024,
        vram_after_bytes=0,
        cpu_fallback=False,
        certification_status="PARTIAL",
    )

    verdict = judge_gpu_certification(runtime, gpu)

    assert verdict.status == "FAIL"
    assert verdict.reasons == ("MEAN_OUTPUT_NOT_CUDA", "QUANTILE_OUTPUT_NOT_CUDA")
