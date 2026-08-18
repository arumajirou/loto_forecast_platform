from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "tools" / "runtime_audit" / "taj19_gpu_wait.py"
LAUNCHER = ROOT / "tools" / "taj19-gpu.sh"


def load_module():
    spec = importlib.util.spec_from_file_location("taj19_gpu_wait", HELPER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_launcher_is_bash_syntax_valid_and_never_kills_gpu_processes() -> None:
    text = LAUNCHER.read_text(encoding="utf-8")
    assert "wait-run" in text
    assert "kill " not in text
    assert "pkill" not in text
    assert "nvidia-smi --gpu-reset" not in text
    result = subprocess.run(["bash", "-n", str(LAUNCHER)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_status_ready_when_any_gpu_has_required_free_memory(monkeypatch) -> None:
    module = load_module()
    monkeypatch.setattr(
        module,
        "read_gpus",
        lambda: [module.GpuRow(index=0, name="GPU", total_mib=16000, used_mib=7000, free_mib=9000)],
    )
    monkeypatch.setattr(module, "read_compute_apps", lambda: [])
    assert module.show_status(7168) is True


def test_status_blocked_when_free_memory_is_below_threshold(monkeypatch) -> None:
    module = load_module()
    monkeypatch.setattr(
        module,
        "read_gpus",
        lambda: [module.GpuRow(index=0, name="GPU", total_mib=16000, used_mib=15800, free_mib=200)],
    )
    monkeypatch.setattr(module, "read_compute_apps", lambda: ["uuid, 123, llama-server, 15000"])
    assert module.show_status(7168) is False
