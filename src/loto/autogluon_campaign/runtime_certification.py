from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Sequence

from pydantic import ValidationError

from loto.adapters.autogluon.contracts import ProviderResponseV2


class CertificationStatus(StrEnum):
    VERIFIED = "VERIFIED"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    BLOCKED_RUNTIME = "BLOCKED_RUNTIME"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class CertificationScenario:
    scenario_id: str
    operation: str
    execution_mode: str
    model_ids: tuple[str, ...]
    artifact_key: str
    requested_device: str = "cpu"
    presets: str | None = None
    hyperparameters: dict[str, Any] | None = None
    hyperparameter_tune_kwargs: dict[str, Any] | None = None
    enable_ensemble: bool = False
    time_limit_seconds: int = 120
    environment: dict[str, str] = field(default_factory=dict)
    depends_on: str | None = None


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    scenario_id: str
    status: str
    return_code: int | None
    request_path: str
    response_path: str
    stdout_path: str
    stderr_path: str
    request_sha256: str
    response_sha256: str | None
    response_status: str | None
    prediction_count: int | None
    finite: bool | None
    runtime_evidence: dict[str, Any] | None
    errors: tuple[str, ...]
    started_at: str
    finished_at: str


@dataclass(frozen=True, slots=True)
class RuntimeCertificationReport:
    schema_version: int
    run_id: str
    status: CertificationStatus
    started_at: str
    finished_at: str
    repo_root: str
    output_dir: str
    provider_command: tuple[str, ...]
    python_version: str
    platform: str
    scenario_count: int
    verified_count: int
    failed_count: int
    blocked_count: int
    scenarios: tuple[ScenarioResult, ...]
    report_sha256: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload


@dataclass(frozen=True, slots=True)
class RuntimeCertificationConfig:
    repo_root: Path
    output_dir: Path
    provider_command: tuple[str, ...]
    timeout_seconds: int = 900
    scenario_ids: tuple[str, ...] = ()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _prepare_output_directory(path: Path) -> Path:
    resolved = path.resolve()
    if resolved.exists():
        if not resolved.is_dir():
            raise ValueError(f"output_dir must be a directory: {resolved}")
        if any(resolved.iterdir()):
            raise ValueError(
                "output_dir must be absent or empty to prevent stale certification evidence: "
                f"{resolved}"
            )
    else:
        resolved.mkdir(parents=True, exist_ok=False)
    return resolved


