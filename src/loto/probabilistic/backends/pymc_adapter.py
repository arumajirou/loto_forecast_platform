from __future__ import annotations

from typing import Any

import numpy as np

from loto.probabilistic.backends.base import ProbabilisticBackend
from loto.probabilistic.catalog import get_inference_profile
from loto.probabilistic.models.copula_native import MODEL_ID as COPULA_MODEL_ID
from loto.probabilistic.models.copula_pymc import build_gaussian_copula_graph
from loto.probabilistic.models.native_common import profile_settings
from loto.probabilistic.models.pymc_native import build_pymc_graph
from loto.probabilistic.native import NativePosterior


def _posterior_values(idata: Any, variable: str) -> np.ndarray:
    posterior = getattr(idata, "posterior", None)
    if posterior is None:
        raise ValueError("PyMC result has no posterior group")
    data = posterior[variable]
    values = np.asarray(data.values, dtype=float)
    if values.ndim < 2:
        raise ValueError(f"posterior variable {variable} has invalid shape {values.shape}")
    if values.ndim == 2:
        values = values.reshape(values.shape[0] * values.shape[1], 1, 1)
    else:
        values = values.reshape(values.shape[0] * values.shape[1], *values.shape[2:])
    if values.ndim == 2:
        values = values[:, None, :]
    if values.ndim != 3:
        raise ValueError(f"{variable} must reduce to (draw, position, class); got {values.shape}")
    return values


def _posterior_matrix_values(idata: Any, variable: str) -> np.ndarray:
    posterior = getattr(idata, "posterior", None)
    if posterior is None or variable not in posterior:
        raise ValueError(f"PyMC result has no posterior variable {variable}")
    values = np.asarray(posterior[variable].values, dtype=float)
    if values.ndim != 4:
        raise ValueError(f"{variable} must have chain/draw/matrix dimensions; got {values.shape}")
    return values.reshape(values.shape[0] * values.shape[1], *values.shape[2:])


def _safe_statistic(function: Any, idata: Any, reducer: str) -> float | None:
    try:
        result = function(idata)
        if hasattr(result, "to_array"):
            values = np.asarray(result.to_array().values, dtype=float)
        else:
            values = np.asarray(result, dtype=float)
        values = values[np.isfinite(values)]
        if not len(values):
            return None
        return float(np.max(values) if reducer == "max" else np.min(values))
    except Exception:
        return None


