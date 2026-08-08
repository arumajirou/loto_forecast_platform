from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import socket
import subprocess
import tempfile
import tomllib
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

EXPECTED_MERLION_VERSION = "2.0.4"
EXPECTED_REGISTRY = "https://pypi.org/simple"
MIN_FREE_BYTES = 5 * 1024**3
NETWORK_HOSTS = ("pypi.org", "files.pythonhosted.org", "github.com")


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
        temp_path = Path(stream.name)
    temp_path.replace(path)


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _command_result(
    command: Sequence[str],
    *,
    timeout_seconds: float,
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
) -> dict[str, Any]:
    try:
        completed = runner(
            list(command),
            check=False,
            capture_output=True,
            text=False,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "returncode": None,
            "stdout": "",
            "stderr": f"{type(exc).__name__}: {exc}",
        }
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout.decode("utf-8", errors="replace").strip(),
        "stderr": completed.stderr.decode("utf-8", errors="replace").strip(),
    }


def _dns_probe(
    host: str,
    resolver: Callable[..., Any] = socket.getaddrinfo,
) -> dict[str, Any]:
    try:
        records = resolver(host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        return {"host": host, "reachable": False, "detail": f"{type(exc).__name__}: {exc}"}
    addresses = sorted({str(record[4][0]) for record in records})
    return {"host": host, "reachable": True, "addresses": addresses[:8]}


def build_preflight_report(
    root: Path,
    env_dir: Path,
    *,
    timeout_seconds: float = 10.0,
    min_free_bytes: int = MIN_FREE_BYTES,
    which: Callable[[str], str | None] = shutil.which,
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
    resolver: Callable[..., Any] = socket.getaddrinfo,
    disk_usage: Callable[[str | os.PathLike[str]], Any] = shutil.disk_usage,
) -> dict[str, Any]:
    root = root.resolve()
    env_dir = env_dir.resolve()
    blockers: list[str] = []
    warnings: list[str] = []

    uv_path = which("uv")
    uv_result: dict[str, Any]
    python_result: dict[str, Any]
    if uv_path is None:
        blockers.append("UV_NOT_FOUND")
        uv_result = {"found": False, "path": None, "version": None}
        python_result = {"found": False, "path": None, "version": None}
    else:
        version_probe = _command_result(
            [uv_path, "--version"],
            timeout_seconds=timeout_seconds,
            runner=runner,
        )
        uv_result = {
            "found": version_probe["returncode"] == 0,
            "path": uv_path,
            "version": version_probe["stdout"] or None,
            "stderr": version_probe["stderr"],
        }
        if version_probe["returncode"] != 0:
            blockers.append("UV_VERSION_PROBE_FAILED")
        python_probe = _command_result(
            [uv_path, "python", "find", "--no-python-downloads", "3.11"],
            timeout_seconds=timeout_seconds,
            runner=runner,
        )
        python_path = python_probe["stdout"].splitlines()[-1] if python_probe["stdout"] else None
        python_version = None
        if python_probe["returncode"] == 0 and python_path:
            version_result = _command_result(
                [python_path, "--version"],
                timeout_seconds=timeout_seconds,
                runner=runner,
            )
            python_version = version_result["stdout"] or version_result["stderr"] or None
        python_result = {
            "found": python_probe["returncode"] == 0,
            "path": python_path,
            "version": python_version,
            "stderr": python_probe["stderr"],
        }

    pyproject = env_dir / "pyproject.toml"
    filesystem = {
        "pyproject_exists": pyproject.is_file(),
        "environment_directory_exists": env_dir.is_dir(),
        "environment_directory_writable": os.access(env_dir, os.W_OK),
    }
    if not filesystem["pyproject_exists"]:
        blockers.append("ISOLATED_PYPROJECT_MISSING")
    if not filesystem["environment_directory_exists"]:
        blockers.append("ISOLATED_ENVIRONMENT_DIRECTORY_MISSING")
    elif not filesystem["environment_directory_writable"]:
        blockers.append("ISOLATED_ENVIRONMENT_DIRECTORY_NOT_WRITABLE")

    usage = disk_usage(root)
    disk = {
        "free_bytes": int(usage.free),
        "minimum_free_bytes": int(min_free_bytes),
        "sufficient": int(usage.free) >= int(min_free_bytes),
    }
    if not disk["sufficient"]:
        blockers.append("INSUFFICIENT_FREE_DISK")

    network = [_dns_probe(host, resolver=resolver) for host in NETWORK_HOSTS]
    reachable = {row["host"]: bool(row["reachable"]) for row in network}
    python_download_possible = reachable.get("github.com", False)
    package_index_resolvable = reachable.get("pypi.org", False) and reachable.get(
        "files.pythonhosted.org", False
    )
    if not python_result["found"] and not python_download_possible:
        blockers.append("PYTHON_311_UNAVAILABLE_AND_DOWNLOAD_BLOCKED")
    if not package_index_resolvable:
        warnings.append("PACKAGE_INDEX_DNS_UNAVAILABLE")

    can_attempt = not blockers
    if blockers:
        status = "BLOCKED"
    elif warnings:
        status = "DEGRADED"
    elif python_result["found"]:
        status = "READY"
    else:
        status = "READY_WITH_PYTHON_DOWNLOAD"

    report: dict[str, Any] = {
        "schema_version": "merlion-bootstrap-preflight-v1",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "status": status,
        "can_attempt_bootstrap": can_attempt,
        "root": str(root),
        "environment_directory": str(env_dir),
        "uv": uv_result,
        "python_311": python_result,
        "filesystem": filesystem,
        "disk": disk,
        "network_dns": network,
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
    }
    report["report_sha256"] = _canonical_sha256(report)
    return report


def _source_details(source: Mapping[str, Any]) -> tuple[str, str]:
    if not source:
        return "missing", ""
    for kind in ("registry", "git", "url", "path", "editable", "virtual"):
        if kind in source:
            return kind, str(source[kind])
    keys = ",".join(sorted(str(key) for key in source))
    return "unknown", keys


def _artifact_rows(package: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    sdist = package.get("sdist")
    if isinstance(sdist, Mapping):
        rows.append({"kind": "sdist", **dict(sdist)})
    wheels = package.get("wheels", [])
    if isinstance(wheels, list):
        for wheel in wheels:
            if isinstance(wheel, Mapping):
                rows.append({"kind": "wheel", **dict(wheel)})
    return rows


def audit_uv_lock(lock_path: Path, pyproject_path: Path) -> dict[str, Any]:
    lock_data = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    project_data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    blockers: list[str] = []
    warnings: list[str] = ["LICENSE_DATA_NOT_PRESENT_IN_UV_LOCK"]
    inventory: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()

    packages = lock_data.get("package", [])
    if not isinstance(packages, list) or not packages:
        blockers.append("LOCK_HAS_NO_PACKAGES")
        packages = []

    for package in packages:
        if not isinstance(package, Mapping):
            blockers.append("LOCK_PACKAGE_ENTRY_INVALID")
            continue
        name = str(package.get("name", ""))
        version = str(package.get("version", ""))
        source = package.get("source", {})
        if not isinstance(source, Mapping):
            source = {}
        source_kind, source_value = _source_details(source)
        key = (name, version, source_kind, source_value)
        if key in seen:
            blockers.append(f"DUPLICATE_PACKAGE:{name}:{version}")
        seen.add(key)

        artifacts = _artifact_rows(package)
        hashes = [str(row.get("hash", "")) for row in artifacts]
        valid_hashes = [value for value in hashes if value.startswith("sha256:")]
        if source_kind == "registry":
            if source_value != EXPECTED_REGISTRY:
                blockers.append(f"UNEXPECTED_REGISTRY:{name}:{source_value}")
            if not artifacts:
                blockers.append(f"REGISTRY_PACKAGE_WITHOUT_ARTIFACTS:{name}")
            if len(valid_hashes) != len(artifacts):
                blockers.append(f"REGISTRY_PACKAGE_HASH_INCOMPLETE:{name}")
        elif source_kind == "virtual" and name == project_data.get("project", {}).get("name"):
            pass
        else:
            blockers.append(f"UNTRUSTED_SOURCE:{name}:{source_kind}:{source_value}")

        dependency_count = len(package.get("dependencies", []))
        inventory.append(
            {
                "name": name,
                "version": version,
                "source_kind": source_kind,
                "source": source_value,
                "artifact_count": len(artifacts),
                "sha256_artifact_count": len(valid_hashes),
                "dependency_count": dependency_count,
            }
        )

    by_name: dict[str, list[dict[str, Any]]] = {}
    for row in inventory:
        by_name.setdefault(str(row["name"]), []).append(row)

    merlion_rows = by_name.get("salesforce-merlion", [])
    if len(merlion_rows) != 1:
        blockers.append("MERLION_PACKAGE_COUNT_NOT_ONE")
    elif merlion_rows[0]["version"] != EXPECTED_MERLION_VERSION:
        blockers.append(f"MERLION_VERSION_MISMATCH:{merlion_rows[0]['version']}")

    numpy_rows = by_name.get("numpy", [])
    if not numpy_rows:
        blockers.append("NUMPY_PACKAGE_MISSING")
    else:
        for row in numpy_rows:
            try:
                major = int(str(row["version"]).split(".", 1)[0])
            except ValueError:
                blockers.append(f"NUMPY_VERSION_INVALID:{row['version']}")
                continue
            if major >= 2:
                blockers.append(f"NUMPY_MAJOR_NOT_ISOLATED:{row['version']}")

    expected_requires_python = project_data.get("project", {}).get("requires-python")
    lock_requires_python = lock_data.get("requires-python")
    if expected_requires_python != lock_requires_python:
        blockers.append(
            f"REQUIRES_PYTHON_MISMATCH:{lock_requires_python}:{expected_requires_python}"
        )

    inventory.sort(key=lambda row: (str(row["name"]), str(row["version"]), str(row["source"])))
    report: dict[str, Any] = {
        "schema_version": "merlion-uv-lock-audit-v1",
        "status": "PASS" if not blockers else "BLOCKED",
        "lock_sha256": hashlib.sha256(lock_path.read_bytes()).hexdigest(),
        "pyproject_sha256": hashlib.sha256(pyproject_path.read_bytes()).hexdigest(),
        "lock_version": lock_data.get("version"),
        "lock_revision": lock_data.get("revision"),
        "requires_python": lock_requires_python,
        "package_count": len(inventory),
        "registry_package_count": sum(row["source_kind"] == "registry" for row in inventory),
        "artifact_count": sum(int(row["artifact_count"]) for row in inventory),
        "sha256_artifact_count": sum(int(row["sha256_artifact_count"]) for row in inventory),
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "inventory": inventory,
    }
    report["report_sha256"] = _canonical_sha256(report)
    return report


def write_inventory_csv(path: Path, inventory: Iterable[Mapping[str, Any]]) -> None:
    fieldnames = [
        "name",
        "version",
        "source_kind",
        "source",
        "artifact_count",
        "sha256_artifact_count",
        "dependency_count",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in inventory:
            writer.writerow(dict(row))
        stream.flush()
        os.fsync(stream.fileno())
        temp_path = Path(stream.name)
    temp_path.replace(path)
