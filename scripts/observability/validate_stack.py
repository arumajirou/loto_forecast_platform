#!/usr/bin/env python3
"""Static, fail-closed validation for the local LGTM deployment assets."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy" / "observability"
DIGEST_RE = re.compile(r"^[^@\s]+@sha256:[0-9a-f]{64}$")
EXPECTED_TAGS = {
    "GRAFANA_IMAGE_TAG": "grafana/grafana:13.1.1",
    "ALLOY_IMAGE_TAG": "grafana/alloy:v1.18.0",
    "PROMETHEUS_IMAGE_TAG": "prom/prometheus:v3.11.3",
    "LOKI_IMAGE_TAG": "grafana/loki:3.7.2",
    "TEMPO_IMAGE_TAG": "grafana/tempo:2.10.5",
    "BUSYBOX_IMAGE_TAG": "busybox:1.37.0-uclibc",
}
REQUIRED_FILES = (
    "compose.yaml",
    "images.versions.env",
    "alloy/config.alloy",
    "prometheus/prometheus.yml",
    "prometheus/rules/platform-alerts.yml",
    "loki/config.yml",
    "tempo/config.yml",
    "grafana/provisioning/datasources/datasources.yml",
    "grafana/provisioning/dashboards/dashboards.yml",
    "grafana/dashboards/platform-overview.json",
)
EXPECTED_SERVICES = {"grafana", "prometheus", "loki", "tempo", "alloy"}
PROHIBITED_COMPOSE_TEXT = (
    "/var/run/docker.sock",
    "network_mode: host",
    "pid: host",
    "privileged: true",
)
PROHIBITED_DASHBOARD_LABELS = (
    "run_id=",
    "request_id=",
    "trace_id=",
    "span_id=",
    "git_sha=",
    "model_revision=",
    "artifact_path=",
    "dataset_hash=",
    "config_hash=",
    "error_message=",
    "user_id=",
)


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_lock() -> dict[str, Any]:
    lock_env_path = DEPLOY / "images.lock.env"
    lock_json_path = DEPLOY / "IMAGE_DIGESTS.lock.json"
    require(lock_env_path.exists(), "images.lock.env is required")
    require(lock_json_path.exists(), "IMAGE_DIGESTS.lock.json is required")
    env = read_env(lock_env_path)
    expected_keys = {key.removesuffix("_TAG") for key in EXPECTED_TAGS}
    require(set(env) == expected_keys, "locked image key inventory mismatch")
    for key, value in env.items():
        require(bool(DIGEST_RE.fullmatch(value)), f"{key} is not digest locked")
    payload = json.loads(lock_json_path.read_text(encoding="utf-8"))
    require(payload.get("schema_version") == "1.0.0", "invalid image lock schema")
    require(set(payload.get("images", {})) == expected_keys, "lock JSON inventory mismatch")
    for key, record in payload["images"].items():
        require(record.get("tag") == EXPECTED_TAGS[f"{key}_TAG"], f"{key} tag drift")
        require(record.get("locked_ref") == env[key], f"{key} lock disagreement")
    return payload


def validate() -> dict[str, Any]:
    for relative in REQUIRED_FILES:
        require((DEPLOY / relative).is_file(), f"missing required file: {relative}")

    versions = read_env(DEPLOY / "images.versions.env")
    require(versions == EXPECTED_TAGS, "reviewed image tag inventory drifted")

    compose_path = DEPLOY / "compose.yaml"
    compose_text = compose_path.read_text(encoding="utf-8")
    compose = load_yaml(compose_path)
    services = compose.get("services", {})
    require(set(services) == EXPECTED_SERVICES, "compose service inventory mismatch")
    for text in PROHIBITED_COMPOSE_TEXT:
        require(text not in compose_text, f"prohibited compose setting: {text}")
    for name, service in services.items():
        require(service.get("security_opt") == ["no-new-privileges:true"], f"{name} security_opt")
        for port in service.get("ports", []):
            require(str(port).startswith("127.0.0.1:"), f"{name} exposes a non-loopback port")
    require('GF_AUTH_ANONYMOUS_ENABLED: "false"' in compose_text, "anonymous Grafana")
    require('GF_USERS_ALLOW_SIGN_UP: "false"' in compose_text, "Grafana signup enabled")
    require("images.lock.env" not in compose_text, "compose must not depend on committed locks")

    prometheus = load_yaml(DEPLOY / "prometheus/prometheus.yml")
    jobs = {item["job_name"] for item in prometheus["scrape_configs"]}
    require(jobs == EXPECTED_SERVICES, "Prometheus internal scrape jobs mismatch")
    require(
        prometheus.get("rule_files") == ["/etc/prometheus/rules/*.yml"],
        "Prometheus rule file inventory mismatch",
    )
    rules = load_yaml(DEPLOY / "prometheus/rules/platform-alerts.yml")
    alerts = {
        rule["alert"]
        for group in rules.get("groups", [])
        for rule in group.get("rules", [])
    }
    require(
        alerts
        == {
            "LotoObservabilityComponentDown",
            "LotoTelemetryDropsDetected",
            "LotoArtifactIntegrityFailure",
            "LotoPredictionLockVerificationFailure",
            "LotoPipelineStageNoRecentSuccess",
        },
        "Prometheus alert inventory mismatch",
    )

    loki_text = (DEPLOY / "loki/config.yml").read_text(encoding="utf-8")
    require("retention_enabled: true" in loki_text, "Loki retention is not enabled")
    require("schema: v13" in loki_text and "store: tsdb" in loki_text, "Loki TSDB v13 required")

    tempo_text = (DEPLOY / "tempo/config.yml").read_text(encoding="utf-8")
    require("block_retention: 168h" in tempo_text, "Tempo retention drift")
    require("backend: local" in tempo_text, "Tempo local evaluation backend required")

    alloy_text = (DEPLOY / "alloy/config.alloy").read_text(encoding="utf-8")
    require("prometheus.remote_write" in alloy_text, "Alloy Prometheus route missing")
    require("otelcol.receiver.otlp" in alloy_text, "Alloy OTLP receiver missing")
    require("otelcol.exporter.otlp" in alloy_text, "Alloy Tempo exporter missing")
    require("loki.source.file" in alloy_text, "Alloy JSONL source missing")
    label_block = alloy_text.split('stage.labels {', 1)[1].split('}', 1)[0]
    require(
        "run_id" not in label_block and "trace_id" not in label_block,
        "high-cardinality Loki label",
    )

    datasources = load_yaml(DEPLOY / "grafana/provisioning/datasources/datasources.yml")
    uids = {item["uid"] for item in datasources["datasources"]}
    require(uids == {"prometheus", "loki", "tempo"}, "Grafana datasource inventory mismatch")

    dashboard = json.loads(
        (DEPLOY / "grafana/dashboards/platform-overview.json").read_text(encoding="utf-8")
    )
    require(dashboard.get("uid") == "loto-platform-overview-v1", "dashboard UID drift")
    require(len(dashboard.get("panels", [])) == 6, "dashboard panel inventory mismatch")
    dashboard_text = json.dumps(dashboard, sort_keys=True)
    for label in PROHIBITED_DASHBOARD_LABELS:
        require(label not in dashboard_text, f"prohibited dashboard label selector: {label}")

    return {
        "schema_version": "1.0.0",
        "status": "PASS",
        "services": sorted(services),
        "image_tags": versions,
        "dashboard_uid": dashboard["uid"],
        "dashboard_panels": len(dashboard["panels"]),
        "prometheus_jobs": sorted(jobs),
        "loopback_ports_only": True,
        "docker_socket_mounted": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-lock", action="store_true")
    args = parser.parse_args()
    result = validate()
    if args.require_lock:
        result["image_lock"] = validate_lock()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
