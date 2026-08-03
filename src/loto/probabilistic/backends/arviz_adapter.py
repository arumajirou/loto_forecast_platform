from __future__ import annotations

from typing import Any

import numpy as np

from loto.probabilistic.backends.base import ProbabilisticBackend
from loto.probabilistic.models.native_common import bounded_training_data, categorical_counts
from loto.probabilistic.native import NativePosterior


def _dirichlet_draws(alpha: np.ndarray, draws: int, rng: np.random.Generator) -> np.ndarray:
    return np.stack(
        [np.stack([rng.dirichlet(row) for row in alpha], axis=0) for _ in range(draws)], axis=0
    )


def _log_likelihood(draws: np.ndarray, y: np.ndarray) -> np.ndarray:
    values = np.asarray(y, dtype=int)
    if values.ndim == 1:
        values = values[:, None]
    result = np.empty((draws.shape[0], len(values) * values.shape[1]), dtype=float)
    for sample in range(draws.shape[0]):
        chosen = draws[sample][np.arange(values.shape[1])[None, :], values]
        result[sample] = np.log(np.maximum(chosen, 1e-15)).reshape(-1)
    return result


class ArviZStackingBackend(ProbabilisticBackend):
    backend_id = "arviz"
    modules = ("arviz",)
    implemented = True

    def execute(
        self,
        spec: Any,
        *,
        y: np.ndarray,
        classes: int,
        target_mode: str,
        geometry: Any,
        config: Any,
        seed: int,
        inference_profile_id: str | None = None,
    ) -> NativePosterior:
        probe = self.probe()
        if not probe.available:
            raise RuntimeError(f"ArviZ backend unavailable: {probe.detail}")
        import arviz as az  # type: ignore

        values = bounded_training_data(y, config.native_max_train_rows).astype(int)
        if values.ndim == 1:
            values = values[:, None]
        rng = np.random.default_rng(seed)
        draws_count = max(64, int(config.native_draws))
        age = np.arange(len(values) - 1, -1, -1, dtype=float)
        definitions = {
            "uniform": np.full((values.shape[1], classes), config.prior_concentration),
            "expanding": config.prior_concentration + categorical_counts(values, classes),
            "rolling": config.prior_concentration
            + categorical_counts(values[-min(config.rolling_window, len(values)) :], classes),
            "discounted": config.prior_concentration
            + categorical_counts(values, classes, np.power(config.discount_factor, age)),
        }
        model_draws = {
            name: _dirichlet_draws(alpha, draws_count, rng) for name, alpha in definitions.items()
        }
        idata_map: dict[str, Any] = {}
        for name, draws in model_draws.items():
            log_likelihood = _log_likelihood(draws, values)
            # ArviZ requires chain/draw axes. A harmless dummy posterior is included because
            # some ArviZ releases reject log_likelihood-only inputs.
            try:
                idata_map[name] = az.from_dict(
                    posterior={"dummy": np.zeros((1, draws_count, 1), dtype=float)},
                    log_likelihood={"observed": log_likelihood[None, :, :]},
                )
            except TypeError:
                idata_map[name] = az.from_dict(
                    {
                        "posterior": {"dummy": np.zeros((1, draws_count, 1), dtype=float)},
                        "log_likelihood": {"observed": log_likelihood[None, :, :]},
                    }
                )
        try:
            comparison = az.compare(idata_map, ic="loo", method="stacking", scale="log")
        except TypeError:
            comparison = az.compare(idata_map, method="stacking")
        weights = np.asarray(
            [float(comparison.loc[name, "weight"]) for name in definitions], dtype=float
        )
        weights = np.maximum(weights, 0.0)
        weights /= np.maximum(weights.sum(), 1e-15)
        stacked_draws = np.zeros_like(next(iter(model_draws.values())))
        for weight, draws in zip(weights, model_draws.values(), strict=True):
            stacked_draws += weight * draws
        diagnostics: dict[str, Any] = {
            "posterior_finite": bool(np.isfinite(stacked_draws).all()),
            "probability_simplex_valid": True,
            "rhat_max": None,
            "ess_bulk_min": None,
            "ess_tail_min": None,
            "divergences": None,
            "elbo_finite": None,
            "elbo_stable": None,
            "loo_warning": bool(comparison.get("warning", False).any())
            if hasattr(comparison, "get")
            else None,
        }
        return NativePosterior(
            model_id=spec.model_id,
            backend=self.backend_id,
            family=spec.family,
            target_mode=target_mode,
            game=geometry.key,
            probability_draws=stacked_draws,
            metadata={
                "native_graph_id": spec.native_graph_id,
                "training_rows_used": len(values),
                "algorithm": "PSIS-LOO stacking",
                "component_models": list(definitions),
                "stacking_weights": dict(zip(definitions, weights.tolist(), strict=True)),
                "library_version": getattr(az, "__version__", "unknown"),
            },
            diagnostics=diagnostics,
            native_payload=comparison,
        )


__all__ = ["ArviZStackingBackend"]
