from __future__ import annotations

import hashlib
import json
import math
import random
import statistics as stats
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

LOCK_SCHEMA = "autogluon-holdout-prospective-lock-v1"
SCORE_SCHEMA = "autogluon-holdout-prospective-score-v1"
REQUIRED_BASELINES = (
    "baseline_random",
    "baseline_fixed",
    "baseline_mean",
    "baseline_median",
    "baseline_last",
    "baseline_frequency",
    "baseline_ar1",
)


class HoldoutProspectiveError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class GeometryContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    game_id: str = Field(min_length=1)
    position_columns: tuple[str, ...]
    candidate_min: int
    candidate_max: int
    selection_count: int = Field(gt=0)
    horizon: int = Field(gt=0)
    allow_duplicates: bool = False
    sort_policy: str = "ascending"

    @model_validator(mode="after")
    def valid(self) -> "GeometryContract":
        if not self.position_columns or len(set(self.position_columns)) != len(
            self.position_columns
        ):
            raise ValueError("positions must be non-empty and unique")
        if self.selection_count != len(self.position_columns):
            raise ValueError("selection_count mismatch")
        if self.candidate_min > self.candidate_max:
            raise ValueError("invalid domain")
        return self


class SelectionEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    selection_id: str = Field(min_length=1)
    selected_candidate_id: str = Field(min_length=1)
    model_seeds: tuple[int, ...] = (1, 2, 3)
    selection_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    automatic_selection: bool = False

    @field_validator("model_seeds")
    @classmethod
    def seeds(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if len(value) < 3 or len(set(value)) != len(value):
            raise ValueError("at least three unique seeds are required")
        return value

    @model_validator(mode="after")
    def no_auto(self) -> "SelectionEvidence":
        if self.automatic_selection:
            raise ValueError("automatic selection is forbidden")
        return self


class PredictionRow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    candidate_id: str
    seed: int
    draw_id: int
    values: tuple[float, ...]

    @field_validator("values")
    @classmethod
    def finite(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        result = tuple(float(item) for item in value)
        if not result or any(not math.isfinite(item) for item in result):
            raise ValueError("predictions must be finite")
        return result


@dataclass(frozen=True)
class MetricResult:
    hit_at_1: float
    all_position_hit_at_1: float
    exact_hit_rate: float
    mae: float
    mse: float
    rmse: float
    position_hit_at_1: tuple[float, ...]


@dataclass(frozen=True)
class DriftPolicy:
    hit_target: float = 0.90
    warning_hit_drop: float = 0.05
    critical_hit_drop: float = 0.10
    warning_mae_increase: float = 0.50
    critical_mae_increase: float = 1.00


@dataclass(frozen=True)
class LockResult:
    output_dir: str
    lock_path: str
    lock_sha256: str
    stage: str
    candidate_id: str
    prediction_rows: int
    baseline_rows: int


@dataclass(frozen=True)
class ScoreResult:
    output_dir: str
    report_path: str
    status: str
    stage: str
    selected_candidate_id: str
    operational_state: str


def _canon(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode()


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _file_hash(path: Path) -> str:
    return _digest(path.read_bytes())


def _write(path: Path, value: Any) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)


def _empty(path: Path) -> Path:
    root = path.resolve()
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise HoldoutProspectiveError("OUTPUT_NOT_EMPTY", str(root))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _tree_hash(root: Path) -> str:
    parts = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if path.is_symlink():
            raise HoldoutProspectiveError("SYMLINK_FORBIDDEN", str(path))
        parts += [path.relative_to(root).as_posix().encode(), path.read_bytes()]
    return _digest(b"\0".join(parts))


def _write_evidence(root: Path, payload_names: Sequence[str]) -> None:
    manifest = {
        "schema_version": 1,
        "files": [
            {
                "path": name,
                "bytes": (root / name).stat().st_size,
                "sha256": _file_hash(root / name),
            }
            for name in sorted(payload_names)
        ],
    }
    _write(root / "ARTIFACT_MANIFEST.json", manifest)
    lines = [
        f"{_file_hash(path)}  {path.name}"
        for path in sorted(root.iterdir())
        if path.is_file() and path.name != "SHA256SUMS"
    ]
    (root / "SHA256SUMS").write_text("\n".join(lines) + "\n")


def _verify_hashes(root: Path, code: str) -> set[str]:
    for path in root.rglob("*"):
        if path.is_symlink():
            raise HoldoutProspectiveError("SYMLINK_FORBIDDEN", str(path))
        if not path.is_file() and not path.is_dir():
            raise HoldoutProspectiveError("SPECIAL_FILE_FORBIDDEN", str(path))
    observed = {path.name for path in root.iterdir() if path.is_file()}
    sums: dict[str, str] = {}
    for line in (root / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split("  ", 1)
        sums[name] = digest
    if set(sums) != observed - {"SHA256SUMS"}:
        raise HoldoutProspectiveError(f"{code}_SHA_COVERAGE_MISMATCH", str(sums))
    for name, digest in sums.items():
        if _file_hash(root / name) != digest:
            raise HoldoutProspectiveError(f"{code}_FILE_HASH_MISMATCH", name)
    manifest = json.loads((root / "ARTIFACT_MANIFEST.json").read_text())
    records = manifest.get("files")
    if not isinstance(records, list):
        raise HoldoutProspectiveError(f"{code}_MANIFEST_INVALID", "files")
    expected = observed - {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
    by_name = {record.get("path"): record for record in records}
    if set(by_name) != expected:
        raise HoldoutProspectiveError(f"{code}_MANIFEST_COVERAGE_MISMATCH", str(by_name))
    for name, record in by_name.items():
        path = root / name
        if record.get("bytes") != path.stat().st_size:
            raise HoldoutProspectiveError(f"{code}_MANIFEST_SIZE_MISMATCH", name)
        if record.get("sha256") != _file_hash(path):
            raise HoldoutProspectiveError(f"{code}_MANIFEST_HASH_MISMATCH", name)
    return observed


def _actual_field(value: Any) -> str | None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if any(token in str(key).lower() for token in ("actual", "observed", "outcome")):
                return str(key)
            found = _actual_field(child)
            if found:
                return found
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for child in value:
            found = _actual_field(child)
            if found:
                return found
    return None


def _vector(row: Mapping[str, Any], geometry: GeometryContract) -> tuple[float, ...]:
    try:
        result = tuple(float(row[name]) for name in geometry.position_columns)
    except (KeyError, TypeError, ValueError) as exc:
        raise HoldoutProspectiveError("VECTOR_INVALID", str(exc)) from exc
    if any(not math.isfinite(item) for item in result):
        raise HoldoutProspectiveError("VECTOR_INVALID", str(result))
    if any(
        item < geometry.candidate_min or item > geometry.candidate_max
        for item in result
    ):
        raise HoldoutProspectiveError("VECTOR_OUT_OF_RANGE", str(result))
    if not geometry.allow_duplicates and len(set(result)) != len(result):
        raise HoldoutProspectiveError("VECTOR_DUPLICATE", str(result))
    if geometry.sort_policy == "ascending" and tuple(sorted(result)) != result:
        raise HoldoutProspectiveError("VECTOR_ORDER_INVALID", str(result))
    return result


def _history(
    rows: Sequence[Mapping[str, Any]], geometry: GeometryContract
) -> tuple[dict[str, Any], ...]:
    forbidden = _actual_field(rows)
    if forbidden:
        raise HoldoutProspectiveError("ACTUAL_FIELD_FORBIDDEN", forbidden)
    output = []
    draw_ids = []
    for row in rows:
        draw_id = row.get("draw_id")
        if isinstance(draw_id, bool) or not isinstance(draw_id, int):
            raise HoldoutProspectiveError("HISTORY_DRAW_ID_INVALID", str(draw_id))
        values = _vector(row, geometry)
        output.append({"draw_id": draw_id, **dict(zip(geometry.position_columns, values))})
        draw_ids.append(draw_id)
    if len(rows) < 3 or any(right <= left for left, right in zip(draw_ids, draw_ids[1:])):
        raise HoldoutProspectiveError("HISTORY_ORDER_INVALID", str(draw_ids))
    return tuple(output)


def compute_metrics(prediction: Sequence[float], actual: Sequence[float]) -> MetricResult:
    if len(prediction) != len(actual) or not prediction:
        raise HoldoutProspectiveError("METRIC_SHAPE_MISMATCH", "prediction/actual")
    errors = [float(left) - float(right) for left, right in zip(prediction, actual)]
    hits = tuple(float(abs(error) <= 1.0) for error in errors)
    mse = stats.fmean(error * error for error in errors)
    return MetricResult(
        hit_at_1=stats.fmean(hits),
        all_position_hit_at_1=float(all(hits)),
        exact_hit_rate=stats.fmean(float(error == 0) for error in errors),
        mae=stats.fmean(abs(error) for error in errors),
        mse=mse,
        rmse=math.sqrt(mse),
        position_hit_at_1=hits,
    )


def _frequency(vectors: Sequence[tuple[float, ...]]) -> tuple[float, ...]:
    result = []
    for position in range(len(vectors[0])):
        values = [row[position] for row in vectors]
        result.append(min(set(values), key=lambda item: (-values.count(item), item)))
    return tuple(result)


def _ar1(vectors: Sequence[tuple[float, ...]]) -> tuple[float, ...]:
    result = []
    for position in range(len(vectors[0])):
        values = [row[position] for row in vectors]
        left, right = values[:-1], values[1:]
        mean_left, mean_right = stats.fmean(left), stats.fmean(right)
        denominator = sum((item - mean_left) ** 2 for item in left)
        if denominator == 0:
            result.append(values[-1])
            continue
        slope = sum(
            (x - mean_left) * (y - mean_right) for x, y in zip(left, right)
        ) / denominator
        result.append(mean_right - slope * mean_left + slope * values[-1])
    return tuple(result)


def build_baseline_predictions(
    history_rows: Sequence[Mapping[str, Any]],
    future_draw_ids: Sequence[int],
    geometry: GeometryContract,
) -> tuple[PredictionRow, ...]:
    history = _history(history_rows, geometry)
    vectors = [_vector(row, geometry) for row in history]
    positions = range(geometry.selection_count)
    width = geometry.candidate_max - geometry.candidate_min
    fixed = tuple(
        float(
            geometry.candidate_min
            + round((index + 1) * width / (geometry.selection_count + 1))
        )
        for index in positions
    )
    deterministic = {
        "baseline_fixed": fixed,
        "baseline_mean": tuple(stats.fmean(row[pos] for row in vectors) for pos in positions),
        "baseline_median": tuple(stats.median(row[pos] for row in vectors) for pos in positions),
        "baseline_last": vectors[-1],
        "baseline_frequency": _frequency(vectors),
        "baseline_ar1": _ar1(vectors),
    }
    rows = []
    domain = range(geometry.candidate_min, geometry.candidate_max + 1)
    for seed in (1, 2, 3):
        rng = random.Random(seed)
        for draw_id in future_draw_ids:
            sampled = rng.sample(list(domain), geometry.selection_count)
            values = tuple(float(item) for item in sorted(sampled))
            rows.append(PredictionRow(candidate_id="baseline_random", seed=seed,
                                      draw_id=draw_id, values=values))
    for candidate, values in deterministic.items():
        rows.extend(
            PredictionRow(candidate_id=candidate, seed=0, draw_id=draw_id, values=values)
            for draw_id in future_draw_ids
        )
    return tuple(rows)


def _prediction_rows(rows: Sequence[Mapping[str, Any]]) -> tuple[PredictionRow, ...]:
    return tuple(PredictionRow.model_validate(row) for row in rows)


from loto.autogluon_campaign.holdout_prospective_lock import (  # noqa: E402
    create_prediction_lock,
    verify_prediction_lock,
)
from loto.autogluon_campaign.holdout_prospective_score import (  # noqa: E402
    score_prediction_lock,
    verify_scoring_output,
)
