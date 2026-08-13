from loto.adapters.autogluon.inventory import SOURCE_ENSEMBLE_SPECS, SOURCE_MODEL_SPECS
from loto.adapters.gluonts.p6_registry import EXPECTED_MODELS
from loto.models.catalog_full import build_catalog
from loto.models.implementation_catalog import (
    AUTOGLOUON_BROAD_V1_ID,
    GLUONTS_BROAD_V1_ID,
    SKFORECAST_BROAD_V1_ID,
    SKFORECAST_SOURCE_REVISION,
    SKFORECAST_VERSION,
    autogluon_implementation_identities,
    expanded_implementation_catalog,
    expanded_inventory_counts,
    gluonts_implementation_identities,
    skforecast_implementation_identities,
)
from loto.models.skforecast_inventory import SKFORECAST_IMPLEMENTATION_SPECS


def test_autogluon_expansion_uses_all_source_models_and_unique_ensemble_classes() -> None:
    rows = autogluon_implementation_identities()
    model_rows = [row for row in rows if row.source_kind == "autogluon_source_model"]
    ensemble_rows = [row for row in rows if row.source_kind == "autogluon_source_ensemble"]

    assert len(SOURCE_MODEL_SPECS) == 29
    assert len(model_rows) == len(SOURCE_MODEL_SPECS)
    assert len(ensemble_rows) == len({spec.expected_class_name for spec in SOURCE_ENSEMBLE_SPECS})
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


def test_gluonts_expansion_uses_all_nine_deterministic_p6_registry_models() -> None:
    rows = gluonts_implementation_identities()

    assert len(rows) == 9
    assert tuple(row.class_name for row in rows) == EXPECTED_MODELS
    assert len({row.implementation_id for row in rows}) == len(rows)
    assert all(row.source_kind == "gluonts_p6_registry" for row in rows)
    assert all(row.canonical_v1_model_id == GLUONTS_BROAD_V1_ID for row in rows)
    assert all(row.execution_surface == "gluonts_p6_provider" for row in rows)
    assert all(row.runtime_status == "NOT_RUN" for row in rows)
    assert not any(row.runtime_certified for row in rows)
    assert all("cpu_p6_contract" in row.capabilities for row in rows)
    assert all("GPU support is not certified" in row.notes for row in rows)

    assert {row.implementation_id for row in rows} == {
        "gluonts-torch-deepnpts",
        "gluonts-torch-deepar",
        "gluonts-torch-tide",
        "gluonts-torch-simplefeedforward",
        "gluonts-torch-temporalfusiontransformer",
        "gluonts-torch-wavenet",
        "gluonts-torch-dlinear",
        "gluonts-torch-patchtst",
        "gluonts-torch-lagtst",
    }


def test_skforecast_phase4a_has_reviewed_27_identity_manifest() -> None:
    rows = skforecast_implementation_identities()
    ids = {row.implementation_id for row in rows}

    assert len(SKFORECAST_IMPLEMENTATION_SPECS) == 27
    assert len(rows) == 27
    assert len(ids) == 27
    assert ids == {
        "skforecast-recursive-ridge",
        "skforecast-recursive-histgb",
        "skforecast-recursive-lightgbm",
        "skforecast-recursive-xgboost",
        "skforecast-recursive-catboost",
        "skforecast-recursive-classifier-logistic",
        "skforecast-direct-ridge",
        "skforecast-recursive-multiseries-ridge",
        "skforecast-direct-multivariate-ridge",
        "skforecast-equivalent-date",
        "skforecast-stats-arar",
        "skforecast-stats-arima",
        "skforecast-stats-ets",
        "skforecast-stats-sarimax",
        "skforecast-stats-sktime-arima",
        "skforecast-stats-aeon-arima",
        "skforecast-stats-aeon-ets",
        "skforecast-rnn-lstm",
        "skforecast-rnn-gru",
        "skforecast-foundation-chronos2-amazon",
        "skforecast-foundation-chronos2-small",
        "skforecast-foundation-chronos2-synth",
        "skforecast-foundation-timesfm25",
        "skforecast-foundation-moirai2",
        "skforecast-foundation-tabicl-v2",
        "skforecast-foundation-tabpfn-ts3",
        "skforecast-foundation-t0",
    }
    assert all(row.canonical_v1_model_id == SKFORECAST_BROAD_V1_ID for row in rows)
    assert all(row.source_version == SKFORECAST_VERSION for row in rows)
    assert all(row.source_revision == SKFORECAST_SOURCE_REVISION for row in rows)
    assert not any(row.runtime_certified for row in rows)


