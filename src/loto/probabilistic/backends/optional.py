from __future__ import annotations

from typing import Any

from loto.probabilistic.backends.base import ProbabilisticBackend


class ProbeOnlyBackend(ProbabilisticBackend):
    def execute(self, *args: Any, **kwargs: Any) -> Any:
        probe = self.probe()
        if not probe.available:
            raise RuntimeError(f"{self.backend_id} is unavailable: {probe.detail}")
        raise NotImplementedError(
            f"native {self.backend_id} execution is not a primary PPL-01 path; "
            "select the model's primary backend or an implemented cross-backend adapter"
        )


class CmdStanPyBackend(ProbeOnlyBackend):
    backend_id = "stan"
    modules = ("cmdstanpy", "arviz")


class BlackJAXBackend(ProbeOnlyBackend):
    backend_id = "blackjax"
    modules = ("blackjax", "jax")


class TFPBackend(ProbeOnlyBackend):
    backend_id = "tfp"
    modules = ("tensorflow_probability",)
