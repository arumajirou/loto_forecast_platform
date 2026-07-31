from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from loto.contracts import CandidateProbability, DecodedCombination, ForecastPackage


def test_candidate_probability_rejects_out_of_range_number():
    with pytest.raises(ValidationError):
        CandidateProbability(candidate_number=38, probability=0.2, rank_score=0.1)


def test_decoded_combination_requires_strictly_ascending_unique_numbers():
    with pytest.raises(ValidationError):
        DecodedCombination(numbers=[1, 2, 2, 7, 9, 11, 15], score=1.0)


def test_forecast_package_accepts_legal_loto7_combination():
    package = ForecastPackage(
        forecast_id="fc-1",
        draw_id="loto7-700",
        model_id="model-1",
        data_version="data-v1",
        feature_set_id="features-v1",
        created_at=datetime.now(UTC),
        draw_time=datetime.now(UTC) + timedelta(minutes=1),
        combination=DecodedCombination(numbers=[1, 4, 9, 15, 22, 30, 37], score=1.0),
        candidates=[
            CandidateProbability(candidate_number=i, probability=7 / 37, rank_score=0.0)
            for i in range(1, 38)
        ],
    )
    assert package.combination.numbers[-1] == 37
