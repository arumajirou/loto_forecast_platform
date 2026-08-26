from __future__ import annotations

from loto.evaluation.parameter_sweep.contracts import (
    ModelInventoryRow,
    ParameterCategory,
    ParameterDescriptor,
    SearchSpaceStatus,
)
from loto.evaluation.parameter_sweep.search_spaces import build_search_spaces
from loto.evaluation.parameter_sweep.smoke import classify_failure, normalized_smoke_status
from loto.evaluation.parameter_sweep.trials import build_ofat_trials


def _row(
    model_id: str,
    *,
    task: str = "position_series",
    library: str = "statsforecast",
    parameter: str | None = None,
    reason: str | None = "NOT_YET_SMOKED",
) -> ModelInventoryRow:
    parameters = ()
    if parameter is not None:
        parameters = (
            ParameterDescriptor(
                name=parameter,
                required=False,
                category=ParameterCategory.TUNABLE_HYPERPARAMETER,
                tunable=True,
                provenance=("test",),
                reason="test probe",
            ),
        )
    return ModelInventoryRow(
        model_id=model_id,
        source="catalog",
        library=library,
        class_name="FakeModel",
        family="test",
        task=task,
        provider=library,
        adapter="test",
        runtime=library,
        supports_bingo5=None if reason == "NOT_YET_SMOKED" else False,
        reason_if_not_supported=reason,
        parameter_inventory=parameters,
    )


def test_alpha_search_is_bounded_and_keeps_certification_anchor() -> None:
    row = _row("sf-ses", parameter="alpha")
    row = row.model_copy(update={"certification_params": {"alpha": 0.3}})
    [space] = build_search_spaces([row], train_rows=410)
    assert space.status is SearchSpaceStatus.READY
    assert space.trial_budget <= 100
    assert len(space.dimensions) == 1
    assert space.dimensions[0].parameter == "alpha"
    assert 0.3 in space.dimensions[0].values
    assert len(space.dimensions[0].values) < 10


def test_ofat_trials_never_create_cartesian_product() -> None:
    row = _row("sf-seasonal-es", parameter="alpha")
    row = row.model_copy(
        update={
            "certification_params": {
                "alpha": 0.3,
            }
        }
    )
    [space] = build_search_spaces([row], train_rows=410)
    trials = build_ofat_trials(space)
    assert trials[0]["kind"] == "baseline"
    assert trials[0]["params"]["alpha"] == 0.3
    assert len(trials) == len(space.dimensions[0].values)
    assert all(set(trial["params"]) == {"alpha"} for trial in trials)


def test_unapproved_tunable_parameter_fails_closed() -> None:
    row = _row("nf-example", library="neuralforecast", parameter="mystery_width")
    [space] = build_search_spaces([row], train_rows=410)
    assert space.status is SearchSpaceStatus.UNRESOLVED_PARAMETER
    assert space.unresolved_parameters == ("mystery_width",)
    assert space.trial_budget == 0


def test_current_unified_route_gap_is_not_searchable() -> None:
    row = _row("mlfa-example", library="mlforecast_auto", parameter="learning_rate")
    [space] = build_search_spaces([row], train_rows=410)
    assert space.status is SearchSpaceStatus.NOT_ROUTABLE
    assert "PositionSeriesWorker" in space.reason
    assert space.trial_budget == 0


def test_nanmodel_is_expected_negative_and_never_searchable() -> None:
    row = _row("sf-nanmodel", reason="EXPECTED_NEGATIVE_CONTROL")
    row = row.model_copy(update={"class_name": "NaNModel"})
    [space] = build_search_spaces([row], train_rows=410)
    assert space.status is SearchSpaceStatus.EXPECTED_NEGATIVE_CONTROL
    assert space.trial_budget == 0
    assert normalized_smoke_status({"candidate_id": "sf-nanmodel", "status": "FAILED"}) == (
        "EXPECTED_NEGATIVE_CONTROL"
    )


def test_reconciliation_method_is_not_standalone() -> None:
    row = _row("hf-bottomup", task="reconciliation")
    [space] = build_search_spaces([row], train_rows=410)
    assert space.status is SearchSpaceStatus.NON_STANDALONE_METHOD
    assert space.trial_budget == 0


def test_failure_taxonomy_separates_constructor_and_nonfinite() -> None:
    constructor = {
        "status": "FAILED",
        "reason": "one or more approved seeds failed",
        "failures": [
            {
                "type": "TypeError",
                "reason": "AutoRegressive.__init__() missing 1 required positional argument: 'lags'",
            }
        ],
    }
    nonfinite = {
        "status": "FAILED",
        "reason": "one or more approved seeds failed",
        "failures": [{"type": "ValueError", "reason": "prediction contains NaN/Inf"}],
    }
    assert classify_failure(constructor).value == "CONSTRUCTOR_ERROR"
    assert classify_failure(nonfinite).value == "NONFINITE_OUTPUT"
