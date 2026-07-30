from loto.evaluation.theory import LotterySpec, solve_within_tau_optimum


def test_loto7_theoretical_decoder_is_legal_and_deterministic():
    first = solve_within_tau_optimum(LotterySpec(n=37, k=7, tau=1))
    second = solve_within_tau_optimum(LotterySpec(n=37, k=7, tau=1))
    assert first == second
    assert first["legal_ascending"]["opt"] is True
