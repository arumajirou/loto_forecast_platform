from loto.adapters.autogluon.inventory import SOURCE_ENSEMBLE_SPECS, SOURCE_MODEL_SPECS
from loto.models.catalog_full import build_catalog
from loto.models.implementation_catalog import (
    AUTOGLOUON_BROAD_V1_ID,
    autogluon_implementation_identities,
    expanded_implementation_catalog,
    expanded_inventory_counts,
)


def test_autogluon_expansion_uses_all_source_models_and_unique_ensemble_classes() -> None:
    rows = autogluon_implementation_identities()
    model_rows = [row for row in rows if row.source_kind == "autogluon_source_model"]
    ensemble_rows = [row for row in rows if row.source_kind == "autogluon_source_ensemble"]

    assert len(SOURCE_MODEL_SPECS) == 29
    assert len(model_rows) == len(SOURCE_MODEL_SPECS)
    assert len(ensemble_rows) == len(
        {spec.expected_class_name for spec in SOURCE_ENSEMBLE_SPECS}
    )
    assert len(ensemble_rows) == 8
    assert len(rows) == 37
    assert len({row.implementation_id for row in rows}) == len(rows)
    assert all(row.canonical_v1_model_id == AUTOGLOUON_BROAD_V1_ID for row in rows)
    assert all(row.runtime_status == "NOT_RUN" for row in rows)
    assert not any(row.runtime_certified for row in rows)


def test_weighted_autogluon_alias_does_not_inflate_unique_ensemble_count() -> None:
    rows = autogluon_implementation_identities()
    ensembles = [row for row in rows if row.source_kind == "autogluon_source_ensemble"]

    greedy = next(row for row in ensembles if row.class_name == "GreedyEnsemble")
    assert greedy.implementation_id == "autogluon-ensemble-greedy"
    assert "Greedy,Weighted" in greedy.notes
    assert not any(row.implementation_id == "autogluon-ensemble-weighted" for row in ensembles)


def test_expanded_v2_preserves_frozen_broad_v1_and_derives_phase_one_count() -> None:
    broad_v1 = build_catalog()
    expanded = expanded_implementation_catalog()
    counts = expanded_inventory_counts()

    assert len(broad_v1) == 174
    assert counts["broad_v1"] == 174
    assert counts["autogluon_broad_v1_umbrella_count"] == 1
    assert counts["autogluon_source_models"] == 29
    assert counts["autogluon_unique_ensembles"] == 8
    assert counts["autogluon_expanded_total"] == 37
    assert counts["expanded_v2"] == len(expanded) == 210
    assert counts["delta_vs_broad_v1"] == 36
    assert len({row.implementation_id for row in expanded}) == len(expanded)


def test_expanded_v2_replaces_only_autogluon_umbrella_in_phase_one() -> None:
    broad_ids = {entry.model_id for entry in build_catalog()}
    expanded_ids = {row.implementation_id for row in expanded_implementation_catalog()}

    assert AUTOGLOUON_BROAD_V1_ID in broad_ids
    assert AUTOGLOUON_BROAD_V1_ID not in expanded_ids
    assert broad_ids - {AUTOGLOUON_BROAD_V1_ID} <= expanded_ids
    assert "autogluon-deepar" in expanded_ids
    assert "autogluon-chronos2" in expanded_ids
    assert "autogluon-toto" in expanded_ids
