from __future__ import annotations

import asyncio
from collections.abc import Sequence

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from loto.api.health_observability import (
    DependencyCriticality,
    DependencyName,
    DependencyProbeSpec,
    DependencyState,
    ProbeObservation,
    ReadinessStatus,
    default_probe_specs,
    install_health_observability,
)


class FakeProbe:
    def __init__(
        self,
        state: DependencyState,
        *,
        detail_code: str = "fake_result",
        delay_seconds: float = 0.0,
        error: Exception | None = None,
    ) -> None:
        self.state = state
        self.detail_code = detail_code
        self.delay_seconds = delay_seconds
        self.error = error

    async def probe(self) -> ProbeObservation:
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        if self.error is not None:
            raise self.error
        return ProbeObservation(state=self.state, detail_code=self.detail_code)


def _specs(
    *,
    required_state: DependencyState = DependencyState.CONFIGURED_AND_READY,
    optional_state: DependencyState = DependencyState.NOT_CONFIGURED,
    required_probe: FakeProbe | None = None,
    optional_probe: FakeProbe | None = None,
) -> tuple[DependencyProbeSpec, ...]:
    specs: list[DependencyProbeSpec] = []
    for name in DependencyName:
        is_required = name in {
            DependencyName.REGISTRY_DATABASE,
            DependencyName.ARTIFACT_STORE,
        }
        state = required_state if is_required else optional_state
        probe = required_probe if is_required else optional_probe
        configured = state not in {
            DependencyState.NOT_CONFIGURED,
            DependencyState.NOT_APPLICABLE,
            DependencyState.UNKNOWN,
        }
        applicable = state != DependencyState.NOT_APPLICABLE
        if state == DependencyState.UNKNOWN:
            configured = None
        if not applicable:
            configured = None
            probe = None
        elif state == DependencyState.NOT_CONFIGURED:
            probe = None
        elif probe is None:
            probe = FakeProbe(state)
        specs.append(
            DependencyProbeSpec(
                name=name,
                criticality=(
                    DependencyCriticality.REQUIRED
                    if is_required
                    else DependencyCriticality.OPTIONAL
                ),
                configured=configured,
                applicable=applicable,
                probe=probe,
            )
        )
    return tuple(specs)


def _client(
    specs: Sequence[DependencyProbeSpec],
    *,
    timeout_seconds: float = 0.1,
) -> TestClient:
    app = FastAPI()
    install_health_observability(
        app,
        probe_specs=specs,
        timeout_seconds=timeout_seconds,
    )
    return TestClient(app)


def test_livez_checks_process_only_and_ignores_failing_dependencies() -> None:
    failing = FakeProbe(
        DependencyState.CONFIGURED_BUT_UNAVAILABLE,
        error=RuntimeError("postgresql://user:secret@example.invalid/db"),
    )
    client = _client(_specs(required_probe=failing))

    response = client.get("/livez")

    assert response.status_code == 200
    assert response.json()["status"] == "ALIVE"
    assert response.headers["X-Request-ID"] == response.json()["request_id"]


def test_request_id_is_preserved_when_safe_and_replaced_when_unsafe() -> None:
    client = _client(_specs())

    safe = client.get("/livez", headers={"X-Request-ID": "trace-123"})
    unsafe = client.get("/livez", headers={"X-Request-ID": "secret value with spaces"})

    assert safe.json()["request_id"] == "trace-123"
    assert safe.headers["X-Request-ID"] == "trace-123"
    assert unsafe.json()["request_id"] != "secret value with spaces"
    assert len(unsafe.json()["request_id"]) <= 128


def test_required_dependency_failure_is_unready() -> None:
    client = _client(_specs(required_state=DependencyState.CONFIGURED_BUT_UNAVAILABLE))

    response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["status"] == ReadinessStatus.UNREADY.value


def test_optional_dependency_failure_is_degraded_not_dead_or_unready() -> None:
    client = _client(_specs(optional_state=DependencyState.CONFIGURED_BUT_UNAVAILABLE))

    readiness = client.get("/readyz")
    liveness = client.get("/livez")

    assert readiness.status_code == 200
    assert readiness.json()["status"] == ReadinessStatus.DEGRADED.value
    assert liveness.status_code == 200


