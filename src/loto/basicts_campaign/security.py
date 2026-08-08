from __future__ import annotations

import importlib
from typing import Any

from .contracts import ImportReference, SafeConfig

_ALLOWED_MODULE_ROOTS = (
    "basicts",
    "loto.adapters.basicts",
    "torch.optim",
    "torch.optim.lr_scheduler",
)


class UnsafeImportReference(ValueError):
    """Raised when a declarative object reference is outside the approved surface."""


# Pre-conflict PR #56 tests and callers used this name for the same fail-closed condition.
ConfigImportRejected = UnsafeImportReference


def is_allowed_module(module: str) -> bool:
    return any(module == root or module.startswith(f"{root}.") for root in _ALLOWED_MODULE_ROOTS)


def validate_import_reference(reference: ImportReference) -> None:
    if not is_allowed_module(reference.module):
        raise UnsafeImportReference(f"module is not allowlisted: {reference.module}")


def resolve_import_reference(reference: ImportReference) -> Any:
    validate_import_reference(reference)
    module = importlib.import_module(reference.module)
    try:
        return getattr(module, reference.name)
    except AttributeError as exc:
        raise UnsafeImportReference(
            f"allowlisted object does not exist: {reference.module}.{reference.name}"
        ) from exc


def validate_safe_config(config: SafeConfig, *, resolve: bool = False) -> dict[str, str]:
    references = {
        "model": config.model,
        "optimizer": config.optimizer,
    }
    if config.lr_scheduler is not None:
        references["lr_scheduler"] = config.lr_scheduler

    resolved: dict[str, str] = {}
    for key, reference in references.items():
        validate_import_reference(reference)
        if resolve:
            obj = resolve_import_reference(reference)
            resolved[key] = f"{obj.__module__}.{obj.__name__}"
        else:
            resolved[key] = f"{reference.module}.{reference.name}"
    return resolved
