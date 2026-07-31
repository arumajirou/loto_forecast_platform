"""Catalog counts must be computed from primary-source lists, never hand-typed."""

from loto.models.catalog_full import (
    MLFORECAST_AUTOMODELS,
    NEURALFORECAST_AUTOMODELS,
    NEURALFORECAST_MODELS,
    RECONCILIATION_METHODS,
    STATSFORECAST_MODELS,
    TSFM_MODELS,
    build_catalog,
    catalog_by_library,
    catalog_counts,
)


def test_primary_source_list_sizes():
    """Sizes as transcribed from upstream ``__all__`` on 2026-07-30."""
    assert len(NEURALFORECAST_MODELS) == 37
    assert len(NEURALFORECAST_AUTOMODELS) == 36
    assert len(STATSFORECAST_MODELS) == 41
    assert len(MLFORECAST_AUTOMODELS) == 8
    assert len(RECONCILIATION_METHODS) == 10


def test_no_duplicate_names_within_any_primary_list():
    for names in (
        NEURALFORECAST_MODELS,
        NEURALFORECAST_AUTOMODELS,
        STATSFORECAST_MODELS,
        MLFORECAST_AUTOMODELS,
        RECONCILIATION_METHODS,
    ):
        assert len(set(names)) == len(names)


def test_every_automodel_has_a_base_model():
    bases = set(NEURALFORECAST_MODELS)
    missing = [a for a in NEURALFORECAST_AUTOMODELS if a[4:] not in bases]
    assert not missing, f"AutoModels without a base estimator: {missing}"


def test_catalog_ids_are_unique():
    ids = [e.model_id for e in build_catalog()]
    assert len(set(ids)) == len(ids)


def test_library_subtotals_sum_to_total():
    counts = catalog_counts()
    subtotals = {k: v for k, v in counts.items() if not k.startswith("_") and k != "TOTAL"}
    assert sum(subtotals.values()) == counts["TOTAL"]


def test_catalog_is_strictly_larger_than_v2():
    assert catalog_counts()["TOTAL"] > 84


def test_seasonal_naive_control_is_present():
    """SeasonalNaive is the reference nothing has ever beaten; it must always be sweepable."""
    ids = {e.model_id for e in build_catalog()}
    assert "sf-seasonalnaive" in ids
    assert "sf-naive" in ids
    assert "uniform" in ids


def test_intermittent_family_is_present():
    """Per-number occurrence is an intermittent series; Croston-family models apply."""
    families = {e.model_id: e.family for e in build_catalog()}
    intermittent = [m for m, f in families.items() if f == "intermittent"]
    assert len(intermittent) == 6


def test_conformal_model_is_registered():
    ids = {e.model_id for e in build_catalog()}
    assert "sf-conformalseasonalpool" in ids


def test_every_tsfm_entry_declares_a_repo_id():
    for entry in build_catalog():
        if entry.library == "tsfm":
            assert entry.repo_id, f"{entry.model_id} has no repo_id"


def test_unpinned_revisions_are_flagged_not_fabricated():
    """An unverified commit SHA is worse than an explicit gap."""
    unpinned = [e.model_id for e in build_catalog() if e.revision_status == "UNPINNED"]
    assert unpinned, "expected TSFM entries to be explicitly unpinned"
    for entry in build_catalog():
        if entry.revision_status == "UNPINNED":
            assert entry.revision is None


def test_ttm_uses_the_apache_licensed_repo():
    """ibm-research/ttm-r3 is non-commercial; the granite r2 checkpoint is Apache-2.0."""
    entry = next(e for e in build_catalog() if e.model_id == "granite-ttm-r2")
    assert entry.repo_id == "ibm-granite/granite-timeseries-ttm-r2"
    assert entry.license == "Apache-2.0"
    assert not any(e.repo_id == "ibm-research/ttm-r3" for e in build_catalog())


def test_gated_model_is_kept_as_an_explicit_blocked_entry():
    entry = next(e for e in build_catalog() if e.model_id == "t0-alpha")
    assert "GATED" in entry.notes


def test_fft_models_are_annotated_with_the_precision_constraint():
    fft = [e for e in build_catalog() if e.model_id in ("nf-timesnet", "nf-fedformer")]
    assert fft and all("32-true" in e.notes for e in fft)


def test_multivariate_models_require_n_series():
    for entry in build_catalog():
        if entry.multivariate:
            assert entry.requires_n_series, f"{entry.model_id} is multivariate but not flagged"


def test_every_entry_records_its_primary_source():
    for entry in build_catalog():
        row = entry.to_row()
        if entry.library in (
            "neuralforecast",
            "neuralforecast_auto",
            "statsforecast",
            "mlforecast_auto",
            "hierarchicalforecast",
        ):
            assert row["primary_source"], f"{entry.model_id} lacks provenance"


def test_by_library_partitions_the_catalog():
    grouped = catalog_by_library()
    assert sum(len(v) for v in grouped.values()) == len(build_catalog())


def test_tsfm_repo_ids_are_unique():
    repos = [s["repo_id"] for s in TSFM_MODELS]
    assert len(set(repos)) == len(repos)
