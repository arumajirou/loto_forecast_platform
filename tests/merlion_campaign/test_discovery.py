from __future__ import annotations

import sys
import types

from loto.merlion_campaign.discovery import discover_factory_aliases


def test_discovery_separates_importability_from_discovery(monkeypatch) -> None:
    module = types.ModuleType("fake_merlion_module")
    module.Example = object
    monkeypatch.setitem(sys.modules, "fake_merlion_module", module)
    rows = discover_factory_aliases(
        {
            "Good": "fake_merlion_module:Example",
            "Missing": "missing_optional_module:Example",
        }
    )
    statuses = {row.model_name: row.import_status for row in rows}
    assert statuses == {
        "Good": "IMPORTABLE",
        "Missing": "OPTIONAL_DEPENDENCY_MISSING",
    }
