from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Sequence

from loto.adapters.autogluon.covariate_capabilities import (
    CovariateRole,
    model_capability_inventory,
)


class CovariateCertificationStatus(StrEnum):
    VERIFIED = "VERIFIED"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    BLOCKED_RUNTIME = "BLOCKED_RUNTIME"
    FAILED = "FAILED"


_RUNTIME_BLOCK_CODES = frozenset(
    {
        "RUNTIME_IMPORT_FAILED",
        "RUNTIME_VERSION_MISMATCH",
        "PACKAGE_MISSING",
        "OPTIONAL_DEPENDENCY_MISSING",
        "LICENSE_RESTRICTED",
    }
)


@dataclass(frozen=True, slots=True)
class CovariateCertificationScenario:
    scenario_id: str
    operation: str
    model_ids: tuple[str, ...]
    roles: tuple[CovariateRole, ...]
    routes: tuple[str, ...]
    artifact_key: str
    regressor: str | None = None
    depends_on: str | None = None
    time_limit_seconds: int = 180


@dataclass(frozen=True, slots=True)
class CovariateScenarioResult:
    scenario_id: str
    status: str
    return_code: int | None
    request_path: str
    response_path: str
    stdout_path: str
    stderr_path: str
    request_sha256: str
    response_sha256: str | None
    prediction_sha256: str | None
    capability_sha256: str | None
    provider_error_code: str | None
    errors: tuple[str, ...]
    started_at: str
    finished_at: str


@dataclass(frozen=True, slots=True)
class CovariateCertificationReport:
    schema_version: int
    run_id: str
    profile: str
    status: CovariateCertificationStatus
    started_at: str
    finished_at: str
    repo_root: str
    output_dir: str
    provider_command: tuple[str, ...]
    scenario_count: int
    verified_count: int
    blocked_count: int
    failed_count: int
    python_version: str
    platform: str
    scenarios: tuple[CovariateScenarioResult, ...]
    report_sha256: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload


@dataclass(frozen=True, slots=True)
class CovariateCertificationConfig:
    repo_root: Path
    output_dir: Path
    provider_command: tuple[str, ...]
    profile: str = "smoke"
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
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
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


def _slug(value: str) -> str:
    return "".join(character.lower() if character.isalnum() else "-" for character in value)


def smoke_scenarios() -> tuple[CovariateCertificationScenario, ...]:
    return (
        CovariateCertificationScenario(
            scenario_id="native-tft-all-fit",
            operation="fit_predict_save",
            model_ids=("TemporalFusionTransformer",),
            roles=(CovariateRole.KNOWN, CovariateRole.PAST, CovariateRole.STATIC),
            routes=("native", "native", "native"),
            artifact_key="native-tft-all",
        ),
        CovariateCertificationScenario(
            scenario_id="native-tft-all-load",
            operation="load_predict",
            model_ids=("TemporalFusionTransformer",),
            roles=(CovariateRole.KNOWN, CovariateRole.PAST, CovariateRole.STATIC),
            routes=("native", "native", "native"),
            artifact_key="native-tft-all",
            depends_on="native-tft-all-fit",
        ),
        CovariateCertificationScenario(
            scenario_id="native-deepar-known-static-fit",
            operation="fit_predict_save",
            model_ids=("DeepAR",),
            roles=(CovariateRole.KNOWN, CovariateRole.STATIC),
            routes=("native", "native"),
            artifact_key="native-deepar-known-static",
        ),
        CovariateCertificationScenario(
            scenario_id="regressor-naive-known-static-fit",
            operation="fit_predict_save",
            model_ids=("Naive",),
            roles=(CovariateRole.KNOWN, CovariateRole.STATIC),
            routes=("covariate_regressor", "covariate_regressor"),
            artifact_key="regressor-naive-known-static",
            regressor="LR",
        ),
        CovariateCertificationScenario(
            scenario_id="regressor-naive-known-static-load",
            operation="load_predict",
            model_ids=("Naive",),
            roles=(CovariateRole.KNOWN, CovariateRole.STATIC),
            routes=("covariate_regressor", "covariate_regressor"),
            artifact_key="regressor-naive-known-static",
            regressor="LR",
            depends_on="regressor-naive-known-static-fit",
        ),
        CovariateCertificationScenario(
            scenario_id="native-multi-deepar-tide-known-static-fit",
            operation="fit_predict_save",
            model_ids=("DeepAR", "TiDE"),
            roles=(CovariateRole.KNOWN, CovariateRole.STATIC),
            routes=("native", "native", "native", "native"),
            artifact_key="native-multi-deepar-tide-known-static",
        ),
    )


