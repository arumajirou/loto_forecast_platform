"""NeuralForecast AutoSegRNN class factory."""

from __future__ import annotations

from typing import Any

from .contracts import ArchitectureProfile, TrainingProfile


def build_auto_segrnn_class(
    *,
    base_auto: type[Any],
    basic_variant_generator: type[Any],
    random_sampler: type[Any],
    losses: Any,
    segrnn_class: type[Any],
    tune: Any,
    module_name: str,
) -> type[Any]:
    class AutoSegRNN(base_auto):
        """Ray/Optuna AutoModel wrapper for the local SegRNN model."""

        def __init__(
            self,
            h: int,
            loss: Any = None,
            valid_loss: Any = None,
            config: Any = None,
            search_alg: Any = None,
            num_samples: int = 10,
            time_budget: int | None = None,
            refit_with_val: bool = False,
            verbose: bool = False,
            alias: str | None = None,
            backend: str = "ray",
            callbacks: list[Any] | None = None,
            ray_options: Any = None,
            optuna_options: Any = None,
        ) -> None:
            if loss is None:
                loss = losses.MAE()
            if config is None:
                config = self.get_default_config(h=h, backend=backend)
            if search_alg is None:
                if backend == "ray":
                    search_alg = basic_variant_generator(random_state=1)
                elif backend == "optuna":
                    search_alg = random_sampler(seed=1)
                else:
                    raise ValueError(f"unsupported AutoSegRNN backend: {backend}")
            super().__init__(
                cls_model=segrnn_class,
                h=h,
                loss=loss,
                valid_loss=valid_loss,
                config=config,
                search_alg=search_alg,
                num_samples=num_samples,
                time_budget=time_budget,
                refit_with_val=refit_with_val,
                verbose=verbose,
                alias=alias,
                backend=backend,
                callbacks=callbacks,
                ray_options=ray_options,
                optuna_options=optuna_options,
            )
            self.loto_model_id = "nf-local-auto-segrnn"

        @classmethod
        def get_default_config(
            cls,
            h: int,
            backend: str,
            n_series: int | None = None,
        ) -> Any:
            del n_series
            if not isinstance(h, int) or isinstance(h, bool) or h < 1:
                raise ValueError("h must be a positive integer")
            config: dict[str, Any] = {
                "h": None,
                "architecture_profile": tune.choice(
                    [profile.value for profile in ArchitectureProfile]
                ),
                "training_profile": tune.choice([profile.value for profile in TrainingProfile]),
                "learning_rate": tune.loguniform(1e-5, 1e-2),
                "batch_size": tune.choice([16, 32, 64]),
                "windows_batch_size": tune.choice([128, 256, 512]),
                "dropout": tune.choice([0.0, 0.1, 0.2]),
                "scaler_type": tune.choice(["identity", "robust"]),
                "random_seed": tune.randint(1, 20),
            }
            if backend == "optuna":
                return cls._ray_config_to_optuna(config)
            if backend != "ray":
                raise ValueError(f"unsupported AutoSegRNN backend: {backend}")
            return config

    AutoSegRNN.__name__ = "AutoSegRNN"
    AutoSegRNN.__qualname__ = "AutoSegRNN"
    AutoSegRNN.__module__ = module_name
    return AutoSegRNN
