"""Atomic evidence persistence and strict artifact verification."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from .canonical import canonical_json, loads_strict_object, sha256_bytes
from .chronyc import verify_raw_observation
from .contracts import ClockHealthDecision, ClockHealthPolicy, ClockObservation

ModelT = TypeVar("ModelT", bound=BaseModel)


def write_json_atomic(path: Path, value: object, *, refuse_overwrite: bool = True) -> Path:
    if refuse_overwrite and path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (canonical_json(value) + "\n").encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def load_model_json(path: Path, model_type: type[ModelT]) -> ModelT:
    raw = path.read_text(encoding="utf-8")
    value = loads_strict_object(raw)
    return model_type.model_validate_json(canonical_json(value), strict=True)


def write_evidence_bundle(
    output_dir: Path,
    *,
    observation: ClockObservation,
    decision: ClockHealthDecision,
    policy: ClockHealthPolicy,
    tracking_stdout: bytes,
    sources_stdout: bytes,
    tracking_stderr: bytes = b"",
    sources_stderr: bytes = b"",
) -> dict[str, str]:
    if decision.observation_sha256 != observation.observation_sha256:
        raise ValueError("decision observation hash mismatch")
    if decision.policy_sha256 != policy.policy_sha256:
        raise ValueError("decision policy hash mismatch")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError("output directory must be new or empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    verify_raw_observation(
        observation,
        tracking_raw=tracking_stdout,
        sources_raw=sources_stdout,
    )
    files: dict[str, bytes] = {
        "chronyc_tracking.txt": tracking_stdout,
        "chronyc_sources.txt": sources_stdout,
        "chronyc_tracking.stderr": tracking_stderr,
        "chronyc_sources.stderr": sources_stderr,
        "observation.json": (canonical_json(observation) + "\n").encode("utf-8"),
        "decision.json": (canonical_json(decision) + "\n").encode("utf-8"),
        "policy.json": (canonical_json(policy) + "\n").encode("utf-8"),
    }
    for name, payload in files.items():
        _write_bytes_atomic(output_dir / name, payload)
    sums = {name: sha256_bytes(payload) for name, payload in sorted(files.items())}
    manifest = {
        "schema_version": "1.0.0",
        "artifact_count": len(files),
        "artifacts": [
            {"path": name, "sha256": sums[name], "size_bytes": len(files[name])}
            for name in sorted(files)
        ],
        "prediction_lock_allowed": decision.prediction_lock_allowed,
        "status": decision.status.value,
        "external_trust_established": False,
    }
    manifest_bytes = (canonical_json(manifest) + "\n").encode("utf-8")
    _write_bytes_atomic(output_dir / "ARTIFACT_MANIFEST.json", manifest_bytes)
    sums["ARTIFACT_MANIFEST.json"] = sha256_bytes(manifest_bytes)
    sum_lines = "".join(f"{digest}  {name}\n" for name, digest in sorted(sums.items()))
    _write_bytes_atomic(output_dir / "SHA256SUMS", sum_lines.encode("utf-8"))
    return sums


def verify_evidence_bundle(output_dir: Path) -> None:
    manifest = loads_strict_object(
        (output_dir / "ARTIFACT_MANIFEST.json").read_text(encoding="utf-8")
    )
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("manifest artifacts must be a list")
    if manifest.get("artifact_count") != len(artifacts):
        raise ValueError("manifest artifact_count mismatch")
    if manifest.get("external_trust_established") is not False:
        raise ValueError("clock bundle cannot establish external trust")
    expected_names: set[str] = set()
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise ValueError("manifest artifact must be an object")
        path = artifact.get("path")
        digest = artifact.get("sha256")
        size = artifact.get("size_bytes")
        if not isinstance(path, str) or Path(path).name != path:
            raise ValueError("manifest artifact path is unsafe")
        if path in expected_names:
            raise ValueError("duplicate manifest path")
        expected_names.add(path)
        payload = (output_dir / path).read_bytes()
        if len(payload) != size or sha256_bytes(payload) != digest:
            raise ValueError(f"artifact mismatch: {path}")
    manifest_payload = (output_dir / "ARTIFACT_MANIFEST.json").read_bytes()
    expected_sums = {
        **{
            artifact["path"]: artifact["sha256"]
            for artifact in artifacts
            if isinstance(artifact, dict)
        },
        "ARTIFACT_MANIFEST.json": sha256_bytes(manifest_payload),
    }
    parsed_sums = _parse_sha256sums((output_dir / "SHA256SUMS").read_text(encoding="utf-8"))
    if parsed_sums != expected_sums:
        raise ValueError("SHA256SUMS does not match manifest inventory")
    entries = list(output_dir.iterdir())
    if any(not path.is_file() for path in entries):
        raise ValueError("evidence bundle contains non-file entries")
    actual_names = {path.name for path in entries}
    if actual_names != set(expected_sums) | {"SHA256SUMS"}:
        raise ValueError("evidence bundle contains missing or extra files")
    observation = load_model_json(output_dir / "observation.json", ClockObservation)
    decision = load_model_json(output_dir / "decision.json", ClockHealthDecision)
    policy = load_model_json(output_dir / "policy.json", ClockHealthPolicy)
    verify_raw_observation(
        observation,
        tracking_raw=(output_dir / "chronyc_tracking.txt").read_bytes(),
        sources_raw=(output_dir / "chronyc_sources.txt").read_bytes(),
    )
    if decision.observation_sha256 != observation.observation_sha256:
        raise ValueError("decision observation hash mismatch")
    if decision.policy_sha256 != policy.policy_sha256:
        raise ValueError("decision policy hash mismatch")


def _parse_sha256sums(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        if not line:
            continue
        parts = line.split("  ", 1)
        if len(parts) != 2:
            raise ValueError("malformed SHA256SUMS line")
        digest, name = parts
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError("malformed SHA256SUMS digest")
        if Path(name).name != name or name in result:
            raise ValueError("unsafe or duplicate SHA256SUMS path")
        result[name] = digest
    return result


def _write_bytes_atomic(path: Path, payload: bytes) -> None:
    if path.exists():
        raise FileExistsError(path)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)