def _path_is_within(path: Path, directory: Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
    except ValueError:
        return False
    return True


def _history(rows: int = 24) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    for index in range(rows):
        offset = index % 3
        history.append(
            {
                "draw_no": index + 1,
                "draw_date": f"2026-01-{index + 1:02d}",
                "n1": 1 + offset,
                "n2": 4 + offset,
                "n3": 7 + offset,
            }
        )
    return history


def default_scenarios() -> tuple[CertificationScenario, ...]:
    return (
        CertificationScenario(
            scenario_id="explicit-naive-fit",
            operation="fit_predict_save",
            execution_mode="explicit_single_model",
            model_ids=("Naive",),
            artifact_key="naive",
        ),
        CertificationScenario(
            scenario_id="explicit-naive-load",
            operation="load_predict",
            execution_mode="explicit_single_model",
            model_ids=("Naive",),
            artifact_key="naive",
            depends_on="explicit-naive-fit",
        ),
        CertificationScenario(
            scenario_id="explicit-theta-fit",
            operation="fit_predict_save",
            execution_mode="explicit_single_model",
            model_ids=("Theta",),
            artifact_key="theta",
        ),
        CertificationScenario(
            scenario_id="preset-fast-training",
            operation="fit_predict_save",
            execution_mode="preset_automl",
            model_ids=(),
            artifact_key="preset-fast",
            presets="fast_training",
            enable_ensemble=True,
        ),
        CertificationScenario(
            scenario_id="multi-naive-theta",
            operation="fit_predict_save",
            execution_mode="explicit_multi_model",
            model_ids=("Naive", "Theta"),
            artifact_key="multi-naive-theta",
            hyperparameters={"Naive": {}, "Theta": {}},
            enable_ensemble=True,
        ),
        CertificationScenario(
            scenario_id="hpo-seasonal-naive",
            operation="fit_predict_save",
            execution_mode="hpo_single_model",
            model_ids=("SeasonalNaive",),
            artifact_key="hpo-seasonal-naive",
            hyperparameters={
                "SeasonalNaive": {
                    "seasonal_period": {
                        "__space__": "categorical",
                        "choices": [1, 2],
                    }
                }
            },
            hyperparameter_tune_kwargs={
                "num_trials": 2,
                "scheduler": "local",
                "searcher": "auto",
            },
            time_limit_seconds=180,
        ),
        CertificationScenario(
            scenario_id="forced-cpu-fallback",
            operation="fit_predict_save",
            execution_mode="explicit_single_model",
            model_ids=("Naive",),
            artifact_key="forced-cpu-fallback",
            requested_device="cuda",
            environment={"CUDA_VISIBLE_DEVICES": ""},
        ),
    )


def _request_payload(
    scenario: CertificationScenario,
    *,
    run_id: str,
    artifact_dir: Path,
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "provider_version": 2,
        "run_id": f"{run_id}-{scenario.scenario_id}",
        "operation": scenario.operation,
        "execution_mode": scenario.execution_mode,
        "model_ids": list(scenario.model_ids),
        "artifact_dir": str(artifact_dir),
        "history": _history(),
        "geometry": {
            "game_id": "numbers3-certification",
            "position_columns": ["n1", "n2", "n3"],
            "candidate_min": 0,
            "candidate_max": 9,
            "selection_count": 3,
            "horizon": 1,
            "allow_duplicates": False,
            "sort_policy": "ascending",
        },
        "predictor": {
            "target": "target",
            "prediction_length": 1,
            "freq": "D",
            "eval_metric": "MAE",
            "quantile_levels": [0.1, 0.5, 0.9],
            "cache_predictions": True,
        },
        "fit": {
            "time_limit_seconds": scenario.time_limit_seconds,
            "presets": scenario.presets,
            "hyperparameters": scenario.hyperparameters,
            "hyperparameter_tune_kwargs": scenario.hyperparameter_tune_kwargs,
            "num_val_windows": 1,
            "refit_every_n_windows": 1,
            "refit_full": False,
            "enable_ensemble": scenario.enable_ensemble,
            "skip_model_selection": False,
        },
        "seed": 1,
        "requested_device": scenario.requested_device,
    }


def _validate_response(
    scenario: CertificationScenario,
    payload: dict[str, Any],
    *,
    artifact_dir: Path,
    expected_run_id: str,
) -> tuple[list[str], ProviderResponseV2 | None]:
    errors: list[str] = []
    try:
        response = ProviderResponseV2.model_validate(payload)
    except ValidationError as exc:
        return [f"response schema validation failed: {exc}"], None
    if response.run_id != expected_run_id:
        errors.append(
            f"response run_id mismatch: expected {expected_run_id}, got {response.run_id}"
        )
    if response.operation.value != scenario.operation:
        errors.append(
            f"response operation mismatch: expected {scenario.operation}, "
            f"got {response.operation.value}"
        )
    if response.status != "OK":
        errors.append(
            f"provider status is {response.status}: "
            f"{response.error.code if response.error else 'NO_ERROR_CODE'}"
        )
        return errors, response
    expected_count = 3
    if len(response.predictions) != expected_count:
        errors.append(
            f"prediction count mismatch: expected {expected_count}, got "
            f"{len(response.predictions)}"
        )
    if response.metadata.get("finite") is not True:
        errors.append("metadata.finite must be true")
    expected_models = list(scenario.model_ids)
    if response.metadata.get("selected_model_ids") != expected_models:
        errors.append(
            "selected_model_ids mismatch: "
            f"expected {expected_models}, got {response.metadata.get('selected_model_ids')}"
        )
    evidence = response.runtime_evidence
    if evidence is None or evidence.pid is None or evidence.pid <= 0:
        errors.append("runtime evidence must include a positive provider PID")
    if evidence is not None and evidence.requested_device.value != scenario.requested_device:
        errors.append(
            "runtime requested_device mismatch: "
            f"expected {scenario.requested_device}, got {evidence.requested_device.value}"
        )
    if scenario.requested_device == "cpu" and evidence is not None:
        if evidence.resolved_device != "cpu":
            errors.append("CPU scenario did not resolve to CPU")
        if evidence.cpu_fallback:
            errors.append("CPU scenario must not be marked as CPU fallback")
        if evidence.gpu_used:
            errors.append("CPU scenario must not report GPU use")
    if scenario.scenario_id == "forced-cpu-fallback":
        if evidence is None or not evidence.cpu_fallback:
            errors.append("forced CPU fallback was not recorded")
        if evidence is not None and evidence.resolved_device != "cpu":
            errors.append("forced CPU fallback did not resolve to CPU")
    if scenario.operation == "fit_predict_save" and not artifact_dir.exists():
        errors.append("fit scenario did not create artifact directory")
    for name in (
        "provider_context",
        "execution_plan",
        "timeline_mapping",
    ):
        path = response.artifacts.get(name)
        if path is None:
            errors.append(f"missing persisted artifact: {name}")
            continue
        artifact_path = Path(path)
        if not artifact_path.is_file():
            errors.append(f"missing persisted artifact: {name}")
            continue
        if not _path_is_within(artifact_path, artifact_dir):
            errors.append(
                f"persisted artifact escapes artifact_dir: {name}={artifact_path}"
            )
    return errors, response


def _scenario_status(return_code: int | None, errors: list[str]) -> str:
    if return_code is None:
        return CertificationStatus.BLOCKED_RUNTIME.value
    if return_code != 0 or errors:
        return CertificationStatus.FAILED.value
    return CertificationStatus.VERIFIED.value


def run_runtime_certification(
    config: RuntimeCertificationConfig,
) -> RuntimeCertificationReport:
    started = datetime.now(timezone.utc)
    run_id = started.strftime("autogluon-p5-%Y%m%dT%H%M%SZ")
    if not config.provider_command:
        raise ValueError("provider_command must not be empty")
    if config.timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    output_dir = _prepare_output_directory(config.output_dir)
    scenarios = default_scenarios()
    if config.scenario_ids:
        requested = set(config.scenario_ids)
        scenarios = tuple(item for item in scenarios if item.scenario_id in requested)
        missing = sorted(requested - {item.scenario_id for item in scenarios})
        if missing:
            raise ValueError(f"unknown scenario IDs: {missing}")

    results: list[ScenarioResult] = []
    artifact_root = output_dir / "model-artifacts"
    for scenario in scenarios:
        scenario_dir = output_dir / "scenarios" / scenario.scenario_id
        scenario_dir.mkdir(parents=True, exist_ok=True)
        artifact_dir = artifact_root / scenario.artifact_key
        request_path = scenario_dir / "request.json"
        response_path = scenario_dir / "response.json"
        stdout_path = scenario_dir / "stdout.log"
        stderr_path = scenario_dir / "stderr.log"
        payload = _request_payload(
            scenario,
            run_id=run_id,
            artifact_dir=artifact_dir,
        )
        _write_json_atomic(request_path, payload)
        if scenario.depends_on is not None:
            dependency = next(
                (item for item in results if item.scenario_id == scenario.depends_on),
                None,
            )
            if dependency is None or dependency.status != CertificationStatus.VERIFIED.value:
                now = datetime.now(timezone.utc).isoformat()
                message = f"scenario dependency not verified: {scenario.depends_on}"
                stdout_path.write_text("", encoding="utf-8")
                stderr_path.write_text(message + "\n", encoding="utf-8")
                results.append(
                    ScenarioResult(
                        scenario_id=scenario.scenario_id,
                        status=CertificationStatus.BLOCKED_RUNTIME.value,
                        return_code=None,
                        request_path=str(request_path),
                        response_path=str(response_path),
                        stdout_path=str(stdout_path),
                        stderr_path=str(stderr_path),
                        request_sha256=_sha256_file(request_path),
                        response_sha256=None,
                        response_status=None,
                        prediction_count=None,
                        finite=None,
                        runtime_evidence=None,
                        errors=(message,),
                        started_at=now,
                        finished_at=now,
                    )
                )
                continue
        command = [
            *config.provider_command,
            "--request",
            str(request_path),
            "--response",
            str(response_path),
        ]
        environment = os.environ.copy()
        environment.update(scenario.environment)
        scenario_started = datetime.now(timezone.utc)
        return_code: int | None = None
        errors: list[str] = []
        response_payload: dict[str, Any] | None = None
        try:
            completed = subprocess.run(
                command,
                cwd=config.repo_root,
                env=environment,
                capture_output=True,
                text=True,
                timeout=config.timeout_seconds,
                check=False,
            )
            return_code = completed.returncode
            stdout_path.write_text(completed.stdout, encoding="utf-8")
            stderr_path.write_text(completed.stderr, encoding="utf-8")
            if not response_path.is_file():
                errors.append("provider did not create response JSON")
            else:
                response_payload = json.loads(response_path.read_text(encoding="utf-8"))
                validation_errors, _response = _validate_response(
                    scenario,
                    response_payload,
                    artifact_dir=artifact_dir,
                    expected_run_id=payload["run_id"],
                )
                errors.extend(validation_errors)
            if return_code != 0:
                errors.append(f"provider command exited with code {return_code}")
        except FileNotFoundError as exc:
            errors.append(f"runtime command not found: {exc}")
            stdout_path.write_text("", encoding="utf-8")
            stderr_path.write_text(str(exc) + "\n", encoding="utf-8")
        except subprocess.TimeoutExpired as exc:
            return_code = 124
            errors.append(f"provider timed out after {config.timeout_seconds} seconds")
            stdout_path.write_text(exc.stdout or "", encoding="utf-8")
            stderr_path.write_text(exc.stderr or "", encoding="utf-8")
        except Exception as exc:
            return_code = 125
            errors.append(f"certification harness failed: {type(exc).__name__}: {exc}")
            stdout_path.write_text("", encoding="utf-8")
            stderr_path.write_text(str(exc) + "\n", encoding="utf-8")

        response_hash = _sha256_file(response_path) if response_path.is_file() else None
        response_status = response_payload.get("status") if response_payload else None
        predictions = response_payload.get("predictions") if response_payload else None
        metadata = response_payload.get("metadata") if response_payload else None
        scenario_finished = datetime.now(timezone.utc)
        results.append(
            ScenarioResult(
                scenario_id=scenario.scenario_id,
                status=_scenario_status(return_code, errors),
                return_code=return_code,
                request_path=str(request_path),
                response_path=str(response_path),
                stdout_path=str(stdout_path),
                stderr_path=str(stderr_path),
                request_sha256=_sha256_file(request_path),
                response_sha256=response_hash,
                response_status=response_status,
                prediction_count=len(predictions) if isinstance(predictions, list) else None,
                finite=metadata.get("finite") if isinstance(metadata, dict) else None,
                runtime_evidence=(
                    response_payload.get("runtime_evidence") if response_payload else None
                ),
                errors=tuple(errors),
                started_at=scenario_started.isoformat(),
                finished_at=scenario_finished.isoformat(),
            )
        )

    verified_count = sum(item.status == CertificationStatus.VERIFIED for item in results)
    blocked_count = sum(item.status == CertificationStatus.BLOCKED_RUNTIME for item in results)
    failed_count = len(results) - verified_count - blocked_count
    if verified_count == len(results) and results:
        status = CertificationStatus.VERIFIED
    elif blocked_count == len(results) and results:
        status = CertificationStatus.BLOCKED_RUNTIME
    elif verified_count > 0:
        status = CertificationStatus.PARTIALLY_VERIFIED
    else:
        status = CertificationStatus.FAILED

    finished = datetime.now(timezone.utc)
    report_without_hash = {
        "schema_version": 1,
        "run_id": run_id,
        "status": status.value,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "repo_root": str(config.repo_root.resolve()),
        "output_dir": str(output_dir),
        "provider_command": list(config.provider_command),
        "python_version": sys.version,
        "platform": platform.platform(),
        "scenario_count": len(results),
        "verified_count": verified_count,
        "failed_count": failed_count,
        "blocked_count": blocked_count,
        "scenarios": [asdict(item) for item in results],
    }
    report_hash = _sha256_bytes(_canonical_json(report_without_hash))
    report = RuntimeCertificationReport(
        schema_version=1,
        run_id=run_id,
        status=status,
        started_at=started.isoformat(),
        finished_at=finished.isoformat(),
        repo_root=str(config.repo_root.resolve()),
        output_dir=str(output_dir),
        provider_command=config.provider_command,
        python_version=sys.version,
        platform=platform.platform(),
        scenario_count=len(results),
        verified_count=verified_count,
        failed_count=failed_count,
        blocked_count=blocked_count,
        scenarios=tuple(results),
        report_sha256=report_hash,
    )
    report_path = output_dir / "RUNTIME_CERTIFICATION_REPORT.json"
    _write_json_atomic(report_path, report.to_dict())
    sums = [
        f"{_sha256_file(path)}  {path.relative_to(output_dir)}"
        for path in sorted(output_dir.rglob("*"))
        if path.is_file() and path.name != "SHA256SUMS"
    ]
    (output_dir / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    return report


def _default_provider_command(repo_root: Path) -> tuple[str, ...]:
    return (
        "uv",
        "run",
        "--project",
        str(repo_root / "environments" / "autogluon-timeseries"),
        "--locked",
        "python",
        str(repo_root / "scripts" / "run_autogluon_timeseries_provider.py"),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run AutoGluon TimeSeries protocol-v2 runtime certification."
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--scenario", action="append", default=[])
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = args.repo_root.resolve()
    report = run_runtime_certification(
        RuntimeCertificationConfig(
            repo_root=repo_root,
            output_dir=args.output_dir,
            provider_command=_default_provider_command(repo_root),
            timeout_seconds=args.timeout_seconds,
            scenario_ids=tuple(args.scenario),
        )
    )
    print(f"AUTOGLUON_P5_STATUS={report.status.value}")
    print(f"AUTOGLUON_P5_RUN_ID={report.run_id}")
    print(f"AUTOGLUON_P5_SCENARIOS={report.scenario_count}")
    print(f"AUTOGLUON_P5_VERIFIED={report.verified_count}")
    print(f"AUTOGLUON_P5_FAILED={report.failed_count}")
    print(f"AUTOGLUON_P5_BLOCKED={report.blocked_count}")
    print(f"AUTOGLUON_P5_REPORT_SHA256={report.report_sha256}")
    print(f"AUTOGLUON_P5_OUTPUT={report.output_dir}")
    if report.status is CertificationStatus.VERIFIED:
        return 0
    if report.status is CertificationStatus.PARTIALLY_VERIFIED:
        return 1
    if report.status is CertificationStatus.BLOCKED_RUNTIME:
        return 2
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
