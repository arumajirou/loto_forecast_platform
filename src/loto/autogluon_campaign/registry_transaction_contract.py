from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote, urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from loto.autogluon_campaign.approval_authorization_contract import (
    ApprovalAuthorizationError,
    RegistrySubject,
    canonical_sha256,
    parse_utc,
    verify_registry_authorization,
)

P19_SCHEMA = "autogluon-registry-transaction-v1"
REGISTRY_SCHEMA = "autogluon-file-json-registry-v1"
BACKEND = "file-json-cas-v1"


class RegistryTransactionError(ApprovalAuthorizationError):
    pass


class RegistryPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    backend: Literal["file-json-cas-v1"] = BACKEND
    compare_and_swap_required: Literal[True] = True
    append_only_consumption_ledger_required: Literal[True] = True
    one_time_authorization_required: Literal[True] = True
    same_directory_atomic_replace_required: Literal[True] = True
    fsync_required: Literal[True] = True
    external_registry_adapter_enabled: Literal[False] = False
    automatic_deployment: Literal[False] = False
    automatic_retraining: Literal[False] = False
    rollback_automatic: Literal[False] = False


class RegistryHistoryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["autogluon-registry-history-record-v1"] = (
        "autogluon-registry-history-record-v1"
    )
    transaction_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_id: str = Field(pattern=r"^[A-Za-z0-9._-]+$", min_length=1)
    git_commit: str = Field(pattern=r"^[0-9a-f]{7,40}$")
    authorization_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    authorization_seal_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    transaction_nonce: str = Field(pattern=r"^[0-9a-f]{64}$")
    committed_at_utc: str = Field(
        pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
    )
    expected_pre_state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    pre_generation: int = Field(ge=0)
    post_generation: int = Field(ge=1)
    previous_binding: RegistrySubject | None
    new_binding: RegistrySubject
    record_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_record(self) -> "RegistryHistoryRecord":
        parse_utc(self.committed_at_utc, label="committed_at_utc")
        if self.post_generation != self.pre_generation + 1:
            raise ValueError("history generation must advance exactly once")
        core = self.model_dump(mode="json")
        claimed = core.pop("record_sha256")
        if canonical_sha256(core) != claimed:
            raise ValueError("history record SHA-256 mismatch")
        return self