def full_scenarios() -> tuple[CovariateCertificationScenario, ...]:
    scenarios: list[CovariateCertificationScenario] = []
    for capability in model_capability_inventory():
        model = capability.model_id
        slug = _slug(model)
        known_route = "native" if capability.native_known else "covariate_regressor"
        scenarios.append(
            CovariateCertificationScenario(
                scenario_id=f"{slug}-known-{known_route}-fit",
                operation="fit_predict_save",
                model_ids=(model,),
                roles=(CovariateRole.KNOWN,),
                routes=(known_route,),
                artifact_key=f"{slug}-known-{known_route}",
                regressor=None if known_route == "native" else "LR",
            )
        )
        if capability.native_past:
            scenarios.append(
                CovariateCertificationScenario(
                    scenario_id=f"{slug}-past-native-fit",
                    operation="fit_predict_save",
                    model_ids=(model,),
                    roles=(CovariateRole.PAST,),
                    routes=("native",),
                    artifact_key=f"{slug}-past-native",
                )
            )
        static_route = "native" if capability.native_static else "covariate_regressor"
        scenarios.append(
            CovariateCertificationScenario(
                scenario_id=f"{slug}-static-{static_route}-fit",
                operation="fit_predict_save",
                model_ids=(model,),
                roles=(CovariateRole.STATIC,),
                routes=(static_route,),
                artifact_key=f"{slug}-static-{static_route}",
                regressor=None if static_route == "native" else "LR",
            )
        )
    return tuple(scenarios)


def scenarios_for_profile(profile: str) -> tuple[CovariateCertificationScenario, ...]:
    if profile == "smoke":
        return smoke_scenarios()
    if profile == "full":
        return full_scenarios()
    raise ValueError("profile must be 'smoke' or 'full'")


def _history(rows: int = 48) -> list[dict[str, Any]]:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    history: list[dict[str, Any]] = []
    for index in range(rows):
        offset = index % 3
        history.append(
            {
                "draw_no": index + 1,
                "draw_date": (start + timedelta(days=index)).date().isoformat(),
                "n1": 1 + offset,
                "n2": 4 + offset,
                "n3": 7 + offset,
                "holiday": index % 2,
                "rain": float((index * 3) % 7),
            }
        )
    return history


