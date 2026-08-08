"""Fail-closed FastAPI liveness, readiness, and dependency observability."""

from __future__ import annotations

import asyncio
import re
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Gauge
from pydantic import BaseModel, ConfigDict, Field, field_validator

REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        validate_default=True,
    )


class DependencyName(StrEnum):
    REGISTRY_DATABASE = "registry_database"
    POSTGRESQL = "postgresql"
    MLFLOW = "mlflow"
    ARTIFACT_STORE = "artifact_store"
    PREDICTION_LOCK_VERIFIER = "prediction_lock_verifier"
    DATA_FRESHNESS = "data_freshness"
    GPU_SERVICE = "gpu_service"
    JOB_QUEUE = "job_queue"


class DependencyState(StrEnum):
    CONFIGURED_AND_READY = "CONFIGURED_AND_READY"
    CONFIGURED_BUT_UNAVAILABLE = "CONFIGURED_BUT_UNAVAILABLE"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNKNOWN = "UNKNOWN"


class DependencyCriticality(StrEnum):
    REQUIRED = "REQUIRED"
    OPTIONAL = "OPTIONAL"


class ReadinessStatus(StrEnum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    UNREADY = "UNREADY"


class ProbeObservation(StrictModel):
    state: DependencyState
    detail_code: str = Field(default="probe_completed", pattern=r"^[a-z0-9_]{1,64}$")


@runtime_checkable
class DependencyProbe(Protocol):
    async def probe(self) -> ProbeObservation:
        """Return one secret-free observation without mutating service state."""


@dataclass(frozen=True)
class DependencyProbeSpec:
    name: DependencyName
    criticality: DependencyCriticality
    configured: bool | None
    applicable: bool = True
    probe: DependencyProbe | None = None

    def __post_init__(self) -> None:
        if not self.applicable:
            if self.configured is not None or self.probe is not None:
                raise ValueError("not-applicable dependency must not be configured or probed")
        if self.configured is False and self.probe is not None:
            raise ValueError("unconfigured dependency must not have a live probe")


class DependencyStatus(StrictModel):
    dependency: DependencyName
    criticality: DependencyCriticality
    state: DependencyState
    ready: bool
    detail_code: str = Field(pattern=r"^[a-z0-9_]{1,64}$")
    latency_ms: float = Field(ge=0.0)
    checked_at_utc: datetime

    @field_validator("checked_at_utc")
    @classmethod
    def timezone_aware(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("checked_at_utc must be timezone-aware")
        return value


class LivenessResponse(StrictModel):
    status: str = "ALIVE"
    request_id: str = Field(min_length=1, max_length=128)


class DependencyHealthResponse(StrictModel):
    status: ReadinessStatus
    request_id: str = Field(min_length=1, max_length=128)
    checked_at_utc: datetime
    probe_timeout_seconds: float = Field(gt=0.0, le=60.0)
    dependencies: list[DependencyStatus]


_HEALTH_REQUESTS = Counter(
    "loto_health_endpoint_requests_total",
    "Health endpoint requests by bounded endpoint and outcome.",
    ("endpoint", "outcome"),
)
_DEPENDENCY_PROBES = Counter(
    "loto_dependency_probe_total",
    "Dependency probe results by fixed dependency and bounded state.",
    ("dependency", "state"),
)
_DEPENDENCY_READY = Gauge(
    "loto_dependency_ready",
    "Whether a fixed dependency is configured and ready.",
    ("dependency",),
)
_DEPENDENCY_LATENCY = Gauge(
    "loto_dependency_probe_duration_seconds",
    "Most recent dependency probe duration.",
    ("dependency",),
)
_READINESS = Gauge(
    "loto_api_readiness_status",
    "One-hot API readiness state.",
    ("status",),
)


def _safe_request_id(candidate: str | None) -> str:
    if candidate and _REQUEST_ID_PATTERN.fullmatch(candidate):
        return candidate
    return uuid.uuid4().hex


def install_request_id_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = _safe_request_id(request.headers.get(REQUEST_ID_HEADER))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


def default_probe_specs() -> tuple[DependencyProbeSpec, ...]:
    """Return honest placeholders without connecting to any live dependency."""

    required = {
        DependencyName.REGISTRY_DATABASE,
        DependencyName.ARTIFACT_STORE,
    }
    return tuple(
        DependencyProbeSpec(
            name=name,
            criticality=(
                DependencyCriticality.REQUIRED
                if name in required
                else DependencyCriticality.OPTIONAL
            ),
            configured=True if name in required else False,
            applicable=True,
            probe=None,
        )
        for name in DependencyName
    )


class DependencyHealthService:
    def __init__(
        self,
        specs: Sequence[DependencyProbeSpec],
        *,
        timeout_seconds: float = 1.0,
    ) -> None:
        if not 0.0 < timeout_seconds <= 60.0:
            raise ValueError("timeout_seconds must be in (0, 60]")
        names = [spec.name for spec in specs]
        if len(names) != len(set(names)):
            raise ValueError("dependency probe names must be unique")
        expected = set(DependencyName)
        actual = set(names)
        if actual != expected:
            missing = sorted(item.value for item in expected - actual)
            extra = sorted(item.value for item in actual - expected)
            raise ValueError(
                f"dependency probe inventory mismatch: missing={missing}, extra={extra}"
            )
        self._specs = tuple(specs)
        self.timeout_seconds = timeout_seconds

    async def _run_one(self, spec: DependencyProbeSpec) -> DependencyStatus:
        started = time.perf_counter()
        state: DependencyState
        detail_code: str
        if not spec.applicable:
            state = DependencyState.NOT_APPLICABLE
            detail_code = "not_applicable"
        elif spec.configured is False:
            state = DependencyState.NOT_CONFIGURED
            detail_code = "not_configured"
        elif spec.configured is None:
            state = DependencyState.UNKNOWN
            detail_code = "configuration_unknown"
        elif spec.probe is None:
            state = DependencyState.UNKNOWN
            detail_code = "probe_not_registered"
        else:
            try:
                observation = await asyncio.wait_for(
                    spec.probe.probe(),
                    timeout=self.timeout_seconds,
                )
                if observation.state not in {
                    DependencyState.CONFIGURED_AND_READY,
                    DependencyState.CONFIGURED_BUT_UNAVAILABLE,
                }:
                    state = DependencyState.UNKNOWN
                    detail_code = "invalid_probe_state"
                else:
                    state = observation.state
                    detail_code = observation.detail_code
            except TimeoutError:
                state = DependencyState.CONFIGURED_BUT_UNAVAILABLE
                detail_code = "probe_timeout"
            except Exception:
                state = DependencyState.CONFIGURED_BUT_UNAVAILABLE
                detail_code = "probe_exception"
        latency_ms = max(0.0, (time.perf_counter() - started) * 1000.0)
        ready = state == DependencyState.CONFIGURED_AND_READY
        checked_at = datetime.now(UTC)
        _DEPENDENCY_PROBES.labels(spec.name.value, state.value).inc()
        _DEPENDENCY_READY.labels(spec.name.value).set(1.0 if ready else 0.0)
        _DEPENDENCY_LATENCY.labels(spec.name.value).set(latency_ms / 1000.0)
        return DependencyStatus(
            dependency=spec.name,
            criticality=spec.criticality,
            state=state,
            ready=ready,
            detail_code=detail_code,
            latency_ms=latency_ms,
            checked_at_utc=checked_at,
        )

    async def snapshot(self, request_id: str) -> DependencyHealthResponse:
        statuses = list(await asyncio.gather(*(self._run_one(spec) for spec in self._specs)))
        overall = classify_readiness(statuses)
        for candidate in ReadinessStatus:
            _READINESS.labels(candidate.value).set(1.0 if candidate == overall else 0.0)
        return DependencyHealthResponse(
            status=overall,
            request_id=request_id,
            checked_at_utc=datetime.now(UTC),
            probe_timeout_seconds=self.timeout_seconds,
            dependencies=statuses,
        )


def classify_readiness(statuses: Sequence[DependencyStatus]) -> ReadinessStatus:
    required_failure_states = {
        DependencyState.CONFIGURED_BUT_UNAVAILABLE,
        DependencyState.NOT_CONFIGURED,
        DependencyState.UNKNOWN,
    }
    optional_degraded_states = {
        DependencyState.CONFIGURED_BUT_UNAVAILABLE,
        DependencyState.UNKNOWN,
    }
    if any(
        item.criticality == DependencyCriticality.REQUIRED and item.state in required_failure_states
        for item in statuses
    ):
        return ReadinessStatus.UNREADY
    if any(
        item.criticality == DependencyCriticality.OPTIONAL
        and item.state in optional_degraded_states
        for item in statuses
    ):
        return ReadinessStatus.DEGRADED
    return ReadinessStatus.READY


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", _safe_request_id(None)))


def build_health_router(service: DependencyHealthService) -> APIRouter:
    router = APIRouter(tags=["health"])

    @router.get("/livez", response_model=LivenessResponse)
    async def livez(request: Request) -> LivenessResponse:
        _HEALTH_REQUESTS.labels("livez", "alive").inc()
        return LivenessResponse(request_id=_request_id(request))

    @router.get("/readyz", response_model=DependencyHealthResponse)
    async def readyz(request: Request) -> JSONResponse:
        snapshot = await service.snapshot(_request_id(request))
        outcome = snapshot.status.value.casefold()
        _HEALTH_REQUESTS.labels("readyz", outcome).inc()
        status_code = 503 if snapshot.status == ReadinessStatus.UNREADY else 200
        return JSONResponse(status_code=status_code, content=snapshot.model_dump(mode="json"))

    @router.get("/health/dependencies", response_model=DependencyHealthResponse)
    async def health_dependencies(request: Request) -> DependencyHealthResponse:
        snapshot = await service.snapshot(_request_id(request))
        _HEALTH_REQUESTS.labels(
            "health_dependencies",
            snapshot.status.value.casefold(),
        ).inc()
        return snapshot

    return router


def install_health_observability(
    app: FastAPI,
    *,
    probe_specs: Sequence[DependencyProbeSpec] | None = None,
    timeout_seconds: float = 1.0,
) -> DependencyHealthService:
    install_request_id_middleware(app)
    service = DependencyHealthService(
        probe_specs or default_probe_specs(),
        timeout_seconds=timeout_seconds,
    )
    app.state.dependency_health_service = service
    app.include_router(build_health_router(service))
    return service


def dependency_status_map(
    response: DependencyHealthResponse,
) -> Mapping[DependencyName, DependencyStatus]:
    return {item.dependency: item for item in response.dependencies}
