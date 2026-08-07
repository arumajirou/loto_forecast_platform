from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import importlib.util
import sys
from pathlib import Path
from typing import Any

from loto.basicts_campaign.installed_provenance import (
    EXPECTED_DISTRIBUTION_NAME,
    InstalledProvenanceError,
    _distribution_files,
    _record_integrity,
)

DLINEAR_ARCH_MODULE = "basicts.models.DLinear.arch.dlinear_arch"
DLINEAR_CONFIG_MODULE = "basicts.models.DLinear.config.dlinear_config"
DLINEAR_MODULE_CONTRACTS: tuple[tuple[str, str, str, str], ...] = (
    (
        "dlinear_arch",
        DLINEAR_ARCH_MODULE,
        "basicts/models/DLinear/arch/dlinear_arch.py",
        "DLinear",
    ),
    (
        "dlinear_config",
        DLINEAR_CONFIG_MODULE,
        "basicts/models/DLinear/config/dlinear_config.py",
        "DLinearConfig",
    ),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reject_symlink_chain(path: Path, root: Path, *, label: str) -> None:
    candidate = path
    while True:
        if candidate.is_symlink():
            raise InstalledProvenanceError(f"{label} path contains a symbolic link")
        if candidate == root:
            return
        if candidate.parent == candidate:
            raise InstalledProvenanceError(f"{label} path escaped the distribution root")
        candidate = candidate.parent


def _distribution_module_file(
    distribution: importlib.metadata.Distribution,
    *,
    label: str,
    expected_entry: str,
) -> tuple[Path, dict[str, Any]]:
    candidates = [
        entry
        for entry in _distribution_files(distribution)
        if str(entry).replace("\\", "/") == expected_entry
    ]
    if len(candidates) != 1:
        raise InstalledProvenanceError(
            f"{label} distribution entry mismatch: expected one {expected_entry}, "
            f"got {len(candidates)}"
        )
    entry = candidates[0]
    raw_path = Path(distribution.locate_file(entry))
    root = raw_path
    for _ in Path(expected_entry).parts:
        root = root.parent
    _reject_symlink_chain(raw_path, root, label=label)
    if not raw_path.is_file():
        raise InstalledProvenanceError(f"{label} distribution file is missing")
    resolved_root = root.resolve(strict=True)
    resolved = raw_path.resolve(strict=True)
    if not resolved.is_relative_to(resolved_root):
        raise InstalledProvenanceError(f"{label} distribution file escaped its root")
    record = _record_integrity(entry, resolved, label=label)
    return resolved, {
        "label": label,
        "distribution_entry": expected_entry,
        "distribution_path": str(resolved),
        "record_status": record[f"{label}_record_status"],
        "record_hash_mode": record[f"{label}_record_hash_mode"],
        "record_hash_value": record[f"{label}_record_hash_value"],
        "record_size_bytes": record[f"{label}_record_size_bytes"],
        "module_file_sha256": _sha256(resolved),
    }


def _module_origin(
    module_name: str,
    expected_path: Path,
    *,
    label: str,
) -> tuple[str, bool]:
    already_loaded = module_name in sys.modules
    preloaded = sys.modules.get(module_name)
    if preloaded is not None:
        loaded_file = getattr(preloaded, "__file__", None)
        if not isinstance(loaded_file, str) or not loaded_file:
            raise InstalledProvenanceError(f"{label} preloaded module file is missing")
        loaded_path = Path(loaded_file)
        if loaded_path.is_symlink() or not loaded_path.is_file():
            raise InstalledProvenanceError(f"{label} preloaded module file is unsafe")
        if loaded_path.resolve(strict=True) != expected_path:
            raise InstalledProvenanceError(f"{label} preloaded module is shadowed")

    try:
        spec = importlib.util.find_spec(module_name)
    except (ImportError, AttributeError, ValueError) as exc:
        raise InstalledProvenanceError(f"cannot resolve {label} import spec") from exc
    if spec is None or not isinstance(spec.origin, str) or not spec.origin:
        raise InstalledProvenanceError(f"{label} import spec origin is missing")
    if spec.submodule_search_locations is not None:
        raise InstalledProvenanceError(f"{label} import spec unexpectedly describes a package")
    origin = Path(spec.origin)
    if origin.is_symlink() or not origin.is_file():
        raise InstalledProvenanceError(f"{label} import origin is unsafe")
    resolved_origin = origin.resolve(strict=True)
    if resolved_origin != expected_path:
        raise InstalledProvenanceError(f"{label} import origin is shadowed")

    module = importlib.import_module(module_name)
    loaded_file = getattr(module, "__file__", None)
    if not isinstance(loaded_file, str) or not loaded_file:
        raise InstalledProvenanceError(f"{label} loaded module file is missing")
    loaded_path = Path(loaded_file)
    if loaded_path.is_symlink() or not loaded_path.is_file():
        raise InstalledProvenanceError(f"{label} loaded module file is unsafe")
    resolved_loaded = loaded_path.resolve(strict=True)
    if resolved_loaded != expected_path:
        raise InstalledProvenanceError(f"{label} loaded module is shadowed")
    return str(resolved_loaded), already_loaded


def verify_dlinear_runtime_modules() -> dict[str, Any]:
    """Bind DLinear implementation modules to BasicTS distribution RECORD entries."""

    try:
        distribution = importlib.metadata.distribution(EXPECTED_DISTRIBUTION_NAME)
    except importlib.metadata.PackageNotFoundError as exc:
        raise InstalledProvenanceError("BasicTS is not installed") from exc

    evidence: list[dict[str, Any]] = []
    for label, module_name, expected_entry, required_symbol in DLINEAR_MODULE_CONTRACTS:
        expected_path, item = _distribution_module_file(
            distribution,
            label=label,
            expected_entry=expected_entry,
        )
        loaded_file, already_loaded = _module_origin(
            module_name,
            expected_path,
            label=label,
        )
        module = sys.modules.get(module_name)
        if module is None:
            raise InstalledProvenanceError(f"{label} module was not retained after import")
        symbol = getattr(module, required_symbol, None)
        if symbol is None:
            raise InstalledProvenanceError(
                f"{label} module does not expose required symbol {required_symbol}"
            )
        if getattr(symbol, "__module__", None) != module_name:
            raise InstalledProvenanceError(
                f"{label} required symbol is defined by another module"
            )
        evidence.append(
            {
                **item,
                "module_name": module_name,
                "required_symbol": required_symbol,
                "symbol_module": getattr(symbol, "__module__"),
                "import_spec_origin": str(expected_path),
                "loaded_module_file": loaded_file,
                "module_already_loaded": already_loaded,
            }
        )

    return {
        "dlinear_module_provenance_status": "PASS",
        "dlinear_runtime_modules": evidence,
    }
