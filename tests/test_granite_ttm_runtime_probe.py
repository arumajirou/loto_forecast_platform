from pathlib import Path

PROBE = Path("scripts/tsfm/run_granite_ttm_runtime_probe.py")
PROJECT = Path("environments/granite-ttm/pyproject.toml")
WRAPPER = Path("environments/granite-ttm/run-python.sh")


def test_runtime_probe_is_pinned_and_fail_closed():
    text = PROBE.read_text(encoding="utf-8")

    assert 'REPO_ID = "ibm-granite/granite-timeseries-ttm-r2"' in text
    assert 'REVISION = "d6a79570cac0f33d526601cd3a0fc7c80a8f9a2f"' in text
    assert "trust_remote_code=False" in text
    assert '"runtime_vram_certified": False' in text
    assert '"runtime_vram_certified": True' in text
    assert '"sm_120"' in text
    assert 'return 0 if payload["status"] == "PASS" else 2' in text


def test_runtime_probe_requires_cuda_evidence():
    text = PROBE.read_text(encoding="utf-8")

    assert 'first_parameter.device.type != "cuda"' in text
    assert 'prediction.device.type != "cuda"' in text
    assert "torch.cuda.max_memory_allocated" in text
    assert "torch.cuda.max_memory_reserved" in text
    assert "torch.isfinite(prediction)" in text


def test_granite_environment_pins_cuda_13_torch():
    text = PROJECT.read_text(encoding="utf-8")

    assert '"torch==2.12.1"' in text
    assert 'name = "pytorch-cu130"' in text
    assert 'url = "https://download.pytorch.org/whl/cu130"' in text
    assert 'torch = { index = "pytorch-cu130" }' in text


def test_granite_wrapper_adds_nvidia_library_paths():
    text = WRAPPER.read_text(encoding="utf-8")

    assert 'find "$SITE_PACKAGES/nvidia"' in text
    assert "-name lib" in text
    assert "LD_LIBRARY_PATH" in text
    assert 'exec "$PYTHON" "$@"' in text
