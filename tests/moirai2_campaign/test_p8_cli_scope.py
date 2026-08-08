from __future__ import annotations

from pathlib import Path


def test_certification_cli_is_two_process_and_fail_closed() -> None:
    source = (Path(__file__).parents[2] / "scripts" / "certify_moirai2_runtime.py").read_text(
        encoding="utf-8"
    )
    assert 'label="run-a"' in source
    assert 'label="run-b"' in source
    assert "exist_ok=False" in source
    assert "requires an explicit pinned local snapshot_path" in source
    assert "compare_provider_responses" in source
    assert "certify_external_gpu_evidence" in source
    assert "rerun" not in source.lower()
