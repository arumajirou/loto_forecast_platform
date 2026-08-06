from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RuntimeScenario(StrictModel):
    scenario_id: str = Field(min_length=1)
    series_layout: str
    cross_learning: bool
    prediction_length: int = Field(gt=0)
    context_length: int = Field(gt=0)
    quantile_levels: tuple[float, ...]
    use_past_covariates: bool = False
    use_future_covariates: bool = False
    verify_covariate_perturbation: bool = False

    @model_validator(mode="after")
    def validate_layout(self) -> RuntimeScenario:
        allowed = {
            "position_local": False,
            "position_panel": True,
            "position_multivariate": False,
        }
        if self.series_layout not in allowed:
            raise ValueError("unsupported series layout")
        if self.cross_learning != allowed[self.series_layout]:
            raise ValueError("cross_learning does not match series layout")
        if self.use_future_covariates and not self.use_past_covariates:
            raise ValueError("future covariates require past covariates")
        if self.verify_covariate_perturbation and not self.use_past_covariates:
            raise ValueError("covariate perturbation requires covariates")
        return self


class RuntimeMatrixConfig(StrictModel):
    run_id: str = Field(min_length=1)
    scenarios: tuple[RuntimeScenario, ...] = Field(min_length=1)
    required_status: str = "OK"
    runtime_mode: Literal["real", "injected"] = "injected"

    @model_validator(mode="after")
    def validate_unique_scenarios(self) -> RuntimeMatrixConfig:
        ids = [scenario.scenario_id for scenario in self.scenarios]
        if len(ids) != len(set(ids)):
            raise ValueError("scenario_id values must be unique")
        return self


@dataclass(frozen=True)
class RuntimeMatrixResult:
    status: str
    rows: tuple[dict[str, Any], ...]
    report: dict[str, Any]
    evidence: tuple[dict[str, Any], ...]


Executor = Callable[[dict[str, Any]], dict[str, Any]]


def default_scenarios() -> tuple[RuntimeScenario, ...]:
    return (
        RuntimeScenario(
            scenario_id="z0-local-h1",
            series_layout="position_local",
            cross_learning=False,
            prediction_length=1,
            context_length=512,
            quantile_levels=(0.1, 0.5, 0.9),
        ),
        RuntimeScenario(
            scenario_id="z1-panel-cross-h1",
            series_layout="position_panel",
            cross_learning=True,
            prediction_length=1,
            context_length=512,
            quantile_levels=(0.1, 0.5, 0.9),
        ),
        RuntimeScenario(
            scenario_id="z2-multivariate-h5",
            series_layout="position_multivariate",
            cross_learning=False,
            prediction_length=5,
            context_length=1024,
            quantile_levels=(0.1, 0.5, 0.9),
        ),
        RuntimeScenario(
            scenario_id="z3-past-covariates-h2",
            series_layout="position_multivariate",
            cross_learning=False,
            prediction_length=2,
            context_length=512,
            quantile_levels=(0.1, 0.5, 0.9),
            use_past_covariates=True,
            verify_covariate_perturbation=True,
        ),
        RuntimeScenario(
            scenario_id="z4-known-future-h2",
            series_layout="position_multivariate",
            cross_learning=False,
            prediction_length=2,
            context_length=512,
            quantile_levels=(0.05, 0.1, 0.5, 0.9, 0.95),
            use_past_covariates=True,
            use_future_covariates=True,
            verify_covariate_perturbation=True,
        ),
    )


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _perturbed_request(
    request: dict[str, Any],
    scenario: RuntimeScenario,
) -> dict[str, Any]:
    perturbed = json.loads(json.dumps(request))
    if scenario.use_future_covariates:
        rows = perturbed.get("future_covariates", [])
    else:
        rows = perturbed.get("past_covariates", [])
    if not rows:
        raise ValueError("covariate perturbation requested without covariate rows")
    first_key = sorted(rows[0])[0]
    value = rows[0][first_key]
    if not isinstance(value, (int, float)):
        raise ValueError("covariate perturbation requires a numeric covariate")
    rows[0][first_key] = value + 1
    perturbed["run_id"] = f"{request['run_id']}-perturbed"
    return perturbed


