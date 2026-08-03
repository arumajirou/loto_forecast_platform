from __future__ import annotations

from loto.probabilistic.catalog import (
    build_unified_catalog_rows,
    catalog_counts,
    list_inference_profiles,
    list_probabilistic_model_specs,
    unified_catalog_counts,
)


def test_catalog_has_all_designed_entries() -> None:
    models = list_probabilistic_model_specs()
    profiles = list_inference_profiles()
    assert len(models) == 72
    assert len(profiles) == 29
    assert len({item.model_id for item in models}) == 72
    assert len({item.profile_id for item in profiles}) == 29
    assert all(item.implementation_status == "IMPLEMENTED" for item in models)


def test_unified_catalog_is_computed_not_hard_coded() -> None:
    counts = unified_catalog_counts()
    assert counts == {"existing": 174, "probabilistic": 72, "total": 246}
    rows = build_unified_catalog_rows()
    assert len({row["model_id"] for row in rows}) == len(rows)
    assert catalog_counts()["probabilistic_models"] == 72
