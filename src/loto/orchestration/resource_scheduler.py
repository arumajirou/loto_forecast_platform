from __future__ import annotations

from loto.orchestration.resource_scheduler_impl import (
    ResolvedResourcePlan,
    ResourceLease,
    ResourcePolicy,
    ResourceScheduler,
    ResourceSnapshot,
    collect_resource_snapshot,
    resolve_resource_plan,
)
from loto.orchestration.resource_scheduler_impl import (
    runtime_resource_class as _runtime_resource_class,
)

_GPU_OPTIONAL_BROAD_LIBRARIES = frozenset({"xgboost", "catboost", "lightgbm"})


def runtime_resource_class(
    *,
    model_id: str,
    library: str,
    class_name: str = "",
    capabilities: tuple[str, ...] = (),
) -> str:
    """Return the runtime scheduling class with certified broad-tree GPU routing.

    The frozen Broad catalog predates the ``gpu_optional`` capability on the shared
    model specs for XGBoost, CatBoost, and LightGBM. Keep the catalog identity unchanged
    while making the runtime scheduler consume only backend capabilities that have been
    wired and verified on the self-hosted GPU runtime.

    LightGBM is certified specifically for its OpenCL backend (``device_type="gpu"``),
    not for the separate CUDA tree learner. The model factory therefore remains
    responsible for injecting the correct backend-specific device parameters after a
    GPU lease is granted.
    """

    effective_capabilities = capabilities
    if library in _GPU_OPTIONAL_BROAD_LIBRARIES and "gpu_optional" not in capabilities:
        effective_capabilities = (*capabilities, "gpu_optional")
    return _runtime_resource_class(
        model_id=model_id,
        library=library,
        class_name=class_name,
        capabilities=effective_capabilities,
    )


__all__ = [
    "ResolvedResourcePlan",
    "ResourceLease",
    "ResourcePolicy",
    "ResourceScheduler",
    "ResourceSnapshot",
    "collect_resource_snapshot",
    "resolve_resource_plan",
    "runtime_resource_class",
]
