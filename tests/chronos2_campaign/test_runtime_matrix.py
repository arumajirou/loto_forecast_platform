from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from loto.chronos2_campaign.runtime_matrix import (
    RuntimeMatrixConfig,
    RuntimeScenario,
    default_scenarios,
    persist_runtime_matrix,
    run_runtime_matrix,
)


def _base_request() -> dict:
    history = []
    for index in range(12):
        history.append(
            {
                "draw_no": index + 1,
                "draw_date": f"2026-01-{index + 1:02d}",
                "n1": 1,
                "n2": 5,
                "n3": 9,
            }
        )
    return {
        "schema_version": 2,
        "run_id": "runtime-test",
        "operation": "predict",
        "model_id": "chronos-2",
        "repo_id": "amazon/chronos-2",
        "revision": "a" * 40,
        "game_geometry": {
            "game_id": "numbers3",
            "position_count": 3,
            "candidate_min": 0,
            "candidate_max": 9,
            "allow_duplicates": True,
            "sort_policy": "preserve",
            "position_ranges": {},
        },
        "position_columns": ["n1", "n2", "n3"],
        "history": history,
        "batch_size": 3,
        "device": "cpu",
        "dtype": "float32",
        "attention_implementation": "sdpa",
        "seed": 1,
        "local_files_only": True,
    }


def _executor(request: dict) -> dict:
    positions = request["position_columns"]
    horizon = request["prediction_length"]
    covariate_effect = 0.0
    for rows_name in ("past_covariates", "future_covariates"):
        for row in request.get(rows_name, []):
            covariate_effect += sum(
                float(value) for value in row.values() if isinstance(value, (int, float))
            )
    covariate_effect *= 1e-6
    point = [[float(index + 1) + covariate_effect] * horizon for index in range(len(positions))]
    quantiles = {
        str(level): [
            [float(index + 1) + covariate_effect + float(level) - 0.5] * horizon
            for index in range(len(positions))
        ]
        for level in request["quantile_levels"]
    }
    return {
        "status": "OK",
        "run_id": request["run_id"],
        "point_forecast": point,
        "quantiles": quantiles,
        "series_identity": positions,
        "runtime_evidence": {
            "finite": True,
            "shape_verified": True,
            "quantile_monotonicity_verified": True,
            "cpu_fallback": False,
        },
    }


def test_default_runtime_matrix_covers_z0_to_z4() -> None:
    scenarios = default_scenarios()
    assert [scenario.scenario_id.split("-", 1)[0] for scenario in scenarios] == [
        "z0",
        "z1",
        "z2",
        "z3",
        "z4",
    ]
    assert {scenario.prediction_length for scenario in scenarios} == {1, 2, 5}
    assert any(scenario.cross_learning for scenario in scenarios)
    assert any(scenario.use_future_covariates for scenario in scenarios)
    assert sum(scenario.verify_covariate_perturbation for scenario in scenarios) == 2


def test_runtime_scenario_rejects_invalid_cross_learning() -> None:
    with pytest.raises(ValueError, match="cross_learning"):
        RuntimeScenario(
            scenario_id="invalid",
            series_layout="position_local",
            cross_learning=True,
            prediction_length=1,
            context_length=8,
            quantile_levels=(0.1, 0.5, 0.9),
        )


def test_runtime_scenario_rejects_future_without_past() -> None:
    with pytest.raises(ValueError, match="future covariates"):
        RuntimeScenario(
            scenario_id="invalid",
            series_layout="position_multivariate",
            cross_learning=False,
            prediction_length=1,
            context_length=8,
            quantile_levels=(0.1, 0.5, 0.9),
            use_future_covariates=True,
        )


def test_runtime_matrix_passes_all_scenarios() -> None:
    config = RuntimeMatrixConfig(
        run_id="runtime",
        scenarios=default_scenarios(),
        runtime_mode="real",
    )
    result = run_runtime_matrix(_base_request(), config, _executor)
    assert result.status == "PASS"
    assert result.report["passed"] == 5
    assert all(row["verified"] for row in result.rows)
    assert len(result.evidence) == 5
    assert all(item["control_request"]["artifact_dir"] is None for item in result.evidence)


def test_runtime_matrix_injected_mode_is_not_formal_pass() -> None:
    config = RuntimeMatrixConfig(run_id="runtime", scenarios=default_scenarios())
    result = run_runtime_matrix(_base_request(), config, _executor)
    assert result.status == "PARTIALLY_VERIFIED"
    assert result.report["runtime_mode"] == "injected"


