from __future__ import annotations

from dataclasses import dataclass

from loto.contracts import PromotionDecision


@dataclass(frozen=True)
class PromotionInputs:
    candidate_model_id: str
    champion_model_id: str
    hits_candidate: float
    hits_champion: float
    brier_candidate: float
    brier_champion: float
    logloss_candidate: float
    logloss_champion: float
    ece_candidate: float
    ece_champion: float
    fold_wins: int
    total_folds: int
    bootstrap_ci_low: float
    shadow_draws: int
    critical_failures: int = 0


def assess_promotion(i: PromotionInputs) -> PromotionDecision:
    hits_improvement = i.hits_candidate - i.hits_champion
    gates = {
        "no_critical_failures": i.critical_failures == 0,
        "majority_fold_wins": i.fold_wins > i.total_folds / 2,
        "provisional_effect": hits_improvement >= 0.10,
        "formal_effect": hits_improvement >= 0.15,
        "bootstrap_positive": i.bootstrap_ci_low > 0,
        "brier_noninferior": i.brier_candidate <= i.brier_champion * 1.02,
        "logloss_noninferior": i.logloss_candidate <= i.logloss_champion * 1.02,
        "ece_noninferior": i.ece_candidate <= i.ece_champion + 0.02,
        "shadow_minimum": i.shadow_draws >= 20,
        "shadow_formal": i.shadow_draws >= 50,
    }
    core = all(gates[k] for k in (
        "no_critical_failures", "majority_fold_wins", "provisional_effect",
        "brier_noninferior", "logloss_noninferior", "ece_noninferior",
    ))
    if core and gates["formal_effect"] and gates["bootstrap_positive"] and gates["shadow_formal"]:
        decision = "PROMOTE_FORMAL"
    elif core and gates["bootstrap_positive"] and gates["shadow_minimum"]:
        decision = "PROMOTE_PROVISIONAL"
    else:
        decision = "CONTINUE_EVALUATION"
    reasons = [f"hits_improvement={hits_improvement:.4f}"]
    reasons.extend(f"{name}={value}" for name, value in gates.items())
    return PromotionDecision(
        candidate_model_id=i.candidate_model_id,
        champion_model_id=i.champion_model_id,
        decision=decision,
        reasons=reasons,
        gates=gates,
    )
