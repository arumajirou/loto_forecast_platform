from loto.darts_campaign.discovery import PUBLIC_FORECASTING_EXPORTS_0_46_1
from loto.models.catalog_full import build_catalog
from loto.models.darts_source_inventory import (
    DARTS_BROAD_V1_ID,
    DARTS_SOURCE_EXCLUSIONS,
    darts_source_manifest_sha256,
)
from loto.models.expanded_inventory_v2 import (
    AUTOGLOUON_BROAD_V1_ID,
    GLUONTS_BROAD_V1_ID,
    darts_implementation_identities,
    expanded_implementation_catalog,
    expanded_inventory_counts,
)


def test_darts_source_expansion_is_deterministic_and_fail_closed() -> None:
    rows = darts_implementation_identities()
    names = {row.class_name for row in rows}
    exclusions = {row.public_name: row for row in DARTS_SOURCE_EXCLUSIONS}

    assert len(PUBLIC_FORECASTING_EXPORTS_0_46_1) == 58
    assert len(DARTS_SOURCE_EXCLUSIONS) == 3
    assert len(rows) == 55
    assert len({row.implementation_id for row in rows}) == 55

    assert exclusions["EnsembleModel"].kind == "ABSTRACT_BASE"
    assert exclusions["RandomForest"].replacement == "RandomForestModel"
    assert exclusions["RegressionModel"].replacement == "SKLearnModel"

    assert "EnsembleModel" not in names
    assert "RandomForest" not in names
    assert "RegressionModel" not in names
    assert "RandomForestModel" in names
    assert "SKLearnModel" in names
    assert "NLinearModel" in names
    assert "DLinearModel" in names
    assert "Chronos2Model" in names

    assert all(row.canonical_v1_model_id == DARTS_BROAD_V1_ID for row in rows)
    assert all(row.runtime_status == "NOT_RUN" for row in rows)
    assert not any(row.runtime_certified for row in rows)
    assert all(row.execution_surface == "darts_provider_pending" for row in rows)
    assert all(row.capabilities == ("source_declared",) for row in rows)


def test_darts_source_manifest_hash_is_stable_shape() -> None:
    digest = darts_source_manifest_sha256()

    assert len(digest) == 64
    assert int(digest, 16) >= 0
    assert digest == darts_source_manifest_sha256()


def test_combined_expanded_v2_preserves_broad_and_derives_272() -> None:
    broad = build_catalog()
    expanded = expanded_implementation_catalog()
    counts = expanded_inventory_counts()

    assert len(broad) == 174
    assert counts["broad_v1"] == 174

    assert counts["autogluon_expanded_total"] == 37
    assert counts["gluonts_expanded_total"] == 9
    assert counts["darts_public_exports"] == 58
    assert counts["darts_expanded_total"] == 55
    assert counts["darts_excluded_abstract_bases"] == 1
    assert counts["darts_excluded_deprecated_aliases"] == 2

    assert len(expanded) == 272
    assert counts["expanded_v2"] == 272
    assert counts["delta_vs_broad_v1"] == 98
    assert counts["by_library"]["autogluon"] == 37
    assert counts["by_library"]["gluonts"] == 9
    assert counts["by_library"]["darts"] == 55
    assert len({row.implementation_id for row in expanded}) == len(expanded)

    expanded_ids = {row.implementation_id for row in expanded}
    assert AUTOGLOUON_BROAD_V1_ID not in expanded_ids
    assert GLUONTS_BROAD_V1_ID not in expanded_ids
    assert DARTS_BROAD_V1_ID not in expanded_ids
    assert "autogluon-deepar" in expanded_ids
    assert "gluonts-torch-deepar" in expanded_ids
    assert "darts-nlinearmodel" in expanded_ids
    assert "darts-dlinearmodel" in expanded_ids
    assert "darts-chronos2model" in expanded_ids
