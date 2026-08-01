from pathlib import Path

SCRIPT = Path("scripts/tsfm/run_patchtsmixer_runtime_probe.py")


def test_runtime_probe_is_pinned_and_fail_closed():
    text = SCRIPT.read_text(encoding="utf-8")

    assert 'REPO_ID = "ibm-granite/granite-timeseries-patchtsmixer"' in text
    assert 'REVISION = "90dc5a88d45f032b7dceefb5d814ca2af54f2ff9"' in text
    assert "trust_remote_code=False" in text
    assert '"runtime_vram_certified": False' in text
    assert '"runtime_vram_certified": True' in text
    assert 'return 0 if payload["status"] == "PASS" else 2' in text


def test_runtime_probe_requires_cuda_evidence():
    text = SCRIPT.read_text(encoding="utf-8")

    assert 'first_parameter.device.type != "cuda"' in text
    assert 'prediction_outputs.device.type != "cuda"' in text
    assert "torch.cuda.max_memory_allocated" in text
    assert "torch.cuda.max_memory_reserved" in text
    assert "torch.isfinite(prediction_outputs)" in text
