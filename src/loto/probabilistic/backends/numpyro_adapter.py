from __future__ import annotations

from contextlib import nullcontext
from typing import Any

import numpy as np

from loto.probabilistic.backends.base import ProbabilisticBackend
from loto.probabilistic.catalog import get_inference_profile
from loto.probabilistic.models.native_common import profile_settings
from loto.probabilistic.models.numpyro_native import build_numpyro_graph
from loto.probabilistic.native import NativePosterior


def _jax_device(config: Any, jax: Any) -> tuple[Any, str]:
    try:
        gpu_devices = list(jax.devices("gpu"))
    except Exception:
        gpu_devices = []
    cpu_devices = list(jax.devices("cpu"))
    if config.native_device == "cpu":
        return cpu_devices[0], "cpu"
    if config.native_device == "cuda":
        if not gpu_devices:
            raise RuntimeError("native_device=cuda requested but JAX GPU is unavailable")
        return gpu_devices[0], "cuda"
    if gpu_devices:
        return gpu_devices[0], "cuda"
    return cpu_devices[0], "cpu"


class NumPyroBackend(ProbabilisticBackend):
    backend_id = "numpyro"
    modules = ("numpyro", "jax", "arviz")
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
            raise RuntimeError(f"NumPyro backend unavailable: {probe.detail}")
        import jax
        import numpyro
        from numpyro.infer import MCMC, NUTS, SVI, Predictive, Trace_ELBO
        from numpyro.infer.autoguide import AutoLowRankMultivariateNormal, AutoNormal
        from numpyro.optim import Adam

        device, resolved_device = _jax_device(config, jax)
        context = jax.default_device(device) if hasattr(jax, "default_device") else nullcontext()
        with context:
            profile_id = inference_profile_id or spec.primary_profile or "numpyro-svi-lowrank"
            profile = get_inference_profile(profile_id)
            settings = profile_settings(config, profile)
            graph = build_numpyro_graph(
                spec,
                y=y,
                classes=classes,
                target_mode=target_mode,
                geometry=geometry,
                config=config,
                seed=seed,
            )
            key = jax.random.PRNGKey(seed)
            algorithm = str(profile.algorithm).lower()
            diagnostics: dict[str, Any] = {
                "rhat_max": None,
                "ess_bulk_min": None,
                "ess_tail_min": None,
                "divergences": None,
                "elbo_finite": None,
                "elbo_stable": None,
                "posterior_finite": True,
                "probability_simplex_valid": True,
            }
            native_payload: Any
            if "nuts" in algorithm or "hmc" in algorithm:
                kernel = NUTS(graph.model, target_accept_prob=settings["target_accept"])
                mcmc = MCMC(
                    kernel,
                    num_warmup=settings["warmup"],
                    num_samples=settings["draws"],
                    num_chains=settings["chains"],
                    progress_bar=config.native_progressbar,
                )
                mcmc.run(key, *graph.model_args, **graph.model_kwargs)
                posterior_samples = mcmc.get_samples(group_by_chain=False)
                predictive = Predictive(
                    graph.model,
                    posterior_samples=posterior_samples,
                    return_sites=["next_probabilities"],
                )
                key, prediction_key = jax.random.split(key)
                draws = np.asarray(
                    predictive(prediction_key, *graph.model_args, **graph.model_kwargs)[
                        "next_probabilities"
                    ]
                )
                try:
                    extra = mcmc.get_extra_fields(group_by_chain=False)
                    diagnostics["divergences"] = int(np.asarray(extra.get("diverging", [])).sum())
                except Exception:
                    pass
                native_payload = mcmc
            else:
                guide = (
                    AutoLowRankMultivariateNormal(graph.model)
                    if "lowrank" in profile_id
                    else AutoNormal(graph.model)
                )
                svi = SVI(
                    graph.model,
                    guide,
                    Adam(0.01),
                    Trace_ELBO(num_particles=settings["particles"]),
                )
                result = svi.run(
                    key,
                    settings["steps"],
                    *graph.model_args,
                    progress_bar=config.native_progressbar,
                    **graph.model_kwargs,
                )
                losses = np.asarray(result.losses, dtype=float)
                diagnostics["elbo_finite"] = bool(np.isfinite(losses).all())
                if len(losses) >= 20 and np.isfinite(losses).all():
                    tail = losses[-max(10, len(losses) // 10) :]
                    diagnostics["elbo_stable"] = bool(
                        np.std(tail) / max(abs(float(np.mean(tail))), 1e-9) < 0.2
                    )
                predictive = Predictive(
                    graph.model,
                    guide=guide,
                    params=result.params,
                    num_samples=settings["posterior_draws"],
                    return_sites=["next_probabilities"],
                )
                key, prediction_key = jax.random.split(key)
                draws = np.asarray(
                    predictive(prediction_key, *graph.model_args, **graph.model_kwargs)[
                        "next_probabilities"
                    ]
                )
                native_payload = result

        return NativePosterior(
            model_id=spec.model_id,
            backend=self.backend_id,
            family=spec.family,
            target_mode=target_mode,
            game=geometry.key,
            probability_draws=draws,
            metadata={
                **graph.metadata,
                "native_graph_id": graph.graph_id,
                "inference_profile_id": profile_id,
                "algorithm": profile.algorithm,
                "settings": settings,
                "resolved_device": resolved_device,
                "jax_device": str(device),
                "library_version": getattr(numpyro, "__version__", "unknown"),
                "jax_version": getattr(jax, "__version__", "unknown"),
            },
            diagnostics=diagnostics,
            native_payload=native_payload,
        )


__all__ = ["NumPyroBackend"]
