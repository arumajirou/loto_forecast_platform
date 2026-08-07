"""Deterministic runtime-evidence artifacts, manifests, and ZIP packaging."""

from __future__ import annotations

import json
import os
import stat
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from .contracts import ArtifactIdentity, contains_control_characters
from .identity import sha256_file


class ArtifactVerificationError(RuntimeError):
    pass


_FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def _safe_output_path(path: Path, *, overwrite: bool) -> Path:
    raw = path.expanduser().absolute()
    parent = raw.parent
    current = Path(parent.anchor)
    for component in parent.parts[1:]:
        current = current / component
        if current.exists() and current.is_symlink():
            raise ArtifactVerificationError("output path contains a symlink component")
    parent.mkdir(parents=True, exist_ok=True)
    current = Path(parent.anchor)
    for component in parent.parts[1:]:
        current = current / component
        if current.is_symlink():
            raise ArtifactVerificationError("output path contains a symlink component")
    resolved_parent = parent.resolve(strict=True)
    target = resolved_parent / raw.name
    if target.is_symlink():
        raise ArtifactVerificationError("output path must not be a symlink")
    if target.exists() and not overwrite:
        raise ArtifactVerificationError("output already exists and overwrite was not authorized")
    return target


def _fsync_directory(path: Path) -> None:
    if not hasattr(os, "O_DIRECTORY"):
        return
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write_text(path: Path, content: str, *, overwrite: bool = False) -> None:
    target = _safe_output_path(path, overwrite=overwrite)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        _fsync_directory(target.parent)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_write_json(path: Path, payload: Any, *, overwrite: bool = False) -> None:
    content = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"
    _atomic_write_text(path, content, overwrite=overwrite)


def _safe_files(root: Path) -> list[Path]:
    root = root.resolve(strict=True)
    files: list[Path] = []
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ArtifactVerificationError(f"symlink is forbidden: {path}")
        if path.is_file():
            resolved = path.resolve(strict=True)
            try:
                resolved.relative_to(root)
            except ValueError as exc:
                raise ArtifactVerificationError(f"artifact escapes root: {path}") from exc
            files.append(resolved)
    return sorted(files, key=lambda item: item.relative_to(root).as_posix())


def build_artifact_manifest(
    root: Path,
    *,
    excluded: set[str] | None = None,
) -> list[ArtifactIdentity]:
    excluded = excluded or set()
    root = root.resolve(strict=True)
    records: list[ArtifactIdentity] = []
    for path in _safe_files(root):
        relative = path.relative_to(root).as_posix()
        if relative in excluded:
            continue
        records.append(
            ArtifactIdentity(
                relative_path=relative,
                sha256=sha256_file(path),
                size_bytes=path.stat().st_size,
                role="runtime_evidence",
            )
        )
    return records


def write_sha256s(root: Path, output: Path, *, overwrite: bool = False) -> None:
    root = root.resolve(strict=True)
    target = _safe_output_path(output, overwrite=overwrite)
    excluded = {target.relative_to(root).as_posix()} if target.is_relative_to(root) else set()
    records = build_artifact_manifest(root, excluded=excluded)
    lines = [f"{record.sha256}  {record.relative_path}" for record in records]
    _atomic_write_text(
        target,
        "\n".join(lines) + ("\n" if lines else ""),
        overwrite=overwrite,
    )


def verify_sha256s(root: Path, manifest_path: Path) -> list[ArtifactIdentity]:
    root = root.resolve(strict=True)
    if manifest_path.is_symlink():
        raise ArtifactVerificationError("SHA256SUMS must not be a symlink")
    lines = manifest_path.read_text(encoding="utf-8").splitlines()
    parsed: list[ArtifactIdentity] = []
    seen: set[str] = set()
    for line in lines:
        digest, separator, relative = line.partition("  ")
        if separator != "  " or len(digest) != 64:
            raise ArtifactVerificationError("invalid SHA256SUMS row")
        try:
            ArtifactIdentity(
                relative_path=relative,
                sha256=digest,
                size_bytes=0,
                role="runtime_evidence",
            )
        except ValueError as exc:
            raise ArtifactVerificationError(f"unsafe SHA256SUMS path: {relative}") from exc
        if relative in seen or relative.casefold() in {item.casefold() for item in seen}:
            raise ArtifactVerificationError(f"duplicate SHA256SUMS path: {relative}")
        seen.add(relative)
        path = root / relative
        if path.is_symlink():
            raise ArtifactVerificationError(f"symlink is forbidden: {relative}")
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(root)
        except (OSError, ValueError) as exc:
            raise ArtifactVerificationError(f"unsafe or missing artifact: {relative}") from exc
        if not resolved.is_file():
            raise ArtifactVerificationError(f"artifact is not a regular file: {relative}")
        actual = sha256_file(resolved)
        if actual != digest:
            raise ArtifactVerificationError(f"artifact hash mismatch: {relative}")
        parsed.append(
            ArtifactIdentity(
                relative_path=relative,
                sha256=digest,
                size_bytes=resolved.stat().st_size,
                role="runtime_evidence",
            )
        )
    expected = {
        path.relative_to(root).as_posix()
        for path in _safe_files(root)
        if path.resolve() != manifest_path.resolve()
    }
    if seen != expected:
        raise ArtifactVerificationError(
            f"SHA256SUMS inventory mismatch: missing={sorted(expected - seen)}, "
            f"extra={sorted(seen - expected)}"
        )
    return parsed


