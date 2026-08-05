from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote, urlparse

from pydantic import BaseModel, ConfigDict, Field, model_validator

from loto.sktime_campaign.approval_authorization import (
    AuthorizationConsumptionLedger,
    RegistrySubject,
    RegistryTransactionRequest,
    canonical_sha256,
    validate_registry_transaction_request,
    verify_registry_authorization,
)


class RegistryBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: RegistrySubject
    transaction_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    authorization_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    registered_at_utc: str = Field(
        pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
    )


class RegistryHistoryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    transaction_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    previous_state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    authorization_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    authorization_seal_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    transaction_nonce: str = Field(pattern=r"^[0-9a-f]{64}$")
    committed_at_utc: str = Field(
        pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
    )
    previous_binding: RegistryBinding | None
    new_binding: RegistryBinding
    record_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def verify_record(self) -> "RegistryHistoryRecord":
        payload = self.model_dump(mode="json", exclude={"record_sha256"})
        if canonical_sha256(payload) != self.record_sha256:
            raise ValueError("registry history record SHA-256 mismatch")
        return self


class FileRegistryState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    backend: Literal["file-json-cas-v1"] = "file-json-cas-v1"
    registry_target: str = Field(min_length=1)
    generation: int = Field(ge=0)
    current_binding: RegistryBinding | None = None
    consumed_authorization_ids: list[str] = Field(default_factory=list)
    consumed_transaction_nonces: list[str] = Field(default_factory=list)
    transaction_history: list[RegistryHistoryRecord] = Field(default_factory=list)
    state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def verify_state(self) -> "FileRegistryState":
        if len(self.consumed_authorization_ids) != len(
            set(self.consumed_authorization_ids)
        ):
            raise ValueError("consumed authorization IDs must be unique")
        if len(self.consumed_transaction_nonces) != len(
            set(self.consumed_transaction_nonces)
        ):
            raise ValueError("consumed transaction nonces must be unique")
        if len(self.transaction_history) != self.generation:
            raise ValueError("registry generation/history length mismatch")
        if len(self.consumed_authorization_ids) != self.generation:
            raise ValueError("registry authorization ledger length mismatch")
        if len(self.consumed_transaction_nonces) != self.generation:
            raise ValueError("registry nonce ledger length mismatch")
        payload = self.model_dump(mode="json", exclude={"state_sha256"})
        if canonical_sha256(payload) != self.state_sha256:
            raise ValueError("registry state SHA-256 mismatch")
        if self.transaction_history:
            if self.current_binding != self.transaction_history[-1].new_binding:
                raise ValueError("current binding differs from latest history record")
        elif self.current_binding is not None:
            raise ValueError("generation zero registry must not have a binding")
        return self


class P8RegistryTransactionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    operation: Literal["compare_and_swap_registry_write"] = (
        "compare_and_swap_registry_write"
    )
    output_dir: str = Field(min_length=1)
    run_id: str = Field(pattern=r"^[A-Za-z0-9._-]+$", min_length=1)
    git_commit: str = Field(pattern=r"^[0-9a-f]{7,40}$")
    code_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    p7_bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    registry_state_path: str = Field(min_length=1)
    authorization: dict[str, Any]
    transaction: RegistryTransactionRequest
    automatic_deployment: Literal[False] = False
    automatic_retraining: Literal[False] = False

    @model_validator(mode="after")
    def validate_request(self) -> "P8RegistryTransactionRequest":
        verify_registry_authorization(self.authorization)
        if self.transaction.authorization_id != self.authorization.get(
            "authorization_id"
        ):
            raise ValueError("P8 transaction authorization ID mismatch")
        if self.transaction.authorization_seal_sha256 != self.authorization.get(
            "seal_sha256"
        ):
            raise ValueError("P8 transaction authorization seal mismatch")
        if self.transaction.subject.model_dump(mode="json") != self.authorization.get(
            "subject"
        ):
            raise ValueError("P8 transaction subject differs from authorization")
        expected_path = file_registry_path(self.transaction.subject.registry_target)
        if Path(self.registry_state_path).resolve() != expected_path:
            raise ValueError("registry state path differs from authorized target")
        return self


def parse_utc(value: str, *, label: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise ValueError(f"{label} must use strict UTC Z format") from exc


def file_registry_path(target: str) -> Path:
    parsed = urlparse(target)
    if parsed.scheme != "file+json" or parsed.netloc:
        raise ValueError("P8 reference backend requires file+json:///absolute/path")
    path = Path(unquote(parsed.path))
    if not path.is_absolute():
        raise ValueError("file registry target must use an absolute path")
    return path.resolve()


def sealed_state(
    *,
    registry_target: str,
    generation: int = 0,
    current_binding: RegistryBinding | None = None,
    consumed_authorization_ids: list[str] | None = None,
    consumed_transaction_nonces: list[str] | None = None,
    transaction_history: list[RegistryHistoryRecord] | None = None,
) -> FileRegistryState:
    payload = {
        "schema_version": "1.0",
        "backend": "file-json-cas-v1",
        "registry_target": registry_target,
        "generation": generation,
        "current_binding": (
            current_binding.model_dump(mode="json") if current_binding else None
        ),
        "consumed_authorization_ids": consumed_authorization_ids or [],
        "consumed_transaction_nonces": consumed_transaction_nonces or [],
        "transaction_history": [
            item.model_dump(mode="json") for item in (transaction_history or [])
        ],
    }
    return FileRegistryState(**payload, state_sha256=canonical_sha256(payload))


def _load_state(path: Path) -> FileRegistryState:
    if path.is_symlink():
        raise ValueError("registry state path must not be a symlink")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"unable to read registry state: {exc}") from exc
    return FileRegistryState.model_validate(payload)


