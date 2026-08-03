from __future__ import annotations

from loto.game.geometry import GameGeometry
from loto.probabilistic.backends import get_backend
from loto.probabilistic.catalog import backend_available, get_inference_profile
from loto.probabilistic.contracts import CompatibilityDecision, ProbabilisticModelSpec
from loto.probabilistic.statuses import CompatibilityReason


def compatible_task(spec: ProbabilisticModelSpec, geometry: GameGeometry) -> str | None:
    if geometry.family == "digits":
        preference = (
            "categorical_context",
            "joint_discrete_copula",
            "dynamic_multinomial",
            "online_changepoint",
            "digit_categorical",
            "digit_ordinal",
            "window_count",
            "calibration",
            "ensemble",
            "decision",
        )
    else:
        preference = (
            "fixed_cardinality_subset",
            "ordered_without_replacement",
            "dynamic_multinomial",
            "online_changepoint",
            "select_position_categorical",
            "select_position_ordinal",
            "select_candidate_inclusion",
            "select_position_inclusion",
            "window_count",
            "calibration",
            "ensemble",
            "decision",
        )
    return next((task for task in preference if task in spec.tasks), None)


def required_resource_class(spec: ProbabilisticModelSpec, backend: str) -> str:
    if backend in {
        "numpyro",
        "pyro",
        "blackjax",
        "pymc+blackjax",
        "pymc+numpyro",
        "tfp",
        "tensorflow_probability",
    }:
        return "gpu" if spec.family == "deep_probabilistic" else "heavy_cpu"
    if backend in {"pymc", "pymc_bart", "stan", "cmdstanpy"}:
        return (
            "heavy_cpu"
            if spec.priority != "p0"
            or spec.family
            in {
                "gaussian_process",
                "mixture",
                "state_space",
                "regime_switching",
                "changepoint",
                "count",
            }
            else "light_cpu"
        )
    if backend == "arviz":
        return "light_cpu"
    if spec.family in {
        "deep_probabilistic",
        "gaussian_process",
        "nonparametric",
        "mixture",
        "state_space",
        "regime_switching",
        "changepoint",
    }:
        return "heavy_cpu"
    return "light_cpu"


def decide_compatibility(
    spec: ProbabilisticModelSpec,
    *,
    geometry: GameGeometry,
    backend: str = "builtin",
    profile_id: str | None = None,
    include_experimental: bool = True,
    draw_order_verified: bool = False,
) -> CompatibilityDecision:
    task = compatible_task(spec, geometry)
    if task is None:
        return CompatibilityDecision(
            False,
            CompatibilityReason.TARGET_MODE_UNSUPPORTED,
            None,
            profile_id,
            None,
            (f"game={geometry.key}", f"tasks={','.join(spec.tasks)}"),
        )
    if spec.experimental and not include_experimental:
        return CompatibilityDecision(
            False, CompatibilityReason.EXPERIMENTAL_DISABLED, None, profile_id, None
        )
    if task == "ordered_without_replacement" and not draw_order_verified:
        return CompatibilityDecision(
            False,
            CompatibilityReason.DRAW_ORDER_REQUIRED,
            None,
            profile_id,
            None,
            ("draw_order_verified=false",),
        )
    # The builtin reference backend is available for every implemented catalog entry.
    if backend != "builtin" and backend not in spec.backends:
        return CompatibilityDecision(
            False,
            CompatibilityReason.BACKEND_NOT_DECLARED,
            None,
            profile_id,
            None,
            (f"declared={','.join(spec.backends)}",),
        )
    if not backend_available(backend):
        return CompatibilityDecision(
            False, CompatibilityReason.BACKEND_UNAVAILABLE, backend, profile_id, None
        )
    if backend != "builtin":
        try:
            probe = get_backend(backend).probe()
        except KeyError:
            probe = None
        if probe is None or not probe.implemented:
            return CompatibilityDecision(
                False,
                CompatibilityReason.MODEL_BLOCKED,
                backend,
                profile_id,
                None,
                (
                    "native adapter is probe-only in this release",
                    "builtin reference path is implemented",
                ),
            )
    if profile_id:
        profile = get_inference_profile(profile_id)
        accepted = {backend}
        if backend == "stan":
            accepted.add("cmdstanpy")
        if backend == "pymc_bart":
            accepted.add("pymc")
        if profile.backend not in accepted:
            return CompatibilityDecision(
                False,
                CompatibilityReason.PROFILE_BACKEND_MISMATCH,
                backend,
                profile_id,
                None,
                (f"profile_backend={profile.backend}",),
            )
        discrete = spec.family in {"mixture", "nonparametric", "regime_switching", "changepoint"}
        if discrete and profile.continuous_only:
            return CompatibilityDecision(
                False,
                CompatibilityReason.CONTINUOUS_SAMPLER_WITH_DISCRETE_LATENT,
                backend,
                profile_id,
                None,
            )
    return CompatibilityDecision(
        True,
        CompatibilityReason.ALLOWED,
        backend,
        profile_id,
        required_resource_class(spec, backend),
        (
            f"target_mode={task}",
            "reference_backend=true" if backend == "builtin" else "native_backend=true",
        ),
    )
