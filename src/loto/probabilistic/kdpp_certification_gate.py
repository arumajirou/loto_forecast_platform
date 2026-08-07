from __future__ import annotations

import hashlib
import json
import math
import shutil
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MODEL_ID = "pp-k-dpp-fixed-k"
SCHEMA_VERSION = "1.0.0"
APPROVAL_TOKEN = "APPROVE-KDPP-HISTORY-BUNDLE"
HISTORY_FILES = {"history_manifest.json", "item_ids.json", "training.npz", "SHA256SUMS"}
RUNTIME_FILES = {
    "state/kdpp_state.json",
    "state/kdpp_state.npz",
    "state/artifact_manifest.json",
    "state/SHA256SUMS",
    "request.json",
    "response.json",
    "prediction.lock.json",
    "runtime_evidence.json",
    "CERTIFICATION_SHA256SUMS",
}
_HEX = set("0123456789abcdef")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, allow_inf_nan=False)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_sha256(value: str) -> str:
    if len(value) != 64 or not set(value) <= _HEX:
        raise ValueError("expected lowercase SHA-256")
    return value


def parse_utc(value: object) -> object:
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


def require_utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise ValueError(f"{field} must be UTC")
    return value


def safe_relative(value: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or "." in path.parts or ".." in path.parts or "\\" in value:
        raise ValueError("path must be safe relative POSIX")
    return value


class KDPPHistoryManifest(StrictModel):
    schema_version: Literal[SCHEMA_VERSION]
    model_id: Literal[MODEL_ID]
    bundle_status: Literal["VERIFIED_REAL_HISTORY"]
    data_role: Literal["TRAIN_ONLY"]
    game: Literal["numbers3", "numbers4", "miniloto", "loto6", "loto7"]
    target_layout: Literal["position_local", "unordered_fixed_cardinality"]
    position: int | None = Field(default=None, ge=1, le=4)
    source_system: str = Field(min_length=1, max_length=256)
    source_snapshot: str = Field(min_length=1, max_length=512)
    source_query_sha256: str
    source_data_sha256: str
    created_at_utc: datetime
    train_start: int = Field(ge=0)
    train_end: int = Field(ge=0)
    forecast_origin: int = Field(ge=1)
    row_count: int = Field(ge=2)
    context_length: int = Field(ge=1)
    prediction_lengths: tuple[Literal[1, 2, 5], ...]
    cardinality: int = Field(ge=1)
    item_count: int = Field(ge=2)
    training_npz_sha256: str
    item_ids_json_sha256: str
    read_only_source: Literal[True]
    raw_data_immutable: Literal[True]
    draw_order_verified: Literal[True]
    future_actuals_included: Literal[False]
    holdout_included: Literal[False]
    prospective_included: Literal[False]
    formal_approval_required: Literal[True]

    @field_validator(
        "source_query_sha256",
        "source_data_sha256",
        "training_npz_sha256",
        "item_ids_json_sha256",
    )
    @classmethod
    def hashes(cls, value: str) -> str:
        return validate_sha256(value)

    @field_validator("created_at_utc", mode="before")
    @classmethod
    def parse_created(cls, value: object) -> object:
        return parse_utc(value)

    @field_validator("created_at_utc")
    @classmethod
    def created_is_utc(cls, value: datetime) -> datetime:
        return require_utc(value, "created_at_utc")

    @field_validator("prediction_lengths", mode="before")
    @classmethod
    def tuple_lengths(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def geometry(self) -> KDPPHistoryManifest:
        if self.prediction_lengths != (1, 2, 5):
            raise ValueError("prediction_lengths must be (1, 2, 5)")
        if self.train_end - self.train_start + 1 != self.row_count:
            raise ValueError("row_count does not match train range")
        if self.forecast_origin <= self.train_end or self.context_length > self.row_count:
            raise ValueError("invalid chronology/context")
        if self.game in {"numbers3", "numbers4"}:
            limit = 3 if self.game == "numbers3" else 4
            if (
                self.target_layout != "position_local"
                or self.position is None
                or self.position > limit
            ):
                raise ValueError("Numbers3/4 require valid position_local geometry")
            if (self.item_count, self.cardinality) != (10, 1):
                raise ValueError("Numbers3/4 require ten items and k=1")
        else:
            expected = {"miniloto": (31, 5), "loto6": (43, 6), "loto7": (37, 7)}[self.game]
            if self.target_layout != "unordered_fixed_cardinality" or self.position is not None:
                raise ValueError("lottery games require unordered geometry")
            if (self.item_count, self.cardinality) != expected:
                raise ValueError("lottery item count/cardinality mismatch")
        return self


class KDPPHistoryApproval(StrictModel):
    schema_version: Literal[SCHEMA_VERSION]
    model_id: Literal[MODEL_ID]
    decision: Literal["APPROVED"]
    approval_token: Literal[APPROVAL_TOKEN]
    reviewer: str = Field(min_length=1, max_length=256)
    reviewed_at_utc: datetime
    history_manifest_sha256: str
    history_sha256sums_sha256: str
    source_read_only_confirmed: Literal[True]
    train_only_confirmed: Literal[True]
    draw_order_confirmed: Literal[True]
    row_count_confirmed: Literal[True]
    game_geometry_confirmed: Literal[True]
    cutoff_confirmed: Literal[True]
    no_future_actuals_confirmed: Literal[True]
    no_holdout_confirmed: Literal[True]
    no_prospective_confirmed: Literal[True]

    @field_validator("history_manifest_sha256", "history_sha256sums_sha256")
    @classmethod
    def hashes(cls, value: str) -> str:
        return validate_sha256(value)

    @field_validator("reviewed_at_utc", mode="before")
    @classmethod
    def parse_reviewed(cls, value: object) -> object:
        return parse_utc(value)

    @field_validator("reviewed_at_utc")
    @classmethod
    def reviewed_is_utc(cls, value: datetime) -> datetime:
        return require_utc(value, "reviewed_at_utc")


class KDPPProcessRecord(StrictModel):
    label: Literal["A", "B"]
    external_pid: int = Field(ge=1)
    runtime_pid: int = Field(ge=1)
    return_code: Literal[0]
    stdout_sha256: str
    stderr_sha256: str
    runtime_tree_sha256: str
    state_sha256: str
    prediction_sha256: str
    prediction_seal_sha256: str
    started_at_utc: datetime
    completed_at_utc: datetime

    @field_validator(
        "stdout_sha256",
        "stderr_sha256",
        "runtime_tree_sha256",
        "state_sha256",
        "prediction_sha256",
        "prediction_seal_sha256",
    )
    @classmethod
    def hashes(cls, value: str) -> str:
        return validate_sha256(value)

    @field_validator("started_at_utc", "completed_at_utc", mode="before")
    @classmethod
    def parse_times(cls, value: object) -> object:
        return parse_utc(value)

    @model_validator(mode="after")
    def chronology(self) -> KDPPProcessRecord:
        require_utc(self.started_at_utc, "started_at_utc")
        require_utc(self.completed_at_utc, "completed_at_utc")
        if self.completed_at_utc < self.started_at_utc:
            raise ValueError("process completion precedes start")
        return self


class KDPPFormalVerificationReport(StrictModel):
    schema_version: Literal[SCHEMA_VERSION]
    model_id: Literal[MODEL_ID]
    status: Literal["PASS", "FAIL"]
    certification_class: Literal["CPU_FORMAL", "NOT_CERTIFIED"]
    formal_runtime_certification: bool
    approved_real_history_verified: bool
    train_only_verified: bool
    two_distinct_processes_verified: bool
    exact_prediction_replay_verified: bool
    exact_state_replay_verified: bool
    prediction_seals_verified: bool
    cpu_only_verified: bool
    no_actuals_verified: bool
    artifact_integrity_verified: bool
    process_records: tuple[KDPPProcessRecord, KDPPProcessRecord]
    verified_at_utc: datetime
    failure_codes: tuple[str, ...] = ()

    @field_validator("verified_at_utc", mode="before")
    @classmethod
    def parse_verified(cls, value: object) -> object:
        return parse_utc(value)

    @model_validator(mode="after")
    def consistent(self) -> KDPPFormalVerificationReport:
        require_utc(self.verified_at_utc, "verified_at_utc")
        gates = (
            self.approved_real_history_verified,
            self.train_only_verified,
            self.two_distinct_processes_verified,
            self.exact_prediction_replay_verified,
            self.exact_state_replay_verified,
            self.prediction_seals_verified,
            self.cpu_only_verified,
            self.no_actuals_verified,
            self.artifact_integrity_verified,
        )
        should_pass = all(gates) and not self.failure_codes
        if should_pass != (self.status == "PASS"):
            raise ValueError("status disagrees with gates")
        if should_pass != self.formal_runtime_certification:
            raise ValueError("formal certification disagrees with gates")
        expected = "CPU_FORMAL" if should_pass else "NOT_CERTIFIED"
        if self.certification_class != expected:
            raise ValueError("certification_class disagrees with gates")
        if {record.label for record in self.process_records} != {"A", "B"}:
            raise ValueError("process records must contain A and B")
        return self


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return payload


def _regular_files(root: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("symlinks are forbidden")
        if path.is_file():
            files[path.relative_to(root).as_posix()] = path
    return files


def verify_inventory(root: Path, inventory_name: str, expected: set[str]) -> None:
    inventory = root / inventory_name
    records: dict[str, str] = {}
    for line in inventory.read_text(encoding="utf-8").splitlines():
        digest, separator, name = line.partition("  ")
        if not separator or name in records:
            raise ValueError("invalid SHA256SUMS")
        records[safe_relative(name)] = validate_sha256(digest)
    if set(records) != expected:
        raise ValueError("SHA256SUMS coverage mismatch")
    for name, digest in records.items():
        if sha256_file(root / name) != digest:
            raise ValueError(f"SHA-256 mismatch: {name}")


def tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for name, path in sorted(_regular_files(root).items()):
        digest.update(f"{sha256_file(path)}  {name}\n".encode())
    return digest.hexdigest()


def validate_history_bundle(
    root: Path, approval_path: Path
) -> tuple[KDPPHistoryManifest, KDPPHistoryApproval, tuple[str, ...]]:
    files = _regular_files(root)
    if set(files) != HISTORY_FILES:
        raise ValueError("history bundle file set mismatch")
    verify_inventory(root, "SHA256SUMS", HISTORY_FILES - {"SHA256SUMS"})
    manifest = KDPPHistoryManifest.model_validate(_load_json(files["history_manifest.json"]))
    approval = KDPPHistoryApproval.model_validate(_load_json(approval_path))
    if approval.history_manifest_sha256 != sha256_file(files["history_manifest.json"]):
        raise ValueError("approval manifest hash mismatch")
    if approval.history_sha256sums_sha256 != sha256_file(files["SHA256SUMS"]):
        raise ValueError("approval checksum hash mismatch")
    if manifest.training_npz_sha256 != sha256_file(files["training.npz"]):
        raise ValueError("training NPZ hash mismatch")
    if manifest.item_ids_json_sha256 != sha256_file(files["item_ids.json"]):
        raise ValueError("item IDs hash mismatch")
    item_ids_payload = json.loads(files["item_ids.json"].read_text(encoding="utf-8"))
    if not isinstance(item_ids_payload, list) or not all(
        isinstance(item, str) for item in item_ids_payload
    ):
        raise ValueError("item_ids.json must be an array of strings")
    item_ids = tuple(item_ids_payload)
    if len(item_ids) != manifest.item_count or len(set(item_ids)) != len(item_ids):
        raise ValueError("item ID count/uniqueness mismatch")
    if manifest.game in {"numbers3", "numbers4"}:
        expected_ids = tuple(f"n{manifest.position}:{digit}" for digit in range(10))
    else:
        expected_ids = tuple(str(index) for index in range(1, manifest.item_count + 1))
    if item_ids != expected_ids:
        raise ValueError("item IDs do not match canonical game geometry")
    with np.load(files["training.npz"], allow_pickle=False) as arrays:
        supported_arrays = (
            {"training_indicators", "draw_nos"},
            {"training_indicators", "draw_nos", "item_features"},
        )
        if set(arrays.files) not in supported_arrays:
            raise ValueError("training NPZ array set mismatch")
        training = np.asarray(arrays["training_indicators"])
        draw_nos = np.asarray(arrays["draw_nos"])
        if "item_features" in arrays:
            features = np.asarray(arrays["item_features"], dtype=np.float64)
            if (
                features.ndim != 2
                or features.shape[0] != manifest.item_count
                or not np.isfinite(features).all()
            ):
                raise ValueError("invalid item_features")
    if training.shape != (manifest.row_count, manifest.item_count):
        raise ValueError("training shape mismatch")
    if not np.isfinite(training).all() or not np.isin(training, (0, 1)).all():
        raise ValueError("training must be finite binary")
    if not np.all(training.sum(axis=1) == manifest.cardinality):
        raise ValueError("fixed cardinality violation")
    expected_draws = np.arange(manifest.train_start, manifest.train_end + 1)
    if draw_nos.ndim != 1 or not np.array_equal(draw_nos, expected_draws):
        raise ValueError("draw_nos must be increasing and gap-free")
    return manifest, approval, item_ids


def copy_approved_history(source: Path, destination: Path) -> None:
    if destination.exists():
        raise FileExistsError(destination)
    destination.mkdir(parents=True)
    for name in sorted(HISTORY_FILES):
        shutil.copy2(source / name, destination / name)


def verify_runtime_directory(root: Path) -> dict[str, Any]:
    files = _regular_files(root)
    if set(files) != RUNTIME_FILES:
        raise ValueError("runtime file set mismatch")
    verify_inventory(root, "CERTIFICATION_SHA256SUMS", RUNTIME_FILES - {"CERTIFICATION_SHA256SUMS"})
    verify_inventory(
        root / "state",
        "SHA256SUMS",
        {"kdpp_state.json", "kdpp_state.npz", "artifact_manifest.json"},
    )
    request = _load_json(files["request.json"])
    response = _load_json(files["response.json"])
    lock = _load_json(files["prediction.lock.json"])
    evidence = _load_json(files["runtime_evidence.json"])
    state = _load_json(files["state/kdpp_state.json"])
    for name, payload in (("request", request), ("response", response), ("lock", lock)):
        if payload.get("model_id") != MODEL_ID or payload.get("actuals_used") is not False:
            raise ValueError(f"{name} identity/actuals mismatch")
    if response.get("requested_device") != "cpu" or response.get("effective_device") != "cpu":
        raise ValueError("response is not CPU-only")
    if response.get("cpu_fallback") is not False or response.get("gpu_not_applicable") is not True:
        raise ValueError("CPU fallback/GPU evidence mismatch")
    if response.get("gpu_uuid") is not None or response.get("gpu_process_vram_mb") is not None:
        raise ValueError("GPU fields must be null")
    if response.get("quantiles") is not None or response.get("finite_check") is not True:
        raise ValueError("quantile/finite evidence mismatch")
    if (
        response.get("exact_cardinality_check") is not True
        or response.get("duplicate_check") is not True
    ):
        raise ValueError("cardinality/duplicate evidence mismatch")
    if response.get("point_forecast_semantics") != "SEEDED_EXACT_KDPP_SAMPLE":
        raise ValueError("point semantics mismatch")
    prediction_hash = validate_sha256(str(lock.get("prediction_sha256")))
    if prediction_hash != evidence.get("prediction_sha256"):
        raise ValueError("prediction hash mismatch")
    state_hash = validate_sha256(str(evidence.get("state_sha256")))
    if state_hash != state.get("state_sha256"):
        raise ValueError("state hash mismatch")
    runtime_pid = int(evidence.get("runtime_pid", 0))
    if runtime_pid < 1 or runtime_pid != int(response.get("runtime_pid", 0)):
        raise ValueError("runtime PID mismatch")
    cardinality = int(response.get("cardinality", 0))
    points = response.get("point_forecast")
    marginals = response.get("marginal_inclusion_probabilities")
    if (
        not isinstance(points, list)
        or not isinstance(marginals, list)
        or len(points) != len(marginals)
    ):
        raise ValueError("forecast/marginal horizon mismatch")
    for subset in points:
        if (
            not isinstance(subset, list)
            or len(subset) != cardinality
            or len(set(subset)) != cardinality
        ):
            raise ValueError("invalid exact subset")
    for row in marginals:
        invalid_row = not isinstance(row, list) or any(
            not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or not 0 <= float(value) <= 1
            for value in row
        )
        if invalid_row:
            raise ValueError("invalid marginals")
        if not math.isclose(sum(float(v) for v in row), cardinality, abs_tol=1e-8):
            raise ValueError("marginals do not sum to k")
    return {
        "prediction_sha256": prediction_hash,
        "state_sha256": state_hash,
        "runtime_pid": runtime_pid,
        "tree_sha256": tree_sha256(root),
        "request": request,
        "response": response,
    }


def write_json(path: Path, payload: Any) -> None:
    if isinstance(payload, BaseModel):
        payload = payload.model_dump(mode="json")
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    path.write_text(serialized, encoding="utf-8")
