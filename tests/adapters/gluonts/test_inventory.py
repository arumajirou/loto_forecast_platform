from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from loto.adapters.gluonts.inventory import (
    CheckState,
    FormalAvailability,
    InventoryCategory,
    RuntimeInventory,
    RuntimeInventoryEntry,
    inventory_sha256,
)

ROOT = Path(__file__).resolve().parents[3]


def _discovered_entry() -> RuntimeInventoryEntry:
    return RuntimeInventoryEntry(
        name="DeepAREstimator",
        category=InventoryCategory.PYTORCH_ESTIMATOR,
        module="gluonts.torch.model.deepar",
        qualname="DeepAREstimator",
        class_path="gluonts.torch.model.deepar.DeepAREstimator",
        import_state=CheckState.PASS,
        export_state=CheckState.PASS,
        class_state=CheckState.PASS,
        signature_state=CheckState.PASS,
        constructor_signature="(freq: str, prediction_length: int)",
        formal_availability=FormalAvailability.DISCOVERED_ONLY,
    )


def test_inventory_summary_does_not_promote_discovery_to_verified() -> None:
    inventory = RuntimeInventory(
        lane="compat",
        generated_at_utc="2026-08-05T00:00:00+00:00",
        entries=[_discovered_entry()],
    )

    assert inventory.summary["total"] == 1
    assert inventory.summary["formally_verified"] == 0
    assert inventory.summary["by_category"]["PYTORCH_ESTIMATOR"] == 1
    assert len(inventory_sha256(inventory)) == 64
    assert inventory_sha256(inventory) == inventory_sha256(inventory)


def test_verified_estimator_requires_runtime_checks() -> None:
    with pytest.raises(ValidationError, match="category checks"):
        RuntimeInventoryEntry(
            name="DeepAREstimator",
            category=InventoryCategory.PYTORCH_ESTIMATOR,
            module="gluonts.torch.model.deepar",
            import_state=CheckState.PASS,
            export_state=CheckState.PASS,
            class_state=CheckState.PASS,
            signature_state=CheckState.PASS,
            formal_availability=FormalAvailability.VERIFIED,
        )


def test_failed_entry_requires_error_evidence() -> None:
    with pytest.raises(ValidationError, match="at least one error"):
        RuntimeInventoryEntry(
            name="BrokenEstimator",
            category=InventoryCategory.PYTORCH_ESTIMATOR,
            module="gluonts.torch",
            formal_availability=FormalAvailability.FAILED,
        )


def test_root_and_provider_inventory_contracts_are_identical() -> None:
    paths = [
        ROOT / "src" / "loto" / "adapters" / "gluonts" / "inventory.py",
        ROOT / "environments" / "gluonts-compat" / "src" / "loto_gluonts_provider" / "inventory.py",
        ROOT / "environments" / "gluonts-latest" / "src" / "loto_gluonts_provider" / "inventory.py",
    ]
    contents = [path.read_text(encoding="utf-8") for path in paths]
    assert contents[0] == contents[1] == contents[2]
