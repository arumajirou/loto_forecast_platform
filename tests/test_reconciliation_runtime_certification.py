from __future__ import annotations

import hashlib
import json
import sys
import types
from pathlib import Path

import numpy as np
import pytest

from loto.reconciliation import runtime_certification as rc


@pytest.fixture
def fake_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    module = types.ModuleType("hierarchicalforecast")
    module.__version__ = rc.TARGET_VERSION
    monkeypatch.setitem(sys.modules, "hierarchicalforecast", module)
    monkeypatch.setattr(
        rc,
        "_dependency_state",
        lambda: rc.DependencyState(
            import_status="PASS",
            installed_version=rc.TARGET_VERSION,
            module_version=rc.TARGET_VERSION,
            distribution_version=rc.TARGET_VERSION,
            version_consistent=True,
        ),
    )


def _fake_reconcile(base, hierarchy, *, method, coherence_tolerance, **kwargs):
    if rc.EXPECTED_METHOD_STATUS[method] == "UNSUPPORTED_HIERARCHY":
        return {
            "status": "UNSUPPORTED_HIERARCHY",
            "method": method,
            "actual_execution": False,
            "hierarchy_is_strict": False,
        }
    if method == "ERM":
        assert kwargs["insample_actuals"].shape[0] == hierarchy.n_total
        assert kwargs["insample_forecasts"].shape[0] == hierarchy.n_total
    bottom = np.asarray(base[-hierarchy.n_bottom :], dtype=float)
    reconciled = hierarchy.summing_matrix @ bottom
    return {
        "status": "VERIFIED",
        "method": method,
        "actual_execution": True,
        "upstream_version": rc.TARGET_VERSION,
        "hierarchy_is_strict": False,
        "requires_insample": method == "ERM",
        "upstream_options": {},
        "bottom": bottom,
        "reconciled": reconciled,
        "finite": True,
        "shape": list(reconciled.shape),
        "coherence_error": 0.0,
        "coherence_tolerance": coherence_tolerance,
    }


def _verify_sha256s(run_dir: Path) -> None:
    rows = (run_dir / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 4
    for row in rows:
        digest, filename = row.split("  ", maxsplit=1)
        actual = hashlib.sha256((run_dir / filename).read_bytes()).hexdigest()
        assert digest == actual


def test_full_runtime_matrix_writes_verified_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_dependency: None,
) -> None:
    monkeypatch.setattr(rc, "reconcile_with_hierarchicalforecast", _fake_reconcile)
    config = rc.RuntimeCertificationConfig(output_root=tmp_path)

    result = rc.run_certification(config)

    assert result["status"] == "VERIFIED"
    assert result["formal_success"] is True
    assert result["summary"] == {
        "expected_cases": 40,
        "executed_cases": 40,
        "passed_cases": 40,
        "failed_cases": 0,
        "exact_version_match": True,
        "module_distribution_version_consistent": True,
    }
    run_dir = Path(result["run_directory"])
    assert {path.name for path in run_dir.iterdir()} == {
        "ARTIFACT_MANIFEST.json",
        "METHOD_RESULTS.json",
        "INPUT_EVIDENCE.json",
        "RUNTIME_CERTIFICATION.json",
        "SHA256SUMS",
    }
    method_payload = json.loads((run_dir / "METHOD_RESULTS.json").read_text())
    assert len(method_payload["results"]) == 40
    assert {row["method"] for row in method_payload["results"]} == set(rc.UPSTREAM_METHODS)
    assert {row["game"] for row in method_payload["results"]} == set(rc.DEFAULT_GAMES)
    assert all(row["case_status"] == "PASS" for row in method_payload["results"])
    _verify_sha256s(run_dir)


def test_dependency_failure_is_persisted_and_not_promoted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        rc,
        "_dependency_state",
        lambda: rc.DependencyState(
            import_status="FAILED",
            error="ImportError: package missing",
        ),
    )

    result = rc.run_certification(rc.RuntimeCertificationConfig(output_root=tmp_path))

    assert result["status"] == "BLOCKED_DEPENDENCY"
    assert result["formal_success"] is False
    assert result["summary"]["executed_cases"] == 0
    run_dir = Path(result["run_directory"])
    persisted = json.loads((run_dir / "RUNTIME_CERTIFICATION.json").read_text())
    assert persisted["dependency"]["error"] == "ImportError: package missing"
    inputs = json.loads((run_dir / "INPUT_EVIDENCE.json").read_text())
    assert set(inputs["games"]) == set(rc.DEFAULT_GAMES)
    assert persisted["data_sha256"] != hashlib.sha256(b"{}").hexdigest()
    _verify_sha256s(run_dir)


def test_version_mismatch_fails_even_when_all_cases_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installed = "1.6.0"
    monkeypatch.setattr(
        rc,
        "_dependency_state",
        lambda: rc.DependencyState(
            import_status="PASS",
            installed_version=installed,
            module_version=installed,
            distribution_version=installed,
            version_consistent=True,
        ),
    )

    def fake_reconcile(base, hierarchy, *, method, coherence_tolerance, **kwargs):
        result = _fake_reconcile(
            base,
            hierarchy,
            method=method,
            coherence_tolerance=coherence_tolerance,
            **kwargs,
        )
        if result["status"] == "VERIFIED":
            result["upstream_version"] = installed
        return result

    monkeypatch.setattr(rc, "reconcile_with_hierarchicalforecast", fake_reconcile)

    result = rc.run_certification(rc.RuntimeCertificationConfig(output_root=tmp_path))

    assert result["status"] == "FAILED_VERSION_MISMATCH"
    assert result["summary"]["passed_cases"] == 40
    assert result["summary"]["exact_version_match"] is False


