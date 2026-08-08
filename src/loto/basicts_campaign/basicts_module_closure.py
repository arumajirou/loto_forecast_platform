from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import sys
from pathlib import Path
from typing import Any

from loto.basicts_campaign.dlinear_runtime_provenance import (
    DLINEAR_ARCH_MODULE,
    DLINEAR_CONFIG_MODULE,
    DLINEAR_MODULE_CONTRACTS,
    verify_dlinear_runtime_modules,
)
from loto.basicts_campaign.installed_provenance import (
    EXPECTED_DISTRIBUTION_NAME,
    EXPECTED_PACKAGE_INIT,
    InstalledProvenanceError,
    _distribution_files,
    _record_integrity,
)

DECOMPOSITION_MODULE = "basicts.modules.decomposition"
CONFIGS_PACKAGE = "basicts.configs"
MODEL_CONFIG_MODULE = "basicts.configs.model_config"
RUNTIME_CRITICAL_MODULES = frozenset(
    {
        DLINEAR_ARCH_MODULE,
        DLINEAR_CONFIG_MODULE,
        DECOMPOSITION_MODULE,
        CONFIGS_PACKAGE,
        MODEL_CONFIG_MODULE,
    }
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reject_symlink_chain(path: Path, root: Path, *, label: str) -> None:
    if not path.is_absolute() or not root.is_absolute():
        raise InstalledProvenanceError(f"{label} path is not absolute")
    candidate = path
    while True:
        if candidate.is_symlink():
            raise InstalledProvenanceError(f"{label} path contains a symbolic link")
        if candidate == root:
            return
        if candidate.parent == candidate:
            raise InstalledProvenanceError(f"{label} path escaped the distribution root")
        candidate = candidate.parent


def _distribution_roots(distribution: importlib.metadata.Distribution) -> tuple[Path, Path]:
    candidates = [
        entry
        for entry in _distribution_files(distribution)
        if str(entry).replace("\\", "/") == EXPECTED_PACKAGE_INIT
    ]
    if len(candidates) != 1:
        raise InstalledProvenanceError(
            "BasicTS package root entry mismatch: "
            f"expected one {EXPECTED_PACKAGE_INIT}, got {len(candidates)}"
        )
    package_init = Path(distribution.locate_file(candidates[0]))
    root = package_init
    for _ in Path(EXPECTED_PACKAGE_INIT).parts:
        root = root.parent
    _reject_symlink_chain(package_init, root, label="BasicTS distribution root")
    if not package_init.is_file():
        raise InstalledProvenanceError("BasicTS distribution package __init__.py is missing")
    resolved_root = root.resolve(strict=True)
    resolved_init = package_init.resolve(strict=True)
    if resolved_init != resolved_root / EXPECTED_PACKAGE_INIT:
        raise InstalledProvenanceError("BasicTS distribution root is inconsistent")
    return root, resolved_root


def _entry_for_path(
    distribution: importlib.metadata.Distribution,
    relative_path: str,
    *,
    label: str,
) -> Any:
    candidates = [
        entry
        for entry in _distribution_files(distribution)
        if str(entry).replace("\\", "/") == relative_path
    ]
    if len(candidates) != 1:
        raise InstalledProvenanceError(
            f"{label} distribution entry mismatch: expected one {relative_path}, "
            f"got {len(candidates)}"
        )
    return candidates[0]


def _module_record_evidence(
    distribution: importlib.metadata.Distribution,
    raw_root: Path,
    resolved_root: Path,
    *,
    module_name: str,
    module: Any,
    index: int,
) -> dict[str, Any]:
    loaded_file = getattr(module, "__file__", None)
    if not isinstance(loaded_file, str) or not loaded_file:
        raise InstalledProvenanceError(f"loaded BasicTS module file is missing: {module_name}")
    loaded_path = Path(loaded_file)
    _reject_symlink_chain(loaded_path, raw_root, label=module_name)
    if not loaded_path.is_file():
        raise InstalledProvenanceError(f"loaded BasicTS module file is unsafe: {module_name}")
    resolved = loaded_path.resolve(strict=True)
    if not resolved.is_relative_to(resolved_root):
        raise InstalledProvenanceError(
            f"loaded BasicTS module escaped the distribution root: {module_name}"
        )
    relative_path = resolved.relative_to(resolved_root).as_posix()
    label = f"loaded_basicts_module_{index}"
    entry = _entry_for_path(distribution, relative_path, label=module_name)
    located = Path(distribution.locate_file(entry))
    _reject_symlink_chain(located, raw_root, label=module_name)
    if not located.is_file() or located.resolve(strict=True) != resolved:
        raise InstalledProvenanceError(
            f"loaded BasicTS module differs from its distribution entry: {module_name}"
        )
    record = _record_integrity(entry, resolved, label=label)

    try:
        spec = importlib.util.find_spec(module_name)
    except (ImportError, AttributeError, ValueError) as exc:
        raise InstalledProvenanceError(
            f"cannot resolve loaded BasicTS module spec: {module_name}"
        ) from exc
    if spec is None or not isinstance(spec.origin, str) or not spec.origin:
        raise InstalledProvenanceError(
            f"loaded BasicTS module spec origin is missing: {module_name}"
        )
    spec_path = Path(spec.origin)
    _reject_symlink_chain(spec_path, raw_root, label=module_name)
    if not spec_path.is_file() or spec_path.resolve(strict=True) != resolved:
        raise InstalledProvenanceError(f"loaded BasicTS module spec is shadowed: {module_name}")
    return {
        "module_name": module_name,
        "distribution_entry": relative_path,
        "distribution_path": str(resolved),
        "import_spec_origin": str(resolved),
        "loaded_module_file": str(resolved),
        "record_status": record[f"{label}_record_status"],
        "record_hash_mode": record[f"{label}_record_hash_mode"],
        "record_hash_value": record[f"{label}_record_hash_value"],
        "record_size_bytes": record[f"{label}_record_size_bytes"],
        "module_file_sha256": _sha256(resolved),
        "is_package": spec.submodule_search_locations is not None,
    }


def _loaded_module_evidence(
    distribution: importlib.metadata.Distribution,
    raw_root: Path,
    resolved_root: Path,
) -> list[dict[str, Any]]:
    names = sorted(name for name in sys.modules if name == "basicts" or name.startswith("basicts."))
    if not names:
        raise InstalledProvenanceError("DLinear import loaded no BasicTS modules")
    return [
        _module_record_evidence(
            distribution,
            raw_root,
            resolved_root,
            module_name=module_name,
            module=sys.modules[module_name],
            index=index,
        )
        for index, module_name in enumerate(names)
    ]


def _dependency_bindings() -> dict[str, Any]:
    arch = sys.modules[DLINEAR_ARCH_MODULE]
    config = sys.modules[DLINEAR_CONFIG_MODULE]
    decomposition = sys.modules[DECOMPOSITION_MODULE]
    configs_package = sys.modules[CONFIGS_PACKAGE]
    model_config = sys.modules[MODEL_CONFIG_MODULE]

    moving_average = getattr(decomposition, "MovingAverageDecomposition", None)
    if (
        moving_average is None
        or getattr(moving_average, "__module__", None) != DECOMPOSITION_MODULE
        or getattr(arch, "MovingAverageDecomposition", None) is not moving_average
    ):
        raise InstalledProvenanceError(
            "DLinear decomposition dependency is not bound to the verified module"
        )
    basic_config = getattr(model_config, "BasicTSModelConfig", None)
    if basic_config is None or getattr(basic_config, "__module__", None) != MODEL_CONFIG_MODULE:
        raise InstalledProvenanceError("BasicTSModelConfig is missing or has the wrong origin")
    if getattr(config, "BasicTSModelConfig", None) is not basic_config:
        raise InstalledProvenanceError(
            "DLinearConfig module base dependency is not bound to model_config"
        )
    if getattr(configs_package, "BasicTSModelConfig", None) is not basic_config:
        raise InstalledProvenanceError("basicts.configs export is not bound to model_config")
    dlinear_config = getattr(config, "DLinearConfig", None)
    if not isinstance(dlinear_config, type) or len(dlinear_config.__mro__) < 2:
        raise InstalledProvenanceError("DLinearConfig class hierarchy is invalid")
    if dlinear_config.__mro__[1] is not basic_config:
        raise InstalledProvenanceError(
            "DLinearConfig does not directly inherit the verified BasicTSModelConfig"
        )
    return {
        "dlinear_dependency_binding_status": "PASS",
        "dlinear_dependency_bindings": {
            "decomposition_symbol": (f"{moving_average.__module__}.{moving_average.__name__}"),
            "config_base_symbol": f"{basic_config.__module__}.{basic_config.__name__}",
            "dlinear_config_direct_base": (
                f"{dlinear_config.__mro__[1].__module__}.{dlinear_config.__mro__[1].__name__}"
            ),
            "arch_decomposition_object_identity": True,
            "config_model_config_object_identity": True,
            "configs_export_object_identity": True,
            "dlinear_config_direct_base_identity": True,
        },
    }


def verify_dlinear_import_closure() -> dict[str, Any]:
    """Bind the complete loaded BasicTS closure for DLinear to distribution RECORD."""

    preloaded = sorted(
        name for name in sys.modules if name == "basicts" or name.startswith("basicts.")
    )
    if preloaded:
        raise InstalledProvenanceError(
            "BasicTS modules were already loaded before DLinear provenance verification: "
            f"{preloaded}"
        )
    try:
        distribution = importlib.metadata.distribution(EXPECTED_DISTRIBUTION_NAME)
    except importlib.metadata.PackageNotFoundError as exc:
        raise InstalledProvenanceError("BasicTS is not installed") from exc

    raw_root, resolved_root = _distribution_roots(distribution)
    critical = verify_dlinear_runtime_modules()
    closure = _loaded_module_evidence(distribution, raw_root, resolved_root)
    closure_names = {item["module_name"] for item in closure}
    if not RUNTIME_CRITICAL_MODULES.issubset(closure_names):
        raise InstalledProvenanceError(
            "DLinear critical modules are missing from the loaded BasicTS closure"
        )
    return {
        **critical,
        "basicts_module_closure_status": "PASS",
        "preloaded_basicts_modules": preloaded,
        "loaded_basicts_module_count": len(closure),
        "loaded_basicts_modules": closure,
        **_dependency_bindings(),
    }
