from loto.evaluation.promotion import PromotionInputs, assess_promotion


def test_formal_promotion_requires_shadow_50_and_all_gates():
    decision = assess_promotion(PromotionInputs(
        candidate_model_id="candidate", champion_model_id="champion",
        hits_candidate=1.55, hits_champion=1.35,
        brier_candidate=0.150, brier_champion=0.151,
        logloss_candidate=0.49, logloss_champion=0.50,
        ece_candidate=0.03, ece_champion=0.03,
        fold_wins=4, total_folds=6, bootstrap_ci_low=0.01,
        shadow_draws=50, critical_failures=0,
    ))
    assert decision.decision == "PROMOTE_FORMAL"


def test_evidence_shortage_is_continue_not_reject():
    decision = assess_promotion(PromotionInputs(
        candidate_model_id="candidate", champion_model_id="champion",
        hits_candidate=1.47, hits_champion=1.35,
        brier_candidate=0.150, brier_champion=0.151,
        logloss_candidate=0.49, logloss_champion=0.50,
        ece_candidate=0.03, ece_champion=0.03,
        fold_wins=4, total_folds=6, bootstrap_ci_low=-0.01,
        shadow_draws=10, critical_failures=0,
    ))
    assert decision.decision == "CONTINUE_EVALUATION"
