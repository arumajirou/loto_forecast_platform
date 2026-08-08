from __future__ import annotations

import sys
from pathlib import Path

import pytest

from loto.autogluon_campaign.covariate_runtime_certification import (
    CovariateCertificationConfig,
    CovariateCertificationStatus,
    full_scenarios,
    request_payload,
    run_covariate_runtime_certification,
    smoke_scenarios,
    validate_response,
)


def _write_fake_provider(path: Path, *, error_code: str | None = None) -> None:
    source = """
import argparse
import hashlib
import json
import os
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--request", required=True)
parser.add_argument("--response", required=True)
args = parser.parse_args()
request = json.loads(Path(args.request).read_text(encoding="utf-8"))
response_path = Path(args.response)
artifact_dir = Path(request["artifact_dir"])
error_code = __ERROR_CODE__
if error_code:
    payload = {
        "run_id": request["run_id"],
        "status": "ERROR",
        "operation": request["operation"],
        "predictions": [],
        "metadata": {},
        "artifacts": {},
        "runtime_evidence": None,
        "error": {"code": error_code, "phase": "runtime_import", "message": error_code},
    }
else:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifacts = {}
    names = {
        "provider_context": "loto_provider_context_v2.json",
        "execution_plan": "loto_execution_plan_v2.json",
        "timeline_mapping": "loto_timeline_mapping_v2.json",
        "covariate_context": "loto_covariate_context_v2.json",
        "covariate_capability_context": "loto_covariate_capability_v2.json",
    }
    for key, name in names.items():
        target = artifact_dir / name
        if not target.exists():
            target.write_text("{}\\n", encoding="utf-8")
        artifacts[key] = str(target)
    predictions = []
    for item in range(1, 4):
        for step in range(1, 3):
            predictions.append({
                "item_id": f"position-{item}",
                "timestamp": f"2026-01-0{step}T00:00:00Z",
                "horizon_step": step,
                "mean": float(item + step),
                "quantiles": {"0.1": 0.0, "0.5": 1.0, "0.9": 2.0},
            })
    known = request["predictor"].get("known_covariates_names", [])
    covariates = request.get("covariates", {})
    roles = []
    if known:
        roles.append("known_covariates")
    if covariates.get("past_covariates_names"):
        roles.append("past_covariates")
    if covariates.get("static_feature_names"):
        roles.append("static_features")
    model_roles = []
    configs = request["fit"]["hyperparameters"]
    for model_id in request["model_ids"]:
        config = configs[model_id]
        regressor = config.get("covariate_regressor")
        for role in roles:
            route = "covariate_regressor" if regressor else "native"
            model_roles.append({
                "model_id": model_id,
                "role": role,
                "route": route,
                "covariate_regressor": regressor,
            })
    decision_without_hash = {
        "schema_version": 1,
        "autogluon_version": "1.5.0",
        "execution_mode": request["execution_mode"],
        "selected_model_ids": request["model_ids"],
        "requested_roles": roles,
        "model_roles": model_roles,
    }
    decision_hash = hashlib.sha256(
        json.dumps(
            decision_without_hash,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    decision = {**decision_without_hash, "decision_sha256": decision_hash}
    payload = {
        "run_id": request["run_id"],
        "status": "OK",
        "operation": request["operation"],
        "predictions": predictions,
        "metadata": {
            "finite": True,
            "selected_model_ids": request["model_ids"],
            "covariate_capability_decision": decision,
            "covariate_capability_sha256": decision_hash,
        },
        "artifacts": artifacts,
        "runtime_evidence": {
            "pid": os.getpid(),
            "resolved_device": "cpu",
            "gpu_used": False,
        },
        "error": None,
    }
response_path.parent.mkdir(parents=True, exist_ok=True)
response_path.write_text(json.dumps(payload), encoding="utf-8")
""".replace("__ERROR_CODE__", repr(error_code))
    path.write_text(source, encoding="utf-8")


def test_smoke_profile_has_native_regressor_multi_and_load() -> None:
    scenarios = smoke_scenarios()
    assert len(scenarios) == 6
    assert any(item.regressor == "LR" for item in scenarios)
    assert any(len(item.model_ids) == 2 for item in scenarios)
    assert sum(item.operation == "load_predict" for item in scenarios) == 2


