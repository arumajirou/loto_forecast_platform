from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tomllib
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

REVIEW_SCHEMA = "tirex2-lock-review-v1"
APPROVAL_SCHEMA = "tirex2-lock-approval-v1"
REPORT_FILENAME = "LOCK_REVIEW_REPORT.json"
APPROVAL_FILENAME = "LOCK_REVIEW_APPROVAL.json"
LOCK_FILENAME = "uv.lock"
APPLY_TOKEN = "APPLY-REVIEWED-TIREX2-LOCK"
EXPECTED_REGISTRY = "https://pypi.org/simple"
EXPECTED_TIREX_ARTIFACT_HASHES = frozenset(
    {
        "sha256:1d9f0ead93662d4438371ef0bb3b6319dc4811ba9d17fe343c8fa8f456b1730b",
        "sha256:bc82b6e0698b9828888cd6e5037717dba8e107320116725061824308e10fbeb2",
    }
)

_FORBIDDEN_SOURCE_KEYS = {
    "directory",
    "editable",
    "git",
    "path",
    "url",
    "workspace",
}


class LockReviewError(RuntimeError):
    pass


@dataclass(frozen=True)
class DirectRequirement:
    name: str
    raw: str
    constraints: tuple[tuple[str, str], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "raw": self.raw,
            "constraints": [list(item) for item in self.constraints],
        }


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


def _parse_version(value: str) -> tuple[int, ...]:
    match = re.fullmatch(r"v?(\d+(?:\.\d+)*)", value.strip())
    if match is None:
        raise LockReviewError(f"unsupported version syntax: {value!r}")
    return tuple(int(part) for part in match.group(1).split("."))


