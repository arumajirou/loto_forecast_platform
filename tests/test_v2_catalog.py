from loto.models.catalog import get_model_spec, list_model_specs


def test_catalog_contains_required_families():
    ids = {item.model_id for item in list_model_specs()}
    assert {"uniform", "frequency", "logistic", "stats-autoarima", "mlforecast-lightgbm", "nf-nhits", "chronos-bolt-tiny"} <= ids


def test_model_availability_is_explicit():
    row = get_model_spec("nf-nhits").to_dict()
    assert isinstance(row["available"], bool)
    assert row["library"] == "neuralforecast"
