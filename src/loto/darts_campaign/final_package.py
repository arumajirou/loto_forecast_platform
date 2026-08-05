from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

REQUIRED_DOCUMENTS: tuple[str, ...] = (
    "README.md",
    "REQUIREMENTS.md",
    "SPECIFICATION.md",
    "ARCHITECTURE.md",
    "DATA_CONTRACT.md",
    "TEST_PLAN.md",
    "VERIFICATION_REPORT.md",
    "CHANGELOG.md",
    "HANDOFF.md",
    "RUNBOOK.md",
    "ARTIFACT_MANIFEST.md",
    "SHA256SUMS",
)
HASHED_DOCUMENTS: tuple[str, ...] = REQUIRED_DOCUMENTS[:-1]
FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
NORMALIZED_MODE = 0o100644


class FinalPackageError(ValueError):
    """Raised when the final handoff package fails a fail-closed contract."""


class FinalPackageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=1, ge=1)
    package_id: str = Field(min_length=1)
    source_dir: Path
    output_zip: Path
    source_commit: str = Field(min_length=7)
    base_commit: str = Field(min_length=7)
    generated_at_utc: str = Field(min_length=1)
    required_documents: tuple[str, ...] = REQUIRED_DOCUMENTS
    compression_level: int = Field(default=9, ge=0, le=9)

    @model_validator(mode="after")
    def validate_contract(self) -> "FinalPackageConfig":
        if self.required_documents != REQUIRED_DOCUMENTS:
            raise ValueError("required_documents must exactly match the final handoff contract")
        if self.output_zip.suffix.lower() != ".zip":
            raise ValueError("output_zip must end with .zip")
        return self


class ManifestEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class PackageVerification(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    package_id: str
    zip_path: str
    zip_size_bytes: int = Field(ge=1)
    zip_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    member_count: int = Field(ge=1)
    members: tuple[str, ...]
    content_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    passed: bool


@dataclass(frozen=True)
class BuiltPackage:
    config: FinalPackageConfig
    entries: tuple[ManifestEntry, ...]
    verification: PackageVerification


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_member_name(name: str) -> str:
    if not name or "\\" in name:
        raise FinalPackageError(f"unsafe package path: {name!r}")
    candidate = PurePosixPath(name)
    if candidate.is_absolute() or ".." in candidate.parts or len(candidate.parts) != 1:
        raise FinalPackageError(f"unsafe package path: {name!r}")
    return candidate.as_posix()


def validate_required_documents(source_dir: Path) -> tuple[Path, ...]:
    if not source_dir.is_dir():
        raise FinalPackageError(f"source directory is missing: {source_dir}")
    paths: list[Path] = []
    for name in REQUIRED_DOCUMENTS:
        _safe_member_name(name)
        path = source_dir / name
        if not path.is_file():
            raise FinalPackageError(f"required document is missing: {name}")
        paths.append(path)
    unexpected = sorted(
        path.name
        for path in source_dir.iterdir()
        if path.is_file() and path.name not in REQUIRED_DOCUMENTS
    )
    if unexpected:
        raise FinalPackageError(f"unexpected package documents: {unexpected}")
    return tuple(paths)


def build_manifest_entries(source_dir: Path) -> tuple[ManifestEntry, ...]:
    validate_required_documents(source_dir)
    return tuple(
        ManifestEntry(
            path=name,
            size_bytes=(source_dir / name).stat().st_size,
            sha256=sha256_file(source_dir / name),
        )
        for name in HASHED_DOCUMENTS
    )


def render_sha256s(entries: Sequence[ManifestEntry]) -> str:
    expected = tuple(entry.path for entry in entries)
    if expected != HASHED_DOCUMENTS:
        raise FinalPackageError("manifest entry order must match HASHED_DOCUMENTS")
    return "".join(f"{entry.sha256}  {entry.path}\n" for entry in entries)


def verify_sha256s(source_dir: Path) -> tuple[ManifestEntry, ...]:
    checksum_path = source_dir / "SHA256SUMS"
    if not checksum_path.is_file():
        raise FinalPackageError("SHA256SUMS is missing")
    parsed: dict[str, str] = {}
    checksum_lines = checksum_path.read_text(encoding="utf-8").splitlines()
    for line_number, raw_line in enumerate(checksum_lines, 1):
        if not raw_line.strip():
            continue
        try:
            digest, name = raw_line.split("  ", 1)
        except ValueError as error:
            raise FinalPackageError(f"invalid SHA256SUMS line {line_number}") from error
        _safe_member_name(name)
        if name in parsed:
            raise FinalPackageError(f"duplicate SHA256SUMS entry: {name}")
        invalid_digest = len(digest) != 64 or any(
            character not in "0123456789abcdef" for character in digest
        )
        if invalid_digest:
            raise FinalPackageError(f"invalid SHA-256 digest for {name}")
        parsed[name] = digest
    if tuple(parsed) != HASHED_DOCUMENTS:
        raise FinalPackageError("SHA256SUMS members or order differ from the contract")
    entries = build_manifest_entries(source_dir)
    for entry in entries:
        if parsed[entry.path] != entry.sha256:
            raise FinalPackageError(f"SHA-256 mismatch: {entry.path}")
    return entries


def content_manifest_sha256(entries: Sequence[ManifestEntry]) -> str:
    payload = [entry.model_dump(mode="json") for entry in entries]
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256_bytes(canonical.encode("utf-8"))


def _write_deterministic_zip(
    source_dir: Path,
    output_zip: Path,
    *,
    compression_level: int,
) -> None:
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_zip.with_suffix(output_zip.suffix + ".tmp")
    if temporary.exists():
        temporary.unlink()
    with zipfile.ZipFile(
        temporary,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=compression_level,
        strict_timestamps=True,
    ) as archive:
        for name in REQUIRED_DOCUMENTS:
            data = (source_dir / name).read_bytes()
            info = zipfile.ZipInfo(filename=_safe_member_name(name), date_time=FIXED_ZIP_TIME)
            info.create_system = 3
            info.external_attr = NORMALIZED_MODE << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(
                info,
                data,
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=compression_level,
            )
    os.replace(temporary, output_zip)


def inspect_zip(path: Path) -> tuple[str, ...]:
    if not path.is_file():
        raise FinalPackageError(f"ZIP is missing: {path}")
    with zipfile.ZipFile(path, "r") as archive:
        members = tuple(item.filename for item in archive.infolist())
        if members != REQUIRED_DOCUMENTS:
            raise FinalPackageError("ZIP members or order differ from the contract")
        for item in archive.infolist():
            _safe_member_name(item.filename)
            if item.date_time != FIXED_ZIP_TIME:
                raise FinalPackageError(f"non-deterministic timestamp: {item.filename}")
            if (item.external_attr >> 16) != NORMALIZED_MODE:
                raise FinalPackageError(f"non-normalized mode: {item.filename}")
            if item.file_size <= 0:
                raise FinalPackageError(f"empty required document: {item.filename}")
        bad_member = archive.testzip()
        if bad_member is not None:
            raise FinalPackageError(f"ZIP CRC failure: {bad_member}")
    return members


def verify_zip_against_source(path: Path, source_dir: Path) -> PackageVerification:
    entries = verify_sha256s(source_dir)
    members = inspect_zip(path)
    with tempfile.TemporaryDirectory(prefix="darts-final-verify-") as temp_dir:
        extraction_root = Path(temp_dir)
        with zipfile.ZipFile(path, "r") as archive:
            for item in archive.infolist():
                member_name = _safe_member_name(item.filename)
                target = extraction_root / member_name
                target.write_bytes(archive.read(item))
        verify_sha256s(extraction_root)
        for name in REQUIRED_DOCUMENTS:
            if (extraction_root / name).read_bytes() != (source_dir / name).read_bytes():
                raise FinalPackageError(f"ZIP content differs from source: {name}")
    return PackageVerification(
        package_id=path.stem,
        zip_path=str(path),
        zip_size_bytes=path.stat().st_size,
        zip_sha256=sha256_file(path),
        member_count=len(members),
        members=members,
        content_manifest_sha256=content_manifest_sha256(entries),
        passed=True,
    )


def build_final_package(config: FinalPackageConfig) -> BuiltPackage:
    source_dir = config.source_dir.resolve()
    output_zip = config.output_zip.resolve()
    if output_zip.parent == source_dir or source_dir in output_zip.parents:
        raise FinalPackageError("output ZIP must be outside the source document directory")
    entries = build_manifest_entries(source_dir)
    expected_sha256s = render_sha256s(entries)
    checksum_path = source_dir / "SHA256SUMS"
    if checksum_path.read_text(encoding="utf-8") != expected_sha256s:
        raise FinalPackageError("SHA256SUMS is stale; regenerate it before packaging")
    _write_deterministic_zip(
        source_dir,
        output_zip,
        compression_level=config.compression_level,
    )
    verification = verify_zip_against_source(output_zip, source_dir)
    return BuiltPackage(config=config, entries=entries, verification=verification)


def refresh_sha256s(source_dir: Path) -> tuple[ManifestEntry, ...]:
    placeholder = source_dir / "SHA256SUMS"
    placeholder.touch(exist_ok=True)
    entries = build_manifest_entries(source_dir)
    placeholder.write_text(render_sha256s(entries), encoding="utf-8", newline="\n")
    return entries


def _load_config(path: Path) -> FinalPackageConfig:
    import yaml

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return FinalPackageConfig.model_validate(payload)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build deterministic Darts final handoff ZIP")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--refresh-sha256s", action="store_true")
    args = parser.parse_args(argv)
    config = _load_config(args.config)
    if args.refresh_sha256s:
        refresh_sha256s(config.source_dir)
    built = build_final_package(config)
    print(json.dumps(built.verification.model_dump(mode="json"), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
