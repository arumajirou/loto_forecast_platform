from __future__ import annotations

from typing import Any

import numpy as np

from loto.probabilistic.models.copula_native import fit_gaussian_copula_categorical
from loto.probabilistic.models.native_common import bounded_training_data
from loto.probabilistic.models.pymc_native import PyMCGraph


def build_gaussian_copula_graph(
    spec: Any,
    *,
    y: np.ndarray,
    classes: int,
    target_mode: str,
    geometry: Any,
    config: Any,
    seed: int,
) -> PyMCGraph:
    del target_mode
    import pymc as pm  # type: ignore
    import pytensor.tensor as pt  # type: ignore

    values = bounded_training_data(y, config.native_max_train_rows).astype(int)
    if values.ndim == 1:
        values = values[:, None]
    state = fit_gaussian_copula_categorical(
        values,
        game=geometry.key,
        classes=classes,
        config=config,
        seed=seed,
    )
    complete = state.latent_scores[np.isfinite(state.latent_scores).all(axis=1)]
    if len(complete) < max(3, state.positions + 1):
        raise ValueError(
            "Gaussian copula requires enough complete rows for correlation inference"
        )
    with pm.Model() as model:
        scale_dist = pm.LogNormal.dist(
            mu=0.0,
            sigma=float(config.copula_scale_prior_sigma),
            shape=state.positions,
        )
        chol, correlation, scales = pm.LKJCholeskyCov(
            "copula_cholesky",
            n=state.positions,
            eta=float(config.copula_lkj_eta),
            sd_dist=scale_dist,
            compute_corr=True,
        )
        pm.MvNormal(
            "copula_latent_observed",
            mu=pt.zeros(state.positions),
            chol=chol,
            observed=complete,
        )
        pm.Deterministic("copula_correlation_matrix", correlation)
        pm.Deterministic("copula_scales", scales)
        pm.Deterministic(
            "next_probabilities",
            pt.as_tensor_variable(state.marginal_probabilities),
        )
    return PyMCGraph(
        model=model,
        graph_id=spec.native_graph_id,
        metadata={
            "training_rows_used": len(values),
            "classes": classes,
            "positions": int(values.shape[1]),
            "seed": seed,
            "marginal_probabilities": state.marginal_probabilities.tolist(),
            "thresholds": state.thresholds.tolist(),
            "initial_correlation": state.correlation.tolist(),
            "label_order": [list(labels) for labels in state.label_order],
            "complete_rows": int(len(complete)),
            "latent_transform": state.metadata["latent_transform"],
            "threshold_fit_scope": state.metadata["threshold_fit_scope"],
        },
    )


__all__ = ["build_gaussian_copula_graph"]
