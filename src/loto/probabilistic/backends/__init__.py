from __future__ import annotations

from loto.probabilistic.backends.arviz_adapter import ArviZStackingBackend
from loto.probabilistic.backends.base import BackendProbe, ProbabilisticBackend
from loto.probabilistic.backends.builtin import BuiltinBackend
from loto.probabilistic.backends.numpyro_adapter import NumPyroBackend
from loto.probabilistic.backends.optional import BlackJAXBackend, CmdStanPyBackend, TFPBackend
from loto.probabilistic.backends.pymc_adapter import PyMCBackend
from loto.probabilistic.backends.pymc_bart_adapter import PyMCBartBackend
from loto.probabilistic.backends.pyro_adapter import PyroBackend

_BACKENDS: dict[str, ProbabilisticBackend] = {
    "builtin": BuiltinBackend(),
    "pymc": PyMCBackend(),
    "pymc_bart": PyMCBartBackend(),
    "numpyro": NumPyroBackend(),
    "pyro": PyroBackend(),
    "arviz": ArviZStackingBackend(),
    "stan": CmdStanPyBackend(),
    "cmdstanpy": CmdStanPyBackend(),
    "blackjax": BlackJAXBackend(),
    "tfp": TFPBackend(),
    "tensorflow_probability": TFPBackend(),
}


def get_backend(name: str) -> ProbabilisticBackend:
    try:
        return _BACKENDS[name]
    except KeyError as exc:
        raise KeyError(f"unknown probabilistic backend: {name}") from exc


def probe_backends() -> list[dict[str, object]]:
    unique = {value.backend_id: value for value in _BACKENDS.values()}
    return [
        backend.probe().to_dict() for backend in sorted(unique.values(), key=lambda x: x.backend_id)
    ]


__all__ = ["BackendProbe", "ProbabilisticBackend", "get_backend", "probe_backends"]
