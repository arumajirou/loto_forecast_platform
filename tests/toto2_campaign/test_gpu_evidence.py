from __future__ import annotations

import pytest

from loto.toto2_campaign.gpu_evidence import (
    parse_compute_apps_csv,
    summarize_pid_samples,
)


def test_parse_and_summarize_provider_pid() -> None:
    samples = parse_compute_apps_csv(
        "1234, GPU-aaa, 64\n9999, GPU-bbb, 128\n1234, GPU-aaa, 70\n"
    )
    summary = summarize_pid_samples(samples, 1234)
    assert summary == {
        "provider_pid": 1234,
        "captured": True,
        "capture_count": 2,
        "gpu_uuid": "GPU-aaa",
        "max_gpu_memory_mib": 70,
        "min_gpu_memory_mib": 64,
    }


def test_parser_rejects_malformed_rows() -> None:
    with pytest.raises(ValueError, match="invalid nvidia-smi row"):
        parse_compute_apps_csv("1234,GPU-aaa\n")


def test_summary_rejects_pid_on_multiple_gpus() -> None:
    samples = parse_compute_apps_csv("1234, GPU-aaa, 64\n1234, GPU-bbb, 64\n")
    with pytest.raises(ValueError, match="multiple GPU UUIDs"):
        summarize_pid_samples(samples, 1234)
