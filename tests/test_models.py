import numpy as np
import pandas as pd

from loto.models.base import ModelCapabilities
from loto.models.baselines import FrequencyCandidateAdapter, UniformCandidateAdapter


def test_adapters_declare_capabilities_and_emit_37_probabilities():
    uniform = UniformCandidateAdapter()
    assert uniform.capabilities & ModelCapabilities.PROBABILITY_PREDICTION
    pred = uniform.predict(pd.DataFrame({"candidate_number": range(1, 38)}))
    assert len(pred) == 37
    assert np.allclose(pred["probability"], 7 / 37)


def test_frequency_adapter_uses_only_supplied_history():
    model = FrequencyCandidateAdapter(alpha=1.0)
    history = pd.DataFrame({"candidate_number": [1, 1, 2, 3], "selected": [1, 1, 1, 0]})
    model.fit(history)
    pred = model.predict(pd.DataFrame({"candidate_number": range(1, 38)})).set_index(
        "candidate_number"
    )
    assert pred.loc[1, "probability"] > pred.loc[37, "probability"]
