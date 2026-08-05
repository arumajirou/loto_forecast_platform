from loto.statsforecast.sealing import seal_prospective_prediction, verify_prediction_seal


def test_prospective_seal_detects_tampering() -> None:
    sealed = seal_prospective_prediction(
        {"game": "numbers4", "prediction": [1, 2, 3, 4], "actual_known": False}
    )
    assert verify_prediction_seal(sealed)
    sealed["prediction"][0] = 9
    assert not verify_prediction_seal(sealed)