def _scenario_request(base_request: dict[str, Any], scenario: RuntimeScenario) -> dict[str, Any]:
    request = json.loads(json.dumps(base_request))
    request["run_id"] = f"{base_request['run_id']}-{scenario.scenario_id}"
    request["series_layout"] = scenario.series_layout
    request["cross_learning"] = scenario.cross_learning
    request["prediction_length"] = scenario.prediction_length
    request["context_length"] = scenario.context_length
    request["quantile_levels"] = list(scenario.quantile_levels)
    request["artifact_dir"] = None
    request["reference_manifest_path"] = None
    history = request.get("history", [])
    if scenario.use_past_covariates:
        request["past_covariates"] = [
            {
                "draw_month": int(str(row["draw_date"])[5:7]),
                "draw_weekday": index % 7,
            }
            for index, row in enumerate(history)
        ]
    else:
        request["past_covariates"] = []
    if scenario.use_future_covariates:
        request["future_covariates"] = [
            {
                "draw_month": 1,
                "draw_weekday": step % 7,
            }
            for step in range(scenario.prediction_length)
        ]
    else:
        request["future_covariates"] = []
    return request


def _verify_response(
    request: dict[str, Any],
    response: dict[str, Any],
    required_status: str,
) -> dict[str, Any]:
    errors: list[str] = []
    if response.get("status") != required_status:
        errors.append(f"status={response.get('status')!r}")
    expected_positions = int(request["game_geometry"]["position_count"])
    expected_horizon = int(request["prediction_length"])
    point = response.get("point_forecast", [])
    if len(point) != expected_positions:
        errors.append("point position count mismatch")
    elif any(len(row) != expected_horizon for row in point):
        errors.append("point horizon mismatch")
    quantiles = response.get("quantiles", {})
    expected_levels = {str(level) for level in request["quantile_levels"]}
    if set(quantiles) != expected_levels:
        errors.append("quantile level mismatch")
    series_identity = response.get("series_identity", [])
    if len(series_identity) != expected_positions:
        errors.append("series identity count mismatch")
    runtime = response.get("runtime_evidence") or {}
    if runtime.get("finite") is not True:
        errors.append("finite evidence missing")
    if runtime.get("shape_verified") is not True:
        errors.append("shape evidence missing")
    if runtime.get("quantile_monotonicity_verified") is not True:
        errors.append("quantile monotonicity evidence missing")
    if runtime.get("cpu_fallback") is not False:
        errors.append("cpu fallback detected or unspecified")
    return {
        "verified": not errors,
        "errors": errors,
        "response_sha256": _canonical_sha256(response),
    }


