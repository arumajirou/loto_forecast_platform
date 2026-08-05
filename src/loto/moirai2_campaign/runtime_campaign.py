from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from loto.moirai2_campaign.model_manifest import (
    MODEL_ID,
    MODEL_REVISION,
    NATIVE_QUANTILE_LEVELS,
    REPO_ID,
)


class RuntimeCampaignError(RuntimeError):
    pass


@dataclass(frozen=True)
class RuntimeCase:
    name: str
    time_semantics: str
    covariate_mode: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


FORMAL_CASES: tuple[RuntimeCase, ...] = (
    RuntimeCase("draw-target-only", "draw_sequence", "target_only"),
    RuntimeCase("draw-past-only", "draw_sequence", "past_only"),
    RuntimeCase(
        "draw-past-known-future",
        "draw_sequence",
        "past_known_future",
    ),
    RuntimeCase("calendar-target-only", "calendar_time", "target_only"),
    RuntimeCase("calendar-past-only", "calendar_time", "past_only"),
    RuntimeCase(
        "calendar-past-known-future",
        "calendar_time",
        "past_known_future",
    ),
)
FORMAL_CASE_NAMES = tuple(case.name for case in FORMAL_CASES)


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_payload(payload: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def deterministic_history(
    *,
    history_length: int,
    position_count: int,
    candidate_min: int,
    candidate_max: int,
) -> list[dict[str, int]]:
    if history_length < 2:
        raise RuntimeCampaignError("history_length must be at least 2")
    domain_size = candidate_max - candidate_min + 1
    if position_count < 1 or position_count > domain_size:
        raise RuntimeCampaignError("position_count is incompatible with candidate domain")
    offset_count = domain_size - position_count + 1
    rows: list[dict[str, int]] = []
    for row_index in range(history_length):
        offset = (row_index * 3) % offset_count
        values = [candidate_min + offset + index for index in range(position_count)]
        rows.append(
            {
                f"n{position + 1}": value
                for position, value in enumerate(values)
            }
        )
    return rows


def draw_timestamps(history_length: int, *, first_draw: int = 100_000) -> list[int]:
    return list(range(first_draw, first_draw + history_length))


def calendar_timestamps(history_length: int) -> list[str]:
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    timestamps: list[str] = []
    day_offset = 0
    for index in range(history_length):
        if index and index % 19 == 0:
            day_offset += 2
        timestamps.append((start + timedelta(days=day_offset)).isoformat())
        day_offset += 1
    return timestamps


def _normalized_steps(length: int) -> list[float]:
    if length < 1:
        raise RuntimeCampaignError("feature length must be positive")
    denominator = max(length - 1, 1)
    return [round(index / denominator, 10) for index in range(length)]


def build_case_request(
    case: RuntimeCase,
    *,
    campaign_id: str,
    snapshot_path: Path,
    device: str,
    history_length: int = 128,
    context_length: int = 128,
    prediction_length: int = 1,
    position_count: int = 7,
    candidate_min: int = 1,
    candidate_max: int = 37,
) -> dict[str, Any]:
    if device not in {"cpu", "cuda"}:
        raise RuntimeCampaignError(f"unsupported device: {device}")
    if context_length > history_length:
        raise RuntimeCampaignError("context_length cannot exceed history_length")
    if prediction_length not in {1, 2, 5}:
        raise RuntimeCampaignError("prediction_length must be one of 1, 2, or 5")
    history = deterministic_history(
        history_length=history_length,
        position_count=position_count,
        candidate_min=candidate_min,
        candidate_max=candidate_max,
    )
    position_columns = [f"n{index + 1}" for index in range(position_count)]
    timestamps: list[int] | list[str]
    if case.time_semantics == "calendar_time":
        timestamps = calendar_timestamps(history_length)
    elif case.time_semantics == "draw_sequence":
        timestamps = draw_timestamps(history_length)
    else:
        raise RuntimeCampaignError(f"unsupported time semantics: {case.time_semantics}")

    past_covariates: dict[str, list[float]] = {}
    future_covariates: dict[str, list[float]] = {}
    availability: dict[str, str] = {}
    if case.covariate_mode in {"past_only", "past_known_future"}:
        past_covariates["cert_past_index"] = _normalized_steps(history_length)
    if case.covariate_mode == "past_known_future":
        total = history_length + prediction_length
        future_covariates["cert_known_step"] = _normalized_steps(total)
        availability["cert_known_step"] = "known_at_prediction_time"
    if case.covariate_mode not in {
        "target_only",
        "past_only",
        "past_known_future",
    }:
        raise RuntimeCampaignError(f"unsupported covariate mode: {case.covariate_mode}")

    return {
        "schema_version": 2,
        "run_id": f"{campaign_id}.{case.name}",
        "operation": "predict",
        "model_id": MODEL_ID,
        "repo_id": REPO_ID,
        "revision": MODEL_REVISION,
        "license_lane": "personal_noncommercial_research",
        "game_geometry": {
            "game_id": "loto7-runtime-certification",
            "position_count": position_count,
            "candidate_min": candidate_min,
            "candidate_max": candidate_max,
            "strictly_increasing": True,
        },
        "series_layout": "position_multivariate",
        "position_columns": position_columns,
        "history": history,
        "timestamps": timestamps,
        "time_semantics": case.time_semantics,
        "past_covariates": past_covariates,
        "future_covariates": future_covariates,
        "future_covariate_availability": availability,
        "context_length": context_length,
        "prediction_length": prediction_length,
        "native_quantile_levels": list(NATIVE_QUANTILE_LEVELS),
        "point_method": "median_q0.5",
        "batch_size": 1,
        "device": device,
        "dtype": "float32",
        "seed": 1,
        "local_files_only": True,
        "snapshot_path": str(snapshot_path.resolve()),
    }


def build_campaign_requests(
    *,
    campaign_id: str,
    snapshot_path: Path,
    device: str,
    selected_cases: Iterable[str] | None = None,
    history_length: int = 128,
    context_length: int = 128,
    prediction_length: int = 1,
) -> dict[str, dict[str, Any]]:
    requested = tuple(selected_cases or FORMAL_CASE_NAMES)
    if len(requested) != len(set(requested)):
        raise RuntimeCampaignError("selected certification cases must be unique")
    selected = set(requested)
    unknown = sorted(selected - set(FORMAL_CASE_NAMES))
    if unknown:
        raise RuntimeCampaignError(f"unknown certification cases: {unknown}")
    if not selected:
        raise RuntimeCampaignError("at least one certification case is required")
    return {
        case.name: build_case_request(
            case,
            campaign_id=campaign_id,
            snapshot_path=snapshot_path,
            device=device,
            history_length=history_length,
            context_length=context_length,
            prediction_length=prediction_length,
        )
        for case in FORMAL_CASES
        if case.name in selected
    }


def validate_generated_request(case_name: str, payload: dict[str, Any]) -> None:
    if case_name not in FORMAL_CASE_NAMES:
        raise RuntimeCampaignError(f"unknown case: {case_name}")
    case = next(item for item in FORMAL_CASES if item.name == case_name)
    history_length = len(payload.get("history", []))
    prediction_length = int(payload.get("prediction_length", 0))
    if history_length < 1:
        raise RuntimeCampaignError("generated request has no history")
    if payload.get("time_semantics") != case.time_semantics:
        raise RuntimeCampaignError("generated request time semantics mismatch")
    timestamps = payload.get("timestamps")
    if not isinstance(timestamps, list) or len(timestamps) != history_length:
        raise RuntimeCampaignError("generated timestamps must match history length")
    past = payload.get("past_covariates")
    future = payload.get("future_covariates")
    availability = payload.get("future_covariate_availability")
    if not isinstance(past, dict) or not isinstance(future, dict):
        raise RuntimeCampaignError("generated covariates must be mappings")
    if not isinstance(availability, dict):
        raise RuntimeCampaignError("future availability must be a mapping")
    expected_past = case.covariate_mode in {"past_only", "past_known_future"}
    expected_future = case.covariate_mode == "past_known_future"
    if bool(past) != expected_past or bool(future) != expected_future:
        raise RuntimeCampaignError("generated covariate mode mismatch")
    if past and len(past["cert_past_index"]) != history_length:
        raise RuntimeCampaignError("past-only certification feature length mismatch")
    if future:
        expected_length = history_length + prediction_length
        if len(future["cert_known_step"]) != expected_length:
            raise RuntimeCampaignError("known-future certification feature length mismatch")
        if availability != {"cert_known_step": "known_at_prediction_time"}:
            raise RuntimeCampaignError("known-future availability evidence mismatch")
    elif availability:
        raise RuntimeCampaignError("availability exists without known-future feature")
    feature_names = [*past, *future]
    if any("actual" in name.lower() for name in feature_names):
        raise RuntimeCampaignError("generated covariate name contains an actual marker")


def summarize_campaign(
    *,
    case_results: list[dict[str, Any]],
    required_cases: Iterable[str],
    runtime_lane: str,
    requested_device: str,
) -> dict[str, Any]:
    required = tuple(required_cases)
    if len(required) != len(set(required)):
        raise RuntimeCampaignError("required case names must be unique")
    observed = [str(result.get("case")) for result in case_results]
    if len(observed) != len(set(observed)):
        raise RuntimeCampaignError("case results contain duplicate cases")
    missing = sorted(set(required) - set(observed))
    extra = sorted(set(observed) - set(required))
    failures: list[dict[str, str]] = []
    for result in case_results:
        case_name = str(result.get("case"))
        if result.get("status") != "PASS":
            failures.append(
                {
                    "case": case_name,
                    "reason": str(result.get("message", "case did not pass")),
                }
            )
            continue
        certification = result.get("certification")
        if not isinstance(certification, dict):
            failures.append({"case": case_name, "reason": "certification missing"})
            continue
        if certification.get("status") != "PASS":
            failures.append({"case": case_name, "reason": "certification not PASS"})
        if certification.get("runtime_lane") != runtime_lane:
            failures.append({"case": case_name, "reason": "runtime lane mismatch"})
        if certification.get("requested_device") != requested_device:
            failures.append({"case": case_name, "reason": "requested device mismatch"})
        if certification.get("separate_process_reload") is not True:
            failures.append({"case": case_name, "reason": "reload evidence missing"})
        comparison = certification.get("prediction_comparison")
        if not isinstance(comparison, dict):
            failures.append({"case": case_name, "reason": "comparison missing"})
            continue
        required_flags = (
            "distinct_processes",
            "exact_prediction_match",
            "artifact_identity_match",
            "model_identity_match",
            "covariate_identity_match",
        )
        for flag in required_flags:
            if comparison.get(flag) is not True:
                failures.append({"case": case_name, "reason": f"{flag} is not true"})
    if missing:
        failures.append({"case": "campaign", "reason": f"missing cases: {missing}"})
    if extra:
        failures.append({"case": "campaign", "reason": f"unexpected cases: {extra}"})
    status = "PASS" if not failures else "FAILED"
    return {
        "schema_version": "moirai2-p8-runtime-campaign-v1",
        "status": status,
        "phase": "P8_RUNTIME_CAMPAIGN",
        "runtime_lane": runtime_lane,
        "requested_device": requested_device,
        "required_cases": list(required),
        "observed_cases": observed,
        "passed_case_count": sum(
            1 for result in case_results if result.get("status") == "PASS"
        ),
        "required_case_count": len(required),
        "failures": failures,
        "case_result_sha256": sha256_payload(case_results),
        "formal_runtime_certified": status == "PASS" and set(required) == set(FORMAL_CASE_NAMES),
        "accuracy_claimed": False,
        "oof_opened": False,
        "holdout_opened": False,
        "prospective_opened": False,
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_sha256_manifest(root: Path, output_path: Path) -> None:
    paths = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.resolve() != output_path.resolve()
    )
    lines = [f"{sha256_file(path)}  {path.relative_to(root).as_posix()}" for path in paths]
    output_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
