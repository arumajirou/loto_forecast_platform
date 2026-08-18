"""Leakage-safe development-only adapter for probabilistic canonical identities.

This module deliberately separates *route resolution* from *scientific scoring*.
A prediction is produced from a history-only :class:`DatasetBundle`; the target
row is not present in that bundle.  The caller is responsible for persisting and
SHA-256 sealing the prediction before reading the target actual.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Sequence

import numpy as np
import pandas as pd

from loto.game.geometry import geometry_for, known_games
from loto.probabilistic.catalog import (
    get_probabilistic_model_spec,
    list_probabilistic_model_specs,
)
from loto.probabilistic.compatibility import compatible_task, decide_compatibility
from loto.probabilistic.config import execution_fingerprint, stable_hash
from loto.probabilistic.contracts import ProbabilisticRunConfig
from loto.probabilistic.dataset import bundle_from_frame
from loto.probabilistic.lifecycle import _fit_predict_once
from loto.probabilistic.native_registry import get_native_implementation


class ProbabilisticScientificRouteError(RuntimeError):
    """Raised when a scientific probabilistic route cannot produce a valid prediction."""


@dataclass(frozen=True, slots=True)
class ProbabilisticScientificRoute:
    model_id: str
    family: str
    game: str
    target_mode: str | None
    backend: str
    inference_profile_id: str | None
    resource_class: str | None
    allowed: bool
    reason_code: str
    details: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ScientificProbabilisticBudget:
    """Frozen common budget for the TAJ-21 probabilistic scientific adapter."""

    posterior_draws: int = 512
    native_chains: int = 1
    native_warmup: int = 100
    native_draws: int = 128
    native_svi_steps: int = 500
    native_particles: int = 1
    native_max_train_rows: int = 500
    subset_max_iter: int = 500


@dataclass(frozen=True, slots=True)
class ProbabilisticOOFPrediction:
    values: tuple[int, ...]
    probabilities: np.ndarray
    metadata: dict[str, Any]


def resolve_probabilistic_scientific_route(
    model_id: str,
    game: str,
    *,
    draw_order_verified: bool = False,
    exogenous_features_available: bool = False,
    exogenous_feature_count: int = 0,
) -> ProbabilisticScientificRoute:
    """Resolve exactly one canonical model/game route using the frozen primary-native path."""

    spec = get_probabilistic_model_spec(model_id)
    native = get_native_implementation(model_id)
    geometry = geometry_for(game)
    if native.primary_backend != spec.primary_backend or native.primary_profile != spec.primary_profile:
        raise ProbabilisticScientificRouteError(
            "probabilistic catalog/native primary route mismatch: "
            f"model={model_id} catalog=({spec.primary_backend},{spec.primary_profile}) "
            f"native=({native.primary_backend},{native.primary_profile})"
        )
    target_mode = compatible_task(spec, geometry)
    decision = decide_compatibility(
        spec,
        geometry=geometry,
        backend=native.primary_backend,
        profile_id=native.primary_profile,
        include_experimental=True,
        draw_order_verified=draw_order_verified,
        prior_profile_id=None,
        exogenous_features_available=exogenous_features_available,
        exogenous_feature_count=exogenous_feature_count,
    )
    return ProbabilisticScientificRoute(
        model_id=model_id,
        family=spec.family,
        game=game,
        target_mode=target_mode,
        backend=native.primary_backend,
        inference_profile_id=native.primary_profile,
        resource_class=decision.required_resource_class,
        allowed=bool(decision.allowed),
        reason_code=str(decision.reason_code),
        details=tuple(str(item) for item in decision.details),
    )


def build_probabilistic_scientific_plan(
    games: Sequence[str] | None = None,
) -> tuple[ProbabilisticScientificRoute, ...]:
    """Return all probabilistic canonical identity x game rows with explicit route status."""

    selected_games = tuple(games) if games is not None else tuple(known_games())
    if not selected_games or len(set(selected_games)) != len(selected_games):
        raise ValueError("games must be non-empty and unique")
    known = set(known_games())
    unknown = sorted(set(selected_games).difference(known))
    if unknown:
        raise ValueError(f"unknown games: {unknown}")

    specs = list_probabilistic_model_specs()
    routes = tuple(
        resolve_probabilistic_scientific_route(spec.model_id, game)
        for game in selected_games
        for spec in specs
    )
    expected = len(specs) * len(selected_games)
    keys = {(route.game, route.model_id) for route in routes}
    if len(routes) != expected or len(keys) != expected:
        raise ProbabilisticScientificRouteError(
            "probabilistic scientific plan contains duplicate or missing model/game rows"
        )
    return routes


def _run_config(
    route: ProbabilisticScientificRoute,
    *,
    seed: int,
    device: str,
    budget: ScientificProbabilisticBudget,
) -> ProbabilisticRunConfig:
    if device not in {"auto", "cpu", "cuda"}:
        raise ValueError(f"unsupported probabilistic scientific device: {device}")
    gpu_enabled = device in {"auto", "cuda"}
    return ProbabilisticRunConfig(
        profile="standard",
        games=[route.game],
        models=[route.model_id],
        seeds=[int(seed)],
        backend_policy="primary_native",
        backends=[route.backend],
        include_experimental=True,
        outer_workers=1,
        max_gpu_jobs=1 if gpu_enabled else 0,
        max_heavy_cpu_jobs=1,
        gpu_priority=gpu_enabled,
        sealed_holdout=True,
        save_posterior_draws=False,
        native_device=device,
        posterior_draws=budget.posterior_draws,
        native_chains=budget.native_chains,
        native_warmup=budget.native_warmup,
        native_draws=budget.native_draws,
        native_svi_steps=budget.native_svi_steps,
        native_particles=budget.native_particles,
        native_max_train_rows=budget.native_max_train_rows,
        subset_max_iter=budget.subset_max_iter,
    )


def predict_probabilistic_from_history(
    history: pd.DataFrame,
    route: ProbabilisticScientificRoute,
    *,
    seed: int,
    protocol_hash: str,
    device: str = "auto",
    budget: ScientificProbabilisticBudget | None = None,
) -> ProbabilisticOOFPrediction:
    """Fit/infer/decode from history only; never accepts or reads the target actual row."""

    if not route.allowed:
        raise ProbabilisticScientificRouteError(
            f"scientific route is not executable: {route.model_id}/{route.game}: "
            f"{route.reason_code}: {route.details}"
        )
    if not route.target_mode:
        raise ProbabilisticScientificRouteError("allowed route is missing target_mode")
    if len(history) < 10:
        raise ProbabilisticScientificRouteError("scientific history must contain at least 10 rows")
    geometry = geometry_for(route.game)
    columns = geometry.column_names()
    missing = [column for column in columns if column not in history.columns]
    if missing:
        raise ProbabilisticScientificRouteError(
            f"scientific history missing target columns for {route.game}: {missing}"
        )

    train_frame = history[[column for column in ("draw_no", *columns) if column in history.columns]].copy()
    data_identity = stable_hash(
        {
            "game": route.game,
            "rows": train_frame[[*columns]].astype(int).values.tolist(),
            "draw_no": train_frame["draw_no"].astype(int).tolist()
            if "draw_no" in train_frame.columns
            else list(range(1, len(train_frame) + 1)),
        }
    )
    bundle = bundle_from_frame(
        train_frame,
        game=route.game,
        data_version=f"taj21-history-{data_identity[:16]}",
    )
    config = _run_config(
        route,
        seed=seed,
        device=device,
        budget=budget or ScientificProbabilisticBudget(),
    )
    spec = get_probabilistic_model_spec(route.model_id)
    fingerprints = execution_fingerprint(
        protocol_hash=protocol_hash,
        model_spec=spec,
        run_config=config,
        backend=route.backend,
        inference_profile_id=route.inference_profile_id,
    )
    posterior, mean, _summary, decoded, metrics, diagnostics = _fit_predict_once(
        model_id=route.model_id,
        bundle=bundle,
        target_mode=route.target_mode,
        backend_name=route.backend,
        inference_profile_id=route.inference_profile_id,
        config=config,
        train_end=bundle.rows,
        seed=seed,
        protocol_hash=protocol_hash,
        fingerprint=fingerprints["execution_fingerprint"],
    )
    if metrics:
        raise ProbabilisticScientificRouteError(
            "prediction-only probabilistic route unexpectedly evaluated target metrics"
        )
    values = np.asarray(decoded, dtype=float)
    if values.shape != (geometry.positions,) or not np.isfinite(values).all():
        raise ProbabilisticScientificRouteError(
            f"probabilistic prediction must have shape ({geometry.positions},), got {values.shape}"
        )
    legal = tuple(int(value) for value in decoded)
    geometry.validate_outcome(legal)
    probabilities = np.asarray(mean, dtype=float)
    if probabilities.ndim != 2 or not np.isfinite(probabilities).all():
        raise ProbabilisticScientificRouteError(
            f"probabilistic mean distribution is invalid: shape={probabilities.shape}"
        )
    if diagnostics.get("status") == "FAIL":
        raise ProbabilisticScientificRouteError(
            f"probabilistic posterior diagnostics failed: {diagnostics.get('failure_codes', [])}"
        )
    return ProbabilisticOOFPrediction(
        values=legal,
        probabilities=probabilities,
        metadata={
            "route": "probabilistic_primary_native_development_oof",
            "model_id": route.model_id,
            "family": route.family,
            "game": route.game,
            "target_mode": route.target_mode,
            "backend": route.backend,
            "inference_profile_id": route.inference_profile_id,
            "resource_class": route.resource_class,
            "protocol_hash": protocol_hash,
            "execution_fingerprint": fingerprints["execution_fingerprint"],
            "history_rows": bundle.rows,
            "history_data_version": bundle.data_version,
            "posterior_draw_count": posterior.draw_count,
            "probability_shape": list(probabilities.shape),
            "diagnostics": diagnostics,
            "target_actual_present_in_fit_bundle": False,
            "target_actual_read": False,
        },
    )
