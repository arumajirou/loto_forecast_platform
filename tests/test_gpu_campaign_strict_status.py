import json
from pathlib import Path

from scripts.gpu_24h_campaign import inspect_research_result


def write_summary(root: Path, payload: dict) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "research_summary.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def test_rejects_missing_summary(tmp_path):
    status, detail = inspect_research_result(tmp_path)

    assert status == "PARTIAL_NO_SUMMARY"
    assert "missing" in detail


def test_rejects_inner_failure(tmp_path):
    write_summary(
        tmp_path,
        {
            "status": "FAILED",
            "successful_trials": 0,
            "champion": None,
        },
    )

    status, _ = inspect_research_result(tmp_path)

    assert status == "INNER_FAILED"


def test_rejects_missing_champion(tmp_path):
    write_summary(
        tmp_path,
        {
            "status": "SUCCEEDED",
            "successful_trials": 1,
            "champion": None,
        },
    )

    status, _ = inspect_research_result(tmp_path)

    assert status == "PARTIAL_NO_CHAMPION"


def test_accepts_verified_success(tmp_path):
    write_summary(
        tmp_path,
        {
            "status": "SUCCEEDED",
            "successful_trials": 1,
            "champion": {
                "model_id": "nf-tide",
            },
        },
    )

    status, detail = inspect_research_result(tmp_path)

    assert status == "SUCCEEDED"
    assert detail == ""