def run_runtime_matrix(
    base_request: dict[str, Any],
    config: RuntimeMatrixConfig,
    executor: Executor,
) -> RuntimeMatrixResult:
    rows: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    for scenario in config.scenarios:
        request = _scenario_request(base_request, scenario)
        response = executor(request)
        verification = _verify_response(request, response, config.required_status)
        perturbation_verified: bool | None = None
        perturbation_response_sha256: str | None = None
        perturbed_request: dict[str, Any] | None = None
        perturbed_response: dict[str, Any] | None = None
        if scenario.verify_covariate_perturbation and verification["verified"]:
            perturbed_request = _perturbed_request(request, scenario)
            perturbed_response = executor(perturbed_request)
            perturbed_verification = _verify_response(
                perturbed_request,
                perturbed_response,
                config.required_status,
            )
            perturbation_response_sha256 = perturbed_verification["response_sha256"]
            point_changed = response.get("point_forecast") != perturbed_response.get(
                "point_forecast"
            )
            perturbation_verified = bool(perturbed_verification["verified"] and point_changed)
            if not perturbed_verification["verified"]:
                verification["errors"].append("perturbed response failed verification")
            if not point_changed:
                verification["errors"].append("covariate perturbation had no forecast effect")
            verification["verified"] = bool(
                verification["verified"] and perturbation_verified
            )
        evidence_rows.append(
            {
                "scenario_id": scenario.scenario_id,
                "control_request": request,
                "control_response": response,
                "perturbed_request": perturbed_request,
                "perturbed_response": perturbed_response,
            }
        )
        rows.append(
            {
                "scenario_id": scenario.scenario_id,
                "series_layout": scenario.series_layout,
                "cross_learning": scenario.cross_learning,
                "prediction_length": scenario.prediction_length,
                "context_length": scenario.context_length,
                "use_past_covariates": scenario.use_past_covariates,
                "use_future_covariates": scenario.use_future_covariates,
                "verify_covariate_perturbation": (
                    scenario.verify_covariate_perturbation
                ),
                "perturbation_verified": perturbation_verified,
                "perturbation_response_sha256": perturbation_response_sha256,
                "request_sha256": _canonical_sha256(request),
                **verification,
            }
        )
    passed = sum(bool(row["verified"]) for row in rows)
    if passed != len(rows):
        status = "PARTIAL"
    elif config.runtime_mode == "real":
        status = "PASS"
    else:
        status = "PARTIALLY_VERIFIED"
    report = {
        "schema_version": 1,
        "run_id": config.run_id,
        "status": status,
        "scenario_count": len(rows),
        "passed": passed,
        "failed": len(rows) - passed,
        "covariate_perturbations_required": sum(
            bool(scenario.verify_covariate_perturbation)
            for scenario in config.scenarios
        ),
        "covariate_perturbations_verified": sum(
            row.get("perturbation_verified") is True for row in rows
        ),
        "runtime_mode": config.runtime_mode,
        "real_runtime_required_for_formal_pass": True,
    }
    return RuntimeMatrixResult(
        status=status,
        rows=tuple(rows),
        report=report,
        evidence=tuple(evidence_rows),
    )


def persist_runtime_matrix(
    result: RuntimeMatrixResult,
    output_dir: str | Path,
) -> dict[str, str]:
    root = Path(output_dir).expanduser().resolve()
    if root.exists() and any(root.iterdir()):
        raise FileExistsError(f"output directory is not empty: {root}")
    if root.exists():
        root.rmdir()
    root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{root.name}.staging-", dir=root.parent)
    )
    try:
        report_path = staging / "CHRONOS2_RUNTIME_MATRIX_REPORT.json"
        rows_path = staging / "CHRONOS2_RUNTIME_MATRIX.json"
        report_path.write_text(
            json.dumps(result.report, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        rows_path.write_text(
            json.dumps(list(result.rows), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        scenario_artifacts: dict[str, dict[str, str]] = {}
        for evidence in result.evidence:
            scenario_id = str(evidence["scenario_id"])
            scenario_root = staging / "scenarios" / scenario_id
            scenario_root.mkdir(parents=True, exist_ok=True)
            paths: dict[str, str] = {}
            for key in (
                "control_request",
                "control_response",
                "perturbed_request",
                "perturbed_response",
            ):
                value = evidence.get(key)
                if value is None:
                    continue
                path = scenario_root / f"{key}.json"
                path.write_text(
                    json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
                    + "\n",
                    encoding="utf-8",
                )
                paths[key] = path.relative_to(staging).as_posix()
            scenario_artifacts[scenario_id] = paths

        manifest_path = staging / "ARTIFACT_MANIFEST.json"
        manifest = {
            "schema_version": 1,
            "status": result.status,
            "artifacts": {
                "report": report_path.name,
                "matrix": rows_path.name,
                "scenarios": scenario_artifacts,
            },
        }
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        sums_path = staging / "SHA256SUMS"
        files: Sequence[Path] = tuple(
            sorted(path for path in staging.rglob("*") if path.is_file())
        )
        lines = [
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}  "
            f"{path.relative_to(staging).as_posix()}"
            for path in files
        ]
        sums_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        staging.replace(root)
        return {
            "report": str(root / report_path.name),
            "matrix": str(root / rows_path.name),
            "manifest": str(root / manifest_path.name),
            "sha256sums": str(root / sums_path.name),
        }
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
