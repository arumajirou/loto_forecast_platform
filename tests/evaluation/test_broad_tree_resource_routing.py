from __future__ import annotations

from loto.models.catalog_full import build_catalog
from loto.orchestration.resource_scheduler import runtime_resource_class


def _resource_class(model_id: str) -> str:
    entry = next(model for model in build_catalog() if model.model_id == model_id)
    return runtime_resource_class(
        model_id=entry.model_id,
        library=entry.library,
        class_name=entry.class_name,
        capabilities=entry.capabilities,
    )


def test_broad_xgboost_and_catboost_are_gpu_routable() -> None:
    assert _resource_class("xgboost-classifier") == "GPU"
    assert _resource_class("catboost-classifier") == "GPU"


def test_broad_lightgbm_stays_cpu_until_build_is_certified() -> None:
    assert _resource_class("lightgbm-classifier") == "CPU"
    assert _resource_class("lightgbm-position") == "CPU"
