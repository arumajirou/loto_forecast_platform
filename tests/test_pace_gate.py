import numpy as np

from loto.evaluation.pace_gate import PaceConfig, PaceGate


def test_one_sided_gate_never_claims_reverse_rejection_from_low_e_value():
    gate = PaceGate(PaceConfig(min_draws=2))
    for _ in range(100):
        gate.update(np.zeros(7, dtype=bool), np.ones(7, dtype=bool))
    assert gate.decision() == "INCONCLUSIVE"