class RegistryState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["autogluon-file-json-registry-v1"] = REGISTRY_SCHEMA
    backend: Literal["file-json-cas-v1"] = BACKEND
    registry_target: str = Field(min_length=1)
    generation: int = Field(ge=0)
    current_binding: RegistrySubject | None
    consumed_authorization_ids: tuple[str, ...]
    consumed_transaction_nonces: tuple[str, ...]
    history: tuple[RegistryHistoryRecord, ...]
    deployment_status: Literal["NOT_DEPLOYED"] = "NOT_DEPLOYED"
    automatic_deployment: Literal[False] = False
    automatic_retraining: Literal[False] = False
    state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("consumed_authorization_ids", "consumed_transaction_nonces")
    @classmethod
    def unique_hashes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(
            len(item) != 64
            or any(ch not in "0123456789abcdef" for ch in item)
            for item in value
        ):
            raise ValueError("consumption ledger contains invalid SHA-256 identity")
        if len(set(value)) != len(value):
            raise ValueError("consumption ledger entries must be unique")
        return value

    @model_validator(mode="after")
    def validate_state(self) -> "RegistryState":
        if self.generation != len(self.history):
            raise ValueError("registry generation must equal history length")
        if len(self.consumed_authorization_ids) != self.generation:
            raise ValueError("authorization ledger length mismatch")
        if len(self.consumed_transaction_nonces) != self.generation:
            raise ValueError("nonce ledger length mismatch")
        if tuple(row.authorization_id for row in self.history) != self.consumed_authorization_ids:
            raise ValueError("authorization ledger order mismatch")
        if tuple(row.transaction_nonce for row in self.history) != self.consumed_transaction_nonces:
            raise ValueError("nonce ledger order mismatch")
        if len({row.transaction_id for row in self.history}) != len(self.history):
            raise ValueError("transaction IDs must be unique")

        prefix_history: list[dict[str, Any]] = []
        prefix_authorizations: list[str] = []
        prefix_nonces: list[str] = []
        previous_binding: RegistrySubject | None = None
        for index, row in enumerate(self.history):
            if row.pre_generation != index or row.post_generation != index + 1:
                raise ValueError("history generation sequence mismatch")
            if row.previous_binding != previous_binding:
                raise ValueError("history previous binding chain mismatch")
            prefix_core = {
                "schema_version": REGISTRY_SCHEMA,
                "backend": BACKEND,
                "registry_target": self.registry_target,
                "generation": index,
                "current_binding": (
                    previous_binding.model_dump(mode="json")
                    if previous_binding
                    else None
                ),
                "consumed_authorization_ids": prefix_authorizations,
                "consumed_transaction_nonces": prefix_nonces,
                "history": prefix_history,
                "deployment_status": "NOT_DEPLOYED",
                "automatic_deployment": False,
                "automatic_retraining": False,
            }
            if row.expected_pre_state_sha256 != canonical_sha256(prefix_core):
                raise ValueError("history expected pre-state SHA-256 mismatch")
            prefix_history.append(row.model_dump(mode="json"))
            prefix_authorizations.append(row.authorization_id)
            prefix_nonces.append(row.transaction_nonce)
            previous_binding = row.new_binding

        if self.generation == 0 and self.current_binding is not None:
            raise ValueError("empty registry cannot have a binding")
        if self.current_binding != previous_binding:
            raise ValueError("current binding does not match latest history record")
        core = self.model_dump(mode="json")
        claimed = core.pop("state_sha256")
        if canonical_sha256(core) != claimed:
            raise ValueError("registry state SHA-256 mismatch")
        return self


class RegistryTransactionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["autogluon-p19-transaction-request-v1"] = (
        "autogluon-p19-transaction-request-v1"
    )
    operation: Literal["consume_authorization_and_register"] = (
        "consume_authorization_and_register"
    )
    run_id: str = Field(pattern=r"^[A-Za-z0-9._-]+$", min_length=1)
    git_commit: str = Field(pattern=r"^[0-9a-f]{7,40}$")
    expected_current_state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    transaction_nonce: str = Field(pattern=r"^[0-9a-f]{64}$")
    executed_at_utc: str = Field(
        pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
    )
    policy: RegistryPolicy = Field(default_factory=RegistryPolicy)

    @model_validator(mode="after")
    def validate_request(self) -> "RegistryTransactionRequest":
        parse_utc(self.executed_at_utc, label="executed_at_utc")
        return self


class RegistryTransactionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    output_dir: str
    status: Literal["PASS"] = "PASS"
    decision: Literal[
        "REGISTRY_TRANSACTION_COMMITTED",
        "IDEMPOTENT_ALREADY_COMMITTED",
    ]
    transaction_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    registry_write_executed: bool
    post_state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    promotion_status: Literal["REGISTERED_NOT_DEPLOYED"] = "REGISTERED_NOT_DEPLOYED"


def registry_target_to_path(target: str) -> Path:
    parsed = urlparse(target)
    if parsed.scheme != "file+json" or parsed.netloc or parsed.query or parsed.fragment:
        raise RegistryTransactionError("REGISTRY_TARGET_INVALID", target)
    decoded = unquote(parsed.path)
    path = Path(decoded)
    if any(part in {".", ".."} for part in path.parts):
        raise RegistryTransactionError("REGISTRY_TARGET_PATH_UNSAFE", target)
    if not path.is_absolute():
        raise RegistryTransactionError("REGISTRY_TARGET_NOT_ABSOLUTE", target)
    return path.resolve(strict=False)