def _model_hyperparameters(
    scenario: CovariateCertificationScenario,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for model_id in scenario.model_ids:
        config: dict[str, Any] = {}
        if scenario.regressor is not None:
            config["covariate_regressor"] = scenario.regressor
        result[model_id] = config
    return result


def request_payload(
    scenario: CovariateCertificationScenario,
    *,
    run_id: str,
    artifact_dir: Path,
) -> dict[str, Any]:
    role_set = set(scenario.roles)
    known = CovariateRole.KNOWN in role_set
    past = CovariateRole.PAST in role_set
    static = CovariateRole.STATIC in role_set
    return {
        "schema_version": 2,
        "provider_version": 2,
        "run_id": f"{run_id}-{scenario.scenario_id}",
        "operation": scenario.operation,
        "execution_mode": (
            "explicit_multi_model" if len(scenario.model_ids) > 1 else "explicit_single_model"
        ),
        "model_ids": list(scenario.model_ids),
        "artifact_dir": str(artifact_dir),
        "history": _history(),
        "geometry": {
            "game_id": "numbers3-covariate-certification",
            "position_columns": ["n1", "n2", "n3"],
            "candidate_min": 0,
            "candidate_max": 9,
            "selection_count": 3,
            "horizon": 2,
            "allow_duplicates": False,
            "sort_policy": "ascending",
        },
        "predictor": {
            "target": "target",
            "known_covariates_names": ["holiday"] if known else [],
            "prediction_length": 2,
            "freq": "D",
            "eval_metric": "MAE",
            "quantile_levels": [0.1, 0.5, 0.9],
            "cache_predictions": True,
        },
        "fit": {
            "time_limit_seconds": scenario.time_limit_seconds,
            "hyperparameters": _model_hyperparameters(scenario),
            "num_val_windows": 1,
            "refit_every_n_windows": 1,
            "refit_full": False,
            "enable_ensemble": len(scenario.model_ids) > 1,
            "skip_model_selection": False,
        },
        "covariates": {
            "past_covariates_names": ["rain"] if past else [],
            "static_feature_names": ["position_group"] if static else [],
            "future_known_covariates": (
                [
                    {"horizon_step": 1, "holiday": 0},
                    {"horizon_step": 2, "holiday": 1},
                ]
                if known
                else []
            ),
            "static_features": (
                [
                    {"item_id": "position-1", "position_group": "low"},
                    {"item_id": "position-2", "position_group": "mid"},
                    {"item_id": "position-3", "position_group": "high"},
                ]
                if static
                else []
            ),
        },
        "seed": 1,
        "requested_device": "cpu",
    }


def _expected_model_roles(
    scenario: CovariateCertificationScenario,
) -> list[dict[str, Any]]:
    expected: list[dict[str, Any]] = []
    route_index = 0
    for model_id in scenario.model_ids:
        for role in scenario.roles:
            expected.append(
                {
                    "model_id": model_id,
                    "role": role.value,
                    "route": scenario.routes[route_index],
                    "covariate_regressor": scenario.regressor,
                }
            )
            route_index += 1
    return expected


def validate_response(
    scenario: CovariateCertificationScenario,
    payload: dict[str, Any],
    *,
    artifact_dir: Path,
    expected_run_id: str,
    expected_prediction_sha256: str | None = None,
) -> tuple[list[str], str | None, str | None, str | None]:
    errors: list[str] = []
    status = payload.get("status")
    error = payload.get("error")
    error_code = error.get("code") if isinstance(error, dict) else None
    if status != "OK":
        return errors, None, None, error_code
    if payload.get("run_id") != expected_run_id:
        errors.append("response run_id does not match the request")
    if payload.get("operation") != scenario.operation:
        errors.append("response operation does not match the scenario")

    predictions = payload.get("predictions")
    if not isinstance(predictions, list) or len(predictions) != 6:
        errors.append("prediction count must equal selection_count * horizon = 6")
        prediction_hash = None
    else:
        prediction_hash = _sha256_bytes(_canonical_json(predictions))
        for row in predictions:
            if not isinstance(row, dict):
                errors.append("prediction row must be a JSON object")
                continue
            try:
                mean = float(row["mean"])
            except (KeyError, TypeError, ValueError):
                errors.append("prediction mean must be numeric")
                continue
            if not math.isfinite(mean):
                errors.append("prediction mean must be finite")
        if expected_prediction_sha256 is not None and prediction_hash != expected_prediction_sha256:
            errors.append("save/load prediction SHA-256 parity failed")

    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        errors.append("metadata must be a JSON object")
        metadata = {}
    if metadata.get("finite") is not True:
        errors.append("metadata.finite must be true")
    if metadata.get("selected_model_ids") != list(scenario.model_ids):
        errors.append("metadata.selected_model_ids mismatch")
    decision = metadata.get("covariate_capability_decision")
    capability_hash = metadata.get("covariate_capability_sha256")
    if not isinstance(decision, dict):
        errors.append("covariate capability decision is missing")
    else:
        if decision.get("selected_model_ids") != list(scenario.model_ids):
            errors.append("capability selected_model_ids mismatch")
        if decision.get("requested_roles") != [role.value for role in scenario.roles]:
            errors.append("capability requested_roles mismatch")
        if decision.get("model_roles") != _expected_model_roles(scenario):
            errors.append("capability model_roles mismatch")
        if decision.get("decision_sha256") != capability_hash:
            errors.append("capability decision SHA-256 metadata mismatch")

    evidence = payload.get("runtime_evidence")
    if not isinstance(evidence, dict):
        errors.append("runtime_evidence must be a JSON object")
    else:
        if not isinstance(evidence.get("pid"), int) or evidence["pid"] <= 0:
            errors.append("runtime_evidence.pid must be a positive integer")
        if evidence.get("resolved_device") != "cpu":
            errors.append("covariate CPU certification must resolve to CPU")
        if evidence.get("gpu_used") is not False:
            errors.append("covariate CPU certification must not report GPU use")

    artifacts = payload.get("artifacts")
    required = (
        "provider_context",
        "execution_plan",
        "timeline_mapping",
        "covariate_context",
        "covariate_capability_context",
    )
    if not isinstance(artifacts, dict):
        errors.append("artifacts must be a JSON object")
    else:
        for name in required:
            value = artifacts.get(name)
            if not isinstance(value, str):
                errors.append(f"missing persisted artifact: {name}")
                continue
            path = Path(value)
            if not path.is_file():
                errors.append(f"persisted artifact does not exist: {name}")
            elif not _path_is_within(path, artifact_dir):
                errors.append(f"persisted artifact escapes artifact_dir: {name}")
    return errors, prediction_hash, capability_hash, error_code


def _scenario_status(
    *,
    return_code: int | None,
    response_status: str | None,
    provider_error_code: str | None,
    errors: list[str],
) -> CovariateCertificationStatus:
    if return_code is None:
        return CovariateCertificationStatus.BLOCKED_RUNTIME
    if response_status == "ERROR" and provider_error_code in _RUNTIME_BLOCK_CODES:
        return CovariateCertificationStatus.BLOCKED_RUNTIME
    if return_code != 0 or response_status != "OK" or errors:
        return CovariateCertificationStatus.FAILED
    return CovariateCertificationStatus.VERIFIED


def _overall_status(
    results: Sequence[CovariateScenarioResult],
) -> CovariateCertificationStatus:
    if any(item.status == CovariateCertificationStatus.FAILED.value for item in results):
        return CovariateCertificationStatus.FAILED
    if results and all(
        item.status == CovariateCertificationStatus.VERIFIED.value for item in results
    ):
        return CovariateCertificationStatus.VERIFIED
    if results and all(
        item.status == CovariateCertificationStatus.BLOCKED_RUNTIME.value for item in results
    ):
        return CovariateCertificationStatus.BLOCKED_RUNTIME
    return CovariateCertificationStatus.PARTIALLY_VERIFIED


def run_covariate_runtime_certification(
    config: CovariateCertificationConfig,
) -> CovariateCertificationReport:
    if not config.provider_command:
        raise ValueError("provider_command must not be empty")
    if config.timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    started = datetime.now(timezone.utc)
    run_id = started.strftime("autogluon-p15-%Y%m%dT%H%M%SZ")
    output_dir = _prepare_output_directory(config.output_dir)
    scenarios = scenarios_for_profile(config.profile)
    if config.scenario_ids:
        requested = set(config.scenario_ids)
        scenarios = tuple(item for item in scenarios if item.scenario_id in requested)
        missing = sorted(requested - {item.scenario_id for item in scenarios})
        if missing:
            raise ValueError(f"unknown scenario IDs: {missing}")

    results: list[CovariateScenarioResult] = []
    artifact_root = output_dir / "model-artifacts"
    for scenario in scenarios:
        scenario_dir = output_dir / "scenarios" / scenario.scenario_id
        scenario_dir.mkdir(parents=True, exist_ok=True)
        artifact_dir = artifact_root / scenario.artifact_key
        request_path = scenario_dir / "request.json"
        response_path = scenario_dir / "response.json"
        stdout_path = scenario_dir / "stdout.log"
        stderr_path = scenario_dir / "stderr.log"
        payload = request_payload(scenario, run_id=run_id, artifact_dir=artifact_dir)
        _write_json_atomic(request_path, payload)
        dependency = None
        if scenario.depends_on is not None:
            dependency = next(
                (item for item in results if item.scenario_id == scenario.depends_on),
                None,
            )
            if dependency is None or dependency.status != CovariateCertificationStatus.VERIFIED:
                now = datetime.now(timezone.utc).isoformat()
                message = f"scenario dependency not verified: {scenario.depends_on}"
                stdout_path.write_text("", encoding="utf-8")
                stderr_path.write_text(message + "\n", encoding="utf-8")
                results.append(
                    CovariateScenarioResult(
                        scenario_id=scenario.scenario_id,
                        status=CovariateCertificationStatus.BLOCKED_RUNTIME.value,
                        return_code=None,
                        request_path=str(request_path),
                        response_path=str(response_path),
                        stdout_path=str(stdout_path),
                        stderr_path=str(stderr_path),
                        request_sha256=_sha256_file(request_path),
                        response_sha256=None,
                        prediction_sha256=None,
                        capability_sha256=None,
                        provider_error_code=None,
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
        scenario_started = datetime.now(timezone.utc)
        return_code: int | None = None
        errors: list[str] = []
        response_payload: dict[str, Any] | None = None
        prediction_hash: str | None = None
        capability_hash: str | None = None
        provider_error_code: str | None = None
        try:
            completed = subprocess.run(
                command,
                cwd=config.repo_root,
                env=os.environ.copy(),
                capture_output=True,
                text=True,
                timeout=config.timeout_seconds,
                check=False,
            )
            return_code = completed.returncode
            stdout_path.write_text(completed.stdout, encoding="utf-8")
            stderr_path.write_text(completed.stderr, encoding="utf-8")
            if response_path.is_file():
                response_payload = json.loads(response_path.read_text(encoding="utf-8"))
                expected_prediction_hash = (
                    dependency.prediction_sha256 if dependency is not None else None
                )
                validated = validate_response(
                    scenario,
                    response_payload,
                    artifact_dir=artifact_dir,
                    expected_run_id=payload["run_id"],
                    expected_prediction_sha256=expected_prediction_hash,
                )
                validation_errors, prediction_hash, capability_hash, provider_error_code = validated
                errors.extend(validation_errors)
            else:
                errors.append("provider did not create response JSON")
            if return_code != 0:
                errors.append(f"provider command exited with code {return_code}")
        except FileNotFoundError as exc:
            stdout_path.write_text("", encoding="utf-8")
            stderr_path.write_text(str(exc) + "\n", encoding="utf-8")
            errors.append(f"runtime command not found: {exc}")
        except subprocess.TimeoutExpired as exc:
            return_code = 124
            stdout_path.write_text(exc.stdout or "", encoding="utf-8")
            stderr_path.write_text(exc.stderr or "", encoding="utf-8")
            errors.append(f"provider timed out after {config.timeout_seconds} seconds")
        except Exception as exc:
            return_code = 125
            stdout_path.write_text("", encoding="utf-8")
            stderr_path.write_text(str(exc) + "\n", encoding="utf-8")
            errors.append(f"certification harness failed: {type(exc).__name__}: {exc}")

        response_status = response_payload.get("status") if response_payload else None
        status = _scenario_status(
            return_code=return_code,
            response_status=response_status,
            provider_error_code=provider_error_code,
            errors=errors,
        )
        scenario_finished = datetime.now(timezone.utc)
        results.append(
            CovariateScenarioResult(
                scenario_id=scenario.scenario_id,
                status=status.value,
                return_code=return_code,
                request_path=str(request_path),
                response_path=str(response_path),
                stdout_path=str(stdout_path),
                stderr_path=str(stderr_path),
                request_sha256=_sha256_file(request_path),
                response_sha256=(_sha256_file(response_path) if response_path.is_file() else None),
                prediction_sha256=prediction_hash,
                capability_sha256=capability_hash,
                provider_error_code=provider_error_code,
                errors=tuple(errors),
                started_at=scenario_started.isoformat(),
                finished_at=scenario_finished.isoformat(),
            )
        )

    status = _overall_status(results)
    verified_count = sum(
        item.status == CovariateCertificationStatus.VERIFIED.value for item in results
    )
    blocked_count = sum(
        item.status == CovariateCertificationStatus.BLOCKED_RUNTIME.value for item in results
    )
    failed_count = sum(item.status == CovariateCertificationStatus.FAILED.value for item in results)
    finished = datetime.now(timezone.utc)
    report_without_hash = {
        "schema_version": 1,
        "run_id": run_id,
        "profile": config.profile,
        "status": status.value,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "repo_root": str(config.repo_root.resolve()),
        "output_dir": str(output_dir),
        "provider_command": list(config.provider_command),
        "scenario_count": len(results),
        "verified_count": verified_count,
        "blocked_count": blocked_count,
        "failed_count": failed_count,
        "python_version": sys.version,
        "platform": platform.platform(),
        "scenarios": [asdict(item) for item in results],
    }
    report_hash = _sha256_bytes(_canonical_json(report_without_hash))
    report = CovariateCertificationReport(
        schema_version=1,
        run_id=run_id,
        profile=config.profile,
        status=status,
        started_at=started.isoformat(),
        finished_at=finished.isoformat(),
        repo_root=str(config.repo_root.resolve()),
        output_dir=str(output_dir),
        provider_command=config.provider_command,
        scenario_count=len(results),
        verified_count=verified_count,
        blocked_count=blocked_count,
        failed_count=failed_count,
        python_version=sys.version,
        platform=platform.platform(),
        scenarios=tuple(results),
        report_sha256=report_hash,
    )
    _write_json_atomic(
        output_dir / "COVARIATE_RUNTIME_CERTIFICATION_REPORT.json",
        report.to_dict(),
    )
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
        description="Run model-by-model AutoGluon covariate runtime certification."
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--profile", choices=("smoke", "full"), default="smoke")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--scenario", action="append", default=[])
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = args.repo_root.resolve()
    report = run_covariate_runtime_certification(
        CovariateCertificationConfig(
            repo_root=repo_root,
            output_dir=args.output_dir,
            provider_command=_default_provider_command(repo_root),
            profile=args.profile,
            timeout_seconds=args.timeout_seconds,
            scenario_ids=tuple(args.scenario),
        )
    )
    print(f"AUTOGLUON_P15_STATUS={report.status.value}")
    print(f"AUTOGLUON_P15_RUN_ID={report.run_id}")
    print(f"AUTOGLUON_P15_PROFILE={report.profile}")
    print(f"AUTOGLUON_P15_SCENARIOS={report.scenario_count}")
    print(f"AUTOGLUON_P15_VERIFIED={report.verified_count}")
    print(f"AUTOGLUON_P15_BLOCKED={report.blocked_count}")
    print(f"AUTOGLUON_P15_FAILED={report.failed_count}")
    print(f"AUTOGLUON_P15_REPORT_SHA256={report.report_sha256}")
    print(f"AUTOGLUON_P15_OUTPUT={report.output_dir}")
    return {
        CovariateCertificationStatus.VERIFIED: 0,
        CovariateCertificationStatus.PARTIALLY_VERIFIED: 1,
        CovariateCertificationStatus.BLOCKED_RUNTIME: 2,
        CovariateCertificationStatus.FAILED: 3,
    }[report.status]


if __name__ == "__main__":
    raise SystemExit(main())
