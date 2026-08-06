from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy" / "observability"


def _load_validator():
    path = ROOT / "scripts" / "observability" / "validate_stack.py"
    spec = importlib.util.spec_from_file_location("validate_stack", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_static_validator_passes_without_runtime_lock() -> None:
    result = _load_validator().validate()
    assert result["status"] == "PASS"
    assert result["loopback_ports_only"] is True
    assert result["docker_socket_mounted"] is False


def test_compose_is_loopback_only_and_has_exact_service_inventory() -> None:
    compose = yaml.safe_load((DEPLOY / "compose.yaml").read_text(encoding="utf-8"))
    assert set(compose["services"]) == {"grafana", "prometheus", "loki", "tempo", "alloy"}
    for service in compose["services"].values():
        assert service["security_opt"] == ["no-new-privileges:true"]
        for port in service.get("ports", []):
            assert str(port).startswith("127.0.0.1:")
    text = (DEPLOY / "compose.yaml").read_text(encoding="utf-8")
    assert "/var/run/docker.sock" not in text
    assert "privileged: true" not in text
    assert "network_mode: host" not in text


def test_exact_reviewed_version_tags_are_pinned_as_inputs() -> None:
    values = _load_validator().read_env(DEPLOY / "images.versions.env")
    assert values == _load_validator().EXPECTED_TAGS
    assert all("@sha256:" not in value for value in values.values())


def test_formal_lock_validation_fails_closed_when_locks_are_absent(tmp_path: Path) -> None:
    module = _load_validator()
    original = module.DEPLOY
    module.DEPLOY = tmp_path
    try:
        with pytest.raises(ValueError, match="images.lock.env"):
            module.validate_lock()
    finally:
        module.DEPLOY = original


def test_alloy_routes_metrics_logs_and_traces_with_bounded_queues() -> None:
    text = (DEPLOY / "alloy" / "config.alloy").read_text(encoding="utf-8")
    for required in (
        'prometheus.scrape "loto_api"',
        'prometheus.remote_write "local"',
        'loki.source.file "loto_jsonl"',
        'otelcol.receiver.otlp "local"',
        'otelcol.exporter.loki "local"',
        'otelcol.exporter.otlp "tempo"',
        "capacity             = 2500",
        "queue_size    = 500",
        'max_elapsed_time = "30s"',
    ):
        assert required in text
    label_block = text.split("stage.labels {", 1)[1].split("}", 1)[0]
    assert "run_id" not in label_block
    assert "trace_id" not in label_block


def test_loki_uses_tsdb_filesystem_and_retention() -> None:
    config = yaml.safe_load((DEPLOY / "loki" / "config.yml").read_text(encoding="utf-8"))
    assert config["auth_enabled"] is False
    assert config["schema_config"]["configs"][0]["store"] == "tsdb"
    assert config["schema_config"]["configs"][0]["schema"] == "v13"
    assert config["compactor"]["retention_enabled"] is True
    assert config["limits_config"]["retention_period"] == "${LOKI_RETENTION_PERIOD:168h}"


def test_tempo_uses_local_evaluation_storage_and_seven_day_retention() -> None:
    config = yaml.safe_load((DEPLOY / "tempo" / "config.yml").read_text(encoding="utf-8"))
    assert config["storage"]["trace"]["backend"] == "local"
    assert config["compactor"]["compaction"]["block_retention"] == "168h"
    protocols = config["distributor"]["receivers"]["otlp"]["protocols"]
    assert set(protocols) == {"grpc", "http"}


def test_grafana_datasources_are_file_provisioned_and_not_editable() -> None:
    config = yaml.safe_load(
        (DEPLOY / "grafana/provisioning/datasources/datasources.yml").read_text(
            encoding="utf-8"
        )
    )
    assert config["prune"] is True
    by_uid = {item["uid"]: item for item in config["datasources"]}
    assert set(by_uid) == {"prometheus", "loki", "tempo"}
    assert all(item["editable"] is False for item in by_uid.values())
    assert by_uid["prometheus"]["isDefault"] is True
    assert by_uid["tempo"]["jsonData"]["tracesToLogsV2"]["datasourceUid"] == "loki"


def test_dashboard_has_stable_uid_and_no_high_cardinality_selectors() -> None:
    dashboard = json.loads(
        (DEPLOY / "grafana/dashboards/platform-overview.json").read_text(encoding="utf-8")
    )
    assert dashboard["uid"] == "loto-platform-overview-v1"
    assert dashboard["editable"] is False
    assert len(dashboard["panels"]) == 6
    text = json.dumps(dashboard, sort_keys=True)
    for forbidden in ("run_id=", "request_id=", "trace_id=", "artifact_path="):
        assert forbidden not in text
    assert "loto_evaluation_hit_at_1" in text


def test_prometheus_scrape_inventory_is_fixed() -> None:
    config = yaml.safe_load(
        (DEPLOY / "prometheus/prometheus.yml").read_text(encoding="utf-8")
    )
    assert {item["job_name"] for item in config["scrape_configs"]} == {
        "prometheus",
        "alloy",
        "loki",
        "tempo",
        "grafana",
    }


def test_secret_and_runtime_files_are_gitignored() -> None:
    text = (DEPLOY / ".gitignore").read_text(encoding="utf-8")
    for required in (
        ".env",
        "images.lock.env",
        "IMAGE_DIGESTS.lock.json",
        "secrets/*",
        "runtime/*",
        "backups/*",
    ):
        assert required in text
    compose = (DEPLOY / "compose.yaml").read_text(encoding="utf-8")
    assert "GF_SECURITY_ADMIN_PASSWORD__FILE" in compose
    assert 'GF_AUTH_ANONYMOUS_ENABLED: "false"' in compose


def test_restore_requires_explicit_destructive_confirmation() -> None:
    text = (ROOT / "scripts/observability/backup_restore.sh").read_text(encoding="utf-8")
    assert 'CONFIRM_RESTORE:-NO' in text
    assert 'RESTORE_STATUS=PASS' in text
    assert 'AUTO_START=false' in text
    assert "sha256sum -c SHA256SUMS" in text


def test_prometheus_alert_rules_are_bounded_and_link_to_runbook() -> None:
    rules = yaml.safe_load(
        (DEPLOY / "prometheus/rules/platform-alerts.yml").read_text(encoding="utf-8")
    )
    alerts = [rule for group in rules["groups"] for rule in group["rules"]]
    assert {item["alert"] for item in alerts} == {
        "LotoObservabilityComponentDown",
        "LotoTelemetryDropsDetected",
        "LotoArtifactIntegrityFailure",
        "LotoPredictionLockVerificationFailure",
        "LotoPipelineStageNoRecentSuccess",
    }
    assert all(item["annotations"].get("runbook_url") for item in alerts)
    encoded = json.dumps(alerts, sort_keys=True)
    for forbidden in ("run_id=", "request_id=", "trace_id=", "artifact_path="):
        assert forbidden not in encoded
