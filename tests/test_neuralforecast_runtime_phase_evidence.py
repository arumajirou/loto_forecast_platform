from loto.neuralforecast.runtime_evidence import cuda_phase_evidence, phase_has_cuda


def _baseline(*, allocated: int = 1024):
    return {
        "pid": 123,
        "cuda_available": True,
        "cuda_current_device": 0,
        "cuda_memory_allocated": allocated,
        "cuda_memory_reserved": 4096,
        "peak_reset": True,
    }


def _runtime(*, peak: int, allocated: int = 1024):
    return {
        "pid": 123,
        "cuda_available": True,
        "cuda_current_device": 0,
        "cuda_memory_allocated": allocated,
        "cuda_memory_reserved": 8192,
        "cuda_peak_memory_allocated": peak,
        "parameter_device": "cpu",
        "trainer_root_device": "cuda:0",
    }


def _gpu(*, external: bool = False):
    return {
        "pid": 123,
        "gpu_pid_verified": True,
        "external_gpu_pid_verified": external,
        "verification_method": (
            "nvidia_smi_compute_apps" if external else "torch_process_local_cuda_context"
        ),
    }


def test_stale_allocator_and_cuda_trainer_config_do_not_certify_phase() -> None:
    baseline = _baseline(allocated=1024)
    runtime = _runtime(peak=1024)
    gpu = _gpu(external=False)

    evidence = cuda_phase_evidence(runtime, gpu, baseline)

    assert evidence["verified"] is False
    assert evidence["verification_method"] == "none"
    assert evidence["process_local_phase_verified"] is False
    assert evidence["peak_delta_bytes"] == 0
    assert phase_has_cuda(runtime, gpu, baseline=baseline) is False


def test_process_local_peak_delta_certifies_current_phase() -> None:
    baseline = _baseline(allocated=1024)
    runtime = _runtime(peak=3072)
    gpu = _gpu(external=False)

    evidence = cuda_phase_evidence(runtime, gpu, baseline)

    assert evidence["verified"] is True
    assert evidence["verification_method"] == "torch_process_local_peak_delta"
    assert evidence["process_local_phase_verified"] is True
    assert evidence["peak_delta_bytes"] == 2048
    assert phase_has_cuda(runtime, gpu, baseline=baseline) is True


def test_process_local_phase_proof_requires_same_pid_and_reset() -> None:
    baseline = _baseline(allocated=1024)
    baseline["pid"] = 999
    runtime = _runtime(peak=4096)
    gpu = _gpu(external=False)

    evidence = cuda_phase_evidence(runtime, gpu, baseline)

    assert evidence["verified"] is False
    assert evidence["same_pid"] is False

    baseline = _baseline(allocated=1024)
    baseline["peak_reset"] = False
    evidence = cuda_phase_evidence(runtime, gpu, baseline)
    assert evidence["verified"] is False
    assert evidence["peak_reset"] is False


def test_external_pid_match_has_priority_without_local_delta() -> None:
    baseline = _baseline(allocated=1024)
    runtime = _runtime(peak=1024)
    gpu = _gpu(external=True)

    evidence = cuda_phase_evidence(runtime, gpu, baseline)

    assert evidence["verified"] is True
    assert evidence["verification_method"] == "nvidia_smi_compute_apps"
    assert evidence["external_gpu_pid_verified"] is True
