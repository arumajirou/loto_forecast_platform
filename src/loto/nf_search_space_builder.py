from __future__ import annotations

from typing import Any, Protocol


class TrialLike(Protocol):
    def suggest_categorical(
        self,
        name: str,
        choices: list[Any],
    ) -> Any:
        ...

    def suggest_float(
        self,
        name: str,
        low: float,
        high: float,
        *,
        step: float | None = None,
        log: bool = False,
    ) -> float:
        ...

    def suggest_int(
        self,
        name: str,
        low: int,
        high: int,
        *,
        step: int = 1,
        log: bool = False,
    ) -> int:
        ...


def build_optuna_config(
    trial: TrialLike,
    parameters: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    config: dict[str, Any] = {}

    for name, spec in parameters.items():
        kind = spec["kind"]

        if kind == "fixed":
            config[name] = spec["value"]
            continue

        if kind == "categorical":
            values = list(spec["values"])

            if not values:
                raise ValueError(
                    f"{name}: empty categorical values"
                )

            if len(values) == 1:
                config[name] = values[0]
            else:
                config[name] = trial.suggest_categorical(
                    name,
                    values,
                )
            continue

        if kind in {
            "float",
            "log_float",
            "discrete_float",
        }:
            step = spec.get("step")

            config[name] = trial.suggest_float(
                name,
                float(spec["lower"]),
                float(spec["upper"]),
                step=(
                    None
                    if step is None
                    else float(step)
                ),
                log=bool(spec.get("log", False)),
            )
            continue

        if kind in {
            "integer",
            "log_int",
        }:
            config[name] = trial.suggest_int(
                name,
                int(spec["lower"]),
                int(spec["upper"]),
                step=int(spec.get("step", 1)),
                log=bool(spec.get("log", False)),
            )
            continue

        raise ValueError(
            f"{name}: unsupported search kind {kind!r}"
        )

    return config


def build_ray_space(
    parameters: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    from ray import tune

    space: dict[str, Any] = {}

    for name, spec in parameters.items():
        kind = spec["kind"]

        if kind == "fixed":
            space[name] = spec["value"]
            continue

        if kind == "categorical":
            values = list(spec["values"])

            if not values:
                raise ValueError(
                    f"{name}: empty categorical values"
                )

            if len(values) == 1:
                space[name] = values[0]
            else:
                space[name] = tune.choice(values)
            continue

        if kind == "float":
            space[name] = tune.uniform(
                float(spec["lower"]),
                float(spec["upper"]),
            )
            continue

        if kind == "log_float":
            space[name] = tune.loguniform(
                float(spec["lower"]),
                float(spec["upper"]),
            )
            continue

        if kind == "discrete_float":
            step = spec.get("step")

            if step is None:
                raise ValueError(
                    f"{name}: discrete_float requires step"
                )

            space[name] = tune.quniform(
                float(spec["lower"]),
                float(spec["upper"]),
                float(step),
            )
            continue

        if kind == "integer":
            low = int(spec["lower"])
            high_inclusive = int(spec["upper"])

            # Ray randint upper bound is exclusive.
            space[name] = tune.randint(
                low,
                high_inclusive + 1,
            )
            continue

        if kind == "log_int":
            raise ValueError(
                f"{name}: log_int is not supported by "
                "the current backend-neutral builder"
            )

        raise ValueError(
            f"{name}: unsupported search kind {kind!r}"
        )

    return space
