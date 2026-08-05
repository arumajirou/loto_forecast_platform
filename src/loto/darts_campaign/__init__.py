"""Isolated Darts discovery, evaluation, and certification contracts."""

from .artifacts import seal_predictions, verify_prediction_seal
from .campaign import (
    CandidateAggregate,
    ChampionDecision,
    MetricVector,
    OOFConfig,
    aggregate_all,
    build_expanding_folds,
    run_oof,
    select_champion,
)
from .evaluation import evaluate_predictions
from .protocol import DartsRequest, DartsResponse, GameGeometry
from .provenance import RunProvenance, build_run_provenance
from .regression_models import (
    REGRESSION_MODEL_IDENTITIES,
    RegressionCampaignConfig,
    RegressionLagContract,
    RegressionModelConfig,
    build_mlforecast_parity_payload,
    run_regression_matrix,
)

__all__ = [
    "CandidateAggregate",
    "ChampionDecision",
    "DartsRequest",
    "DartsResponse",
    "GameGeometry",
    "MetricVector",
    "OOFConfig",
    "REGRESSION_MODEL_IDENTITIES",
    "RegressionCampaignConfig",
    "RegressionLagContract",
    "RegressionModelConfig",
    "RunProvenance",
    "aggregate_all",
    "build_expanding_folds",
    "build_mlforecast_parity_payload",
    "build_run_provenance",
    "evaluate_predictions",
    "run_oof",
    "run_regression_matrix",
    "seal_predictions",
    "select_champion",
    "verify_prediction_seal",
]
