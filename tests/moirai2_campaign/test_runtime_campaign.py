from __future__ import annotations

from pathlib import Path

import pytest

from loto.moirai2_campaign.runtime_campaign import (
    FORMAL_CASE_NAMES,
    RuntimeCampaignError,
    build_campaign_requests,
    calendar_timestamps,
    summarize_campaign,
    validate_generated_request,
)


def _comparison() -> dict[str, object]:
    return {
        "distinct_processes": True,
        "exact_prediction_match": True,
        "artifact_identity_match": True,
        "model_identity_match": True,
        "covariate_identity_match": True,
    }


def _case_result(case: str, *, status: str = "PASS") -> dict[str, object]:
    return {
        "case": case,
        "status": status,
        "message": "ok" if status == "PASS" else "failed",
        "certification": {
            "status": status,
            "runtime_lane": "supported-py311",
            "requested_device": "cpu",
            "separate_process_reload": status == "PASS",
            "prediction_comparison": _comparison(),
        },
    }


def test_builds_exact_six_case_matrix(tmp_path: Path) -> None:
    requests = build_campaign_requests(
        campaign_id="campaign-001",
        snapshot_path=tmp_path,
        device="cpu",
    )
    assert tuple(requests) == FORMAL_CASE_NAMES
    assert len(requests) == 6
    for case_name, payload in requests.items():
        validate_generated_request(case_name, payload)
        assert payload["seed"] == 1
        assert payload["local_files_only"] is True
        assert payload["snapshot_path"] == str(tmp_path.resolve())
        assert payload["run_id"].endswith(case_name)


def test_covariate_modes_and_lengths_are_exact(tmp_path: Path) -> None:
    requests = build_campaign_requests(
        campaign_id="campaign-002",
        snapshot_path=tmp_path,
        device="cuda",
        history_length=64,
        context_length=32,
        prediction_length=5,
    )
    assert requests["draw-target-only"]["past_covariates"] == {}
    assert requests["draw-target-only"]["future_covariates"] == {}
    past = requests["draw-past-only"]["past_covariates"]["cert_past_index"]
    assert len(past) == 64
    combined = requests["calendar-past-known-future"]
    assert len(combined["past_covariates"]["cert_past_index"]) == 64
    assert len(combined["future_covariates"]["cert_known_step"]) == 69
    assert combined["future_covariate_availability"] == {
        "cert_known_step": "known_at_prediction_time"
    }


def test_calendar_fixture_contains_gaps_and_increasing_timestamps() -> None:
    values = calendar_timestamps(50)
    assert len(values) == 50
    assert values == sorted(values)
    dates = [value[:10] for value in values]
    assert dates[19] != "2020-01-20"


def test_unknown_case_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(RuntimeCampaignError, match="unknown certification cases"):
        build_campaign_requests(
            campaign_id="campaign-003",
            snapshot_path=tmp_path,
            device="cpu",
            selected_cases=["not-a-case"],
        )


def test_full_campaign_pass_requires_all_six_cases() -> None:
    results = [_case_result(case) for case in FORMAL_CASE_NAMES]
    summary = summarize_campaign(
        case_results=results,
        required_cases=FORMAL_CASE_NAMES,
        runtime_lane="supported-py311",
        requested_device="cpu",
    )
    assert summary["status"] == "PASS"
    assert summary["passed_case_count"] == 6
    assert summary["formal_runtime_certified"] is True
    assert summary["accuracy_claimed"] is False
    assert summary["oof_opened"] is False


def test_missing_case_fails_campaign() -> None:
    results = [_case_result(case) for case in FORMAL_CASE_NAMES[:-1]]
    summary = summarize_campaign(
        case_results=results,
        required_cases=FORMAL_CASE_NAMES,
        runtime_lane="supported-py311",
        requested_device="cpu",
    )
    assert summary["status"] == "FAILED"
    assert summary["formal_runtime_certified"] is False
    assert any("missing cases" in failure["reason"] for failure in summary["failures"])


def test_changed_reload_flag_fails_campaign() -> None:
    results = [_case_result(case) for case in FORMAL_CASE_NAMES]
    certification = results[0]["certification"]
    assert isinstance(certification, dict)
    comparison = certification["prediction_comparison"]
    assert isinstance(comparison, dict)
    comparison["exact_prediction_match"] = False
    summary = summarize_campaign(
        case_results=results,
        required_cases=FORMAL_CASE_NAMES,
        runtime_lane="supported-py311",
        requested_device="cpu",
    )
    assert summary["status"] == "FAILED"
    assert any(
        failure["reason"] == "exact_prediction_match is not true" for failure in summary["failures"]
    )


def test_subset_pass_is_not_formal_runtime_certification() -> None:
    selected = FORMAL_CASE_NAMES[:2]
    summary = summarize_campaign(
        case_results=[_case_result(case) for case in selected],
        required_cases=selected,
        runtime_lane="supported-py311",
        requested_device="cpu",
    )
    assert summary["status"] == "PASS"
    assert summary["formal_runtime_certified"] is False


def test_duplicate_case_is_rejected_by_factory(tmp_path: Path) -> None:
    with pytest.raises(RuntimeCampaignError, match="must be unique"):
        build_campaign_requests(
            campaign_id="campaign-004",
            snapshot_path=tmp_path,
            device="cpu",
            selected_cases=["draw-target-only", "draw-target-only"],
        )


def test_snapshot_path_word_actual_does_not_trigger_false_leakage(tmp_path: Path) -> None:
    snapshot = tmp_path / "actual-model-cache"
    requests = build_campaign_requests(
        campaign_id="campaign-005",
        snapshot_path=snapshot,
        device="cpu",
        selected_cases=["draw-past-known-future"],
    )
    validate_generated_request(
        "draw-past-known-future",
        requests["draw-past-known-future"],
    )