def test_runtime_matrix_builds_covariates() -> None:
    requests: list[dict] = []

    def executor(request: dict) -> dict:
        requests.append(request)
        return _executor(request)

    config = RuntimeMatrixConfig(run_id="runtime", scenarios=default_scenarios())
    run_runtime_matrix(_base_request(), config, executor)
    z3 = next(request for request in requests if "z3-" in request["run_id"])
    z4 = next(request for request in requests if "z4-" in request["run_id"])
    assert len(z3["past_covariates"]) == len(z3["history"])
    assert z3["future_covariates"] == []
    assert len(z4["past_covariates"]) == len(z4["history"])
    assert len(z4["future_covariates"]) == z4["prediction_length"]


def test_runtime_matrix_detects_covariate_no_effect() -> None:
    def insensitive_executor(request: dict) -> dict:
        stripped = json.loads(json.dumps(request))
        stripped["past_covariates"] = []
        stripped["future_covariates"] = []
        return _executor(stripped)

    config = RuntimeMatrixConfig(
        run_id="runtime",
        scenarios=default_scenarios(),
        runtime_mode="real",
    )
    result = run_runtime_matrix(_base_request(), config, insensitive_executor)
    assert result.status == "PARTIAL"
    failed = [row for row in result.rows if row["verify_covariate_perturbation"]]
    assert len(failed) == 2
    assert all("covariate perturbation had no forecast effect" in row["errors"] for row in failed)


def test_runtime_matrix_detects_shape_failure() -> None:
    def bad_executor(request: dict) -> dict:
        response = _executor(request)
        response["point_forecast"] = [[1.0]]
        return response

    config = RuntimeMatrixConfig(run_id="runtime", scenarios=default_scenarios())
    result = run_runtime_matrix(_base_request(), config, bad_executor)
    assert result.status == "PARTIAL"
    assert result.report["failed"] == 5
    assert all("point position count mismatch" in row["errors"] for row in result.rows)


def test_runtime_matrix_detects_cpu_fallback() -> None:
    def bad_executor(request: dict) -> dict:
        response = _executor(request)
        response["runtime_evidence"]["cpu_fallback"] = True
        return response

    config = RuntimeMatrixConfig(run_id="runtime", scenarios=default_scenarios())
    result = run_runtime_matrix(_base_request(), config, bad_executor)
    assert result.status == "PARTIAL"
    assert all("cpu fallback detected or unspecified" in row["errors"] for row in result.rows)


def test_runtime_matrix_requires_unique_scenario_ids() -> None:
    scenario = default_scenarios()[0]
    with pytest.raises(ValueError, match="unique"):
        RuntimeMatrixConfig(run_id="runtime", scenarios=(scenario, scenario))


def test_persist_runtime_matrix_writes_sha256(tmp_path: Path) -> None:
    config = RuntimeMatrixConfig(run_id="runtime", scenarios=default_scenarios())
    result = run_runtime_matrix(_base_request(), config, _executor)
    artifacts = persist_runtime_matrix(result, tmp_path / "runtime")
    sums_path = Path(artifacts["sha256sums"])
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        path = sums_path.parent / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    report = json.loads(Path(artifacts["report"]).read_text(encoding="utf-8"))
    assert report["real_runtime_required_for_formal_pass"] is True
    scenario_root = Path(artifacts["report"]).parent / "scenarios"
    assert (scenario_root / "z0-local-h1" / "control_request.json").is_file()
    assert (scenario_root / "z4-known-future-h2" / "perturbed_response.json").is_file()


def test_persist_runtime_matrix_refuses_nonempty_output(tmp_path: Path) -> None:
    output = tmp_path / "runtime"
    output.mkdir()
    (output / "existing.txt").write_text("keep", encoding="utf-8")
    config = RuntimeMatrixConfig(run_id="runtime", scenarios=default_scenarios())
    result = run_runtime_matrix(_base_request(), config, _executor)
    with pytest.raises(FileExistsError, match="not empty"):
        persist_runtime_matrix(result, output)


def test_runtime_matrix_persist_is_atomic_on_serialization_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = RuntimeMatrixConfig(run_id="runtime", scenarios=default_scenarios())
    result = run_runtime_matrix(_base_request(), config, _executor)
    output = tmp_path / "runtime"

    original = json.dumps
    calls = {"count": 0}

    def failing_dumps(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 2:
            raise RuntimeError("synthetic serialization failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(
        "loto.chronos2_campaign.runtime_matrix.json.dumps",
        failing_dumps,
    )
    with pytest.raises(RuntimeError, match="synthetic"):
        persist_runtime_matrix(result, output)
    assert not output.exists()
    assert not list(tmp_path.glob(".runtime.staging-*"))
