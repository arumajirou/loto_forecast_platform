from __future__ import annotations

from typing import Callable

from .p6_contract import P6Operation, P6ProviderRequest, P6StageEvidence
from .p6_fit_runtime import fit_serialize
from .p6_reload_runtime import load_predict
from .p6_runtime_common import RuntimeBindings, load_runtime_bindings


def execute_stage(
    request: P6ProviderRequest,
    *,
    bindings_loader: Callable[[], RuntimeBindings] = load_runtime_bindings,
    observed_versions: dict[str, str | None] | None = None,
) -> P6StageEvidence:
    if request.operation is P6Operation.FIT_SERIALIZE:
        return fit_serialize(
            request,
            bindings_loader=bindings_loader,
            observed_versions=observed_versions,
        )
    return load_predict(
        request,
        bindings_loader=bindings_loader,
        observed_versions=observed_versions,
    )


__all__ = [
    "RuntimeBindings",
    "execute_stage",
    "fit_serialize",
    "load_predict",
    "load_runtime_bindings",
]