def test_skforecast_phase4a_preserves_evidence_and_fail_closed_states() -> None:
    rows = {row.implementation_id: row for row in skforecast_implementation_identities()}

    assert sum(row.runtime_status == "OPERATOR_LOCAL_PASS" for row in rows.values()) == 15
    assert sum(row.runtime_status == "NOT_RUN" for row in rows.values()) == 10
    assert sum(row.evidence_class == "SOURCE_DECLARED" for row in rows.values()) == 9
    assert sum(row.evidence_class == "OPERATOR_LOCAL_EVIDENCE" for row in rows.values()) == 18

    classifier = rows["skforecast-recursive-classifier-logistic"]
    assert classifier.class_name == "ForecasterRecursiveClassifier"
    assert classifier.runtime_status == "NOT_RUN"

    moirai = rows["skforecast-foundation-moirai2"]
    assert moirai.runtime_status == "BLOCKED_DEPENDENCY_CONFLICT"
    assert moirai.routability == "BLOCKED"
    assert moirai.block_reason == "UPSTREAM_DEPENDENCY_CONFLICT"

    tabpfn = rows["skforecast-foundation-tabpfn-ts3"]
    assert tabpfn.runtime_status == "BLOCKED_INVALID_OR_EXPIRED_TOKEN"
    assert tabpfn.routability == "BLOCKED"
    assert tabpfn.block_reason == "INVALID_OR_EXPIRED_TOKEN"

    t0 = rows["skforecast-foundation-t0"]
    assert t0.runtime_status == "NOT_RUN"
    assert t0.runtime_certified is False


def test_skforecast_stats_algorithm_and_implementation_ids_are_separate() -> None:
    rows = {row.implementation_id: row for row in skforecast_implementation_identities()}

    assert rows["skforecast-stats-arima"].algorithm_id == "arima"
    assert rows["skforecast-stats-sktime-arima"].algorithm_id == "arima"
    assert rows["skforecast-stats-aeon-arima"].algorithm_id == "arima"
    assert rows["skforecast-stats-arima"].implementation_id != rows[
        "skforecast-stats-sktime-arima"
    ].implementation_id
    assert rows["skforecast-stats-ets"].algorithm_id == "ets"
    assert rows["skforecast-stats-aeon-ets"].algorithm_id == "ets"


def test_chronos2_model_ids_share_algorithm_but_not_implementation_id() -> None:
    rows = [
        row
        for row in skforecast_implementation_identities()
        if row.algorithm_id == "chronos-2"
    ]

    assert len(rows) == 3
    assert len({row.implementation_id for row in rows}) == 3
    assert {row.source_alias for row in rows} == {
        "amazon/chronos-2",
        "autogluon/chronos-2-small",
        "autogluon/chronos-2-synth",
    }


def test_expanded_v2_preserves_broad_v1_and_derives_current_phase_count() -> None:
    broad_v1 = build_catalog()
    expanded = expanded_implementation_catalog()
    counts = expanded_inventory_counts()

    assert len(broad_v1) == 174
    assert counts["broad_v1"] == 174
    assert counts["autogluon_broad_v1_umbrella_count"] == 1
    assert counts["autogluon_source_models"] == 29
    assert counts["autogluon_unique_ensembles"] == 8
    assert counts["autogluon_expanded_total"] == 37
    assert counts["gluonts_broad_v1_umbrella_count"] == 1
    assert counts["gluonts_p6_source_models"] == 9
    assert counts["gluonts_expanded_total"] == 9
    assert len(counts["gluonts_registry_sha256"]) == 64
    assert counts["skforecast_broad_v1_umbrella_count"] == 1
    assert counts["skforecast_expanded_total"] == 27
    assert counts["skforecast_evidence_class"] == {
        "OPERATOR_LOCAL_EVIDENCE": 18,
        "SOURCE_DECLARED": 9,
    }
    assert counts["skforecast_runtime_status"] == {
        "BLOCKED_DEPENDENCY_CONFLICT": 1,
        "BLOCKED_INVALID_OR_EXPIRED_TOKEN": 1,
        "NOT_RUN": 10,
        "OPERATOR_LOCAL_PASS": 15,
    }
    assert counts["by_library"]["autogluon"] == 37
    assert counts["by_library"]["gluonts"] == 9
    assert counts["by_library"]["skforecast"] == 27
    assert counts["expanded_v2"] == len(expanded) == 244
    assert counts["delta_vs_broad_v1"] == 70
    assert len({row.implementation_id for row in expanded}) == len(expanded)


def test_expanded_v2_replaces_three_broad_umbrellas() -> None:
    broad_ids = {entry.model_id for entry in build_catalog()}
    expanded_ids = {row.implementation_id for row in expanded_implementation_catalog()}
    replaced = {
        AUTOGLOUON_BROAD_V1_ID,
        GLUONTS_BROAD_V1_ID,
        SKFORECAST_BROAD_V1_ID,
    }

    assert replaced <= broad_ids
    assert not (replaced & expanded_ids)
    assert broad_ids - replaced <= expanded_ids
    assert "autogluon-deepar" in expanded_ids
    assert "gluonts-torch-deepar" in expanded_ids
    assert "skforecast-recursive-classifier-logistic" in expanded_ids
    assert "skforecast-stats-sarimax" in expanded_ids
    assert "skforecast-foundation-tabicl-v2" in expanded_ids
