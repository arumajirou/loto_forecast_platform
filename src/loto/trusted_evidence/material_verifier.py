"""Read-only SHA-256 verification for retained evidence material."""

from __future__ import annotations

from pathlib import Path

from .canonical import sha256_file
from .model_base import VerificationMaterial


def verify_materials(
    materials: list[VerificationMaterial],
    *,
    material_root: Path,
    label: str,
) -> list[str]:
    failures: list[str] = []
    try:
        root = material_root.resolve(strict=True)
    except OSError as exc:
        return [f"{label} material root unavailable: {type(exc).__name__}: {exc}"]
    if material_root.is_symlink() or not root.is_dir():
        return [f"{label} material root must be a regular directory"]

    for material in materials:
        path = root.joinpath(*material.relative_path.split("/"))
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(root)
        except (OSError, ValueError) as exc:
            failures.append(
                f"{label} material path unavailable or outside root: "
                f"{material.relative_path}: {type(exc).__name__}: {exc}"
            )
            continue
        if path.is_symlink() or not resolved.is_file():
            failures.append(
                f"{label} material must be a regular non-symlink file: {material.relative_path}"
            )
            continue
        try:
            size = resolved.stat().st_size
            digest = sha256_file(resolved)
        except OSError as exc:
            failures.append(
                f"{label} material unreadable: {material.relative_path}: "
                f"{type(exc).__name__}: {exc}"
            )
            continue
        if size != material.size_bytes:
            failures.append(
                f"{label} material size mismatch: {material.relative_path}: "
                f"expected={material.size_bytes}, actual={size}"
            )
        if digest != material.sha256:
            failures.append(
                f"{label} material SHA-256 mismatch: {material.relative_path}: "
                f"expected={material.sha256}, actual={digest}"
            )
    return failures
