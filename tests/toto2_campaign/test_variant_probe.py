from __future__ import annotations

from loto.toto2_campaign.variant_probe import (
    parse_nvidia_compute_app_pids,
    parse_nvidia_compute_apps,
)


def test_parse_nvidia_compute_apps_selects_exact_pid() -> None:
    text = """101, GPU-a, 120
202, GPU-b, 345
not-a-pid, GPU-c, N/A
"""
    records = parse_nvidia_compute_apps(text, pid=202)
    assert len(records) == 1
    assert records[0].pid == 202
    assert records[0].gpu_uuid == "GPU-b"
    assert records[0].used_gpu_memory_mib == 345


def test_parse_nvidia_compute_apps_rejects_zero_vram() -> None:
    records = parse_nvidia_compute_apps("202, GPU-b, 0\n", pid=202)
    assert records == []


def test_parse_nvidia_compute_apps_rejects_other_pid() -> None:
    records = parse_nvidia_compute_apps("202, GPU-b, 345\n", pid=303)
    assert records == []


def test_parse_nvidia_compute_app_pids_keeps_pid_even_with_zero_or_na_vram() -> None:
    text = """101, GPU-a, 0
202, GPU-b, N/A
not-a-pid, GPU-c, 100
"""
    assert parse_nvidia_compute_app_pids(text) == {101, 202}
