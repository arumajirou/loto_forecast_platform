from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from loto.game.geometry import geometry_for
from loto.probabilistic.catalog import (
    get_inference_profile,
    list_inference_profiles,
    list_probabilistic_model_specs,
)
from loto.probabilistic.compatibility import compatible_task, decide_compatibility
from loto.probabilistic.contracts import ProbabilisticRunConfig


@dataclass(frozen=True)
class TrialPlan:
    trial_id: str
    model_id: str
    family: str
    game: str
    target_mode: str
    backend: str
    inference_profile_id: str | None
    resource_class: str | None
    allowed: bool
    reason_code: str
    details: tuple[str, ...]
    seed: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _choose_game(spec, games: list[str]) -> tuple[str, str] | None:
    candidates: list[tuple[int, str, str]] = []
    for game in games:
        geometry = geometry_for(game)
        task = compatible_task(spec, geometry)
        if task is None:
            continue
        score = 0
        if spec.family == "count" and geometry.family == "select":
            score += 20
        if any(t.startswith("select_") for t in spec.tasks) and geometry.family == "select":
            score += 15
        if any(t.startswith("digit_") for t in spec.tasks) and geometry.family == "digits":
            score += 15
        if spec.family in {"decision", "calibration", "ensemble"}:
            score += 5
        candidates.append((score, game, task))
    if not candidates:
        return None
    _, game, task = max(candidates, key=lambda item: (item[0], -games.index(item[1])))
    return game, task


def _selected_specs(config: ProbabilisticRunConfig):
    specs = list_probabilistic_model_specs()
    if config.models != "all":
        requested = set(config.models)
        known = {spec.model_id for spec in specs}
        missing = sorted(requested - known)
        if missing:
            raise ValueError(f"unknown probabilistic models: {missing}")
        specs = [spec for spec in specs if spec.model_id in requested]
    if config.families:
        allowed = set(config.families)
        specs = [spec for spec in specs if spec.family in allowed]
    if not config.include_experimental:
        specs = [spec for spec in specs if not spec.experimental]
    return specs


def build_plan(config: ProbabilisticRunConfig) -> list[TrialPlan]:
    trials: list[TrialPlan] = []
    for spec in _selected_specs(config):
        choice = _choose_game(spec, config.games)
        if choice is None:
            trials.append(
                TrialPlan(
                    trial_id=f"{spec.model_id}__no-compatible-game",
                    model_id=spec.model_id,
                    family=spec.family,
                    game="",
                    target_mode="",
                    backend="builtin",
                    inference_profile_id=None,
                    resource_class=None,
                    allowed=False,
                    reason_code="TARGET_MODE_UNSUPPORTED",
                    details=(f"configured_games={','.join(config.games)}",),
                    seed=config.seeds[0],
                )
            )
            continue
        game, target_mode = choice
        if config.backend_policy == "primary_native":
            backends = [spec.primary_backend]
        elif config.backend_policy == "all_declared":
            backends = list(spec.backends)
        else:
            backends = config.backends or ["builtin"]

        if config.backend_policy == "primary_native":
            profile_ids: list[str | None] = [spec.primary_profile]
        elif config.profile != "exhaustive":
            profile_ids = [None]
        else:
            profile_ids = [None, *config.inference_profiles]
            if not config.inference_profiles:
                profile_ids.extend(profile.profile_id for profile in list_inference_profiles())
        for backend in dict.fromkeys(backends):
            relevant_profiles = profile_ids
            if backend in {"builtin", "arviz"}:
                relevant_profiles = [None]
            elif config.backend_policy == "primary_native":
                relevant_profiles = [spec.primary_profile]
            for profile_id in relevant_profiles:
                if profile_id:
                    try:
                        profile = get_inference_profile(profile_id)
                    except KeyError:
                        trials.append(
                            TrialPlan(
                                trial_id=f"{spec.model_id}__{backend}__{profile_id}",
                                model_id=spec.model_id,
                                family=spec.family,
                                game=game,
                                target_mode=target_mode,
                                backend=backend,
                                inference_profile_id=profile_id,
                                resource_class=None,
                                allowed=False,
                                reason_code="UNKNOWN_INFERENCE_PROFILE",
                                details=(),
                                seed=config.seeds[0],
                            )
                        )
                        continue
                    if config.profile == "exhaustive" and profile.backend not in {
                        backend,
                        "cmdstanpy" if backend == "stan" else backend,
                    }:
                        continue
                decision = decide_compatibility(
                    spec,
                    geometry=geometry_for(game),
                    backend=backend,
                    profile_id=profile_id,
                    include_experimental=config.include_experimental,
                )
                for seed in config.seeds:
                    trial_id = (
                        f"{spec.model_id}__{game}__{backend}__{profile_id or 'analytic'}__s{seed}"
                    )
                    trials.append(
                        TrialPlan(
                            trial_id=trial_id,
                            model_id=spec.model_id,
                            family=spec.family,
                            game=game,
                            target_mode=target_mode,
                            backend=backend,
                            inference_profile_id=profile_id,
                            resource_class=decision.required_resource_class,
                            allowed=decision.allowed,
                            reason_code=str(decision.reason_code),
                            details=decision.details,
                            seed=seed,
                        )
                    )
    return trials


def plan_summary(config: ProbabilisticRunConfig) -> dict[str, Any]:
    trials = build_plan(config)
    allowed = [trial for trial in trials if trial.allowed]
    blocked = [trial for trial in trials if not trial.allowed]
    by_reason: dict[str, int] = {}
    by_resource: dict[str, int] = {}
    for trial in blocked:
        by_reason[trial.reason_code] = by_reason.get(trial.reason_code, 0) + 1
    for trial in allowed:
        key = trial.resource_class or "none"
        by_resource[key] = by_resource.get(key, 0) + 1
    return {
        "profile": config.profile,
        "models_requested": len({trial.model_id for trial in trials}),
        "trials_total": len(trials),
        "trials_allowed": len(allowed),
        "trials_blocked": len(blocked),
        "by_reason": dict(sorted(by_reason.items())),
        "by_resource": dict(sorted(by_resource.items())),
        "trials": [trial.to_dict() for trial in trials],
    }
