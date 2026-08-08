from __future__ import annotations

import fcntl
import json
import os
import stat
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from loto.autogluon_campaign.approval_authorization import (
    verify_approval_authorization,
)
from loto.autogluon_campaign.approval_authorization_contract import (
    SignatureVerifier,
    canonical_sha256,
    verify_registry_authorization,
)
from loto.autogluon_campaign.approval_authorization_io import (
    assert_regular_tree,
    empty_output_dir,
    file_sha256,
    load_json,
    tree_sha256,
    verify_manifest,
    verify_sha256sums,
    write_evidence,
    write_json,
)
from loto.autogluon_campaign.registry_transaction_contract import (
    RegistryState,
    RegistryTransactionError,
    make_registry_state,
    validate_registry_target_matches_path,
)

P19_OUTPUT_FILES = {
    "REQUEST_METADATA.json",
    "P18_LINEAGE.json",
    "TRANSACTION_PLAN.json",
    "PRE_REGISTRY_STATE.json",
    "TRANSACTION_RECEIPT.json",
    "POST_REGISTRY_STATE.json",
    "AUTHORIZATION_CONSUMPTION.json",
    "ROLLBACK_PLAN.json",
    "response.json",
    "ARTIFACT_MANIFEST.json",
    "SHA256SUMS",
}


def assert_no_symlink_components(path: Path, *, allow_missing_leaf: bool) -> None:
    if not path.is_absolute():
        raise RegistryTransactionError("PATH_NOT_ABSOLUTE", str(path))
    current = Path(path.anchor)
    parts = path.parts[1:]
    for index, part in enumerate(parts):
        current = current / part
        is_leaf = index == len(parts) - 1
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError as exc:
            if is_leaf and allow_missing_leaf:
                return
            raise RegistryTransactionError("PATH_COMPONENT_MISSING", str(current)) from exc
        if stat.S_ISLNK(mode):
            raise RegistryTransactionError("SYMLINK_FORBIDDEN", str(current))
        if not is_leaf and not stat.S_ISDIR(mode):
            raise RegistryTransactionError("PATH_PARENT_NOT_DIRECTORY", str(current))


def validate_registry_path(path: Path, *, must_exist: bool) -> Path:
    raw = path.absolute()
    assert_no_symlink_components(raw, allow_missing_leaf=not must_exist)
    if must_exist:
        try:
            mode = raw.lstat().st_mode
        except FileNotFoundError as exc:
            raise RegistryTransactionError("REGISTRY_STATE_MISSING", str(raw)) from exc
        if not stat.S_ISREG(mode):
            raise RegistryTransactionError("REGISTRY_STATE_NOT_REGULAR", str(raw))
    elif raw.exists():
        raise RegistryTransactionError("REGISTRY_STATE_ALREADY_EXISTS", str(raw))
    return raw


