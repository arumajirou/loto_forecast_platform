#!/usr/bin/env python
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from loto.models.catalog_full import build_catalog
from loto.orchestration.weighted_resource_scheduler import (
    WeightedResourceScheduler,
    configure_weighted_profiles,
    weighted_runtime_resource_class,
)

ROOT = Path(__file__).resolve().parents[1]
BASE_RUNNER = ROOT / "scripts" / "run_resource_aware_broad_campaign.py"
DEFAULT_BASE_GPU_SLOT_MIB = 2048


def _load_base_runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location("loto_weighted_base_runner", BASE_RUNNER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load base runner: {BASE_RUNNER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _has_option(argv: list[str], option: str) -> bool:
    return option in argv or any(item.startswith(f"{option}=") for item in argv)


def _inject_weighted_defaults(argv: list[str]) -> list[str]:
    resolved = list(argv)
    if not _has_option(resolved, "--gpu-slot-mib"):
        resolved.extend(["--gpu-slot-mib", str(DEFAULT_BASE_GPU_SLOT_MIB)])
    return resolved


def main(argv: list[str] | None = None) -> int:
    base = _load_base_runner()

    # Configure the profile registry from the same broad catalog the base runner uses,
    # then replace only the scheduling hooks. Execution/evaluation semantics remain
    # the existing audited campaign implementation.
    configure_weighted_profiles(build_catalog())
    base.ResourceScheduler = WeightedResourceScheduler
    base.runtime_resource_class = weighted_runtime_resource_class

    resolved_argv = _inject_weighted_defaults(list(sys.argv[1:] if argv is None else argv))
    return int(base.main(resolved_argv))


if __name__ == "__main__":
    raise SystemExit(main())
