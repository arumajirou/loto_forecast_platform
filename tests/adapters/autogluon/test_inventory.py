from __future__ import annotations

import json
import types

from loto.adapters.autogluon.inventory import (
    SOURCE_ENSEMBLE_SPECS,
    SOURCE_MODEL_SPECS,
    FailureCategory,
    InventoryStatus,
    discover_runtime_inventory,
    write_runtime_inventory,
)


def _fake_runtime(*, extra_aliases: tuple[str, ...] = ()):
    classes = {spec.class_name: type(spec.class_name, (), {}) for spec in SOURCE_MODEL_SPECS}

    class FakeRegistry:
        @classmethod
        def available_aliases(cls):
            return sorted([spec.alias for spec in SOURCE_MODEL_SPECS] + list(extra_aliases))

    classes["ModelRegistry"] = FakeRegistry
    models_module = types.SimpleNamespace(**classes)

    ensemble_classes = {
        spec.expected_class_name: type(spec.expected_class_name, (), {})
        for spec in SOURCE_ENSEMBLE_SPECS
    }

    def get_ensemble_class(name: str):
        spec = next(item for item in SOURCE_ENSEMBLE_SPECS if item.selectable_name == name)
        return ensemble_classes[spec.expected_class_name]

    ensemble_module = types.SimpleNamespace(get_ensemble_class=get_ensemble_class)
    return models_module, ensemble_module


def test_source_manifest_matches_autogluon_1_5_0_contract() -> None:
    assert len(SOURCE_MODEL_SPECS) == 29
    assert len(SOURCE_ENSEMBLE_SPECS) == 9
    assert len({spec.expected_class_name for spec in SOURCE_ENSEMBLE_SPECS}) == 8
    assert any(spec.selectable_name == "PerformanceWeighted" for spec in SOURCE_ENSEMBLE_SPECS)
    weighted = next(spec for spec in SOURCE_ENSEMBLE_SPECS if spec.selectable_name == "Weighted")
    assert weighted.alias_of == "Greedy"
    assert weighted.expected_class_name == "GreedyEnsemble"


def test_runtime_discovery_separates_importable_from_certified() -> None:
    models_module, ensemble_module = _fake_runtime()
    inventory = discover_runtime_inventory(
        models_module=models_module,
        ensemble_module=ensemble_module,
        installed_version="1.5.0",
    )
    assert inventory.status is InventoryStatus.OK
    assert inventory.source_model_count == 29
    assert inventory.runtime_discovered_model_count == 29
    assert inventory.runtime_importable_model_count == 29
    assert inventory.runtime_certified_model_count == 0
    assert inventory.source_ensemble_name_count == 9
    assert inventory.source_unique_ensemble_class_count == 8
    assert inventory.runtime_discovered_ensemble_count == 9
    assert inventory.runtime_certified_ensemble_count == 0
    assert inventory.failures == ()


def test_unknown_runtime_alias_is_preserved_and_fails_partial() -> None:
    models_module, ensemble_module = _fake_runtime(extra_aliases=("FutureModel",))
    inventory = discover_runtime_inventory(
        models_module=models_module,
        ensemble_module=ensemble_module,
        installed_version="1.5.0",
    )
    assert inventory.status is InventoryStatus.PARTIAL
    assert inventory.unknown_runtime_model_aliases == ("FutureModel",)
    assert any(
        failure.category is FailureCategory.UNKNOWN_RUNTIME_ALIAS
        and failure.subject == "FutureModel"
        for failure in inventory.failures
    )


def test_version_mismatch_is_explicit() -> None:
    models_module, ensemble_module = _fake_runtime()
    inventory = discover_runtime_inventory(
        models_module=models_module,
        ensemble_module=ensemble_module,
        installed_version="1.6.0",
    )
    assert inventory.status is InventoryStatus.PARTIAL
    assert inventory.version_matches is False
    assert any(
        failure.category is FailureCategory.VERSION_MISMATCH for failure in inventory.failures
    )


def test_missing_package_is_classified_without_silent_empty_inventory() -> None:
    def missing_version():
        raise ModuleNotFoundError(
            "No module named 'autogluon'",
            name="autogluon",
        )

    inventory = discover_runtime_inventory(version_resolver=missing_version)
    assert inventory.status is InventoryStatus.ERROR
    assert inventory.source_model_count == 29
    assert inventory.runtime_discovered_model_count == 0
    assert any(
        failure.category is FailureCategory.PACKAGE_MISSING for failure in inventory.failures
    )


def test_missing_source_class_is_not_reported_importable() -> None:
    models_module, ensemble_module = _fake_runtime()
    delattr(models_module, "TotoModel")
    inventory = discover_runtime_inventory(
        models_module=models_module,
        ensemble_module=ensemble_module,
        installed_version="1.5.0",
    )
    toto = next(entry for entry in inventory.models if entry.alias == "Toto")
    assert inventory.status is InventoryStatus.PARTIAL
    assert toto.runtime_discovered is True
    assert toto.runtime_importable is False
    assert toto.failure is not None
    assert toto.failure.category is FailureCategory.SOURCE_CLASS_MISSING


def test_inventory_hash_is_deterministic() -> None:
    models_module, ensemble_module = _fake_runtime()
    first = discover_runtime_inventory(
        models_module=models_module,
        ensemble_module=ensemble_module,
        installed_version="1.5.0",
    )
    second = discover_runtime_inventory(
        models_module=models_module,
        ensemble_module=ensemble_module,
        installed_version="1.5.0",
    )
    assert first.inventory_sha256 == second.inventory_sha256
    assert len(first.inventory_sha256) == 64


def test_inventory_write_is_atomic_and_round_trips(tmp_path) -> None:
    models_module, ensemble_module = _fake_runtime()
    inventory = discover_runtime_inventory(
        models_module=models_module,
        ensemble_module=ensemble_module,
        installed_version="1.5.0",
    )
    output = write_runtime_inventory(inventory, tmp_path / "inventory.json")
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["inventory_sha256"] == inventory.inventory_sha256
    assert payload["source_model_count"] == 29
    assert not (tmp_path / ".inventory.json.tmp").exists()


def test_empty_runtime_registry_marks_all_source_aliases_missing() -> None:
    models_module, ensemble_module = _fake_runtime()

    class EmptyRegistry:
        @classmethod
        def available_aliases(cls):
            return []

    models_module.ModelRegistry = EmptyRegistry
    inventory = discover_runtime_inventory(
        models_module=models_module,
        ensemble_module=ensemble_module,
        installed_version="1.5.0",
    )
    assert inventory.status is InventoryStatus.PARTIAL
    assert inventory.runtime_discovered_model_count == 0
    assert (
        sum(
            failure.category is FailureCategory.RUNTIME_ALIAS_MISSING
            for failure in inventory.failures
        )
        == 29
    )
