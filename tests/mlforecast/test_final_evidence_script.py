from pathlib import Path


def script_text() -> str:
    return (
        Path(__file__).parents[2]
        / "docs/mlforecast/run_final_verification_portable.sh"
    ).read_text(encoding="utf-8")


def test_portable_wrapper_is_fail_closed() -> None:
    text = script_text()
    assert "set -Eeuo pipefail" in text
    assert "FINAL_EVIDENCE_FAILED" in text
    assert "FINAL_EVIDENCE_CERTIFIED" in text
    assert "FINAL_EVIDENCE_PRESERVED" in text


def test_portable_wrapper_builds_then_verifies() -> None:
    text = script_text()
    assert text.index("--build") < text.index("--verify")
    assert "run_final_verification_complete.sh" in text
    assert "loto.mlforecast.final_evidence" in text


def test_portable_wrapper_preserves_source_status() -> None:
    text = script_text()
    assert 'exit "$SOURCE_STATUS"' in text
    assert "FINAL_EVIDENCE_REPORT" in text
