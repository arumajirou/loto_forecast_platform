from pathlib import Path


def script_text() -> str:
    return (Path(__file__).parents[2] / "docs/mlforecast/run_final_verification.sh").read_text(
        encoding="utf-8"
    )


def test_script_is_fail_closed() -> None:
    text = script_text()
    assert "set -Eeuo pipefail" in text
    assert "FINAL_VERIFICATION_PASSED" in text
    assert "FINAL_VERIFICATION_BLOCKED" in text
    assert "FINAL_VERIFICATION_FAILED" in text


def test_script_runs_required_gates_in_order() -> None:
    text = script_text()
    names = [
        "focused-pytest",
        "ruff-format",
        "ruff-check",
        "strict-handoff-build",
        "strict-handoff-verify",
        "installed-runtime",
    ]
    offsets = [text.index(name) for name in names]
    assert offsets == sorted(offsets)


def test_script_preserves_evidence() -> None:
    text = script_text()
    assert "FINAL_VERIFICATION.json" in text
    assert "ARTIFACT_MANIFEST.json" in text
    assert "SHA256SUMS" in text
    assert "STEPS.tsv" in text


def test_script_checks_repository_before_and_after() -> None:
    text = script_text()
    assert "git status --porcelain" in text
    assert "repository-unchanged" in text
    assert "AFTER_HEAD" in text


def test_script_uses_frozen_uv_and_single_threads() -> None:
    text = script_text()
    assert text.count("uv run --frozen") >= 6
    for key in (
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ):
        assert f"export {key}=1" in text
