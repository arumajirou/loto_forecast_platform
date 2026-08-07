from __future__ import annotations

import hashlib
import json
import re
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

FIXED_TIME = (1980, 1, 1, 0, 0, 0)
DIGEST = re.compile(r"^[0-9a-f]{64}$")
RUN_ID = re.compile(r"^mlforecast-final-\d{8}-\d{6}-\d+-[0-9a-f]{12}$")
WINDOWS_RESERVED = {"con", "prn", "aux", "nul"} | {
    f"com{number}" for number in range(1, 10)
} | {f"lpt{number}" for number in range(1, 10)}
FINAL_STATUSES = {
    "FINAL_VERIFICATION_PASSED",
    "FINAL_VERIFICATION_BLOCKED",
    "FINAL_VERIFICATION_FAILED",
    "FINAL_VERIFICATION_PARTIAL",
}
SPECIAL = {"ARTIFACT_MANIFEST.json", "SHA256SUMS", "FINAL_GATE_VERIFICATION.json"}
REQUIRED_HANDOFF = {
    "docs/mlforecast/run_final_verification_portable.sh",
    "docs/mlforecast/FINAL_EVIDENCE.md",
    "src/loto/mlforecast/final_evidence.py",
    "src/loto/mlforecast/final_evidence_support.py",
    "tests/mlforecast/test_final_evidence.py",
    "tests/mlforecast/test_final_evidence_script.py",
}


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_name(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        not value
        or "\\" in value
        or "\x00" in value
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.as_posix() != value
        or any(ord(char) < 32 for char in value)
    ):
        raise RuntimeError(f"unsafe final-evidence path: {value!r}")
    for part in path.parts:
        base = part.split(".", 1)[0].casefold()
        if ":" in part or part.endswith((" ", ".")) or base in WINDOWS_RESERVED:
            raise RuntimeError(f"non-portable final-evidence path: {value!r}")
    return path


def reject_symlink_components(path: Path, label: str) -> Path:
    raw = path.expanduser().absolute()
    current = Path(raw.anchor)
    for part in raw.parts[1:]:
        current /= part
        if current.is_symlink():
            raise RuntimeError(f"{label} contains symlink component: {current}")
    return raw


def regular(path: Path, label: str, *, directory: bool = False) -> Path:
    raw = reject_symlink_components(path, label)
    valid = raw.is_dir() if directory else raw.is_file()
    if not valid:
        raise RuntimeError(f"{label} is not regular: {raw}")
    return raw.resolve()


def load_json(data: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"invalid {label}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} must be an object")
    return value


def parse_manifest(data: bytes) -> tuple[dict[str, str], dict[str, int]]:
    value = load_json(data, "ARTIFACT_MANIFEST.json")
    if value.get("format") != 2 or not isinstance(value.get("artifacts"), list):
        raise RuntimeError("unsupported final-run manifest")
    hashes: dict[str, str] = {}
    sizes: dict[str, int] = {}
    for item in value["artifacts"]:
        if not isinstance(item, dict):
            raise RuntimeError("invalid manifest record")
        name, digest, size = item.get("path"), item.get("sha256"), item.get("size_bytes")
        if not isinstance(name, str) or name in hashes or name in SPECIAL:
            raise RuntimeError("invalid or duplicate manifest path")
        safe_name(name)
        if not isinstance(digest, str) or DIGEST.fullmatch(digest) is None:
            raise RuntimeError(f"invalid manifest digest: {name}")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise RuntimeError(f"invalid manifest size: {name}")
        hashes[name], sizes[name] = digest, size
    return hashes, sizes


def parse_sums(data: bytes) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in data.decode("utf-8").splitlines():
        digest, separator, name = line.partition("  ")
        if separator != "  " or name in values or DIGEST.fullmatch(digest) is None:
            raise RuntimeError("invalid SHA256SUMS")
        safe_name(name)
        values[name] = digest
    return values


