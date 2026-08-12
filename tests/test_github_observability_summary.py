from scripts.build_github_observability_summary import classify_workflow


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