def make_history_record(
    *,
    transaction_id: str,
    run_id: str,
    git_commit: str,
    authorization_id: str,
    authorization_seal_sha256: str,
    transaction_nonce: str,
    committed_at_utc: str,
    expected_pre_state_sha256: str,
    pre_generation: int,
    previous_binding: RegistrySubject | None,
    new_binding: RegistrySubject,
) -> RegistryHistoryRecord:
    core = {
        "schema_version": "autogluon-registry-history-record-v1",
        "transaction_id": transaction_id,
        "run_id": run_id,
        "git_commit": git_commit,
        "authorization_id": authorization_id,
        "authorization_seal_sha256": authorization_seal_sha256,
        "transaction_nonce": transaction_nonce,
        "committed_at_utc": committed_at_utc,
        "expected_pre_state_sha256": expected_pre_state_sha256,
        "pre_generation": pre_generation,
        "post_generation": pre_generation + 1,
        "previous_binding": (
            previous_binding.model_dump(mode="json") if previous_binding else None
        ),
        "new_binding": new_binding.model_dump(mode="json"),
    }
    return RegistryHistoryRecord.model_validate(
        {**core, "record_sha256": canonical_sha256(core)}
    )


def make_registry_state(
    *,
    registry_target: str,
    generation: int,
    current_binding: RegistrySubject | None,
    consumed_authorization_ids: tuple[str, ...],
    consumed_transaction_nonces: tuple[str, ...],
    history: tuple[RegistryHistoryRecord, ...],
) -> RegistryState:
    core = {
        "schema_version": REGISTRY_SCHEMA,
        "backend": BACKEND,
        "registry_target": registry_target,
        "generation": generation,
        "current_binding": (
            current_binding.model_dump(mode="json") if current_binding else None
        ),
        "consumed_authorization_ids": list(consumed_authorization_ids),
        "consumed_transaction_nonces": list(consumed_transaction_nonces),
        "history": [row.model_dump(mode="json") for row in history],
        "deployment_status": "NOT_DEPLOYED",
        "automatic_deployment": False,
        "automatic_retraining": False,
    }
    return RegistryState.model_validate({**core, "state_sha256": canonical_sha256(core)})


def transaction_identity(
    *,
    authorization: Mapping[str, Any],
    request: RegistryTransactionRequest,
) -> str:
    verify_registry_authorization(authorization)
    return canonical_sha256(
        {
            "schema_version": P19_SCHEMA,
            "run_id": request.run_id,
            "git_commit": request.git_commit,
            "policy": request.policy.model_dump(mode="json"),
            "authorization_id": authorization["authorization_id"],
            "authorization_seal_sha256": authorization["seal_sha256"],
            "transaction_nonce": request.transaction_nonce,
            "expected_current_state_sha256": request.expected_current_state_sha256,
            "subject": authorization["subject"],
        }
    )


def authorization_is_expired(
    authorization: Mapping[str, Any],
    executed_at_utc: str,
) -> bool:
    issued = parse_utc(str(authorization["issued_at_utc"]), label="issued_at_utc")
    expires = parse_utc(str(authorization["expires_at_utc"]), label="expires_at_utc")
    executed = parse_utc(executed_at_utc, label="executed_at_utc")
    return executed < issued or executed > expires


def validate_registry_target_matches_path(target: str, path: Path) -> Path:
    expected = registry_target_to_path(target)
    actual = path.resolve(strict=False)
    if expected != actual:
        raise RegistryTransactionError(
            "REGISTRY_TARGET_PATH_MISMATCH",
            f"expected={expected} actual={actual}",
        )
    return actual


__all__ = [
    "BACKEND",
    "P19_SCHEMA",
    "REGISTRY_SCHEMA",
    "RegistryHistoryRecord",
    "RegistryPolicy",
    "RegistryState",
    "RegistryTransactionError",
    "RegistryTransactionRequest",
    "RegistryTransactionResult",
    "authorization_is_expired",
    "make_history_record",
    "make_registry_state",
    "registry_target_to_path",
    "transaction_identity",
    "validate_registry_target_matches_path",
]