def validate_source(files: dict[str, bytes], run_id: str) -> tuple[str, dict[str, Any]]:
    required = SPECIAL | {"FINAL_VERIFICATION.json"}
    missing = required - set(files)
    if missing:
        raise RuntimeError(f"final source reports missing: {sorted(missing)}")
    hashes, sizes = parse_manifest(files["ARTIFACT_MANIFEST.json"])
    if parse_sums(files["SHA256SUMS"]) != hashes:
        raise RuntimeError("SHA256SUMS does not match manifest")
    expected = set(hashes) | SPECIAL
    if set(files) != expected:
        raise RuntimeError("final source file set differs from manifest")
    for name, digest in hashes.items():
        if len(files[name]) != sizes[name] or sha_bytes(files[name]) != digest:
            raise RuntimeError(f"final source artifact mismatch: {name}")
    final = load_json(files["FINAL_VERIFICATION.json"], "FINAL_VERIFICATION.json")
    gate = load_json(files["FINAL_GATE_VERIFICATION.json"], "FINAL_GATE_VERIFICATION.json")
    status = final.get("status")
    if final.get("run_id") != run_id or status not in FINAL_STATUSES:
        raise RuntimeError("invalid final verification report")
    if gate.get("status") != "FINAL_GATE_VERIFIED" or gate.get("run_id") != run_id:
        raise RuntimeError("invalid final gate report")
    if gate.get("source_status") != status or gate.get("handoff_status") != "HANDOFF_VERIFIED":
        raise RuntimeError("final gate status mismatch")
    if gate.get("manifest_sha256") != sha_bytes(files["ARTIFACT_MANIFEST.json"]):
        raise RuntimeError("final gate manifest digest mismatch")
    if gate.get("sums_sha256") != sha_bytes(files["SHA256SUMS"]):
        raise RuntimeError("final gate sums digest mismatch")
    if gate.get("file_count") != len(hashes):
        raise RuntimeError("final gate file_count mismatch")
    return status, gate


def source_directory(root: Path) -> tuple[dict[str, bytes], str, dict[str, Any]]:
    root = regular(root, "final Run directory", directory=True)
    if RUN_ID.fullmatch(root.name) is None:
        raise RuntimeError("invalid final Run ID")
    files: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise RuntimeError(f"final Run contains symlink: {path}")
        if path.is_file():
            name = path.relative_to(root).as_posix()
            safe_name(name)
            files[name] = path.read_bytes()
    status, gate = validate_source(files, root.name)
    return files, status, gate


def zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, FIXED_TIME)
    info.create_system = 3
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    return info


def build(run_dir: Path, output_dir: Path) -> tuple[Path, Path]:
    files, status, gate = source_directory(run_dir)
    root = regular(run_dir, "final Run directory", directory=True)
    output = reject_symlink_components(
        output_dir,
        "final-evidence output directory",
    )
    if output == root or root in output.parents:
        raise RuntimeError("invalid final-evidence output directory")
    output.mkdir(parents=True, exist_ok=True)
    reject_symlink_components(output, "final-evidence output directory")
    archive_path = output / f"{root.name}.final-evidence.zip"
    sidecar = archive_path.with_suffix(".zip.sha256")
    if archive_path.exists() or sidecar.exists():
        raise FileExistsError(f"final evidence already exists: {archive_path}")
    report = {
        "format": 1,
        "status": "FINAL_EVIDENCE_BUNDLED",
        "run_id": root.name,
        "source_status": status,
        "source_gate_status": gate["status"],
        "manifest_sha256": sha_bytes(files["ARTIFACT_MANIFEST.json"]),
        "sums_sha256": sha_bytes(files["SHA256SUMS"]),
        "gate_sha256": sha_bytes(files["FINAL_GATE_VERIFICATION.json"]),
        "source_file_count": len(files),
    }
    entries = {f"{root.name}/{name}": data for name, data in files.items()}
    entries[f"{root.name}/FINAL_EVIDENCE_BUNDLE.json"] = (
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    ).encode()
    temporary = archive_path.with_suffix(".zip.tmp")
    if temporary.exists() or temporary.is_symlink():
        raise FileExistsError(f"temporary final evidence already exists: {temporary}")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(entries.items()):
            archive.writestr(zip_info(name), data)
    temporary.replace(archive_path)
    digest = sha_file(archive_path)
    sidecar.write_text(f"{digest}  {archive_path.name}\n", encoding="utf-8")
    return archive_path, sidecar
