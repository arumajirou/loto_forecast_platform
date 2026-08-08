from __future__ import annotations

import csv
import hashlib
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from loto.data_access_ledger import (
    AccessDecision,
    AccessEvent,
    AccessOperation,
    DataRole,
    DatasetSlice,
    FoldRole,
    Stage,
    build_ledger,
    sha256_hex,
    validate_ledger,
)


class ResearchLedgerError(RuntimeError):
    """Base error for research ledger adapter failures."""


class ResearchLedgerPreflightError(ResearchLedgerError):
    """Raised before research execution when the lane cannot be audited safely."""


class ResearchLedgerBlocked(ResearchLedgerError):
    """Raised after evidence is persisted when validation or coverage is incomplete."""


@dataclass(frozen=True)
class ResearchDatasetEvidence:
    dataset_id: str
    dataset_sha256: str
    data_version: str
    game_id: str
    series_ids: tuple[str, ...]
    observed_times: tuple[datetime, ...]
    draw_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.observed_times:
            raise ValueError("observed_times must not be empty")
        if len(self.observed_times) != len(self.draw_ids):
            raise ValueError("observed_times and draw_ids must have equal length")
        for value in self.observed_times:
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("observed_times must be timezone-aware")


class ResearchLedgerAdapterReport(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    status: AccessDecision
    run_id: str
    evidence_mode: str = "POST_RUN_RECONCILIATION"
    runtime_interception: bool = False
    ledger_path: str | None = None
    validation_path: str | None = None
    ledger_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    source_file_sha256_before: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    source_file_sha256_after: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    coverage_gaps: list[str] = Field(default_factory=list)
    verified_events: int = Field(default=0, ge=0)


Runner = Callable[[Any], dict[str, Any]]
EvidenceLoader = Callable[[Any], ResearchDatasetEvidence]
Clock = Callable[[], datetime]


def _getattr_path(value: Any, path: str, default: Any = None) -> Any:
    current = value
    for part in path.split("."):
        if current is None or not hasattr(current, part):
            return default
        current = getattr(current, part)
    return current


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _absolute_path(path: Path) -> Path:
    return Path(os.path.abspath(path.expanduser()))


def _reject_symlink_components(path: Path, *, label: str) -> None:
    absolute = _absolute_path(path)
    for candidate in (absolute, *absolute.parents):
        if candidate.exists() and candidate.is_symlink():
            raise ResearchLedgerPreflightError(
                f"{label} must not contain a symlink component: {candidate}"
            )


def _assert_regular_file(path: Path, *, label: str) -> None:
    _reject_symlink_components(path, label=label)
    if not path.is_file():
        raise ResearchLedgerPreflightError(f"{label} is not a regular file: {path}")


def _assert_safe_output(output: Path) -> None:
    _reject_symlink_components(output, label="output")
    output.mkdir(parents=True, exist_ok=True)
    for name in (
        "data_access_ledger.json",
        "data_access_validation.json",
        "data_access_adapter_report.json",
    ):
        candidate = output / name
        if candidate.is_symlink():
            raise ResearchLedgerPreflightError(
                f"adapter artifact must not be a symlink: {candidate}"
            )


def _atomic_write_json(path: Path, payload: Any) -> None:
    _assert_safe_output(path.parent)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    if temporary.exists() or temporary.is_symlink():
        temporary.unlink()
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            handle.write(text)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _default_runner(config: Any) -> dict[str, Any]:
    from loto.orchestration.research import run_research_experiment

    return run_research_experiment(config)


def _default_evidence_loader(config: Any) -> ResearchDatasetEvidence:
    import pandas as pd

    from loto.data.canonical import canonicalize_loto7

    source = _absolute_path(Path(str(_getattr_path(config, "data.input"))))
    _assert_regular_file(source, label="research input")
    raw = pd.read_csv(source)
    master, manifest = canonicalize_loto7(raw, source=str(source))
    observed_times = tuple(
        _utc(value.to_pydatetime() if hasattr(value, "to_pydatetime") else value)
        for value in master["draw_date"].tolist()
    )
    return ResearchDatasetEvidence(
        dataset_id=str(manifest.dataset_id),
        dataset_sha256=str(manifest.sha256),
        data_version=str(manifest.data_version),
        game_id="loto7",
        series_ids=tuple(f"n{index}" for index in range(1, 8)),
        observed_times=observed_times,
        draw_ids=tuple(str(value) for value in master["draw_id"].tolist()),
    )


def _preflight_gaps(config: Any) -> list[str]:
    gaps: list[str] = []
    if _getattr_path(config, "search.backend", "none") != "none":
        gaps.append("TUNING_RUNTIME_ACCESS_NOT_INTERCEPTED")
    if bool(_getattr_path(config, "runtime.resume", False)):
        gaps.append("RESUME_ARTIFACT_ACCESS_NOT_INTERCEPTED")
    if _getattr_path(config, "observability.mlflow_uri"):
        gaps.append("MLFLOW_WRITE_OCCURS_BEFORE_POST_RUN_VALIDATION")
    return gaps


def _event_id(prefix: str, *parts: object) -> str:
    digest = sha256_hex([str(part) for part in parts])[:24]
    return f"research:{prefix}:{digest}"


def _projection_hash(dataset_sha256: str, projection: str) -> str:
    return sha256_hex({"dataset_sha256": dataset_sha256, "projection": projection})


def _slice(
    evidence: ResearchDatasetEvidence,
    *,
    dataset_id: str,
    dataset_sha256: str,
    data_role: DataRole,
    row_start: int,
    row_end: int,
    forecast_origin: datetime,
    contains_targets: bool,
    contains_actuals: bool,
    fold_id: str | None = None,
    fold_role: FoldRole | None = None,
    draw_id: str | None = None,
) -> DatasetSlice:
    return DatasetSlice(
        dataset_id=dataset_id,
        dataset_sha256=dataset_sha256,
        data_role=data_role,
        game_id=evidence.game_id,
        series_ids=list(evidence.series_ids),
        row_start=row_start,
        row_end=row_end,
        observed_time_start=evidence.observed_times[row_start],
        observed_time_end=evidence.observed_times[row_end],
        available_at=evidence.observed_times[row_end],
        forecast_origin=forecast_origin,
        contains_targets=contains_targets,
        contains_actuals=contains_actuals,
        immutable_source=True,
        fold_id=fold_id,
        fold_role=fold_role,
        draw_id=draw_id,
    )


def _load_successful_trials(output: Path) -> list[tuple[str, int]]:
    path = output / "trial_results.csv"
    if not path.is_file() or path.is_symlink():
        return []
    rows: list[tuple[str, int]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("status") == "SUCCEEDED":
                rows.append((str(row["model_id"]), int(row["seed"])))
    return rows


def _normalize_folds(summary: dict[str, Any]) -> list[dict[str, int | str]]:
    normalized: list[dict[str, int | str]] = []
    for index, raw in enumerate(summary.get("outer_folds", [])):
        try:
            fold_id = str(raw.get("fold_id", f"outer-{index}"))
            train_end = int(raw["train_end"])
            test_start = int(raw["test_start"])
            test_end = int(raw["test_end"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ResearchLedgerBlocked(f"invalid outer fold evidence: {raw!r}") from exc
        if not (0 < train_end <= test_start < test_end):
            raise ResearchLedgerBlocked(f"non-chronological outer fold: {raw!r}")
        normalized.append(
            {
                "fold_id": fold_id,
                "train_end": train_end,
                "test_start": test_start,
                "test_end": test_end,
            }
        )
    return normalized


def _build_events(
    *,
    run_id: str,
    evidence: ResearchDatasetEvidence,
    trials: list[tuple[str, int]],
    folds: list[dict[str, int | str]],
    started_at: datetime,
) -> list[AccessEvent]:
    events: list[AccessEvent] = []
    identity_hash = _projection_hash(evidence.dataset_sha256, "forecast_identity")
    actual_hash = _projection_hash(evidence.dataset_sha256, "actuals")

    def occurred() -> datetime:
        return started_at + timedelta(microseconds=len(events) + 1)

    raw_event_id = _event_id("read", run_id, evidence.dataset_sha256)
    events.append(
        AccessEvent(
            event_id=raw_event_id,
            run_id=run_id,
            sequence_no=1,
            stage=Stage.TRAIN,
            operation=AccessOperation.READ,
            occurred_at=occurred(),
            actor="loto.orchestration.research.adapter",
            input_slices=[
                _slice(
                    evidence,
                    dataset_id=evidence.dataset_id,
                    dataset_sha256=evidence.dataset_sha256,
                    data_role=DataRole.RAW,
                    row_start=0,
                    row_end=len(evidence.observed_times) - 1,
                    forecast_origin=evidence.observed_times[-1],
                    contains_targets=True,
                    contains_actuals=False,
                )
            ],
            parent_event_ids=[],
            actuals_known=True,
            notes="Canonical research input reconciled before delegated execution.",
        )
    )

    for model_id, seed in trials:
        for fold in folds:
            outer_id = str(fold["fold_id"])
            test_start = int(fold["test_start"])
            test_end = int(fold["test_end"])
            for draw_index in range(test_start, test_end):
                if draw_index >= len(evidence.observed_times):
                    raise ResearchLedgerBlocked(f"fold row exceeds canonical dataset: {draw_index}")
                forecast_origin = evidence.observed_times[draw_index]
                draw_id = evidence.draw_ids[draw_index]
                fold_id = f"{outer_id}/draw-{draw_index}"
                train_slice = _slice(
                    evidence,
                    dataset_id=evidence.dataset_id,
                    dataset_sha256=evidence.dataset_sha256,
                    data_role=DataRole.TRAIN,
                    row_start=0,
                    row_end=draw_index - 1,
                    forecast_origin=forecast_origin,
                    contains_targets=True,
                    contains_actuals=False,
                    fold_id=fold_id,
                    fold_role=FoldRole.TRAIN,
                )
                fit_id = _event_id("fit", run_id, model_id, seed, fold_id, evidence.dataset_sha256)
                events.append(
                    AccessEvent(
                        event_id=fit_id,
                        run_id=run_id,
                        sequence_no=len(events) + 1,
                        stage=Stage.OOF,
                        operation=AccessOperation.FIT_MODEL,
                        occurred_at=occurred(),
                        actor=f"loto.orchestration.research:{model_id}",
                        input_slices=[train_slice],
                        parent_event_ids=[raw_event_id],
                        forecast_origin=forecast_origin,
                        fold_id=fold_id,
                        seed=seed,
                        actuals_known=True,
                        notes="Reconciled walk-forward model fit for a successful trial.",
                    )
                )
                identity_slice = _slice(
                    evidence,
                    dataset_id=f"{evidence.dataset_id}:forecast-identity",
                    dataset_sha256=identity_hash,
                    data_role=DataRole.VALIDATION,
                    row_start=draw_index,
                    row_end=draw_index,
                    forecast_origin=forecast_origin,
                    contains_targets=False,
                    contains_actuals=False,
                    fold_id=fold_id,
                    fold_role=FoldRole.VALIDATION,
                    draw_id=draw_id,
                )
                predict_id = _event_id("predict", run_id, model_id, seed, fold_id, draw_id)
                events.append(
                    AccessEvent(
                        event_id=predict_id,
                        run_id=run_id,
                        sequence_no=len(events) + 1,
                        stage=Stage.OOF,
                        operation=AccessOperation.PREDICT,
                        occurred_at=occurred(),
                        actor=f"loto.orchestration.research:{model_id}",
                        input_slices=[identity_slice],
                        parent_event_ids=[fit_id],
                        forecast_origin=forecast_origin,
                        fold_id=fold_id,
                        seed=seed,
                        actuals_known=False,
                        notes="Prediction identity excludes actual target values.",
                    )
                )
                actual_slice = _slice(
                    evidence,
                    dataset_id=f"{evidence.dataset_id}:actuals",
                    dataset_sha256=actual_hash,
                    data_role=DataRole.ACTUALS,
                    row_start=draw_index,
                    row_end=draw_index,
                    forecast_origin=forecast_origin,
                    contains_targets=True,
                    contains_actuals=True,
                    fold_id=fold_id,
                    fold_role=FoldRole.VALIDATION,
                    draw_id=draw_id,
                )
                events.append(
                    AccessEvent(
                        event_id=_event_id("actual", run_id, model_id, seed, fold_id, draw_id),
                        run_id=run_id,
                        sequence_no=len(events) + 1,
                        stage=Stage.OOF,
                        operation=AccessOperation.READ_ACTUALS,
                        occurred_at=occurred(),
                        actor=f"loto.orchestration.research:{model_id}",
                        input_slices=[actual_slice],
                        parent_event_ids=[predict_id],
                        forecast_origin=forecast_origin,
                        fold_id=fold_id,
                        seed=seed,
                        actuals_known=True,
                        notes="Actual access reconciled after the corresponding prediction.",
                    )
                )
    return events


def _write_preflight_report(
    *,
    output: Path,
    run_id: str,
    gaps: list[str],
) -> None:
    report = ResearchLedgerAdapterReport(
        status=AccessDecision.BLOCKED,
        run_id=run_id,
        coverage_gaps=gaps,
    )
    _atomic_write_json(
        output / "data_access_adapter_report.json",
        report.model_dump(mode="json"),
    )


def run_research_experiment_with_ledger(
    config: Any,
    *,
    runner: Runner | None = None,
    evidence_loader: EvidenceLoader | None = None,
    clock: Clock | None = None,
) -> dict[str, Any]:
    """Run the existing research orchestrator through a fail-closed audit adapter.

    This adapter intentionally does not modify or monkeypatch ``research.py``. It
    admits only the lane that can be reconciled from immutable input and output
    artifacts without tuning, resume reads, or MLflow writes occurring before the
    post-run ledger validation gate.
    """

    output = _absolute_path(Path(str(_getattr_path(config, "runtime.output"))))
    _assert_safe_output(output)
    run_id = f"research-ledger-{hashlib.sha256(str(output).encode()).hexdigest()[:12]}"
    gaps = _preflight_gaps(config)
    if gaps:
        _write_preflight_report(output=output, run_id=run_id, gaps=gaps)
        raise ResearchLedgerPreflightError("research ledger preflight blocked: " + ", ".join(gaps))

    source = _absolute_path(Path(str(_getattr_path(config, "data.input"))))
    _assert_regular_file(source, label="research input")
    source_before = _file_sha256(source)
    loader = evidence_loader or _default_evidence_loader
    evidence = loader(config)
    started_at = _utc((clock or (lambda: datetime.now(UTC)))())
    delegated_runner = runner or _default_runner
    summary = delegated_runner(config)
    source_after = _file_sha256(source)

    actual_run_id = str(summary.get("run_id") or run_id)
    coverage_gaps: list[str] = []
    if source_before != source_after:
        coverage_gaps.append("INPUT_CHANGED_DURING_RUN")
    if summary.get("data_version") != evidence.data_version:
        coverage_gaps.append("SUMMARY_DATA_VERSION_MISMATCH")
    if int(summary.get("failed_trials", 0)):
        coverage_gaps.append("FAILED_TRIAL_ACCESS_NOT_FULLY_RECONCILED")
    if int(summary.get("skipped_trials", 0)):
        coverage_gaps.append("SKIPPED_TRIAL_ACCESS_NOT_FULLY_RECONCILED")

    trials = _load_successful_trials(output)
    if len(trials) != int(summary.get("successful_trials", 0)):
        coverage_gaps.append("SUCCESSFUL_TRIAL_ARTIFACT_COUNT_MISMATCH")
    folds = _normalize_folds(summary)
    if not folds:
        coverage_gaps.append("OUTER_FOLD_EVIDENCE_MISSING")

    events = _build_events(
        run_id=actual_run_id,
        evidence=evidence,
        trials=trials,
        folds=folds,
        started_at=started_at,
    )
    expected_seeds = sorted({seed for _, seed in trials})
    ledger = build_ledger(
        run_id=actual_run_id,
        created_at=started_at,
        events=events,
        expected_seeds=expected_seeds,
    )
    validation = validate_ledger(ledger)
    ledger_path = output / "data_access_ledger.json"
    validation_path = output / "data_access_validation.json"
    _atomic_write_json(ledger_path, ledger.model_dump(mode="json"))
    _atomic_write_json(validation_path, validation.model_dump(mode="json"))

    status = (
        AccessDecision.PASS
        if validation.status is AccessDecision.PASS and not coverage_gaps
        else AccessDecision.BLOCKED
    )
    adapter_report = ResearchLedgerAdapterReport(
        status=status,
        run_id=actual_run_id,
        ledger_path=str(ledger_path),
        validation_path=str(validation_path),
        ledger_sha256=ledger.ledger_sha256,
        source_file_sha256_before=source_before,
        source_file_sha256_after=source_after,
        coverage_gaps=coverage_gaps,
        verified_events=validation.verified_event_count,
    )
    adapter_report_path = output / "data_access_adapter_report.json"
    _atomic_write_json(
        adapter_report_path,
        adapter_report.model_dump(mode="json"),
    )

    summary = dict(summary)
    summary["data_access_ledger"] = str(ledger_path)
    summary["data_access_validation"] = str(validation_path)
    summary["data_access_adapter_report"] = str(adapter_report_path)
    summary["data_access_status"] = status.value
    summary["data_access_ledger_sha256"] = ledger.ledger_sha256
    _atomic_write_json(output / "research_summary.json", summary)

    if status is not AccessDecision.PASS:
        details = [*coverage_gaps]
        details.extend(item.code.value for item in validation.findings)
        raise ResearchLedgerBlocked(
            "research ledger validation blocked downstream use: " + ", ".join(sorted(set(details)))
        )
    return summary


__all__ = [
    "ResearchDatasetEvidence",
    "ResearchLedgerAdapterReport",
    "ResearchLedgerBlocked",
    "ResearchLedgerError",
    "ResearchLedgerPreflightError",
    "run_research_experiment_with_ledger",
]
