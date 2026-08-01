from __future__ import annotations

from loto.models.argument_verifier import verify_arguments


def test_verify_arguments_includes_non_common_requested_arguments() -> None:
    rows = verify_arguments(
        {"n_estimators": 2, "custom_switch": "x"},
        {"n_estimators": 2, "custom_switch": "x"},
        {"effective_parameters": {"n_estimators": 2, "custom_switch": "x"}},
    )
    by_name = {row["argument"]: row for row in rows}
    assert by_name["n_estimators"]["status"] == "VERIFIED"
    assert by_name["custom_switch"]["status"] == "VERIFIED"
