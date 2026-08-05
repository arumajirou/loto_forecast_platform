"""Isolated Darts 0.46.1 discovery, evaluation, and certification contracts."""

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

__all__ = [
    "CandidateAggregate",
    "ChampionDecision",
    "DartsRequest",
    "DartsResponse",
    "GameGeometry",
    "MetricVector",
    "OOFConfig",
    "RunProvenance",
    "aggregate_all",
    "build_expanding_folds",
    "build_run_provenance",
    "evaluate_predictions",
    "run_oof",
    "seal_predictions",
    "select_champion",
    "verify_prediction_seal",
]
