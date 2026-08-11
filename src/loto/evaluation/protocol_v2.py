"""Complete, immutable evaluation protocol v2 contracts and artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from loto.evaluation.metric_registry import (
    PRIMARY_METRIC_ID,
    REQUIRED_BASELINE_IDS,
    REQUIRED_POINT_METRICS,
    resolve_metric_id,
    validate_metric_inventory,
)
from loto.evaluation.protocol_diff import (
    ProtocolDiff,
    assert_protocol_diff_comparable,
    build_protocol_diff,
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class StrictModel(BaseModel):
    """Shared strict, immutable protocol contract."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        validate_default=True,
        allow_inf_nan=False,
    )


class IdentityRef(StrictModel):
    """Identity and immutable SHA-256 for an input or policy."""

    identity: str = Field(min_length=1, max_length=256)
    sha256: str

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if not _SHA256_RE.fullmatch(value):
            raise ValueError("sha256 must be a lowercase 64-character digest")
        return value


class GameGeometryIdentity(StrictModel):
    """Game geometry that determines metric meaning."""

    game: str = Field(min_length=1, max_length=64)
    family: str = Field(min_length=1, max_length=32)
    positions: int = Field(ge=1, le=64)
    universe_size: int = Field(ge=1)
    value_min: int
    value_max: int
    ascending: bool

    @model_validator(mode="after")
    def validate_geometry(self) -> GameGeometryIdentity:
        if self.value_max < self.value_min:
            raise ValueError("value_max must be >= value_min")
        if self.positions > self.universe_size and self.family == "select":
            raise ValueError("select-game positions cannot exceed universe_size")
        return self


