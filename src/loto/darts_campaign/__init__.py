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
from .torch_models import (
    TORCH_MODEL_IDENTITIES,
    TorchCampaignConfig,
    TorchDeviceContract,
    TorchModelConfig,
    TorchParallelPolicy,
    TorchRuntimeObservation,
    TorchTrainingContract,
    build_parallel_plan,
    certify_device_use,
    run_torch_matrix,
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
    "TORCH_MODEL_IDENTITIES",
    "RegressionCampaignConfig",
    "RegressionLagContract",
    "RegressionModelConfig",
    "RunProvenance",
    "TorchCampaignConfig",
    "TorchDeviceContract",
    "TorchModelConfig",
    "TorchParallelPolicy",
    "TorchRuntimeObservation",
    "TorchTrainingContract",
    "aggregate_all",
    "build_expanding_folds",
    "build_mlforecast_parity_payload",
    "build_parallel_plan",
    "build_run_provenance",
    "certify_device_use",
    "evaluate_predictions",
    "run_oof",
    "run_regression_matrix",
    "run_torch_matrix",
    "seal_predictions",
    "select_champion",
    "verify_prediction_seal",
]
