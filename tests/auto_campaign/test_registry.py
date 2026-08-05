import pytest


def test_runtime_registry_has_only_base_auto_subclasses() -> None:
    pytest.importorskip("neuralforecast")
    from loto.auto_campaign.registry import discover_auto_models

    records = discover_auto_models()
    assert records
    assert "Autoformer" not in {record.name for record in records}
    assert "AutoTFT" in {record.name for record in records}