def _diagnostics(
    idata: Any, *, variational: bool, losses: list[float] | None = None
) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {
        "posterior_finite": True,
        "probability_simplex_valid": True,
        "rhat_max": None,
        "ess_bulk_min": None,
        "ess_tail_min": None,
        "divergences": None,
        "max_treedepth_hits": None,
        "ebfmi_min": None,
        "elbo_finite": None,
        "elbo_stable": None,
    }
    if variational:
        finite = bool(losses is not None and len(losses) and np.isfinite(losses).all())
        stable = None
        if finite and len(losses or []) >= 20:
            tail = np.asarray(losses[-max(10, len(losses) // 10) :], dtype=float)
            stable = bool(np.std(tail) / max(abs(np.mean(tail)), 1e-9) < 0.2)
        diagnostics.update(elbo_finite=finite, elbo_stable=stable)
        return diagnostics
    try:
        import arviz as az  # type: ignore

        diagnostics["rhat_max"] = _safe_statistic(az.rhat, idata, "max")
        diagnostics["ess_bulk_min"] = _safe_statistic(
            lambda x: az.ess(x, method="bulk"), idata, "min"
        )
        diagnostics["ess_tail_min"] = _safe_statistic(
            lambda x: az.ess(x, method="tail"), idata, "min"
        )
        diagnostics["ebfmi_min"] = _safe_statistic(az.bfmi, idata, "min")
    except Exception:
        pass
    sample_stats = getattr(idata, "sample_stats", None)
    if sample_stats is not None:
        try:
            diagnostics["divergences"] = int(np.asarray(sample_stats["diverging"]).sum())
        except Exception:
            pass
        for name in ("reached_max_treedepth", "tree_depth"):
            try:
                values = np.asarray(sample_stats[name])
                diagnostics["max_treedepth_hits"] = (
                    int(values.sum()) if name.startswith("reached") else None
                )
                break
            except Exception:
                continue
    return diagnostics


class PyMCBackend(ProbabilisticBackend):
    backend_id = "pymc"
    modules = ("pymc", "arviz")
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
            raise RuntimeError(f"PyMC backend unavailable: {probe.detail}")
        import pymc as pm  # type: ignore

        profile_id = inference_profile_id or spec.primary_profile or "pymc-nuts"
        profile = get_inference_profile(profile_id)
        settings = profile_settings(config, profile)
        graph_builder = (
            build_gaussian_copula_graph if spec.model_id == COPULA_MODEL_ID else build_pymc_graph
        )
        graph = graph_builder(
            spec,
            y=y,
            classes=classes,
            target_mode=target_mode,
            geometry=geometry,
            config=config,
            seed=seed,
        )
        algorithm = str(profile.algorithm).lower()
        losses: list[float] | None = None
        variational = "advi" in algorithm
        with graph.model:
            if "smc" in algorithm:
                idata = pm.sample_smc(
                    draws=settings["draws"],
                    chains=settings["chains"],
                    random_seed=seed,
                    progressbar=config.native_progressbar,
                    return_inferencedata=True,
                )
            elif variational:
                method = "fullrank_advi" if "full-rank" in algorithm.lower() else "advi"
                approximation = pm.fit(
                    n=settings["steps"],
                    method=method,
                    random_seed=seed,
                    progressbar=config.native_progressbar,
                )
                losses = list(np.asarray(getattr(approximation, "hist", []), dtype=float))
                idata = approximation.sample(
                    draws=settings["posterior_draws"],
                    random_seed=seed,
                    return_inferencedata=True,
                )
            else:
                idata = pm.sample(
                    draws=settings["draws"],
                    tune=settings["warmup"],
                    chains=settings["chains"],
                    cores=config.native_inner_cores,
                    target_accept=settings["target_accept"],
                    random_seed=seed,
                    progressbar=config.native_progressbar,
                    return_inferencedata=True,
                    compute_convergence_checks=True,
                )
        draws = _posterior_values(idata, graph.probability_variable)
        metadata = {
            **(graph.metadata or {}),
            "native_graph_id": graph.graph_id,
            "inference_profile_id": profile_id,
            "algorithm": profile.algorithm,
            "settings": settings,
            "library_version": getattr(pm, "__version__", "unknown"),
        }
        diagnostics = _diagnostics(idata, variational=variational, losses=losses)
        if spec.model_id == COPULA_MODEL_ID:
            matrices = _posterior_matrix_values(idata, "copula_correlation_matrix")
            mean_correlation = matrices.mean(axis=0)
            minimum_eigenvalue = min(float(np.linalg.eigvalsh(matrix).min()) for matrix in matrices)
            metadata["posterior_correlation_mean"] = mean_correlation.tolist()
            metadata["posterior_correlation_draw_shape"] = list(matrices.shape)
            diagnostics.update(
                correlation_posterior_finite=bool(np.isfinite(matrices).all()),
                correlation_posterior_psd=minimum_eigenvalue >= -1e-8,
                correlation_min_eigenvalue=minimum_eigenvalue,
                marginal_preservation=bool(
                    np.allclose(
                        draws.mean(axis=0),
                        np.asarray(graph.metadata["marginal_probabilities"], dtype=float),
                        atol=1e-10,
                    )
                ),
            )
        return NativePosterior(
            model_id=spec.model_id,
            backend=self.backend_id,
            family=spec.family,
            target_mode=target_mode,
            game=geometry.key,
            probability_draws=draws,
            metadata=metadata,
            diagnostics=diagnostics,
            native_payload=idata,
        )


__all__ = ["PyMCBackend"]
