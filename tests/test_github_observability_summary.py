import pytest

from scripts.build_github_observability_summary import classify_workflow
from scripts.build_github_visual_dashboard import DashboardBuildError, _validate_observability


def test_classify_canonical_ci() -> None:
    assert classify_workflow("ci", ".github/workflows/ci.yml") == "canonical-gate"


def test_classify_observability_dashboards() -> None:
    assert (
        classify_workflow(
            "00 / repository observability dashboard",
            ".github/workflows/github-observability-dashboard.yml",
        )
        == "observability"
    )
    assert (
        classify_workflow(
            "00 / visual dashboard build",
            ".github/workflows/github-visual-dashboard-build.yml",
        )
        == "observability"
    )


def test_classify_windows_portability_gate() -> None:
    assert (
        classify_workflow(
            "windows-portability-ci",
            ".github/workflows/windows-portability-ci.yml",
        )
        == "portability-gate"
    )


def test_classify_runtime_specialized_before_maintenance_terms() -> None:
    assert (
        classify_workflow(
            "autogluon-runtime-debt-diagnostic",
            ".github/workflows/autogluon-runtime-debt-diagnostic.yml",
        )
        == "runtime-specialized"
    )


def test_classify_maintenance_diagnostic() -> None:
    assert (
        classify_workflow(
            "f401-inventory",
            ".github/workflows/f401-inventory.yml",
        )
        == "maintenance-diagnostic"
    )


def test_classify_unknown_specialized() -> None:
    assert (
        classify_workflow(
            "nightly housekeeping",
            ".github/workflows/nightly-housekeeping.yml",
        )
        == "other-specialized"
    )


def _observability_payload(version: int) -> dict[str, object]:
    return {
        "schema_version": version,
        "repository": "arumajirou/loto_forecast_platform",
        "main_sha": "a" * 40,
        "open_issues": [],
        "active_workflows": [],
    }


@pytest.mark.parametrize("version", [1, 2])
def test_visual_dashboard_accepts_supported_observability_schema(version: int) -> None:
    _validate_observability(_observability_payload(version))


def test_visual_dashboard_rejects_unknown_observability_schema() -> None:
    with pytest.raises(DashboardBuildError, match="schema_version must be one of: 1, 2"):
        _validate_observability(_observability_payload(3))
