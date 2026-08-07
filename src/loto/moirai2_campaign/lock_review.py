from __future__ import annotations

import hashlib
import json
import re
import tomllib
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


REVIEW_SCHEMA = "moirai2-lock-review-v1"
APPROVAL_SCHEMA = "moirai2-lock-approval-v1"
REPORT_FILENAME = "LOCK_REVIEW_REPORT.json"
APPROVAL_FILENAME = "LOCK_REVIEW_APPROVAL.json"
LOCK_FILENAME = "uv.lock"

_FORBIDDEN_SOURCE_KEYS = {
    "directory",
    "editable",
    "git",
    "path",
    "url",
    "virtual",
    "workspace",
}
_ALLOWED_ROOT_VIRTUAL = "."


class LockReviewError(RuntimeError):
    pass


@dataclass(frozen=True)
class PackageInventory:
    name: str
    version: str
    source_kind: str
    source_value: str | None
    dependency_names: tuple[str, ...]
    artifact_hashes: tuple[str, ...]
    is_root_project: bool

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["dependency_names"] = list(self.dependency_names)
        payload["artifact_hashes"] = list(self.artifact_hashes)
        return payload


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_payload(payload: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _parse_exact_requirement(raw: str) -> tuple[str, str]:
    if ";" in raw:
        raise LockReviewError(f"environment markers are not allowed: {raw!r}")
    if "@" in raw:
        raise LockReviewError(f"direct URL dependencies are not allowed: {raw!r}")
    if "==" not in raw:
        raise LockReviewError(f"dependency is not exactly pinned: {raw!r}")
    name_part, version = raw.split("==", 1)
    name = name_part.split("[", 1)[0].strip()
    version = version.strip()
    if not name or not version or any(token in version for token in ("*", ",", " ")):
        raise LockReviewError(f"dependency is not a single exact pin: {raw!r}")
    return normalize_name(name), version


def parse_project(pyproject_path: Path) -> dict[str, Any]:
    payload = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project = payload.get("project")
    if not isinstance(project, dict):
        raise LockReviewError("pyproject project table is missing")
    raw_name = project.get("name")
    raw_dependencies = project.get("dependencies")
    if not isinstance(raw_name, str) or not raw_name.strip():
        raise LockReviewError("project name is missing")
    if not isinstance(raw_dependencies, list):
        raise LockReviewError("project dependencies are missing")
    dependencies: dict[str, str] = {}
    for raw in raw_dependencies:
        if not isinstance(raw, str):
            raise LockReviewError(f"dependency is not text: {raw!r}")
        name, version = _parse_exact_requirement(raw)
        if name in dependencies:
            raise LockReviewError(f"duplicate direct dependency: {name}")
        dependencies[name] = version
    return {
        "name": normalize_name(raw_name),
        "requires_python": project.get("requires-python"),
        "dependencies": dependencies,
    }


def _source_details(
    package: dict[str, Any],
    *,
    is_root_project: bool,
) -> tuple[str, str | None, list[str]]:
    source = package.get("source")
    if source is None:
        return "unspecified", None, []
    if not isinstance(source, dict):
        return "invalid", repr(source), ["package source is not a table"]
    keys = sorted(str(key) for key in source)
    violations: list[str] = []
    forbidden = sorted(set(keys) & _FORBIDDEN_SOURCE_KEYS)
    if forbidden:
        if (
            is_root_project
            and forbidden == ["virtual"]
            and source.get("virtual") == _ALLOWED_ROOT_VIRTUAL
        ):
            return "root-virtual", _ALLOWED_ROOT_VIRTUAL, []
        violations.append(f"forbidden source keys: {forbidden}")
    if "registry" in source and len(keys) == 1:
        value = source.get("registry")
        if isinstance(value, str) and value:
            return "registry", value, violations
        violations.append("registry source value is invalid")
        return "registry", repr(value), violations
    if is_root_project and source.get("virtual") == _ALLOWED_ROOT_VIRTUAL:
        return "root-virtual", _ALLOWED_ROOT_VIRTUAL, violations
    if not forbidden:
        violations.append(f"unsupported source keys: {keys}")
    return "+".join(keys) or "empty", repr(source), violations


def _dependency_names(package: dict[str, Any]) -> tuple[str, ...]:
    raw_dependencies = package.get("dependencies", [])
    if not isinstance(raw_dependencies, list):
        raise LockReviewError("package dependencies must be a list")
    names: list[str] = []
    for dependency in raw_dependencies:
        if isinstance(dependency, str):
            names.append(normalize_name(dependency))
        elif isinstance(dependency, dict) and isinstance(dependency.get("name"), str):
            names.append(normalize_name(dependency["name"]))
        else:
            raise LockReviewError(f"invalid locked dependency entry: {dependency!r}")
    return tuple(sorted(names))



def _valid_artifact_hash(value: str) -> bool:
    if not value.startswith("sha256:"):
        return False
    digest = value.removeprefix("sha256:")
    return bool(re.fullmatch(r"[0-9a-f]{64}", digest))


def _artifact_hashes(package: dict[str, Any]) -> tuple[str, ...]:
    hashes: list[str] = []
    sdist = package.get("sdist")
    if isinstance(sdist, dict) and isinstance(sdist.get("hash"), str):
        hashes.append(sdist["hash"])
    wheels = package.get("wheels", [])
    if isinstance(wheels, list):
        for wheel in wheels:
            if isinstance(wheel, dict) and isinstance(wheel.get("hash"), str):
                hashes.append(wheel["hash"])
    return tuple(sorted(set(hashes)))


def inspect_lock(
    *,
    pyproject_path: Path,
    lock_path: Path,
    runtime_lane: str,
) -> dict[str, Any]:
    project = parse_project(pyproject_path)
    lock = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    raw_packages = lock.get("package")
    if not isinstance(raw_packages, list) or not raw_packages:
        raise LockReviewError("uv.lock package entries are missing")

    inventory: list[PackageInventory] = []
    violations: list[str] = []
    warnings: list[str] = []
    locked_versions: dict[str, set[str]] = {}

    for index, raw_package in enumerate(raw_packages):
        if not isinstance(raw_package, dict):
            violations.append(f"package[{index}] is not a table")
            continue
        raw_name = raw_package.get("name")
        raw_version = raw_package.get("version")
        if not isinstance(raw_name, str) or not isinstance(raw_version, str):
            violations.append(f"package[{index}] lacks name or version")
            continue
        name = normalize_name(raw_name)
        is_root = name == project["name"]
        source_kind, source_value, source_violations = _source_details(
            raw_package,
            is_root_project=is_root,
        )
        for message in source_violations:
            violations.append(f"{name}=={raw_version}: {message}")
        try:
            dependency_names = _dependency_names(raw_package)
        except LockReviewError as exc:
            violations.append(f"{name}=={raw_version}: {exc}")
            dependency_names = ()
        artifact_hashes = _artifact_hashes(raw_package)
        if not is_root and source_kind == "registry" and not artifact_hashes:
            violations.append(f"{name}=={raw_version}: registry package lacks artifact hashes")
        invalid_hashes = [value for value in artifact_hashes if not _valid_artifact_hash(value)]
        if invalid_hashes:
            violations.append(
                f"{name}=={raw_version}: invalid artifact hashes={invalid_hashes}"
            )
        inventory.append(
            PackageInventory(
                name=name,
                version=raw_version,
                source_kind=source_kind,
                source_value=source_value,
                dependency_names=dependency_names,
                artifact_hashes=artifact_hashes,
                is_root_project=is_root,
            )
        )
        locked_versions.setdefault(name, set()).add(raw_version)

    for name, expected in sorted(project["dependencies"].items()):
        actual = sorted(locked_versions.get(name, set()))
        if expected not in actual:
            violations.append(
                f"direct dependency mismatch: {name} expected={expected} locked={actual}"
            )

    package_names = set(locked_versions)
    for package in inventory:
        missing = sorted(set(package.dependency_names) - package_names)
        if missing:
            violations.append(
                f"{package.name}=={package.version}: unresolved dependency names={missing}"
            )

    duplicates = {
        name: sorted(versions)
        for name, versions in sorted(locked_versions.items())
        if len(versions) > 1
    }
    if duplicates:
        warnings.append(f"multiple locked versions detected: {duplicates}")

    inventory_payload = [package.as_dict() for package in sorted(
        inventory,
        key=lambda item: (item.name, item.version, item.source_kind),
    )]
    edge_count = sum(len(package.dependency_names) for package in inventory)
    source_counts: dict[str, int] = {}
    for package in inventory:
        source_counts[package.source_kind] = source_counts.get(package.source_kind, 0) + 1

    report = {
        "schema_version": REVIEW_SCHEMA,
        "status": "PASS" if not violations else "FAILED",
        "runtime_lane": runtime_lane,
        "root_project": project["name"],
        "requires_python": project["requires_python"],
        "pyproject_path": str(pyproject_path.resolve()),
        "pyproject_sha256": sha256_file(pyproject_path),
        "lock_path": str(lock_path.resolve()),
        "lock_sha256": sha256_file(lock_path),
        "lock_format_version": lock.get("version"),
        "lock_revision": lock.get("revision"),
        "package_count": len(inventory_payload),
        "dependency_edge_count": edge_count,
        "direct_dependencies": dict(sorted(project["dependencies"].items())),
        "locked_versions": {
            name: sorted(versions) for name, versions in sorted(locked_versions.items())
        },
        "source_counts": dict(sorted(source_counts.items())),
        "packages": inventory_payload,
        "violations": sorted(set(violations)),
        "warnings": sorted(set(warnings)),
    }
    report["inventory_sha256"] = sha256_payload(inventory_payload)
    return report


def _parse_reviewed_at(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise LockReviewError("reviewed_at must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LockReviewError("reviewed_at must include a timezone")
    return parsed


def build_approval(
    *,
    report: dict[str, Any],
    reviewer: str,
    reviewed_at: str,
) -> dict[str, Any]:
    if report.get("schema_version") != REVIEW_SCHEMA:
        raise LockReviewError("unsupported lock review schema")
    if report.get("status") != "PASS" or report.get("violations"):
        raise LockReviewError("failed lock review cannot be approved")
    if not reviewer.strip() or "\n" in reviewer or "\r" in reviewer:
        raise LockReviewError("reviewer must be a non-empty single line")
    _parse_reviewed_at(reviewed_at)
    return {
        "schema_version": APPROVAL_SCHEMA,
        "decision": "APPROVED",
        "runtime_lane": report["runtime_lane"],
        "reviewer": reviewer.strip(),
        "reviewed_at": reviewed_at,
        "pyproject_sha256": report["pyproject_sha256"],
        "lock_sha256": report["lock_sha256"],
        "report_sha256": sha256_payload(report),
        "inventory_sha256": report["inventory_sha256"],
        "violation_count": 0,
    }


def load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise LockReviewError(f"JSON object is required: {path}")
    return payload


def validate_installed_review(
    *,
    environment_path: Path,
    runtime_lane: str,
) -> dict[str, Any]:
    pyproject_path = environment_path / "pyproject.toml"
    lock_path = environment_path / LOCK_FILENAME
    report_path = environment_path / REPORT_FILENAME
    approval_path = environment_path / APPROVAL_FILENAME
    required = (pyproject_path, lock_path, report_path, approval_path)
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise LockReviewError(f"reviewed lock artifacts are missing: {missing}")

    report = load_json_object(report_path)
    approval = load_json_object(approval_path)
    if report.get("schema_version") != REVIEW_SCHEMA:
        raise LockReviewError("installed report schema is invalid")
    if approval.get("schema_version") != APPROVAL_SCHEMA:
        raise LockReviewError("installed approval schema is invalid")
    if report.get("status") != "PASS" or report.get("violations"):
        raise LockReviewError("installed lock review did not pass")
    if approval.get("decision") != "APPROVED":
        raise LockReviewError("installed lock approval is not APPROVED")
    if report.get("runtime_lane") != runtime_lane:
        raise LockReviewError("report runtime lane does not match requested lane")
    if approval.get("runtime_lane") != runtime_lane:
        raise LockReviewError("approval runtime lane does not match requested lane")
    reviewer = approval.get("reviewer")
    reviewed_at = approval.get("reviewed_at")
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise LockReviewError("approval reviewer is missing")
    if not isinstance(reviewed_at, str):
        raise LockReviewError("approval reviewed_at is missing")
    _parse_reviewed_at(reviewed_at)

    actual_project_sha = sha256_file(pyproject_path)
    actual_lock_sha = sha256_file(lock_path)
    actual_report_sha = sha256_payload(report)
    checks = {
        "pyproject_sha256": actual_project_sha,
        "lock_sha256": actual_lock_sha,
        "report_sha256": actual_report_sha,
        "inventory_sha256": sha256_payload(report.get("packages")),
    }
    for key, actual in checks.items():
        if report.get(key) != actual and key != "report_sha256":
            raise LockReviewError(f"report {key} does not match installed artifact")
        if approval.get(key) != actual:
            raise LockReviewError(f"approval {key} does not match installed artifact")
    if int(approval.get("violation_count", -1)) != 0:
        raise LockReviewError("approval violation_count must be zero")

    return {
        "runtime_lane": runtime_lane,
        "reviewer": reviewer.strip(),
        "reviewed_at": reviewed_at,
        "pyproject_path": str(pyproject_path.resolve()),
        "pyproject_sha256": actual_project_sha,
        "lock_path": str(lock_path.resolve()),
        "lock_sha256": actual_lock_sha,
        "report_path": str(report_path.resolve()),
        "report_sha256": actual_report_sha,
        "approval_path": str(approval_path.resolve()),
        "approval_sha256": sha256_file(approval_path),
        "inventory_sha256": report["inventory_sha256"],
        "package_count": report["package_count"],
        "dependency_edge_count": report["dependency_edge_count"],
        "source_counts": report["source_counts"],
    }


def write_sha256_manifest(root: Path, output_path: Path) -> None:
    paths: Iterable[Path] = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.resolve() != output_path.resolve()
    )
    lines = [
        f"{sha256_file(path)}  {path.relative_to(root).as_posix()}"
        for path in paths
    ]
    output_path.write_text(
        "\n".join(lines) + ("\n" if lines else ""),
        encoding="utf-8",
    )
