from __future__ import annotations

from typing import Any

import numpy as np

from loto.probabilistic.backends.base import ProbabilisticBackend
from loto.probabilistic.catalog import get_inference_profile
from loto.probabilistic.models.native_common import profile_settings
from loto.probabilistic.models.pyro_native import build_pyro_graph
from loto.probabilistic.native import NativePosterior


def _device(config: Any, torch: Any) -> str:
    if config.native_device == "cpu":
        return "cpu"
    if config.native_device == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("native_device=cuda requested but CUDA is unavailable")
        return "cuda"
    return "cuda" if torch.cuda.is_available() else "cpu"


class PyroBackend(ProbabilisticBackend):
    backend_id = "pyro"
    modules = ("pyro", "torch")
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
            raise RuntimeError(f"Pyro backend unavailable: {probe.detail}")
        import pyro
        import torch
        from pyro.infer import MCMC, NUTS, Predictive, SVI, Trace_ELBO
        from pyro.infer.autoguide import AutoDiagonalNormal, AutoLowRankMultivariateNormal
        from pyro.optim import ClippedAdam

        pyro.clear_param_store()
        pyro.set_rng_seed(seed)
        device = _device(config, torch)
        if device == "cuda":
            torch.cuda.set_device(0)
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats(0)
        profile_id = inference_profile_id or spec.primary_profile or "pyro-svi-autonormal"
        profile = get_inference_profile(profile_id)
        settings = profile_settings(config, profile)
        graph = build_pyro_graph(
            spec,
            y=y,
            classes=classes,
            target_mode=target_mode,
            geometry=geometry,
            config=config,
            seed=seed,
            device=device,
        )
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
        if "nuts" in algorithm:
            kernel = NUTS(graph.model, target_accept_prob=settings["target_accept"])
            mcmc = MCMC(
                kernel,
                warmup_steps=settings["warmup"],
                num_samples=settings["draws"],
                num_chains=settings["chains"],
                disable_progbar=not config.native_progressbar,
            )
            mcmc.run(*graph.model_args, **graph.model_kwargs)
            posterior_samples = mcmc.get_samples(group_by_chain=False)
            predictive = Predictive(
                graph.model,
                posterior_samples=posterior_samples,
                return_sites=("next_probabilities",),
                parallel=False,
            )
            output = predictive(*graph.model_args, **graph.model_kwargs)
            draws = output["next_probabilities"].detach().cpu().numpy()
            native_payload: Any = mcmc
        else:
            guide = (
                AutoLowRankMultivariateNormal(graph.model)
                if "lowrank" in profile_id
                else AutoDiagonalNormal(graph.model)
            )
            svi = SVI(
                graph.model,
                guide,
                ClippedAdam({"lr": 0.01, "clip_norm": 10.0}),
                Trace_ELBO(num_particles=settings["particles"]),
            )
            losses: list[float] = []
            for _ in range(settings["steps"]):
                losses.append(float(svi.step(*graph.model_args, **graph.model_kwargs)))
            loss_array = np.asarray(losses, dtype=float)
            diagnostics["elbo_finite"] = bool(np.isfinite(loss_array).all())
            if len(loss_array) >= 20 and np.isfinite(loss_array).all():
                tail = loss_array[-max(10, len(loss_array) // 10) :]
                diagnostics["elbo_stable"] = bool(
                    np.std(tail) / max(abs(float(np.mean(tail))), 1e-9) < 0.2
                )
            predictive = Predictive(
                graph.model,
                guide=guide,
                num_samples=settings["posterior_draws"],
                return_sites=("next_probabilities",),
                parallel=False,
            )
            output = predictive(*graph.model_args, **graph.model_kwargs)
            draws = output["next_probabilities"].detach().cpu().numpy()
            native_payload = {"guide": guide, "losses": losses}
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
                "resolved_device": device,
                "cuda_device_name": (
                    torch.cuda.get_device_name(0) if device == "cuda" else None
                ),
                "peak_vram_bytes": (
                    int(torch.cuda.max_memory_allocated(0)) if device == "cuda" else 0
                ),
                "library_version": getattr(pyro, "__version__", "unknown"),
                "torch_version": getattr(torch, "__version__", "unknown"),
            },
            diagnostics=diagnostics,
            native_payload=native_payload,
        )


__all__ = ["PyroBackend"]
