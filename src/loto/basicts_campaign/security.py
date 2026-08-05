from __future__ import annotations

import importlib
import inspect
from typing import Any

from loto.basicts_campaign.protocol import ImportReference

ALLOWED_MODULE_PREFIXES: tuple[str, ...] = (
    "basicts",
    "loto.adapters.basicts",
    "torch.optim",
    "torch.optim.lr_scheduler",
)


class ConfigImportRejected(ValueError):
    """Raised when a serialized config references a non-approved import."""


def module_is_allowed(module: str) -> bool:
    """Return whether a module is inside an explicit BasicTS config allowlist."""

    return any(module == prefix or module.startswith(f"{prefix}.") for prefix in ALLOWED_MODULE_PREFIXES)


def validate_import_reference(reference: ImportReference) -> None:
    """Fail closed before importing a class or function from a config payload."""

    if not module_is_allowed(reference.module):
        raise ConfigImportRejected(
            f"module is outside the BasicTS config allowlist: {reference.module}"
        )
    if not reference.name.isidentifier():
        raise ConfigImportRejected(f"invalid imported object name: {reference.name}")


def resolve_import_reference(reference: ImportReference) -> dict[str, Any]:
    """Resolve one approved reference and return auditable identity evidence."""

    validate_import_reference(reference)
    module = importlib.import_module(reference.module)
    if not hasattr(module, reference.name):
        raise ConfigImportRejected(
            f"approved module does not expose requested object: {reference.module}.{reference.name}"
        )
    value = getattr(module, reference.name)
    return {
        "module": reference.module,
        "name": reference.name,
        "qualified_name": f"{reference.module}.{reference.name}",
        "object_kind": (
            "class" if inspect.isclass(value) else "callable" if callable(value) else "value"
        ),
        "constructor_signature": str(inspect.signature(value)) if callable(value) else None,
    }
