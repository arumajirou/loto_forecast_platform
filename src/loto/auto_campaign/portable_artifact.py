"""Portable, deterministic export for verified AutoModel lineage trees.

The exporter never rewrites source artifacts or their absolute paths. Instead it
copies the complete referenced evidence tree and writes a separate relocation
map from each original path to a package-relative path. Verification resolves
recorded lineage evidence through that map while preserving all original hashes.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import zipfile
from collections import deque
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .persistence import sha256_file, verify_sha256s, write_json
from .verification_seal import verify_verification_seal

PORTABLE_SCHEMA_VERSION = "all-auto-portable-artifact-v1"
PORTABLE_SUMS = "PORTABLE_SHA256SUMS"
PORTABLE_MANIFEST = "PORTABLE_MANIFEST.json"
PORTABLE_README = "PORTABLE_README.md"
_VERIFIED_ROLES = {"target", "source", "predecessor", "coverage"}
_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def _read_json(path: Path, failures: list[str], label: str) -> dict[str, Any]:
    if not path.is_file():
        failures.append(f"{label} missing: {path}")
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        failures.append(f"{label} unreadable: {type(exc).__name__}: {exc}")
        return {}
    if not isinstance(payload, dict) or not payload:
        failures.append(f"{label} must be a non-empty JSON object: {path}")
        return {}
    return payload


def _path_key(value: str | Path) -> str:
    text = str(value).replace("\\", "/")
    while len(text) > 1 and text.endswith("/"):
        text = text[:-1]
    return text


def _safe_relative(value: str, failures: list[str], label: str) -> Path | None:
    if "\\" in value:
        failures.append(f"{label} contains a backslash: {value}")
        return None
    pure = PurePosixPath(value)
    unsafe_component = any(
        not part
        or ":" in part
        or any(ord(character) < 32 for character in part)
        or part.rstrip(" .") != part
        or part.split(".", 1)[0].upper() in _WINDOWS_RESERVED
        for part in pure.parts
    )
    if (
        pure.is_absolute()
        or not pure.parts
        or ".." in pure.parts
        or "." in pure.parts
        or unsafe_component
    ):
        failures.append(f"{label} is unsafe: {value}")
        return None
    return Path(*pure.parts)


def _reject_symlinks(root: Path) -> None:
    if root.is_symlink():
        raise ValueError(f"portable export does not allow symlink roots: {root}")
    if root.is_dir():
        for path in root.rglob("*"):
            if path.is_symlink():
                raise ValueError(f"portable export does not allow symlinks: {path}")


def _tree_fingerprint(root: Path) -> tuple[str, int, int]:
    _reject_symlinks(root)
    digest = hashlib.sha256()
    count = 0
    total = 0
    for path in sorted(
        (item for item in root.rglob("*") if item.is_file()),
        key=lambda item: item.relative_to(root).as_posix(),
    ):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        size = 0
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
                size += len(block)
        digest.update(b"\0")
        count += 1
        total += size
    return digest.hexdigest(), count, total


def _file_fingerprint(path: Path) -> tuple[str, int, int]:
    _reject_symlinks(path)
    return sha256_file(path), 1, path.stat().st_size


def _verified_directory_failures(root: Path, label: str) -> list[str]:
    failures: list[str] = []
    if not root.is_dir():
        return [f"{label} is not a directory: {root}"]
    try:
        _reject_symlinks(root)
    except ValueError as exc:
        failures.append(str(exc))
    report = _read_json(
        root / "VERIFICATION_REPORT.json",
        failures,
        f"{label} report",
    )
    if report and report.get("status") != "PASS":
        failures.append(f"{label} report status is not PASS: {report.get('status')}")
    seal = verify_verification_seal(root)
    failures.extend(f"{label} seal: {item}" for item in seal.get("failures", []))
    failures.extend(f"{label} SHA256: {item}" for item in verify_sha256s(root))
    return failures


def _dependency_refs(root: Path) -> list[tuple[str, Path]]:
    lineage_path = root / "LINEAGE.json"
    if not lineage_path.is_file():
        return []
    failures: list[str] = []
    lineage = _read_json(lineage_path, failures, "lineage")
    if failures:
        raise ValueError("; ".join(failures))
    refs: list[tuple[str, Path]] = []
    for key, role in (
        ("source_evidence", "source"),
        ("predecessor_evidence", "predecessor"),
        ("coverage_evidence", "coverage"),
    ):
        evidence = lineage.get(key)
        if isinstance(evidence, Mapping):
            value = str(evidence.get("path") or "").strip()
            if value:
                refs.append((role, Path(value)))
    runtime = lineage.get("runtime_evidence")
    if isinstance(runtime, Mapping):
        report = runtime.get("campaign_report")
        if isinstance(report, Mapping):
            value = str(report.get("path") or "").strip()
            if value:
                refs.append(("runtime-report", Path(value)))
    return refs


def _collect_entries(run_root: Path) -> list[dict[str, Any]]:
    queue: deque[tuple[str, Path]] = deque([("target", run_root)])
    collected: dict[str, dict[str, Any]] = {}
    while queue:
        role, raw = queue.popleft()
        _reject_symlinks(raw)
        path = raw.resolve()
        key = _path_key(path)
        record = collected.setdefault(key, {"path": path, "roles": set()})
        record["roles"].add(role)
        if record.get("expanded"):
            continue
        record["expanded"] = True
        if not path.exists():
            raise FileNotFoundError(path)
        _reject_symlinks(path)
        if path.is_dir():
            for child_role, child in _dependency_refs(path):
                queue.append((child_role, child))
    entries = list(collected.values())
    for entry in entries:
        path = entry["path"]
        roles = entry["roles"]
        if path.is_dir() and roles & _VERIFIED_ROLES:
            label = "/".join(sorted(roles))
            failures = _verified_directory_failures(path, label)
            if failures:
                raise ValueError("; ".join(failures))
    return entries


def _safe_name(path: Path) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", path.name).strip("-.")
    return value or "artifact"


def _entry_relative(path: Path, roles: set[str]) -> str:
    if "target" in roles:
        return "payload/target"
    digest = hashlib.sha256(_path_key(path).encode("utf-8")).hexdigest()[:16]
    group = "dependencies" if path.is_dir() else "files"
    return f"payload/{group}/{digest}-{_safe_name(path)}"


def _write_portable_sums(root: Path) -> None:
    paths = sorted(
        (
            path
            for path in root.rglob("*")
            if path.is_file() and path.relative_to(root).as_posix() != PORTABLE_SUMS
        ),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    lines = [f"{sha256_file(path)}  {path.relative_to(root).as_posix()}" for path in paths]
    target = root / PORTABLE_SUMS
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _verify_portable_sums(root: Path) -> list[str]:
    failures: list[str] = []
    path = root / PORTABLE_SUMS
    if not path.is_file():
        return [f"{PORTABLE_SUMS} missing"]
    listed: set[str] = set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return [f"{PORTABLE_SUMS} unreadable: {type(exc).__name__}: {exc}"]
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            expected, relative = line.split("  ", 1)
        except ValueError:
            failures.append(f"portable-sums malformed-line:{line_number}")
            continue
        safe = _safe_relative(
            relative,
            failures,
            f"portable-sums line {line_number}",
        )
        if safe is None:
            continue
        normalized = safe.as_posix()
        if normalized in listed:
            failures.append(f"portable-sums duplicate:{normalized}")
            continue
        listed.add(normalized)
        target = root / safe
        if not target.is_file():
            failures.append(f"portable-sums missing:{normalized}")
        elif sha256_file(target) != expected:
            failures.append(f"portable-sums mismatch:{normalized}")
    actual = {
        item.relative_to(root).as_posix()
        for item in root.rglob("*")
        if item.is_file() and item.relative_to(root).as_posix() != PORTABLE_SUMS
    }
    failures.extend(f"portable-sums unlisted:{item}" for item in sorted(actual - listed))
    failures.extend(f"portable-sums listed-but-missing:{item}" for item in sorted(listed - actual))
    return failures


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=repr,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _manifest_content_sha256(manifest: Mapping[str, Any]) -> str:
    payload = {key: value for key, value in manifest.items() if key != "manifest_content_sha256"}
    return _canonical_sha256(payload)


def _resolve_recorded_path(
    recorded: str,
    entries: list[Mapping[str, Any]],
    package_root: Path,
) -> Path | None:
    key = _path_key(recorded)
    matches: list[tuple[int, Mapping[str, Any], str]] = []
    for entry in entries:
        original = _path_key(str(entry.get("original_path") or ""))
        if not original:
            continue
        if key == original:
            matches.append((len(original), entry, ""))
        elif str(entry.get("kind")) == "directory" and key.startswith(original + "/"):
            matches.append((len(original), entry, key[len(original) + 1 :]))
    if not matches:
        return None
    _, entry, tail = max(matches, key=lambda item: item[0])
    failures: list[str] = []
    relative = _safe_relative(
        str(entry.get("relative_path") or ""),
        failures,
        "relocation entry",
    )
    if relative is None:
        return None
    base = package_root / relative
    if not tail:
        candidate = base
    else:
        tail_relative = _safe_relative(tail, failures, "relocation tail")
        if tail_relative is None:
            return None
        candidate = base / tail_relative
    base_resolved = base.resolve()
    candidate_resolved = candidate.resolve()
    if candidate_resolved != base_resolved and base_resolved not in candidate_resolved.parents:
        return None
    return candidate


def _verify_recorded_file(
    evidence: Any,
    entries: list[Mapping[str, Any]],
    package_root: Path,
    failures: list[str],
    label: str,
) -> Path | None:
    if not isinstance(evidence, Mapping):
        failures.append(f"{label} evidence must be an object")
        return None
    recorded = str(evidence.get("path") or "").strip()
    expected = str(evidence.get("sha256") or "").strip()
    if not recorded or not expected:
        failures.append(f"{label} evidence is incomplete")
        return None
    resolved = _resolve_recorded_path(recorded, entries, package_root)
    if resolved is None:
        failures.append(f"{label} has no relocation mapping: {recorded}")
        return None
    if not resolved.is_file():
        failures.append(f"{label} relocated file missing: {resolved}")
        return None
    actual = sha256_file(resolved)
    if actual != expected:
        failures.append(f"{label} SHA256 mismatch: expected={expected}, actual={actual}")
    return resolved


def _verify_relocated_run(
    evidence: Any,
    entries: list[Mapping[str, Any]],
    package_root: Path,
    failures: list[str],
    label: str,
) -> None:
    if not isinstance(evidence, Mapping):
        failures.append(f"{label} evidence must be an object")
        return
    original = str(evidence.get("path") or "").strip()
    relocated = _resolve_recorded_path(original, entries, package_root)
    if relocated is None or not relocated.is_dir():
        failures.append(f"{label} relocated directory missing: {original}")
        return
    _verify_recorded_file(
        evidence.get("manifest"),
        entries,
        package_root,
        failures,
        f"{label} manifest",
    )
    _verify_recorded_file(
        evidence.get("sha256s"),
        entries,
        package_root,
        failures,
        f"{label} SHA256SUMS",
    )
    lineage = evidence.get("lineage")
    if lineage is not None:
        _verify_recorded_file(
            lineage,
            entries,
            package_root,
            failures,
            f"{label} LINEAGE",
        )
    failures.extend(f"{label} current SHA256: {item}" for item in verify_sha256s(relocated))
    seal = verify_verification_seal(relocated)
    failures.extend(f"{label} seal: {item}" for item in seal.get("failures", []))
    current_failures: list[str] = []
    current = _read_json(
        relocated / "manifest.json",
        current_failures,
        f"{label} relocated manifest",
    )
    failures.extend(current_failures)
    for field in (
        "stage",
        "status",
        "code_sha256",
        "data_sha256",
        "lineage_status",
    ):
        if evidence.get(field) != current.get(field):
            failures.append(
                f"{label} {field} changed: "
                f"recorded={evidence.get(field)}, current={current.get(field)}"
            )
    if evidence.get("verification_status") != "PASS":
        failures.append(f"{label} recorded verification_status is not PASS")


def _verify_relocated_lineage(
    run_root: Path,
    entries: list[Mapping[str, Any]],
    package_root: Path,
) -> list[str]:
    failures: list[str] = []
    manifest = _read_json(
        run_root / "manifest.json",
        failures,
        "relocated run manifest",
    )
    lineage = _read_json(
        run_root / "LINEAGE.json",
        failures,
        "relocated lineage",
    )
    if not lineage:
        return failures
    lineage_path = run_root / "LINEAGE.json"
    if manifest.get("lineage_sha256") != sha256_file(lineage_path):
        failures.append("relocated LINEAGE.json hash differs from manifest")
    core = {
        key: value for key, value in lineage.items() if key not in {"created_at", "chain_sha256"}
    }
    chain = _canonical_sha256(core)
    if lineage.get("chain_sha256") != chain:
        failures.append("relocated lineage chain_sha256 is invalid")
    if manifest.get("lineage_chain_sha256") != chain:
        failures.append("relocated manifest lineage_chain_sha256 mismatch")
    run_evidence = lineage.get("run")
    if not isinstance(run_evidence, Mapping):
        failures.append("relocated lineage run evidence must be an object")
        run_evidence = {}
    for key, label in (
        ("campaign_config", "campaign config"),
        ("data_contract", "data contract"),
        ("promotion_gate", "promotion gate"),
    ):
        _verify_recorded_file(
            run_evidence.get(key),
            entries,
            package_root,
            failures,
            label,
        )
    for key, label in (
        ("source_evidence", "source run"),
        ("predecessor_evidence", "predecessor run"),
        ("coverage_evidence", "coverage run"),
    ):
        evidence = lineage.get(key)
        if evidence is not None:
            _verify_relocated_run(
                evidence,
                entries,
                package_root,
                failures,
                label,
            )
    runtime = lineage.get("runtime_evidence")
    if runtime is not None:
        if not isinstance(runtime, Mapping):
            failures.append("runtime evidence must be an object")
        else:
            _verify_recorded_file(
                runtime.get("campaign_report"),
                entries,
                package_root,
                failures,
                "runtime campaign report",
            )
    return failures


def _verify_manifest_identity(
    manifest: Mapping[str, Any],
    entries: list[Mapping[str, Any]],
    target_entry: Mapping[str, Any] | None,
    target_root: Path | None,
    failures: list[str],
) -> None:
    expected = _manifest_content_sha256(manifest)
    if manifest.get("manifest_content_sha256") != expected:
        failures.append("portable manifest_content_sha256 mismatch")
    if target_entry is None or target_root is None:
        return
    if manifest.get("target_original_path") != target_entry.get("original_path"):
        failures.append("portable target_original_path mismatch")
    if manifest.get("target_relative_path") != target_entry.get("relative_path"):
        failures.append("portable target_relative_path mismatch")
    seal_path = target_root / "VERIFICATION_SEAL.json"
    if not seal_path.is_file():
        failures.append("portable target verification seal missing")
    elif manifest.get("target_verification_seal_sha256") != sha256_file(seal_path):
        failures.append("portable target verification seal SHA256 mismatch")
    expected_relocation = {
        _path_key(str(entry.get("original_path") or "")): str(entry.get("relative_path") or "")
        for entry in entries
    }
    if manifest.get("relocation_map") != expected_relocation:
        failures.append("portable relocation_map differs from entries")


def _verify_portable_directory(root: Path) -> dict[str, Any]:
    failures: list[str] = []
    try:
        _reject_symlinks(root)
    except ValueError as exc:
        failures.append(str(exc))
    failures.extend(_verify_portable_sums(root))
    manifest = _read_json(
        root / PORTABLE_MANIFEST,
        failures,
        "portable manifest",
    )
    if manifest.get("schema_version") != PORTABLE_SCHEMA_VERSION:
        failures.append("portable manifest schema_version mismatch")
    raw_entries = manifest.get("entries")
    if not isinstance(raw_entries, list) or not raw_entries:
        failures.append("portable manifest entries must be a non-empty list")
        raw_entries = []
    entries = [entry for entry in raw_entries if isinstance(entry, Mapping)]
    if len(entries) != len(raw_entries):
        failures.append("portable manifest contains a non-object entry")
    original_seen: set[str] = set()
    relative_seen: set[str] = set()
    target_root: Path | None = None
    target_entry: Mapping[str, Any] | None = None
    relocated_lineage_roots: list[Path] = []
    for index, entry in enumerate(entries):
        original = _path_key(str(entry.get("original_path") or ""))
        relative_text = str(entry.get("relative_path") or "")
        safe = _safe_relative(
            relative_text,
            failures,
            f"entry {index} relative_path",
        )
        if not original:
            failures.append(f"entry {index} original_path missing")
        if original in original_seen:
            failures.append(f"entry {index} duplicate original_path: {original}")
        original_seen.add(original)
        roles = entry.get("roles")
        if (
            not isinstance(roles, list)
            or not roles
            or any(not isinstance(role, str) or not role for role in roles)
        ):
            failures.append(f"entry {index} roles must be non-empty strings")
            roles = []
        if safe is None:
            continue
        relative = safe.as_posix()
        if not relative.startswith("payload/"):
            failures.append(f"entry {index} is outside payload/: {relative}")
        folded = relative.casefold()
        if folded in relative_seen:
            failures.append(f"entry {index} duplicate relative_path: {relative}")
        relative_seen.add(folded)
        path = root / safe
        kind = str(entry.get("kind") or "")
        if kind == "directory" and path.is_dir():
            digest, count, size = _tree_fingerprint(path)
        elif kind == "file" and path.is_file():
            digest, count, size = _file_fingerprint(path)
        else:
            failures.append(f"entry {index} missing or wrong kind at {relative}")
            continue
        if entry.get("content_sha256") != digest:
            failures.append(f"entry {index} content_sha256 mismatch")
        if entry.get("file_count") != count:
            failures.append(f"entry {index} file_count mismatch")
        if entry.get("size_bytes") != size:
            failures.append(f"entry {index} size_bytes mismatch")
        if "target" in roles:
            if target_root is not None:
                failures.append("multiple target entries")
            target_root = path
            target_entry = entry
        if kind == "directory" and set(roles) & _VERIFIED_ROLES:
            seal = verify_verification_seal(path)
            failures.extend(f"entry {index} seal: {item}" for item in seal.get("failures", []))
            failures.extend(f"entry {index} SHA256: {item}" for item in verify_sha256s(path))
            if (path / "LINEAGE.json").is_file():
                relocated_lineage_roots.append(path)
    if target_root is None or not target_root.is_dir():
        failures.append("portable target directory missing")
    _verify_manifest_identity(
        manifest,
        entries,
        target_entry,
        target_root,
        failures,
    )
    for lineage_root in relocated_lineage_roots:
        failures.extend(_verify_relocated_lineage(lineage_root, entries, root))
    return {
        "status": "PASS" if not failures else "FAIL",
        "schema_version": PORTABLE_SCHEMA_VERSION,
        "entry_count": len(entries),
        "target_relative_path": manifest.get("target_relative_path"),
        "failures": failures,
    }


def _write_deterministic_zip(root: Path, target: Path) -> None:
    with zipfile.ZipFile(
        target,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
        allowZip64=True,
    ) as archive:
        paths = sorted(
            (item for item in root.rglob("*") if item.is_file()),
            key=lambda item: item.relative_to(root).as_posix(),
        )
        folded_seen: set[str] = set()
        for path in paths:
            relative = path.relative_to(root).as_posix()
            failures: list[str] = []
            if _safe_relative(relative, failures, "archive member") is None:
                raise ValueError("; ".join(failures))
            folded = relative.casefold()
            if folded in folded_seen:
                raise ValueError(f"case-insensitive archive collision: {relative}")
            folded_seen.add(folded)
            info = zipfile.ZipInfo(
                relative,
                date_time=(1980, 1, 1, 0, 0, 0),
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.flag_bits |= 0x800
            with path.open("rb") as source:
                with archive.open(info, "w", force_zip64=True) as destination:
                    shutil.copyfileobj(source, destination, length=1024 * 1024)


def _safe_extract_zip(bundle: Path, target: Path) -> None:
    seen: set[str] = set()
    folded_seen: set[str] = set()
    with zipfile.ZipFile(bundle, "r") as archive:
        for info in archive.infolist():
            name = info.filename
            failures: list[str] = []
            safe = _safe_relative(
                name.rstrip("/"),
                failures,
                "ZIP member",
            )
            if failures or safe is None:
                raise ValueError("; ".join(failures))
            normalized = safe.as_posix()
            if normalized in seen or normalized.casefold() in folded_seen:
                raise ValueError(f"duplicate ZIP member: {normalized}")
            seen.add(normalized)
            folded_seen.add(normalized.casefold())
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ValueError(f"ZIP symlink is not allowed: {normalized}")
            destination = target / safe
            target_resolved = target.resolve()
            destination_resolved = destination.resolve()
            if (
                destination_resolved != target_resolved
                and target_resolved not in destination_resolved.parents
            ):
                raise ValueError(f"ZIP member escapes extraction root: {normalized}")
            if info.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info, "r") as source:
                with destination.open("wb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)


def export_portable_bundle(run_root: Path, output: Path) -> dict[str, Any]:
    """Copy a verified lineage tree and create an atomic deterministic ZIP."""

    _reject_symlinks(run_root)
    run_root = run_root.resolve()
    output = output.resolve()
    if output.suffix.lower() != ".zip":
        raise ValueError("portable output must use the .zip extension")
    if output.exists():
        raise FileExistsError(output)
    entries = _collect_entries(run_root)
    for entry in entries:
        source = entry["path"]
        if source.is_dir() and (output == source or source in output.parents):
            raise ValueError(f"portable output must not be inside a source run: {source}")
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(
        prefix="portable-artifact-",
        dir=output.parent,
    ) as temp_value:
        package_root = Path(temp_value) / "package"
        package_root.mkdir()
        manifest_entries: list[dict[str, Any]] = []
        ordered = sorted(
            entries,
            key=lambda item: (
                "target" not in item["roles"],
                _path_key(item["path"]),
            ),
        )
        for entry in ordered:
            source: Path = entry["path"]
            roles: set[str] = entry["roles"]
            relative = _entry_relative(source, roles)
            destination = package_root / Path(*PurePosixPath(relative).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(
                    source,
                    destination,
                    copy_function=shutil.copy2,
                    symlinks=False,
                )
                digest, count, size = _tree_fingerprint(destination)
                kind = "directory"
            else:
                shutil.copy2(source, destination)
                digest, count, size = _file_fingerprint(destination)
                kind = "file"
            manifest_entries.append(
                {
                    "kind": kind,
                    "original_path": _path_key(source),
                    "relative_path": relative,
                    "roles": sorted(roles),
                    "content_sha256": digest,
                    "file_count": count,
                    "size_bytes": size,
                }
            )

        seal_failures: list[str] = []
        seal = _read_json(
            run_root / "VERIFICATION_SEAL.json",
            seal_failures,
            "target seal",
        )
        if seal_failures:
            raise ValueError("; ".join(seal_failures))
        manifest: dict[str, Any] = {
            "schema_version": PORTABLE_SCHEMA_VERSION,
            "exported_from_sealed_at": seal.get("sealed_at"),
            "target_original_path": _path_key(run_root),
            "target_relative_path": "payload/target",
            "target_verification_seal_sha256": sha256_file(run_root / "VERIFICATION_SEAL.json"),
            "entries": manifest_entries,
            "relocation_map": {
                entry["original_path"]: entry["relative_path"] for entry in manifest_entries
            },
        }
        manifest["manifest_content_sha256"] = _manifest_content_sha256(manifest)
        write_json(package_root / PORTABLE_MANIFEST, manifest)
        readme = (
            "# Portable AutoModel artifact\n\n"
            "This bundle preserves original lineage files unchanged. "
            "PORTABLE_MANIFEST.json maps recorded absolute paths to "
            "package-relative paths.\n"
            "Verify with `loto-auto-campaign verify-portable "
            "--bundle <bundle.zip>`.\n"
        )
        (package_root / PORTABLE_README).write_text(readme, encoding="utf-8")
        _write_portable_sums(package_root)
        verification = _verify_portable_directory(package_root)
        if verification["status"] != "PASS":
            raise ValueError(f"portable staging verification failed: {verification['failures']}")
        partial = output.with_name(output.name + ".partial")
        if partial.exists():
            partial.unlink()
        try:
            _write_deterministic_zip(package_root, partial)
            os.replace(partial, output)
        finally:
            if partial.exists():
                partial.unlink()
    return {
        "status": "PASS",
        "schema_version": PORTABLE_SCHEMA_VERSION,
        "bundle": str(output),
        "bundle_sha256": sha256_file(output),
        "entry_count": len(entries),
        "source_run": str(run_root),
    }


def verify_portable_bundle(bundle: Path) -> dict[str, Any]:
    """Verify a ZIP or an already extracted portable bundle read-only."""

    bundle = bundle.resolve()
    if bundle.is_dir():
        result = _verify_portable_directory(bundle)
        return {
            **result,
            "bundle": str(bundle),
            "bundle_sha256": None,
        }
    if not bundle.is_file():
        return {
            "status": "FAIL",
            "schema_version": PORTABLE_SCHEMA_VERSION,
            "bundle": str(bundle),
            "bundle_sha256": None,
            "failures": ["portable bundle does not exist"],
        }
    try:
        with tempfile.TemporaryDirectory(prefix="verify-portable-") as temp_value:
            root = Path(temp_value)
            _safe_extract_zip(bundle, root)
            result = _verify_portable_directory(root)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        result = {
            "status": "FAIL",
            "schema_version": PORTABLE_SCHEMA_VERSION,
            "entry_count": 0,
            "target_relative_path": None,
            "failures": [f"portable bundle unreadable: {type(exc).__name__}: {exc}"],
        }
    return {
        **result,
        "bundle": str(bundle),
        "bundle_sha256": sha256_file(bundle),
    }
