from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "1.0.0"
MODEL_ID = "nf-local-auto-timellm"
UPSTREAM_MODEL_CLASS = "TimeLLM"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
_REPO_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")


class SnapshotFileEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    relative_path: str
    sha256: str
    size_bytes: int = Field(ge=0)

    @field_validator("relative_path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        if not value or "\\" in value or "\x00" in value:
            raise ValueError("snapshot path must be a non-empty POSIX path")
        path = PurePosixPath(value)
        if path.is_absolute() or value != path.as_posix():
            raise ValueError("snapshot path must be canonical and relative")
        if any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError("snapshot path contains an unsafe component")
        return value

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if not _SHA256_RE.fullmatch(value):
            raise ValueError("sha256 must be 64 lowercase hexadecimal characters")
        return value


class PinnedLLMIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    repo_id: str
    revision: str
    snapshot_path: str
    license_id: str
    files: tuple[SnapshotFileEvidence, ...] = Field(min_length=3)
    trust_remote_code: Literal[False] = False
    local_files_only: Literal[True] = True
    offline: Literal[True] = True
    snapshot_path_must_end_with_revision: Literal[True] = True

    @field_validator("files", mode="before")
    @classmethod
    def normalize_json_file_array(cls, value: Any) -> Any:
        if isinstance(value, list):
            return tuple(value)
        return value

    @field_validator("repo_id")
    @classmethod
    def validate_repo_id(cls, value: str) -> str:
        if not _REPO_ID_RE.fullmatch(value):
            raise ValueError("repo_id must use the Hugging Face author/name form")
        return value

    @field_validator("revision")
    @classmethod
    def validate_revision(cls, value: str) -> str:
        if not _REVISION_RE.fullmatch(value):
            raise ValueError("revision must be an immutable 40-character commit SHA")
        return value

    @field_validator("snapshot_path")
    @classmethod
    def validate_snapshot_path(cls, value: str) -> str:
        path = Path(value)
        if not path.is_absolute():
            raise ValueError("snapshot_path must be absolute")
        if "\x00" in value:
            raise ValueError("snapshot_path contains a NUL character")
        return value

    @field_validator("license_id")
    @classmethod
    def validate_license_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("license_id must be non-empty")
        return value

    @model_validator(mode="after")
    def validate_inventory(self) -> PinnedLLMIdentity:
        paths = [item.relative_path for item in self.files]
        if len(paths) != len(set(paths)):
            raise ValueError("snapshot inventory contains duplicate paths")
        if "config.json" not in paths:
            raise ValueError("snapshot inventory must contain config.json")
        weight_suffixes = (".safetensors", ".bin")
        if not any(path.endswith(weight_suffixes) for path in paths):
            raise ValueError("snapshot inventory must contain a model weight file")
        tokenizer_names = {
            "tokenizer.json",
            "tokenizer_config.json",
            "tokenizer.model",
            "spiece.model",
            "vocab.json",
        }
        if not any(PurePosixPath(path).name in tokenizer_names for path in paths):
            raise ValueError("snapshot inventory must contain tokenizer evidence")
        if Path(self.snapshot_path).name != self.revision:
            raise ValueError("snapshot_path must end with the immutable revision")
        return self


class SnapshotModelMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    hidden_size: int = Field(gt=0)
    num_hidden_layers: int = Field(gt=0)
    model_type: str
    architecture: str | None


class SnapshotVerification(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    status: Literal["PASS"] = "PASS"
    snapshot_path: str
    revision: str
    file_count: int = Field(gt=0)
    inventory_sha256: str
    config_sha256: str

    @field_validator("inventory_sha256", "config_sha256")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        if not _SHA256_RE.fullmatch(value):
            raise ValueError("verification hashes must be lowercase SHA-256")
        return value


class ArchitectureProfile(StrEnum):
    COMPACT = "compact"
    BALANCED = "balanced"
    WIDE = "wide"


class ArchitectureSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    profile: ArchitectureProfile
    input_size: int = Field(gt=0)
    patch_len: int = Field(gt=0)
    stride: int = Field(gt=0)
    d_ff: int = Field(gt=0)
    d_model: int = Field(gt=0)
    n_heads: int = Field(gt=0)
    top_k: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_geometry(self) -> ArchitectureSpec:
        if self.patch_len > self.input_size:
            raise ValueError("patch_len must not exceed input_size")
        if self.stride > self.patch_len:
            raise ValueError("stride must not exceed patch_len")
        if self.d_model % self.n_heads != 0:
            raise ValueError("d_model must be divisible by n_heads")
        return self


class TrialParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    architecture_profile: ArchitectureProfile
    learning_rate: float = Field(gt=0.0, lt=1.0)
    max_steps: int = Field(gt=0)
    val_check_steps: int = Field(gt=0)
    batch_size: int = Field(gt=0)
    windows_batch_size: int = Field(gt=0)
    dropout: float = Field(ge=0.0, lt=0.5)
    scaler_type: Literal["identity", "robust"]
    random_seed: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_training_schedule(self) -> TrialParameters:
        if self.val_check_steps > self.max_steps:
            raise ValueError("val_check_steps must not exceed max_steps")
        return self


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _assert_no_symlink_components(root: Path, relative_path: str) -> Path:
    current = root
    for part in PurePosixPath(relative_path).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"snapshot path uses a symlink: {relative_path}")
    return current


def verify_snapshot(identity: PinnedLLMIdentity) -> SnapshotVerification:
    root = Path(identity.snapshot_path)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("snapshot_path must be a real directory and not a symlink")
    resolved_root = root.resolve(strict=True)
    expected_paths = {item.relative_path for item in identity.files}
    actual_paths: set[str] = set()
    for candidate in root.rglob("*"):
        relative = candidate.relative_to(root).as_posix()
        if candidate.is_symlink():
            raise ValueError(f"snapshot inventory contains a symlink: {relative}")
        if candidate.is_dir():
            continue
        if not candidate.is_file():
            raise ValueError(f"snapshot inventory contains a non-regular file: {relative}")
        actual_paths.add(relative)
    if actual_paths != expected_paths:
        missing = sorted(expected_paths - actual_paths)
        extra = sorted(actual_paths - expected_paths)
        raise ValueError(f"snapshot inventory mismatch: missing={missing}, extra={extra}")

    inventory_rows: list[dict[str, Any]] = []
    config_sha256 = ""

    for evidence in sorted(identity.files, key=lambda item: item.relative_path):
        path = _assert_no_symlink_components(root, evidence.relative_path)
        if not path.is_file():
            raise ValueError(f"snapshot file is missing: {evidence.relative_path}")
        resolved_path = path.resolve(strict=True)
        if not resolved_path.is_relative_to(resolved_root):
            raise ValueError(f"snapshot file escapes the snapshot root: {evidence.relative_path}")
        size_bytes = path.stat().st_size
        sha256 = _sha256_file(path)
        if size_bytes != evidence.size_bytes or sha256 != evidence.sha256:
            raise ValueError(f"snapshot file identity mismatch: {evidence.relative_path}")
        if evidence.relative_path == "config.json":
            config_sha256 = sha256
        inventory_rows.append(
            {
                "path": evidence.relative_path,
                "sha256": sha256,
                "size_bytes": size_bytes,
            }
        )

    canonical = json.dumps(
        inventory_rows,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    inventory_sha256 = hashlib.sha256(canonical).hexdigest()
    load_snapshot_model_metadata(identity)
    return SnapshotVerification(
        snapshot_path=str(resolved_root),
        revision=identity.revision,
        file_count=len(inventory_rows),
        inventory_sha256=inventory_sha256,
        config_sha256=config_sha256,
    )


def _find_positive_int(payload: dict[str, Any], keys: tuple[str, ...]) -> int | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
    text_config = payload.get("text_config")
    if isinstance(text_config, dict):
        return _find_positive_int(text_config, keys)
    return None


def load_snapshot_model_metadata(identity: PinnedLLMIdentity) -> SnapshotModelMetadata:
    config_path = Path(identity.snapshot_path) / "config.json"
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("config.json is not readable canonical JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("config.json root must be an object")
    if payload.get("auto_map"):
        raise ValueError("custom-code auto_map is not allowed for AutoTimeLLM")

    hidden_size = _find_positive_int(payload, ("hidden_size", "n_embd", "d_model"))
    num_hidden_layers = _find_positive_int(
        payload,
        ("num_hidden_layers", "n_layer", "num_layers"),
    )
    if hidden_size is None or num_hidden_layers is None:
        raise ValueError("config.json lacks hidden-size or layer-count metadata")
    architectures = payload.get("architectures")
    architecture = None
    if isinstance(architectures, list) and architectures and isinstance(architectures[0], str):
        architecture = architectures[0]
    model_type = payload.get("model_type")
    if not isinstance(model_type, str) or not model_type:
        raise ValueError("config.json must contain a non-empty model_type")
    return SnapshotModelMetadata(
        hidden_size=hidden_size,
        num_hidden_layers=num_hidden_layers,
        model_type=model_type,
        architecture=architecture,
    )


def resolve_architecture(h: int, profile: ArchitectureProfile | str) -> ArchitectureSpec:
    if not isinstance(h, int) or isinstance(h, bool) or h < 1:
        raise ValueError("h must be a positive integer")
    selected = ArchitectureProfile(profile)
    settings = {
        ArchitectureProfile.COMPACT: (32, 4, 8, 4, 32, 32, 4, 3),
        ArchitectureProfile.BALANCED: (64, 8, 16, 8, 64, 32, 8, 5),
        ArchitectureProfile.WIDE: (96, 16, 16, 8, 128, 64, 8, 5),
    }
    minimum, multiplier, patch_len, stride, d_ff, d_model, n_heads, top_k = settings[selected]
    return ArchitectureSpec(
        profile=selected,
        input_size=max(minimum, h * multiplier),
        patch_len=patch_len,
        stride=stride,
        d_ff=d_ff,
        d_model=d_model,
        n_heads=n_heads,
        top_k=top_k,
    )
