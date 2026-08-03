from __future__ import annotations

from typing import Any

import numpy as np

from loto.probabilistic.backends.base import ProbabilisticBackend
from loto.probabilistic.backends.pymc_adapter import _diagnostics
from loto.probabilistic.catalog import get_inference_profile
from loto.probabilistic.models.native_common import (
    bounded_training_data,
    categorical_design,
    gaussian_kernel_probabilities,
    profile_settings,
)
from loto.probabilistic.native import NativePosterior


class PyMCBartBackend(ProbabilisticBackend):
    backend_id = "pymc_bart"
    modules = ("pymc", "pymc_bart", "arviz")
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
            raise RuntimeError(f"PyMC-BART backend unavailable: {probe.detail}")
        import pymc as pm  # type: ignore
        import pymc_bart as pmb  # type: ignore

        values = bounded_training_data(y, config.native_max_train_rows).astype(int)
        if values.ndim == 1:
            values = values[:, None]
        positions = values.shape[1]
        X_time, X_next_time = categorical_design(values, classes, degree=2, harmonics=2)
        position_train = np.tile(np.arange(positions), len(values))
        X_train = np.column_stack(
            [
                np.repeat(X_time, positions, axis=0),
                np.eye(positions)[position_train],
            ]
        )
        target = values.reshape(-1).astype(float)
        X_next = np.column_stack(
            [
                np.repeat(X_next_time[None, :], positions, axis=0),
                np.eye(positions),
            ]
        )
        profile_id = inference_profile_id or spec.primary_profile or "pymc-nuts"
        profile = get_inference_profile(profile_id)
        settings = profile_settings(config, profile)
        with pm.Model() as model:
            X_data = pm.Data("X", X_train)
            mu = pmb.BART("mu", X_data, target, m=32)
            sigma = pm.HalfNormal("sigma", sigma=1.5)
            pm.Normal("observed", mu=mu, sigma=sigma, observed=target)
            idata = pm.sample(
                draws=settings["draws"],
                tune=settings["warmup"],
                chains=settings["chains"],
                cores=config.native_inner_cores,
                random_seed=seed,
                progressbar=config.native_progressbar,
                return_inferencedata=True,
                target_accept=settings["target_accept"],
            )
            pm.set_data({"X": X_next})
            prediction = pm.sample_posterior_predictive(
                idata,
                var_names=["mu"],
                sample_vars=["mu"],
                predictions=True,
                random_seed=seed + 1,
                progressbar=config.native_progressbar,
                return_inferencedata=True,
            )
        group = getattr(prediction, "predictions", None)
        if group is None:
            raise ValueError("PyMC-BART posterior predictive has no predictions group")
        locations = np.asarray(group["mu"].values, dtype=float)
        if locations.ndim < 3 or locations.shape[-1] != positions:
            raise ValueError(
                "PyMC-BART out-of-sample shape mismatch: "
                f"expected (..., {positions}), got {locations.shape}"
            )
        locations = locations.reshape(-1, positions)
        draws = gaussian_kernel_probabilities(locations, classes, scale=1.0)
        return NativePosterior(
            model_id=spec.model_id,
            backend=self.backend_id,
            family=spec.family,
            target_mode=target_mode,
            game=geometry.key,
            probability_draws=draws,
            metadata={
                "native_graph_id": spec.native_graph_id,
                "training_rows_used": len(values),
                "inference_profile_id": profile_id,
                "algorithm": profile.algorithm,
                "settings": settings,
                "library_version": getattr(pmb, "__version__", "unknown"),
            },
            diagnostics=_diagnostics(idata, variational=False),
            native_payload={"fit": idata, "predictions": prediction},
        )


__all__ = ["PyMCBartBackend"]
