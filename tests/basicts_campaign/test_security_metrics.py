from __future__ import annotations

import numpy as np
import pytest

from loto.basicts_campaign.metrics import evaluate_predictions
from loto.basicts_campaign.protocol import ImportReference
from loto.basicts_campaign.security import ConfigImportRejected, validate_import_reference


def test_config_import_allowlist() -> None:
    validate_import_reference(ImportReference(module="basicts.models.DLinear", name="DLinear"))
    validate_import_reference(ImportReference(module="torch.optim", name="Adam"))


@pytest.mark.parametrize("module", ["os", "pathlib", "subprocess", "loto.probabilistic"])
def test_config_import_rejects_unapproved_modules(module: str) -> None:
    with pytest.raises(ConfigImportRejected):
        validate_import_reference(ImportReference(module=module, name="Object"))


def test_hit_at_one_metrics() -> None:
    actual = np.asarray([[1.0, 5.0], [4.0, 8.0]])
    predicted = np.asarray([[2.0, 7.0], [4.0, 7.0]])
    result = evaluate_predictions(actual, predicted)
    assert result["hit_at_1"] == 0.75
    assert result["position_hit_at_1"] == [1.0, 0.5]
    assert result["all_position_hit_at_1"] == 0.5
    assert result["mae"] == 1.0