class MetricManifest(StrictModel):
    """Canonical metric inventory and primary metric."""

    primary_metric: str = PRIMARY_METRIC_ID
    metric_ids: tuple[str, ...] = REQUIRED_POINT_METRICS

    @field_validator("primary_metric")
    @classmethod
    def validate_primary(cls, value: str) -> str:
        canonical = resolve_metric_id(value)
        if canonical != PRIMARY_METRIC_ID:
            raise ValueError(f"primary metric must be {PRIMARY_METRIC_ID!r}")
        return canonical

    @field_validator("metric_ids")
    @classmethod
    def validate_metrics(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return validate_metric_inventory(value)


class BaselineManifest(StrictModel):
    """Fixed mandatory baseline inventory."""

    baseline_ids: tuple[str, ...] = REQUIRED_BASELINE_IDS

    @field_validator("baseline_ids")
    @classmethod
    def validate_baselines(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("baseline inventory contains duplicates")
        missing = set(REQUIRED_BASELINE_IDS).difference(value)
        if missing:
            raise ValueError(f"baseline inventory is missing required baselines: {sorted(missing)}")
        return value


class ResourceBudget(StrictModel):
    """Result-affecting comparison and search resource budget."""

    cpu_count: int = Field(ge=1)
    gpu_count: int = Field(ge=0)
    gpu_memory_bytes: int = Field(ge=0)
    wall_time_seconds: int = Field(ge=1)
    max_trials: int = Field(ge=1)
    parallel_trials: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_parallelism(self) -> ResourceBudget:
        if self.parallel_trials > self.max_trials:
            raise ValueError("parallel_trials cannot exceed max_trials")
        return self


class EvaluationProtocolV2(StrictModel):
    """Complete scientific identity for one formal evaluation protocol."""

    schema_version: Literal["2.0.0"] = "2.0.0"
    game_geometry: GameGeometryIdentity
    data_snapshot: IdentityRef
    split_manifest: IdentityRef
    feature_manifest: IdentityRef
    metric_manifest: MetricManifest = Field(default_factory=MetricManifest)
    baseline_manifest: BaselineManifest = Field(default_factory=BaselineManifest)
    alpha: float = Field(gt=0.0, lt=1.0)
    multiplicity_correction: str = Field(min_length=1, max_length=64)
    bootstrap_method: str = Field(min_length=1, max_length=64)
    bootstrap_repetitions: int = Field(ge=1)
    conformal_method: str = Field(min_length=1, max_length=64)
    conformal_alpha: float = Field(gt=0.0, lt=1.0)
    sentinel_inventory: tuple[str, ...] = Field(min_length=1)
    sentinel_repetitions: int = Field(ge=1)
    post_processing_identity: IdentityRef
    reconciliation_identity: IdentityRef
    seed_inventory: tuple[int, ...] = Field(min_length=1)
    seed_aggregation_policy: Literal["count_mean_population_variance_std_worst"] = (
        "count_mean_population_variance_std_worst"
    )
    search_space_identity: IdentityRef
    resource_budget: ResourceBudget
    package_versions: dict[str, str] = Field(min_length=1)
    code_hash: str
    git_commit: str

    @field_validator("sentinel_inventory")
    @classmethod
    def validate_sentinels(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("sentinel inventory contains duplicates")
        return value

    @field_validator("seed_inventory")
    @classmethod
    def validate_seeds(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if len(set(value)) != len(value):
            raise ValueError("seed inventory contains duplicates")
        if tuple(sorted(value)) != value:
            raise ValueError("seed inventory must be sorted for canonical identity")
        return value

    @field_validator("package_versions")
    @classmethod
    def validate_package_versions(cls, value: dict[str, str]) -> dict[str, str]:
        if any(not name or not version for name, version in value.items()):
            raise ValueError("package names and versions must be non-empty")
        return value

    @field_validator("code_hash")
    @classmethod
    def validate_code_hash(cls, value: str) -> str:
        if not _SHA256_RE.fullmatch(value):
            raise ValueError("code_hash must be a lowercase SHA-256 digest")
        return value

    @field_validator("git_commit")
    @classmethod
    def validate_git_commit(cls, value: str) -> str:
        if not _GIT_SHA_RE.fullmatch(value):
            raise ValueError("git_commit must be a lowercase 40-character commit SHA")
        return value

    def canonical_payload(self) -> dict[str, Any]:
        """Return the deterministic result-affecting payload."""

        return self.model_dump(mode="json", exclude_none=False)

    @property
    def protocol_hash(self) -> str:
        """SHA-256 over the complete canonical protocol payload."""

        return canonical_sha256(self.canonical_payload())

    @property
    def comparison_budget_hash(self) -> str:
        """SHA-256 over search-space identity and resource budget."""

        return canonical_sha256(
            {
                "search_space_identity": self.search_space_identity.model_dump(mode="json"),
                "resource_budget": self.resource_budget.model_dump(mode="json"),
            }
        )


@dataclass(frozen=True, slots=True)
class LegacyProtocolV1:
    """Read-only wrapper for an unmodified legacy protocol artifact."""

    schema_version: str
    protocol_hash: str
    payload: dict[str, Any]


def _canonical_json_default(value: Any) -> dict[str, str]:
    """Encode explicitly supported runtime-evidence objects deterministically.

    Formal protocol models are already JSON-native through ``model_dump(mode="json")``.
    The fallback is intentionally narrow: NeuralForecast loss modules may appear in
    runtime metadata (for example ``MAE()``) after a successful fit/predict.  Encoding
    their qualified type and stable module ``repr`` keeps campaign evidence writable
    without turning arbitrary Python objects into silently accepted protocol content.
    """

    value_type = type(value)
    module = value_type.__module__
    if module.startswith("neuralforecast.losses."):
        return {
            "__python_type__": f"{module}.{value_type.__qualname__}",
            "__repr__": repr(value),
        }
    raise TypeError(f"Object of type {value_type.__name__} is not JSON serializable")


def canonical_json_bytes(payload: Any) -> bytes:
    """Serialize canonical JSON and reject NaN/Infinity."""

    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_canonical_json_default,
    ).encode("utf-8")


def canonical_sha256(payload: Any) -> str:
    """Hash canonical JSON bytes."""

    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise ValueError(f"duplicate JSON key is forbidden: {key!r}")
        output[key] = value
    return output


def compare_protocols(
    left: EvaluationProtocolV2 | LegacyProtocolV1,
    right: EvaluationProtocolV2 | LegacyProtocolV1,
) -> ProtocolDiff:
    """Build a field-level diff; v1 and v2 are never silently comparable."""

    left_payload = (
        left.canonical_payload() if isinstance(left, EvaluationProtocolV2) else left.payload
    )
    right_payload = (
        right.canonical_payload() if isinstance(right, EvaluationProtocolV2) else right.payload
    )
    left_hash = left.protocol_hash
    right_hash = right.protocol_hash
    return build_protocol_diff(
        left_payload,
        right_payload,
        left_hash=left_hash,
        right_hash=right_hash,
    )


def assert_protocols_comparable(
    left: EvaluationProtocolV2 | LegacyProtocolV1,
    right: EvaluationProtocolV2 | LegacyProtocolV1,
) -> None:
    """Reject comparison for any field difference or schema mismatch."""

    diff = compare_protocols(left, right)
    assert_protocol_diff_comparable(diff)


def _legacy_from_payload(payload: dict[str, Any]) -> LegacyProtocolV1:
    protocol = payload.get("protocol", payload)
    if not isinstance(protocol, dict):
        raise ValueError("legacy protocol payload must be an object")
    schema_version = str(protocol.get("schema_version", "1.0.0"))
    stored_hash = payload.get("protocol_hash")
    protocol_hash = str(stored_hash) if stored_hash else canonical_sha256(protocol)
    return LegacyProtocolV1(
        schema_version=schema_version,
        protocol_hash=protocol_hash,
        payload=dict(protocol),
    )


def read_protocol_artifact(path: str | Path) -> EvaluationProtocolV2 | LegacyProtocolV1:
    """Read protocol v2 strictly while retaining v1 read compatibility."""

    raw = Path(path).read_text(encoding="utf-8")
    payload = json.loads(
        raw,
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"non-finite JSON constant is forbidden: {value}")
        ),
    )
    if not isinstance(payload, dict):
        raise ValueError("protocol artifact must contain a JSON object")
    candidate = payload.get("protocol", payload)
    if isinstance(candidate, dict) and candidate.get("schema_version") == "2.0.0":
        return EvaluationProtocolV2.model_validate_json(canonical_json_bytes(candidate))
    return _legacy_from_payload(payload)


def write_protocol_artifact(
    path: str | Path,
    protocol: EvaluationProtocolV2,
) -> None:
    """Atomically write a new v2 artifact and never rewrite historical files."""

    destination = Path(path)
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite historical artifact: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    artifact = {
        "protocol_hash": protocol.protocol_hash,
        "comparison_budget_hash": protocol.comparison_budget_hash,
        "protocol": protocol.canonical_payload(),
    }
    data = canonical_json_bytes(artifact) + b"\n"
    fd, temp_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, destination)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise
