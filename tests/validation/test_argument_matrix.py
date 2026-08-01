from __future__ import annotations

from loto.models.catalog import ModelSpec
from loto.validation.argument_matrix import build_argument_inventory, build_smoke_cases


def test_inventory_includes_catalog_and_runtime_arguments() -> None:
    spec = ModelSpec(
        "demo",
        "tree",
        "missing-library",
        "candidate",
        "MissingClass",
        default_params={"n_estimators": 10, "custom_switch": "x"},
    )
    rows = build_argument_inventory([spec])
    by_name = {row.argument: row for row in rows}
    assert by_name["n_estimators"].source == "catalog_default_params"
    assert by_name["n_estimators"].smoke_value == 2
    assert by_name["custom_switch"].smoke_eligible is False
    assert by_name["device"].source == "orchestration_runtime"


def test_quick_profile_builds_one_case_per_model() -> None:
    specs = [
        ModelSpec("a", "tree", "builtin", "candidate", "A", default_params={"n_estimators": 9}),
        ModelSpec("b", "tree", "builtin", "candidate", "B"),
    ]
    inventory = build_argument_inventory(specs)
    cases = build_smoke_cases(specs, inventory, profile="quick")
    assert [case.case_id for case in cases] == ["a__quick", "b__quick"]
    assert cases[0].requested_params["n_estimators"] == 2
    assert "retrain_predict" in cases[0].expected_checks


def test_oat_profile_adds_safe_argument_cases_only() -> None:
    spec = ModelSpec(
        "demo",
        "tree",
        "missing-library",
        "candidate",
        "MissingClass",
        default_params={"n_estimators": 10, "custom_switch": "x"},
    )
    inventory = build_argument_inventory([spec])
    cases = build_smoke_cases([spec], inventory, profile="oat")
    ids = {case.case_id for case in cases}
    assert "demo__quick" in ids
    assert "demo__arg__n_estimators" in ids
    assert "demo__arg__custom_switch" not in ids