def _pad_versions(
    left: tuple[int, ...],
    right: tuple[int, ...],
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    width = max(len(left), len(right))
    return left + (0,) * (width - len(left)), right + (0,) * (width - len(right))


def _compare_versions(left: str, right: str) -> int:
    left_parts, right_parts = _pad_versions(_parse_version(left), _parse_version(right))
    return (left_parts > right_parts) - (left_parts < right_parts)


def _parse_requirement(raw: str) -> DirectRequirement:
    if ";" in raw:
        raise LockReviewError(f"environment markers are not allowed: {raw!r}")
    if "@" in raw:
        raise LockReviewError(f"direct URL dependencies are not allowed: {raw!r}")
    match = re.fullmatch(r"\s*([A-Za-z0-9_.-]+)(?:\[[^]]+\])?\s*(.*)\s*", raw)
    if match is None:
        raise LockReviewError(f"invalid dependency requirement: {raw!r}")
    name = normalize_name(match.group(1))
    specifier = match.group(2).strip()
    if not specifier:
        raise LockReviewError(f"unbounded dependency is not allowed: {raw!r}")
    constraints: list[tuple[str, str]] = []
    for item in specifier.split(","):
        constraint = item.strip()
        parsed = re.fullmatch(r"(==|>=|<=|>|<)(\d+(?:\.\d+)*)", constraint)
        if parsed is None:
            raise LockReviewError(f"unsupported dependency constraint: {constraint!r}")
        constraints.append((parsed.group(1), parsed.group(2)))
    return DirectRequirement(name=name, raw=raw, constraints=tuple(constraints))


def _version_satisfies(version: str, requirement: DirectRequirement) -> bool:
    for operator, expected in requirement.constraints:
        comparison = _compare_versions(version, expected)
        if operator == "==" and comparison != 0:
            return False
        if operator == ">=" and comparison < 0:
            return False
        if operator == "<=" and comparison > 0:
            return False
        if operator == ">" and comparison <= 0:
            return False
        if operator == "<" and comparison >= 0:
            return False
    return True


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
    dependencies: dict[str, DirectRequirement] = {}
    for raw in raw_dependencies:
        if not isinstance(raw, str):
            raise LockReviewError(f"dependency is not text: {raw!r}")
        requirement = _parse_requirement(raw)
        if requirement.name in dependencies:
            raise LockReviewError(f"duplicate direct dependency: {requirement.name}")
        dependencies[requirement.name] = requirement
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
    if not isinstance(source, dict):
        return "invalid", repr(source), ["package source is not a table"]
    keys = sorted(str(key) for key in source)
    if is_root_project and keys == ["virtual"] and source.get("virtual") == ".":
        return "root-virtual", ".", []
    forbidden = sorted(set(keys) & _FORBIDDEN_SOURCE_KEYS)
    if forbidden:
        return "+".join(keys), repr(source), [f"forbidden source keys: {forbidden}"]
    if keys == ["registry"]:
        value = source.get("registry")
        if value == EXPECTED_REGISTRY:
            return "registry", value, []
        return "registry", repr(value), [f"registry must be {EXPECTED_REGISTRY}"]
    return "+".join(keys) or "empty", repr(source), [f"unsupported source keys: {keys}"]


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


def _valid_artifact_hash(value: str) -> bool:
    return bool(re.fullmatch(r"sha256:[0-9a-f]{64}", value))


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
            violations.append(f"{name}=={raw_version}: invalid artifact hashes={invalid_hashes}")
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

    for name, requirement in sorted(project["dependencies"].items()):
        actual_versions = sorted(locked_versions.get(name, set()))
        compatible = [
            version for version in actual_versions if _version_satisfies(version, requirement)
        ]
        if not compatible:
            violations.append(
                f"direct dependency mismatch: {name} requirement={requirement.raw!r} "
                f"locked={actual_versions}"
            )

    package_names = set(locked_versions)
    for package in inventory:
        missing = sorted(set(package.dependency_names) - package_names)
        if missing:
            violations.append(
                f"{package.name}=={package.version}: unresolved dependency names={missing}"
            )

    tirex_packages = [package for package in inventory if package.name == "tirex-2"]
    tirex_hashes = {value for package in tirex_packages for value in package.artifact_hashes}
    if not tirex_hashes.intersection(EXPECTED_TIREX_ARTIFACT_HASHES):
        violations.append("tirex-2==0.1.1 official wheel/sdist SHA-256 was not found")

    duplicates = {
        name: sorted(versions)
        for name, versions in sorted(locked_versions.items())
        if len(versions) > 1
    }
    if duplicates:
        warnings.append(f"multiple locked versions detected: {duplicates}")

    inventory_payload = [
        package.as_dict()
        for package in sorted(
            inventory,
            key=lambda item: (item.name, item.version, item.source_kind),
        )
    ]
    source_counts: dict[str, int] = {}
    for package in inventory:
        source_counts[package.source_kind] = source_counts.get(package.source_kind, 0) + 1
    direct_payload = [
        requirement.as_dict() for _, requirement in sorted(project["dependencies"].items())
    ]
    report = {
        "schema_version": REVIEW_SCHEMA,
        "status": "PASS" if not violations else "FAILED",
        "runtime_lane": runtime_lane,
        "root_project": project["name"],
        "requires_python": project["requires_python"],
        "pyproject_file": "pyproject.toml",
        "pyproject_sha256": sha256_file(pyproject_path),
        "lock_file": LOCK_FILENAME,
        "lock_sha256": sha256_file(lock_path),
        "lock_format_version": lock.get("version"),
        "lock_revision": lock.get("revision"),
        "package_count": len(inventory_payload),
        "dependency_edge_count": sum(len(item.dependency_names) for item in inventory),
        "direct_dependencies": direct_payload,
        "locked_versions": {
            name: sorted(versions) for name, versions in sorted(locked_versions.items())
        },
        "source_counts": dict(sorted(source_counts.items())),
        "expected_tirex_artifact_hashes": sorted(EXPECTED_TIREX_ARTIFACT_HASHES),
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
    recomputed = inspect_lock(
        pyproject_path=pyproject_path,
        lock_path=lock_path,
        runtime_lane=runtime_lane,
    )
    if canonical_json_bytes(report) != canonical_json_bytes(recomputed):
        raise LockReviewError("installed review report does not match installed artifacts")
    if approval.get("schema_version") != APPROVAL_SCHEMA:
        raise LockReviewError("installed approval schema is invalid")
    if approval.get("decision") != "APPROVED":
        raise LockReviewError("installed lock approval is not APPROVED")
    if approval.get("runtime_lane") != runtime_lane:
        raise LockReviewError("approval runtime lane does not match requested lane")
    reviewer = approval.get("reviewer")
    reviewed_at = approval.get("reviewed_at")
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise LockReviewError("approval reviewer is missing")
    if not isinstance(reviewed_at, str):
        raise LockReviewError("approval reviewed_at is missing")
    _parse_reviewed_at(reviewed_at)
    checks = {
        "pyproject_sha256": recomputed["pyproject_sha256"],
        "lock_sha256": recomputed["lock_sha256"],
        "report_sha256": sha256_payload(recomputed),
        "inventory_sha256": recomputed["inventory_sha256"],
    }
    for key, actual in checks.items():
        if approval.get(key) != actual:
            raise LockReviewError(f"approval {key} does not match installed artifact")
    if int(approval.get("violation_count", -1)) != 0:
        raise LockReviewError("approval violation_count must be zero")
    return {
        "status": "PASS",
        "runtime_lane": runtime_lane,
        "reviewer": reviewer,
        "reviewed_at": reviewed_at,
        **checks,
    }


def _atomic_write(path: Path, data: bytes) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def install_reviewed_lock(
    *,
    candidate_path: Path,
    environment_path: Path,
    runtime_lane: str,
    reviewer: str,
    reviewed_at: str,
    expected_candidate_lock_sha256: str,
    apply: bool,
    approval_token: str | None,
    expected_current_lock_sha256: str | None = None,
) -> dict[str, Any]:
    candidate_project = candidate_path / "pyproject.toml"
    candidate_lock = candidate_path / LOCK_FILENAME
    candidate_report = candidate_path / REPORT_FILENAME
    environment_project = environment_path / "pyproject.toml"
    for path in (candidate_project, candidate_lock, candidate_report, environment_project):
        if not path.is_file():
            raise LockReviewError(f"required file is missing: {path}")
    if sha256_file(candidate_project) != sha256_file(environment_project):
        raise LockReviewError("candidate and environment pyproject.toml differ")
    actual_lock_sha = sha256_file(candidate_lock)
    if actual_lock_sha != expected_candidate_lock_sha256:
        raise LockReviewError("candidate lock SHA-256 does not match expected value")
    stored_report = load_json_object(candidate_report)
    recomputed_report = inspect_lock(
        pyproject_path=candidate_project,
        lock_path=candidate_lock,
        runtime_lane=runtime_lane,
    )
    if canonical_json_bytes(stored_report) != canonical_json_bytes(recomputed_report):
        raise LockReviewError("candidate review report does not match candidate artifacts")
    approval = build_approval(
        report=recomputed_report,
        reviewer=reviewer,
        reviewed_at=reviewed_at,
    )
    plan = {
        "status": "DRY_RUN" if not apply else "PASS",
        "runtime_lane": runtime_lane,
        "candidate_lock_sha256": actual_lock_sha,
        "report_sha256": sha256_payload(recomputed_report),
        "reviewer": reviewer.strip(),
        "reviewed_at": reviewed_at,
        "apply": apply,
    }
    if not apply:
        return plan
    if approval_token != APPLY_TOKEN:
        raise LockReviewError(f"approval token must equal {APPLY_TOKEN}")

    environment_path.mkdir(parents=True, exist_ok=True)
    targets = {
        environment_path / LOCK_FILENAME: candidate_lock.read_bytes(),
        environment_path / REPORT_FILENAME: (
            json.dumps(recomputed_report, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8"),
        environment_path / APPROVAL_FILENAME: (
            json.dumps(approval, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8"),
    }
    current_lock = environment_path / LOCK_FILENAME
    backup_path: Path | None = None
    if current_lock.exists():
        current_sha = sha256_file(current_lock)
        if expected_current_lock_sha256 != current_sha:
            raise LockReviewError("existing lock replacement SHA-256 guard failed")
        backup_path = environment_path / ".lock-review-backups" / current_sha[:16]
        backup_path.mkdir(parents=True, exist_ok=False)
        for target in targets:
            if target.exists():
                shutil.copy2(target, backup_path / target.name)

    written: list[Path] = []
    try:
        for target, data in targets.items():
            _atomic_write(target, data)
            written.append(target)
        validate_installed_review(
            environment_path=environment_path,
            runtime_lane=runtime_lane,
        )
    except Exception:
        for target in written:
            target.unlink(missing_ok=True)
        if backup_path is not None:
            for backup in backup_path.iterdir():
                shutil.copy2(backup, environment_path / backup.name)
        raise
    plan["backup_path"] = str(backup_path) if backup_path is not None else None
    return plan