def test_not_configured_optional_dependencies_are_neutral() -> None:
    client = _client(_specs(optional_state=DependencyState.NOT_CONFIGURED))

    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json()["status"] == ReadinessStatus.READY.value


def test_required_not_configured_and_unknown_are_unready() -> None:
    for state in (DependencyState.NOT_CONFIGURED, DependencyState.UNKNOWN):
        client = _client(_specs(required_state=state))
        response = client.get("/readyz")
        assert response.status_code == 503
        assert response.json()["status"] == ReadinessStatus.UNREADY.value


def test_not_applicable_dependencies_are_neutral() -> None:
    client = _client(_specs(optional_state=DependencyState.NOT_APPLICABLE))

    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json()["status"] == ReadinessStatus.READY.value


def test_probe_timeout_is_configured_but_unavailable() -> None:
    slow = FakeProbe(
        DependencyState.CONFIGURED_AND_READY,
        delay_seconds=0.05,
    )
    client = _client(_specs(required_probe=slow), timeout_seconds=0.001)

    response = client.get("/health/dependencies")
    rows = {item["dependency"]: item for item in response.json()["dependencies"]}

    assert response.status_code == 200
    assert rows["registry_database"]["state"] == "CONFIGURED_BUT_UNAVAILABLE"
    assert rows["registry_database"]["detail_code"] == "probe_timeout"


def test_probe_exception_is_sanitized_and_never_exposes_dsn() -> None:
    secret_dsn = "postgresql://admin:super-secret@example.invalid/db"
    failing = FakeProbe(
        DependencyState.CONFIGURED_AND_READY,
        error=RuntimeError(secret_dsn),
    )
    client = _client(_specs(required_probe=failing))

    response = client.get("/health/dependencies")
    serialized = response.text

    assert secret_dsn not in serialized
    assert "super-secret" not in serialized
    assert "probe_exception" in serialized


def test_health_dependencies_contains_exact_fixed_inventory() -> None:
    client = _client(_specs())

    response = client.get("/health/dependencies")
    dependencies = response.json()["dependencies"]

    assert response.status_code == 200
    assert {item["dependency"] for item in dependencies} == {item.value for item in DependencyName}
    assert all("latency_ms" in item for item in dependencies)
    assert all("criticality" in item for item in dependencies)


def test_default_specs_do_not_claim_backend_readiness() -> None:
    specs = default_probe_specs()

    required = [item for item in specs if item.criticality == DependencyCriticality.REQUIRED]
    optional = [item for item in specs if item.criticality == DependencyCriticality.OPTIONAL]

    assert all(item.configured is True and item.probe is None for item in required)
    assert all(item.configured is False and item.probe is None for item in optional)


def test_probe_observation_is_strict_and_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ProbeObservation.model_validate(
            {
                "state": "CONFIGURED_AND_READY",
                "detail_code": "ready",
                "dsn": "postgresql://secret",
            }
        )


def test_prometheus_metrics_use_only_bounded_labels() -> None:
    client = _client(_specs())
    request_id = "request-id-must-not-be-a-label"

    client.get("/readyz", headers={"X-Request-ID": request_id})

    from prometheus_client import generate_latest

    metrics = generate_latest().decode("utf-8")
    assert "loto_health_endpoint_requests_total" in metrics
    assert "loto_dependency_probe_total" in metrics
    assert "loto_dependency_ready" in metrics
    assert "loto_api_readiness_status" in metrics
    assert request_id not in metrics
    assert "detail_code=" not in metrics


def test_existing_health_contract_is_unchanged(tmp_path) -> None:
    from loto.api.app import create_app

    client = TestClient(
        create_app(
            tmp_path,
            dependency_probe_specs=_specs(),
            dependency_probe_timeout_seconds=0.1,
        )
    )

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "output_dir": str(tmp_path),
        "auth_enabled": False,
    }
    assert response.headers["X-Request-ID"]


def test_existing_metrics_endpoint_exposes_new_low_cardinality_metrics(tmp_path) -> None:
    from loto.api.app import create_app

    client = TestClient(
        create_app(
            tmp_path,
            dependency_probe_specs=_specs(),
            dependency_probe_timeout_seconds=0.1,
        )
    )
    client.get("/health/dependencies")

    response = client.get("/metrics")

    assert response.status_code == 200
    assert "loto_dependency_probe_total" in response.text
    assert "loto_api_readiness_status" in response.text