def create_deterministic_zip(
    source_root: Path,
    output_zip: Path,
    *,
    overwrite: bool = False,
) -> str:
    source_root = source_root.resolve(strict=True)
    target = _safe_output_path(output_zip, overwrite=overwrite)
    try:
        target.relative_to(source_root)
    except ValueError:
        pass
    else:
        raise ArtifactVerificationError("evidence ZIP must be outside the source evidence root")
    descriptor, temporary_name = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(
            temporary,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
            allowZip64=True,
        ) as archive:
            for path in _safe_files(source_root):
                relative = path.relative_to(source_root).as_posix()
                info = zipfile.ZipInfo(relative, date_time=_FIXED_ZIP_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                with path.open("rb") as source, archive.open(info, "w") as destination:
                    for block in iter(lambda: source.read(1024 * 1024), b""):
                        destination.write(block)
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        _fsync_directory(target.parent)
    finally:
        temporary.unlink(missing_ok=True)
    return sha256_file(target)


def create_evidence_zip(
    source_root: Path,
    output_zip: Path,
    *,
    overwrite: bool = False,
) -> tuple[Path, Path, str]:
    sidecar = output_zip.with_name(f"{output_zip.name}.sha256")
    _safe_output_path(sidecar, overwrite=overwrite)
    digest = create_deterministic_zip(source_root, output_zip, overwrite=overwrite)
    _atomic_write_text(
        sidecar,
        f"{digest}  {output_zip.name}\n",
        overwrite=overwrite,
    )
    return output_zip, sidecar, digest


def _validate_zip_name(name: str) -> None:
    if not name or name.startswith(("/", "\\")) or "\\" in name or ":" in name:
        raise ArtifactVerificationError(f"unsafe ZIP member: {name!r}")
    if contains_control_characters(name):
        raise ArtifactVerificationError(f"unsafe ZIP member: {name!r}")
    if any(part in {"", ".", ".."} for part in name.split("/")):
        raise ArtifactVerificationError(f"unsafe ZIP member: {name!r}")


def verify_evidence_zip(
    zip_path: Path,
    sidecar_path: Path,
    *,
    max_members: int = 100_000,
    max_member_size: int = 8 * 1024**3,
    max_total_size: int = 64 * 1024**3,
    max_compression_ratio: float = 1_000.0,
) -> str:
    if (
        zip_path.is_symlink()
        or sidecar_path.is_symlink()
        or not zip_path.is_file()
        or not sidecar_path.is_file()
    ):
        raise ArtifactVerificationError("ZIP and sidecar must be regular files")
    digest, separator, filename = sidecar_path.read_text(encoding="utf-8").strip().partition("  ")
    if separator != "  " or filename != zip_path.name or digest != sha256_file(zip_path):
        raise ArtifactVerificationError("evidence ZIP sidecar mismatch")
    names: set[str] = set()
    folded_names: set[str] = set()
    total_size = 0
    with zipfile.ZipFile(zip_path, "r") as archive:
        infos = archive.infolist()
        if not infos or len(infos) > max_members:
            raise ArtifactVerificationError("evidence ZIP member count is invalid")
        for info in infos:
            _validate_zip_name(info.filename)
            folded = info.filename.casefold()
            if info.filename in names or folded in folded_names:
                raise ArtifactVerificationError(f"duplicate ZIP member: {info.filename}")
            names.add(info.filename)
            folded_names.add(folded)
            mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(mode) or info.is_dir() or info.flag_bits & 0x1:
                raise ArtifactVerificationError(f"unsupported ZIP member: {info.filename}")
            if info.file_size > max_member_size:
                raise ArtifactVerificationError(f"ZIP member exceeds size limit: {info.filename}")
            total_size += info.file_size
            if total_size > max_total_size:
                raise ArtifactVerificationError("evidence ZIP exceeds total size limit")
            if info.compress_size == 0:
                ratio = float("inf") if info.file_size else 1.0
            else:
                ratio = info.file_size / info.compress_size
            if ratio > max_compression_ratio:
                raise ArtifactVerificationError(
                    f"ZIP member exceeds compression-ratio limit: {info.filename}"
                )
        corrupt = archive.testzip()
        if corrupt is not None:
            raise ArtifactVerificationError(f"evidence ZIP CRC failure: {corrupt}")
    return digest
