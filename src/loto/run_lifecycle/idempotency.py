"""Semantic idempotency-key and conflict detection helpers."""

from __future__ import annotations

from .canonical import sha256_canonical
from .models import RunCommand


def semantic_command_payload(command: RunCommand) -> dict[str, object]:
    """Return exactly the stable semantic fields used for idempotency."""

    return {
        "schema_version": command.schema_version,
        "run_id": command.run_id,
        "command_type": command.command_type.value,
        "phase": command.phase.value,
        "expected_revision": command.expected_revision,
        "subject_hashes": [
            {"name": item.name, "sha256": item.sha256} for item in command.subject_hashes
        ],
        "semantic_parameters": command.semantic_parameters.as_object(),
        "requested_output_names": list(command.requested_output_names),
    }


def compute_semantic_idempotency_key(command: RunCommand) -> str:
    return sha256_canonical(semantic_command_payload(command))


def compute_command_fingerprint(command: RunCommand) -> str:
    """Fingerprint semantic payload independently of a declared key."""

    return sha256_canonical(semantic_command_payload(command))


def effective_idempotency_key(command: RunCommand) -> str:
    return command.declared_idempotency_key or compute_semantic_idempotency_key(command)
