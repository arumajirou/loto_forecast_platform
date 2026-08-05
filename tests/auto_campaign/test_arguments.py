from loto.auto_campaign.arguments import (
    BASE_AUTO_ARGUMENTS,
    FIT_ARGUMENTS,
    NEURALFORECAST_ARGUMENTS,
    build_argument_catalog,
)


def test_all_common_arguments_are_catalogued() -> None:
    rows = build_argument_catalog()
    seen = {(row["layer"], row["argument"]) for row in rows}
    expected = (
        {("BaseAuto", name) for name in BASE_AUTO_ARGUMENTS}
        | {("NeuralForecast", name) for name in NEURALFORECAST_ARGUMENTS}
        | {("fit", name) for name in FIT_ARGUMENTS}
    )
    assert seen == expected
    assert len(rows) == 32
