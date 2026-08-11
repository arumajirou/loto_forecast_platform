from __future__ import annotations

import os
from types import SimpleNamespace

from loto.auto_campaign import runtime


def _empty_nvidia_smi(*args, **kwargs):
    return SimpleNamespace(returncode=0, stdout="", stderr="")


def test_wsl_uses_process_local_cuda_context_when_compute_pid_query_is_empty(monkeypatch):
    monkeypatch.setattr(runtime.subprocess, "run", _empty_nvidia_smi)
    monkeypatch.setattr(runtime, "_is_wsl", lambda: True)
    monkeypatch.setattr(
        runtime,
        "_process_local_cuda_snapshot",
        lambda: {
            "pid": os.getpid(),
            "torch_available": True,
            "cuda_available": True,
            "cuda_current_device": 0,
            "cuda_memory_allocated": 1024,
            "cuda_memory_reserved": 2048,
            "cuda_peak_memory_allocated": 4096,
            "cuda_context_active": True,
        },
    )

    snapshot = runtime.gpu_process_snapshot()

    assert snapshot["pid"] == os.getpid()
    assert snapshot["gpu_pid_verified"] is True
    assert snapshot["verification_method"] == "torch_process_local_cuda_context"
    assert snapshot["platform_wsl"] is True
    assert snapshot["rows"] == []
    assert snapshot["process_local_cuda"]["cuda_context_active"] is True
    assert snapshot["limitation"] == "wsl_nvidia_smi_active_compute_process_query_unavailable"


def test_native_linux_empty_compute_pid_query_remains_fail_closed(monkeypatch):
    monkeypatch.setattr(runtime.subprocess, "run", _empty_nvidia_smi)
    monkeypatch.setattr(runtime, "_is_wsl", lambda: False)
    monkeypatch.setattr(
        runtime,
        "_process_local_cuda_snapshot",
        lambda: (_ for _ in ()).throw(AssertionError("native Linux must not use WSL fallback")),
    )

    snapshot = runtime.gpu_process_snapshot()

    assert snapshot["gpu_pid_verified"] is False
    assert snapshot["verification_method"] == "none"
    assert snapshot["platform_wsl"] is False
    assert snapshot["process_local_cuda"] == {}


def test_wsl_fallback_never_claims_a_different_pid(monkeypatch):
    monkeypatch.setattr(runtime.subprocess, "run", _empty_nvidia_smi)
    monkeypatch.setattr(runtime, "_is_wsl", lambda: True)
    monkeypatch.setattr(
        runtime,
        "_process_local_cuda_snapshot",
        lambda: (_ for _ in ()).throw(AssertionError("different PID must not use local CUDA proof")),
    )

    snapshot = runtime.gpu_process_snapshot(pid=os.getpid() + 1)

    assert snapshot["gpu_pid_verified"] is False
    assert snapshot["verification_method"] == "none"


def test_nvidia_smi_pid_match_has_priority_over_wsl_fallback(monkeypatch):
    pid = os.getpid()

    def matched_nvidia_smi(*args, **kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout=f"{pid}, python, 123\n",
            stderr="",
        )

    monkeypatch.setattr(runtime.subprocess, "run", matched_nvidia_smi)
    monkeypatch.setattr(runtime, "_is_wsl", lambda: True)
    monkeypatch.setattr(
        runtime,
        "_process_local_cuda_snapshot",
        lambda: (_ for _ in ()).throw(AssertionError("external PID match must win")),
    )

    snapshot = runtime.gpu_process_snapshot()

    assert snapshot["gpu_pid_verified"] is True
    assert snapshot["verification_method"] == "nvidia_smi_compute_apps"
    assert snapshot["rows"] == [f"{pid}, python, 123"]
    assert snapshot["process_local_cuda"] == {}