def test_module_distribution_version_inconsistency_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        rc,
        "_dependency_state",
        lambda: rc.DependencyState(
            import_status="PASS",
            installed_version=rc.TARGET_VERSION,
            module_version="1.5.0",
            distribution_version=rc.TARGET_VERSION,
            version_consistent=False,
        ),
    )
    monkeypatch.setattr(rc, "reconcile_with_hierarchicalforecast", _fake_reconcile)

    result = rc.run_certification(rc.RuntimeCertificationConfig(output_root=tmp_path))

    assert result["status"] == "FAILED_VERSION_MISMATCH"
    assert result["summary"]["exact_version_match"] is True
    assert result["summary"]["module_distribution_version_consistent"] is False


def test_incoherent_runtime_result_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_dependency: None,
) -> None:
    def fake_reconcile(base, hierarchy, *, method, coherence_tolerance, **kwargs):
        result = _fake_reconcile(
            base,
            hierarchy,
            method=method,
            coherence_tolerance=coherence_tolerance,
            **kwargs,
        )
        if method == "MinTrace" and result["status"] == "VERIFIED":
            result["coherence_error"] = 1.0
        return result

    monkeypatch.setattr(rc, "reconcile_with_hierarchicalforecast", fake_reconcile)

    result = rc.run_certification(rc.RuntimeCertificationConfig(output_root=tmp_path))

    assert result["status"] == "FAILED_RUNTIME"
    assert result["summary"]["failed_cases"] == len(rc.DEFAULT_GAMES)
    method_payload = json.loads((Path(result["run_directory"]) / "METHOD_RESULTS.json").read_text())
    failures = [row for row in method_payload["results"] if row["case_status"] == "FAIL"]
    assert {row["method"] for row in failures} == {"MinTrace"}
    assert all(row["checks"]["coherence"] is False for row in failures)


def test_unexpected_method_exception_is_persisted_and_remaining_cases_continue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_dependency: None,
) -> None:
    def fake_reconcile(base, hierarchy, *, method, coherence_tolerance, **kwargs):
        if method == "MinTrace":
            raise RuntimeError("unexpected upstream crash")
        return _fake_reconcile(
            base,
            hierarchy,
            method=method,
            coherence_tolerance=coherence_tolerance,
            **kwargs,
        )

    monkeypatch.setattr(rc, "reconcile_with_hierarchicalforecast", fake_reconcile)

    result = rc.run_certification(rc.RuntimeCertificationConfig(output_root=tmp_path))

    assert result["status"] == "FAILED_RUNTIME"
    assert result["summary"]["executed_cases"] == 40
    assert result["summary"]["failed_cases"] == len(rc.DEFAULT_GAMES)
    payload = json.loads((Path(result["run_directory"]) / "METHOD_RESULTS.json").read_text())
    crashes = [row for row in payload["results"] if row["method"] == "MinTrace"]
    assert len(crashes) == len(rc.DEFAULT_GAMES)
    assert all(row["result"]["status"] == "HARNESS_EXCEPTION" for row in crashes)
    assert all("RuntimeError" in row["result"]["traceback"] for row in crashes)
    assert any(
        row["method"] == "ERM" and row["case_status"] == "PASS" for row in payload["results"]
    )


def test_generated_inputs_are_reproducible_and_incoherent() -> None:
    first = rc._build_inputs("loto7", seed=1, horizon=4, insample_size=16)
    second = rc._build_inputs("loto7", seed=1, horizon=4, insample_size=16)

    assert np.array_equal(first.base, second.base)
    assert np.array_equal(first.actuals, second.actuals)
    assert np.array_equal(first.fitted, second.fitted)
    bottom = first.base[-first.hierarchy.n_bottom :]
    coherent = first.hierarchy.summing_matrix @ bottom
    assert not np.allclose(coherent, first.base)
    assert first.evidence == second.evidence


def test_config_rejects_digit_games_and_duplicates(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="requires select family"):
        rc.RuntimeCertificationConfig(output_root=tmp_path, games=("numbers4",))
    with pytest.raises(ValueError, match="duplicates"):
        rc.RuntimeCertificationConfig(output_root=tmp_path, games=("loto7", "loto7"))


def test_cli_exit_code_reflects_formal_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        rc,
        "run_certification",
        lambda config: {"status": "VERIFIED", "config": str(config.output_root)},
    )
    assert rc.main(["--output-root", str(tmp_path), "--games", "loto7"]) == 0

    monkeypatch.setattr(
        rc,
        "run_certification",
        lambda config: {"status": "BLOCKED_DEPENDENCY"},
    )
    assert rc.main(["--output-root", str(tmp_path), "--games", "loto7"]) == 2
