from __future__ import annotations

import types
from dataclasses import replace

from loto.adapters.autogluon.inventory import (
    InventoryStatus,
    SOURCE_ENSEMBLE_SPECS,
    SOURCE_MODEL_SPECS,
    discover_runtime_inventory,
)
from loto.autogluon_campaign import inventory_cli


def _fake_runtime():
    classes = {spec.class_name: type(spec.class_name, (), {}) for spec in SOURCE_MODEL_SPECS}

    class FakeRegistry:
        @classmethod
        def available_aliases(cls):
            return sorted(spec.alias for spec in SOURCE_MODEL_SPECS)

    classes["ModelRegistry"] = FakeRegistry
    models_module = types.SimpleNamespace(**classes)
    ensemble_classes = {
        spec.expected_class_name: type(spec.expected_class_name, (), {})
        for spec in SOURCE_ENSEMBLE_SPECS
    }

    def get_ensemble_class(name: str):
        spec = next(item for item in SOURCE_ENSEMBLE_SPECS if item.selectable_name == name)
        return ensemble_classes[spec.expected_class_name]

    return models_module, types.SimpleNamespace(get_ensemble_class=get_ensemble_class)


def _inventory(status: InventoryStatus):
    models_module, ensemble_module = _fake_runtime()
    inventory = discover_runtime_inventory(
        models_module=models_module,
        ensemble_module=ensemble_module,
        installed_version="1.5.0",
    )
    if status is InventoryStatus.OK:
        return inventory
    return replace(inventory, status=status)


def test_cli_writes_inventory_and_returns_zero_for_ok(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    monkeypatch.setattr(
        inventory_cli,
        "discover_runtime_inventory",
        lambda **_: _inventory(InventoryStatus.OK),
    )
    output = tmp_path / "inventory.json"
    assert inventory_cli.main(["--output", str(output)]) == 0
    assert output.exists()
    captured = capsys.readouterr().out
    assert "AUTOGLUON_SOURCE_MODELS=29" in captured
    assert "AUTOGLUON_SOURCE_ENSEMBLES=9" in captured


def test_cli_partial_is_nonzero_unless_explicitly_allowed(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        inventory_cli,
        "discover_runtime_inventory",
        lambda **_: _inventory(InventoryStatus.PARTIAL),
    )
    output = tmp_path / "partial.json"
    assert inventory_cli.main(["--output", str(output)]) == 1
    assert inventory_cli.main(["--output", str(output), "--allow-partial"]) == 0


def test_cli_error_remains_nonzero_with_allow_partial(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        inventory_cli,
        "discover_runtime_inventory",
        lambda **_: _inventory(InventoryStatus.ERROR),
    )
    assert inventory_cli.main(["--output", str(tmp_path / "error.json"), "--allow-partial"]) == 2


def test_source_contract_constants_are_imported() -> None:
    assert len(SOURCE_MODEL_SPECS) == 29
    assert len(SOURCE_ENSEMBLE_SPECS) == 9
