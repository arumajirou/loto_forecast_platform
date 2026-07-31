from loto.observability.gpu import evaluate_gpu_evidence


def test_gpu_required_trial_fails_without_cuda_tensor_or_vram_evidence():
    result = evaluate_gpu_evidence(
        {"gpu_required": True, "model_device": "cpu", "batch_device": "cpu", "vram_peak_bytes": 0}
    )
    assert result["eligible"] is False


def test_cpu_trial_is_eligible_when_gpu_not_requested():
    result = evaluate_gpu_evidence(
        {"gpu_required": False, "model_device": "cpu", "batch_device": "cpu", "vram_peak_bytes": 0}
    )
    assert result["eligible"] is True