def test_full_profile_covers_all_models_and_roles() -> None:
    scenarios = full_scenarios()
    assert len(scenarios) == 60
    models = {model for scenario in scenarios for model in scenario.model_ids}
    assert len(models) == 29
    assert sum("past-native" in item.scenario_id for item in scenarios) == 2


def test_request_payload_contains_role_specific_data(tmp_path) -> None:
    scenario = smoke_scenarios()[0]
    payload = request_payload(scenario, run_id="run", artifact_dir=tmp_path)
    assert payload["predictor"]["known_covariates_names"] == ["holiday"]
    assert payload["covariates"]["past_covariates_names"] == ["rain"]
    assert len(payload["covariates"]["static_features"]) == 3
    assert payload["seed"] == 1


def test_response_validation_rejects_artifact_escape(tmp_path) -> None:
    scenario = smoke_scenarios()[2]
    artifact_dir = tmp_path / "artifact"
    artifact_dir.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    payload = {
        "run_id": "expected",
        "status": "OK",
        "operation": scenario.operation,
        "predictions": [
            {"mean": float(index), "item_id": "x", "horizon_step": 1} for index in range(6)
        ],
        "metadata": {
            "finite": True,
            "selected_model_ids": list(scenario.model_ids),
            "covariate_capability_decision": {
                "selected_model_ids": list(scenario.model_ids),
                "requested_roles": [role.value for role in scenario.roles],
                "model_roles": [
                    {
                        "model_id": scenario.model_ids[0],
                        "role": role.value,
                        "route": "native",
                        "covariate_regressor": None,
                    }
                    for role in scenario.roles
                ],
                "decision_sha256": "x",
            },
            "covariate_capability_sha256": "x",
        },
        "runtime_evidence": {"pid": 1, "resolved_device": "cpu", "gpu_used": False},
        "artifacts": {
            name: str(outside)
            for name in (
                "provider_context",
                "execution_plan",
                "timeline_mapping",
                "covariate_context",
                "covariate_capability_context",
            )
        },
    }
    errors, *_ = validate_response(
        scenario,
        payload,
        artifact_dir=artifact_dir,
        expected_run_id="expected",
    )
    assert any("escapes artifact_dir" in message for message in errors)


def test_smoke_campaign_verifies_with_fake_provider(tmp_path) -> None:
    provider = tmp_path / "provider.py"
    _write_fake_provider(provider)
    report = run_covariate_runtime_certification(
        CovariateCertificationConfig(
            repo_root=tmp_path,
            output_dir=tmp_path / "out",
            provider_command=(sys.executable, str(provider)),
        )
    )
    assert report.status is CovariateCertificationStatus.VERIFIED
    assert report.verified_count == 6
    assert report.failed_count == 0
    assert (Path(report.output_dir) / "SHA256SUMS").is_file()


def test_runtime_import_error_is_blocked(tmp_path) -> None:
    provider = tmp_path / "provider.py"
    _write_fake_provider(provider, error_code="RUNTIME_IMPORT_FAILED")
    report = run_covariate_runtime_certification(
        CovariateCertificationConfig(
            repo_root=tmp_path,
            output_dir=tmp_path / "out",
            provider_command=(sys.executable, str(provider)),
        )
    )
    assert report.status is CovariateCertificationStatus.BLOCKED_RUNTIME
    assert report.blocked_count == 6


def test_unexpected_provider_error_fails_campaign(tmp_path) -> None:
    provider = tmp_path / "provider.py"
    _write_fake_provider(provider, error_code="MODEL_BUILD_FAILED")
    report = run_covariate_runtime_certification(
        CovariateCertificationConfig(
            repo_root=tmp_path,
            output_dir=tmp_path / "out",
            provider_command=(sys.executable, str(provider)),
            scenario_ids=("native-deepar-known-static-fit",),
        )
    )
    assert report.status is CovariateCertificationStatus.FAILED
    assert report.failed_count == 1


def test_nonempty_output_directory_is_rejected(tmp_path) -> None:
    output = tmp_path / "out"
    output.mkdir()
    (output / "old.txt").write_text("old", encoding="utf-8")
    with pytest.raises(ValueError, match="absent or empty"):
        run_covariate_runtime_certification(
            CovariateCertificationConfig(
                repo_root=tmp_path,
                output_dir=output,
                provider_command=(sys.executable, "missing.py"),
            )
        )