def load_registry_state(path: Path) -> RegistryState:
    registry_path = validate_registry_path(path, must_exist=True)
    try:
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
        state = RegistryState.model_validate(payload)
    except Exception as exc:
        raise RegistryTransactionError("REGISTRY_STATE_INVALID", str(exc)) from exc
    validate_registry_target_matches_path(state.registry_target, registry_path)
    return state


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write_registry_state(path: Path, state: RegistryState) -> None:
    registry_path = path.absolute()
    parent = registry_path.parent
    assert_no_symlink_components(parent, allow_missing_leaf=False)
    temporary = parent / f".{registry_path.name}.tmp-{os.getpid()}"
    if temporary.exists() or temporary.is_symlink():
        raise RegistryTransactionError("REGISTRY_TEMP_EXISTS", str(temporary))
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(temporary, flags, 0o600)
    try:
        payload = (
            json.dumps(
                state.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, registry_path)
        _fsync_directory(parent)
    except Exception:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise
    written = load_registry_state(registry_path)
    if written != state:
        raise RegistryTransactionError("REGISTRY_POST_WRITE_MISMATCH", str(registry_path))


@contextmanager
def registry_lock(path: Path) -> Iterator[None]:
    registry_path = path.absolute()
    lock_path = registry_path.with_name(f".{registry_path.name}.lock")
    assert_no_symlink_components(lock_path, allow_missing_leaf=True)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(lock_path, flags, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def bootstrap_registry(*, registry_path: Path, registry_target: str) -> RegistryState:
    path = validate_registry_path(registry_path, must_exist=False)
    validate_registry_target_matches_path(registry_target, path)
    state = make_registry_state(
        registry_target=registry_target,
        generation=0,
        current_binding=None,
        consumed_authorization_ids=(),
        consumed_transaction_nonces=(),
        history=(),
    )
    atomic_write_registry_state(path, state)
    return state


def read_p18_authorization(
    root: Path,
    *,
    signature_verifier: SignatureVerifier | None = None,
) -> dict[str, Any]:
    source = root.resolve()
    verified = verify_approval_authorization(
        source,
        signature_verifier=signature_verifier,
    )
    authorization = load_json(source / "REGISTRY_AUTHORIZATION.json")
    verify_registry_authorization(authorization)
    requirements = load_json(source / "REGISTRY_TRANSACTION_REQUIREMENTS.json")
    if requirements.get("authorization_id") != authorization["authorization_id"]:
        raise RegistryTransactionError("P18_AUTHORIZATION_ID_MISMATCH", str(source))
    if requirements.get("authorization_seal_sha256") != authorization["seal_sha256"]:
        raise RegistryTransactionError("P18_AUTHORIZATION_SEAL_MISMATCH", str(source))
    if requirements.get("expected_subject") != authorization["subject"]:
        raise RegistryTransactionError("P18_SUBJECT_MISMATCH", str(source))
    required_true = (
        "expected_current_registry_state_sha256_required",
        "compare_and_swap_required",
        "append_only_consumption_ledger_required",
        "authorization_must_be_unexpired",
        "authorization_must_be_unconsumed",
    )
    if any(requirements.get(key) is not True for key in required_true):
        raise RegistryTransactionError("P18_TRANSACTION_REQUIREMENT_INVALID", str(source))
    if requirements.get("registry_write_executed") is not False:
        raise RegistryTransactionError("P18_ALREADY_EXECUTED", str(source))
    return {
        "verified": verified,
        "authorization": authorization,
        "requirements": requirements,
        "source_tree_sha256": tree_sha256(source),
        "authorization_file_sha256": file_sha256(source / "REGISTRY_AUTHORIZATION.json"),
        "requirements_file_sha256": file_sha256(source / "REGISTRY_TRANSACTION_REQUIREMENTS.json"),
    }


def write_transaction_evidence(
    root: Path,
    payloads: Mapping[str, Mapping[str, Any]],
) -> Path:
    output = empty_output_dir(root)
    for name, payload in payloads.items():
        write_json(output / name, payload)
    write_evidence(output, list(payloads))
    return output


def verify_transaction_evidence_files(root: Path) -> None:
    observed = verify_sha256sums(root)
    if observed != P19_OUTPUT_FILES:
        raise RegistryTransactionError(
            "P19_FILE_SET_MISMATCH",
            str(sorted(observed)),
        )
    verify_manifest(
        root,
        P19_OUTPUT_FILES - {"ARTIFACT_MANIFEST.json", "SHA256SUMS"},
    )


def transaction_output_tree_sha256(root: Path) -> str:
    records = [
        {
            "path": path.relative_to(root).as_posix(),
            "sha256": file_sha256(path),
        }
        for path in assert_regular_tree(root)
    ]
    return canonical_sha256(records)


__all__ = [
    "P19_OUTPUT_FILES",
    "assert_no_symlink_components",
    "atomic_write_registry_state",
    "bootstrap_registry",
    "load_registry_state",
    "read_p18_authorization",
    "registry_lock",
    "transaction_output_tree_sha256",
    "validate_registry_path",
    "verify_transaction_evidence_files",
    "write_transaction_evidence",
]
