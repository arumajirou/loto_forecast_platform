from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from loto.probabilistic.native import NativeImplementation


def _source_path() -> Path:
    project = (
        Path(__file__).resolve().parents[3] / "configs" / "probabilistic" / "native_primary.yaml"
    )
    if project.exists():
        return project
    packaged = Path(__file__).resolve().parent / "data" / "native_primary.yaml"
    if packaged.exists():
        return packaged
    raise FileNotFoundError("native_primary.yaml")


@lru_cache(maxsize=1)
def list_native_implementations() -> tuple[NativeImplementation, ...]:
    payload = yaml.safe_load(_source_path().read_text(encoding="utf-8"))
    rows = payload.get("implementations") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise ValueError("native_primary.yaml: implementations must be a list")
    output: list[NativeImplementation] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("native implementation rows must be mappings")
        model_id = str(row.get("model_id", "")).strip()
        if not model_id or model_id in seen:
            raise ValueError(f"duplicate or empty native model_id: {model_id!r}")
        seen.add(model_id)
        output.append(
            NativeImplementation(
                model_id=model_id,
                primary_backend=str(row["primary_backend"]),
                primary_profile=(
                    str(row["primary_profile"]) if row.get("primary_profile") else None
                ),
                implementation_kind=str(row["implementation_kind"]),
                module=str(row["module"]),
                graph_id=str(row["graph_id"]),
                runtime_tier=str(row.get("runtime_tier", "standard")),
            )
        )
    if len(output) < 72:
        raise ValueError(
            f"native implementation registry must preserve all 72 PPL-01 rows; got {len(output)}"
        )
    ppl02_model_id = "pp-conditional-bernoulli-fixed-k"
    if ppl02_model_id not in seen:
        output.append(
            NativeImplementation(
                model_id=ppl02_model_id,
                primary_backend="builtin",
                primary_profile=None,
                implementation_kind="analytic_map_laplace",
                module="loto.probabilistic.models.subset_native",
                graph_id="conditional_bernoulli_fixed_k_v1",
                runtime_tier="standard",
            )
        )
    return tuple(output)


@lru_cache(maxsize=128)
def get_native_implementation(model_id: str) -> NativeImplementation:
    for item in list_native_implementations():
        if item.model_id == model_id:
            return item
    raise KeyError(model_id)


def native_coverage() -> dict[str, Any]:
    rows = list_native_implementations()
    by_backend: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    for row in rows:
        by_backend[row.primary_backend] = by_backend.get(row.primary_backend, 0) + 1
        by_kind[row.implementation_kind] = by_kind.get(row.implementation_kind, 0) + 1
    return {
        "models": len(rows),
        "by_primary_backend": dict(sorted(by_backend.items())),
        "by_implementation_kind": dict(sorted(by_kind.items())),
        "all_primary_paths_declared": len(rows) >= 72,
    }
