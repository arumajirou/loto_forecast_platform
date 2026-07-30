import subprocess

from loto.cli import _probe_torch


def test_torch_probe_timeout_is_reported_not_hung(monkeypatch):
    def boom(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="python", timeout=1)
    monkeypatch.setattr(subprocess, "run", boom)
    result = _probe_torch(timeout_seconds=1)
    assert result["torch_probe_timeout"] is True
