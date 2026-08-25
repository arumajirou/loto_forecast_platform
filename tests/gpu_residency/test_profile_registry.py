from __future__ import annotations

import json

import pytest

from loto.gpu_exclusive.adapters import GpuSnapshot
from loto.gpu_exclusive.models import ResidencyProfileSelector
from loto.gpu_exclusive.residency import (
    ResidencyProfileError,
    load_profile_registry,
    select_exact_profile,
)


def test_exact_tuple_profile_selection(tmp_path) -> None:
    path = tmp_path / "profiles.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "profiles": [
                    {
                        "profile_id": "p1",
                        "certified": True,
                        "gpu": {"uuid": "GPU-x", "index": 0},
                        "llm": {
                            "alias": "qwen",
                            "runtime": "ik_llama",
                            "context_length": 65536,
                            "process_names": ["llama-server"],
                        },
                        "foundation": {
                            "repo_id": "repo",
                            "revision": "rev",
                            "runtime_lane": "lane",
                        },
                        "evidence": {
                            "external_peak_vram_mib": 1000,
                            "sample_count": 3,
                            "certification_run_ids": ["a", "b", "c"],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    registry = load_profile_registry(path)
    profile = select_exact_profile(
        registry,
        selector=ResidencyProfileSelector(
            llm_alias="qwen",
            llm_runtime="ik_llama",
            llm_context_length=65536,
            foundation_repo_id="repo",
            foundation_revision="rev",
            runtime_lane="lane",
        ),
        gpu=GpuSnapshot(
            index=0,
            uuid="GPU-x",
            memory_used_mib=100,
            memory_free_mib=900,
            memory_total_mib=1000,
        ),
    )
    assert profile is not None
    assert profile.profile_id == "p1"


def test_malformed_registry_fails_closed(tmp_path) -> None:
    path = tmp_path / "profiles.json"
    path.write_text('{"schema_version": 2}', encoding="utf-8")
    with pytest.raises(ResidencyProfileError):
        load_profile_registry(path)