def _atomic_write_state(path: Path, state: FileRegistryState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("registry state path must not be a symlink")
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        text=True,
    )
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(
                state.model_dump(mode="json"),
                stream,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary_path.unlink(missing_ok=True)


def bootstrap_registry(path: Path, registry_target: str) -> FileRegistryState:
    path = path.resolve()
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"registry state already exists: {path}")
    if file_registry_path(registry_target) != path:
        raise ValueError("bootstrap path differs from registry target")
    state = sealed_state(registry_target=registry_target)
    _atomic_write_state(path, state)
    return _load_state(path)


def _transaction_id(
    request: P8RegistryTransactionRequest,
    *,
    committed_at_utc: str,
) -> str:
    return canonical_sha256(
        {
            "authorization_id": request.transaction.authorization_id,
            "transaction_nonce": request.transaction.transaction_nonce,
            "subject": request.transaction.subject.model_dump(mode="json"),
            "committed_at_utc": committed_at_utc,
        }
    )


def _find_exact_replay(
    state: FileRegistryState,
    request: P8RegistryTransactionRequest,
) -> RegistryHistoryRecord | None:
    for item in state.transaction_history:
        if item.authorization_id != request.transaction.authorization_id:
            continue
        if item.transaction_nonce != request.transaction.transaction_nonce:
            raise ValueError("authorization replay changed transaction nonce")
        if item.new_binding.subject != request.transaction.subject:
            raise ValueError("authorization replay changed registry subject")
        return item
    return None


def commit_registry_transaction(
    request: P8RegistryTransactionRequest,
    *,
    committed_at_utc: str,
) -> dict[str, Any]:
    parse_utc(committed_at_utc, label="committed_at_utc")
    raw_path = Path(request.registry_state_path)
    if raw_path.is_symlink():
        raise ValueError("registry state path must not be a symlink")
    path = raw_path.resolve()
    lock_path = path.with_name(f".{path.name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock_stream:
        fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX)
        pre_state = _load_state(path)
        if pre_state.registry_target != request.transaction.subject.registry_target:
            raise ValueError("registry state target differs from authorization")
        replay = _find_exact_replay(pre_state, request)
        if replay is not None:
            return {
                "status": "PASS",
                "decision": "IDEMPOTENT_ALREADY_COMMITTED",
                "registry_write_executed": False,
                "transaction_id": replay.transaction_id,
                "pre_state": pre_state.model_dump(mode="json"),
                "post_state": pre_state.model_dump(mode="json"),
                "history_record": replay.model_dump(mode="json"),
                "automatic_deployment": False,
                "deployment_status": "NOT_DEPLOYED",
            }
        if pre_state.state_sha256 != request.transaction.expected_registry_state_sha256:
            raise ValueError("registry compare-and-swap pre-state mismatch")
        ledger = AuthorizationConsumptionLedger(
            consumed_authorization_ids=pre_state.consumed_authorization_ids,
            consumed_transaction_nonces=pre_state.consumed_transaction_nonces,
        )
        validate_registry_transaction_request(
            request.authorization,
            request.transaction,
            ledger,
            verified_at_utc=committed_at_utc,
        )
        transaction_id = _transaction_id(request, committed_at_utc=committed_at_utc)
        binding = RegistryBinding(
            subject=request.transaction.subject,
            transaction_id=transaction_id,
            authorization_id=request.transaction.authorization_id,
            registered_at_utc=committed_at_utc,
        )
        record_payload = {
            "transaction_id": transaction_id,
            "previous_state_sha256": pre_state.state_sha256,
            "authorization_id": request.transaction.authorization_id,
            "authorization_seal_sha256": (
                request.transaction.authorization_seal_sha256
            ),
            "transaction_nonce": request.transaction.transaction_nonce,
            "committed_at_utc": committed_at_utc,
            "previous_binding": (
                pre_state.current_binding.model_dump(mode="json")
                if pre_state.current_binding
                else None
            ),
            "new_binding": binding.model_dump(mode="json"),
        }
        record = RegistryHistoryRecord(
            **record_payload,
            record_sha256=canonical_sha256(record_payload),
        )
        post_state = sealed_state(
            registry_target=pre_state.registry_target,
            generation=pre_state.generation + 1,
            current_binding=binding,
            consumed_authorization_ids=[
                *pre_state.consumed_authorization_ids,
                request.transaction.authorization_id,
            ],
            consumed_transaction_nonces=[
                *pre_state.consumed_transaction_nonces,
                request.transaction.transaction_nonce,
            ],
            transaction_history=[*pre_state.transaction_history, record],
        )
        _atomic_write_state(path, post_state)
        persisted = _load_state(path)
        if persisted != post_state:
            raise RuntimeError("persisted registry state differs from committed state")
        return {
            "status": "PASS",
            "decision": "REGISTRY_TRANSACTION_COMMITTED",
            "registry_write_executed": True,
            "transaction_id": transaction_id,
            "pre_state": pre_state.model_dump(mode="json"),
            "post_state": post_state.model_dump(mode="json"),
            "history_record": record.model_dump(mode="json"),
            "automatic_deployment": False,
            "deployment_status": "NOT_DEPLOYED",
        }
