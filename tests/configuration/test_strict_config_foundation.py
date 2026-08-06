from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from loto.configuration.cli import main
from loto.configuration.contracts import CONFIG_SCHEMA_VERSION, REDACTED_VALUE
from loto.configuration.loader import load_config, resolve_payload, write_resolved_config
from loto.configuration.migration import ConfigMigrationRequiredError, migrate_payload

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "configs/configuration/strict_foundation.example.yaml"


def _payload() -> dict:
    return {
        "config_schema_version": CONFIG_SCHEMA_VERSION,
        "experiment_name": "focused-test",
        "runtime": {
            "output_dir": "artifacts/focused-test",
            "device": {
                "requested": "cpu",
                "cpu_fallback_policy": "not_applicable",
            },
        },
    }


def test_example_loads_with_required_safe_defaults() -> None:
    resolved = load_config(EXAMPLE, environ={})

    assert resolved.config.config_schema_version == CONFIG_SCHEMA_VERSION
    assert resolved.config.split_policy.immutable is True
    assert resolved.config.split_policy.model_fit_scope == "train_only"
    assert resolved.config.split_policy.holdout.auto_open_actuals is False
    assert resolved.config.split_policy.prospective.auto_run is False
    assert resolved.config.evaluation.metrics.primary_metric == "Hit@±1"
    assert {"MAE", "MSE", "RMSE"}.issubset(
        resolved.config.evaluation.metrics.report_metrics
    )
    assert resolved.config.evaluation.seed_policy.best_seed_only_selection is False


def test_unknown_keys_and_strict_types_are_rejected() -> None:
    unknown = _payload() | {"unknown": True}
    with pytest.raises(ValidationError):
        resolve_payload(unknown, environ={})

    wrong_type = _payload()
    wrong_type["evaluation"] = {"seed_policy": {"seeds": ["1"]}}
    with pytest.raises(ValidationError):
        resolve_payload(wrong_type, environ={})


def test_range_and_required_metric_validation() -> None:
    invalid_seed = _payload()
    invalid_seed["evaluation"] = {"seed_policy": {"seeds": [-1]}}
    with pytest.raises(ValidationError):
        resolve_payload(invalid_seed, environ={})

    missing_metric = _payload()
    missing_metric["evaluation"] = {
        "metrics": {
            "primary_metric": "Hit@±1",
            "report_metrics": ["Hit@±1", "MAE", "MSE", "Position Hit@±1"],
        }
    }
    with pytest.raises(ValidationError):
        resolve_payload(missing_metric, environ={})


def test_environment_override_provenance_and_secret_redaction() -> None:
    secret = "do-not-persist-this-token"
    resolved = resolve_payload(
        _payload(),
        environ={
            "LOTO_CONFIG_OUTPUT_DIR": "artifacts/from-env",
            "LOTO_CONFIG_SEEDS": "[7, 8]",
            "LOTO_CONFIG_MLFLOW_ENABLED": "true",
            "LOTO_CONFIG_MLFLOW_TRACKING_URI": "https://mlflow.example.invalid",
            "LOTO_CONFIG_MLFLOW_TOKEN": secret,
        },
    )
    serialized = json.dumps(resolved.envelope(), ensure_ascii=False, sort_keys=True)

    assert resolved.config.runtime.output_dir == "artifacts/from-env"
    assert resolved.config.evaluation.seed_policy.seeds == [7, 8]
    assert len(resolved.overrides) == 5
    assert all(record.source == "environment" for record in resolved.overrides)
    assert secret not in serialized
    assert REDACTED_VALUE in serialized
    assert secret not in resolved.config_sha256


def test_device_request_and_fallback_policy_are_distinct() -> None:
    invalid_cuda = _payload()
    invalid_cuda["runtime"]["device"] = {
        "requested": "cuda",
        "cpu_fallback_policy": "not_applicable",
    }
    with pytest.raises(ValidationError):
        resolve_payload(invalid_cuda, environ={})

    valid_cuda = _payload()
    valid_cuda["runtime"]["device"] = {
        "requested": "cuda",
        "cpu_fallback_policy": "forbid",
    }
    resolved = resolve_payload(valid_cuda, environ={})
    assert resolved.config.runtime.device.requested == "cuda"
    assert resolved.config.runtime.device.cpu_fallback_policy == "forbid"


def test_protected_stages_cannot_be_auto_opened_in_v1() -> None:
    payload = _payload()
    payload["split_policy"] = {"holdout": {"auto_open_actuals": True}}
    with pytest.raises(ValidationError):
        resolve_payload(payload, environ={})


def test_resolved_output_is_atomic_redacted_and_hash_bound(tmp_path) -> None:
    resolved = resolve_payload(_payload(), environ={})
    output = tmp_path / "resolved.json"
    target, sidecar = write_resolved_config(resolved, output)
    envelope = json.loads(target.read_text(encoding="utf-8"))

    assert envelope["resolved_config_sha256"] == resolved.config_sha256
    assert sidecar.read_text(encoding="utf-8") == f"{resolved.config_sha256}  resolved.json\n"
    assert not (tmp_path / ".resolved.json.tmp").exists()
    assert not (tmp_path / ".resolved.json.sha256.tmp").exists()


def test_schema_migration_never_runs_implicitly() -> None:
    unversioned = _payload()
    del unversioned["config_schema_version"]
    with pytest.raises(ConfigMigrationRequiredError):
        resolve_payload(unversioned, environ={})

    old = _payload()
    old["config_schema_version"] = "0.9.0"
    with pytest.raises(ConfigMigrationRequiredError):
        migrate_payload(old)


def test_cli_writes_resolved_artifact_without_printing_secret(tmp_path, capsys) -> None:
    output = tmp_path / "resolved.json"
    assert main([str(EXAMPLE), "--resolved-output", str(output), "--ignore-environment"]) == 0
    stdout = capsys.readouterr().out

    assert '"status": "VALID"' in stdout
    assert output.exists()
    assert output.with_name("resolved.json.sha256").exists()
