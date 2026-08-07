from __future__ import annotations

from loto.sktime_campaign.inventory import (
    inventory_rows_from_estimators,
    summarize_inventory,
)


class CoreForecaster:
    def __init__(self, strategy: str = "last") -> None:
        self.strategy = strategy

    @classmethod
    def get_class_tags(cls) -> dict[str, object]:
        return {
            "python_dependencies": None,
            "capability:missing_values": False,
            "property:randomness": "deterministic",
        }


class OptionalForecaster:
    def __init__(self, alpha: float = 0.1) -> None:
        self.alpha = alpha

    @classmethod
    def get_class_tags(cls) -> dict[str, object]:
        return {
            "python_dependencies": ["optional-package>=1"],
            "capability:pred_int": True,
        }


def test_inventory_is_sorted_and_counts_are_computed() -> None:
    rows = inventory_rows_from_estimators(
        [
            ("OptionalForecaster", OptionalForecaster),
            ("CoreForecaster", CoreForecaster),
        ],
        package_version="1.0.1",
    )

    assert [row["name"] for row in rows] == [
        "CoreForecaster",
        "OptionalForecaster",
    ]
    assert rows[0]["dependency_state"] == "CORE_COMPATIBLE"
    assert rows[1]["dependency_state"] == "OPTIONAL_DEPENDENCY_DECLARED"
    assert "strategy" in rows[0]["constructor_signature"]
    assert rows[0]["construct_status"] == "NOT_ATTEMPTED"

    summary = summarize_inventory(rows)
    assert summary == {
        "discovered": 2,
        "importable": 2,
        "core_compatible": 1,
        "optional_dependency_declared": 1,
        "constructable": 0,
        "runtime_verified": 0,
        "count_source": "sktime.registry.all_estimators('forecaster')",
    }
