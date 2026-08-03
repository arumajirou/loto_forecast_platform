from __future__ import annotations

from typing import Any

import numpy as np

from loto.probabilistic.backends.base import ProbabilisticBackend
from loto.probabilistic.models.bocpd_native import MODEL_ID as BOCPD_MODEL_ID
from loto.probabilistic.models.bocpd_native import fit_bocpd_dirichlet_categorical
from loto.probabilistic.models.copula_native import MODEL_ID as COPULA_MODEL_ID
from loto.probabilistic.models.copula_native import fit_gaussian_copula_categorical
from loto.probabilistic.models.dglm_native import MODEL_ID as DGLM_MODEL_ID
from loto.probabilistic.models.dglm_native import fit_multinomial_dglm
from loto.probabilistic.models.reference import fit_reference, posterior_draws
from loto.probabilistic.models.subset_native import MODEL_ID, fit_conditional_bernoulli_map
from loto.probabilistic.native import NativePosterior


class BuiltinBackend(ProbabilisticBackend):
    backend_id = "builtin"
    modules = ()
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
        if spec.model_id == BOCPD_MODEL_ID:
            state = fit_bocpd_dirichlet_categorical(
                y,
                game=geometry.key,
                classes=classes,
                config=config,
                seed=seed,
            )
            draw_count = (
                config.native_draws
                if config.backend_policy == "primary_native"
                else config.posterior_draws
            )
            draws = state.probability_draws(draw_count, seed=seed)
            return NativePosterior(
                model_id=spec.model_id,
                backend=self.backend_id,
                family=spec.family,
                target_mode=target_mode,
                game=geometry.key,
                probability_draws=draws,
                metadata={
                    **state.to_metadata_dict(),
                    "native_graph_id": spec.native_graph_id,
                    "implementation_kind": "exact_online_message_passing",
                    "native_analytic": True,
                    "inference_profile_id": inference_profile_id,
                    "alert_events": list(state.alert_events),
                    "automatic_retraining": False,
                },
                diagnostics={
                    "posterior_finite": bool(np.isfinite(draws).all()),
                    "probability_simplex_valid": bool(
                        np.allclose(draws.sum(axis=-1), 1.0, atol=1e-7)
                    ),
                    "run_length_posterior_valid": bool(
                        np.isfinite(state.run_length_posterior).all()
                        and np.isclose(state.run_length_posterior.sum(), 1.0)
                    ),
                    "current_changepoint_probability": (state.current_changepoint_probability),
                    "map_run_length": state.map_run_length,
                    "active_run_lengths": int(len(state.run_lengths)),
                    "cumulative_pruned_mass": state.cumulative_pruned_mass,
                    "alert_count": len(state.alert_events),
                    "data_quality_pass_rate": float(state.data_quality_pass.mean()),
                    "rhat_max": None,
                    "ess_bulk_min": None,
                    "ess_tail_min": None,
                    "divergences": None,
                    "elbo_finite": None,
                    "elbo_stable": None,
                },
                native_payload=state,
            )

        if spec.model_id == COPULA_MODEL_ID:
            state = fit_gaussian_copula_categorical(
                y,
                game=geometry.key,
                classes=classes,
                config=config,
                seed=seed,
            )
            draw_count = (
                config.native_draws
                if config.backend_policy == "primary_native"
                else config.posterior_draws
            )
            draws = state.probability_draws(draw_count)
            minimum_eigenvalue = float(np.linalg.eigvalsh(state.correlation).min())
            return NativePosterior(
                model_id=spec.model_id,
                backend=self.backend_id,
                family=spec.family,
                target_mode=target_mode,
                game=geometry.key,
                probability_draws=draws,
                metadata={
                    **state.to_metadata_dict(),
                    "native_graph_id": spec.native_graph_id,
                    "implementation_kind": "analytic_copula_initialization",
                    "native_analytic": True,
                    "primary_backend": spec.primary_backend,
                    "inference_profile_id": inference_profile_id,
                },
                diagnostics={
                    "posterior_finite": bool(np.isfinite(draws).all()),
                    "probability_simplex_valid": bool(
                        np.allclose(draws.sum(axis=-1), 1.0, atol=1e-7)
                    ),
                    "correlation_psd": minimum_eigenvalue >= -1e-8,
                    "correlation_min_eigenvalue": minimum_eigenvalue,
                    "correlation_repair": state.correlation_repair,
                    "marginal_preservation": True,
                    "rhat_max": None,
                    "ess_bulk_min": None,
                    "ess_tail_min": None,
                    "divergences": None,
                    "elbo_finite": None,
                    "elbo_stable": None,
                },
                native_payload=state,
            )

        if spec.model_id == DGLM_MODEL_ID:
            state = fit_multinomial_dglm(
                y,
                game=geometry.key,
                classes=classes,
                config=config,
                seed=seed,
            )
            draw_count = (
                config.native_draws
                if config.backend_policy == "primary_native"
                else config.posterior_draws
            )
            draws = state.probability_draws(draws=draw_count, seed=seed)
            covariance_min = min(
                float(np.linalg.eigvalsh(covariance).min()) for covariance in state.state_covariance
            )
            return NativePosterior(
                model_id=spec.model_id,
                backend=self.backend_id,
                family=spec.family,
                target_mode=target_mode,
                game=geometry.key,
                probability_draws=draws,
                metadata={
                    **state.to_metadata_dict(),
                    "native_graph_id": spec.native_graph_id,
                    "implementation_kind": "sequential_laplace_filter",
                    "native_analytic": True,
                    "inference_profile_id": inference_profile_id,
                },
                diagnostics={
                    "posterior_finite": bool(np.isfinite(draws).all()),
                    "probability_simplex_valid": bool(
                        np.allclose(draws.sum(axis=-1), 1.0, atol=1e-7)
                    ),
                    "state_covariance_psd": covariance_min >= -1e-8,
                    "state_covariance_min_eigenvalue": covariance_min,
                    "max_covariance_jitter": state.max_covariance_jitter,
                    "max_innovation_condition": state.max_innovation_condition,
                    "missing_update_count": int((~state.update_applied).sum()),
                    "rhat_max": None,
                    "ess_bulk_min": None,
                    "ess_tail_min": None,
                    "divergences": None,
                    "elbo_finite": None,
                    "elbo_stable": None,
                },
                native_payload=state,
            )

        if spec.model_id == MODEL_ID:
            posterior = fit_conditional_bernoulli_map(
                y,
                game=geometry.key,
                config=config,
                seed=seed,
                cardinality=geometry.positions,
            )
            draws = posterior.normalized_probability_draws
            return NativePosterior(
                model_id=spec.model_id,
                backend=self.backend_id,
                family=spec.family,
                target_mode=target_mode,
                game=geometry.key,
                probability_draws=draws,
                metadata={
                    **posterior.to_metadata_dict(),
                    "native_graph_id": spec.native_graph_id,
                    "implementation_kind": "analytic_map_laplace",
                    "native_analytic": True,
                    "inference_profile_id": inference_profile_id,
                },
                diagnostics={
                    "posterior_finite": bool(np.isfinite(draws).all()),
                    "probability_simplex_valid": bool(
                        np.allclose(draws.sum(axis=-1), 1.0, atol=1e-7)
                    ),
                    "cardinality_valid_rate": 1.0,
                    "duplicate_violation_rate": 0.0,
                    "optimizer_success": posterior.optimizer_success,
                    "gradient_norm": posterior.gradient_norm,
                    "laplace_ridge": posterior.laplace_ridge,
                    "rhat_max": None,
                    "ess_bulk_min": None,
                    "ess_tail_min": None,
                    "divergences": None,
                    "elbo_finite": None,
                    "elbo_stable": None,
                },
                native_payload=posterior,
            )

        posterior = fit_reference(
            spec,
            y=y,
            classes=classes,
            target_mode=target_mode,
            geometry=geometry,
            config=config,
            seed=seed,
        )
        draws = posterior_draws(
            posterior,
            draws=config.native_draws
            if config.backend_policy == "primary_native"
            else config.posterior_draws,
            seed=seed,
        )
        primary_analytic = spec.primary_backend == "builtin"
        return NativePosterior(
            model_id=spec.model_id,
            backend=self.backend_id,
            family=spec.family,
            target_mode=target_mode,
            game=geometry.key,
            probability_draws=draws,
            metadata={
                **posterior.metadata,
                "native_graph_id": spec.native_graph_id,
                "implementation_kind": "analytic" if primary_analytic else "reference",
                "native_analytic": primary_analytic,
                "inference_profile_id": inference_profile_id,
            },
            diagnostics={
                "posterior_finite": bool(np.isfinite(draws).all()),
                "probability_simplex_valid": bool(np.allclose(draws.sum(axis=-1), 1.0, atol=1e-7)),
                "rhat_max": None,
                "ess_bulk_min": None,
                "ess_tail_min": None,
                "divergences": None,
                "elbo_finite": None,
                "elbo_stable": None,
            },
            native_payload=posterior,
        )
