from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import tomllib
from pathlib import Path
from typing import Any

EXPECTED_UPSTREAM_REVISION = "c2bb6e31e591167e84459775a21a62e70a5893ce"
EXPECTED_GIT_REPOSITORY = "https://github.com/GestaltCogTeam/BasicTS"
EXPECTED_REQUIRES_PYTHON = ">=3.11,<3.12"
EXPECTED_UV_VERSION = "0.12.0"
EXPECTED_RESOLVED_VERSIONS = {
    "basicts": "1.1.0",
    "easy-torch": "1.3.3",
    "numpy": "1.24.4",
    "setuptools": "59.5.0",
    "torch": "2.9.1",
    "transformers": "4.40.1",
}
EXPECTED_DIRECT_DEPENDENCIES = {
    (
        "basicts@git+https://github.com/gestaltcogteam/basicts.git@"
        f"{EXPECTED_UPSTREAM_REVISION}"
    ),
    "numpy==1.24.4",
    "pydantic>=2.10,<3",
    "torch==2.9.1",
}


class LockAuditError(RuntimeError):
    """Raised when the isolated BasicTS dependency resolution is not reproducible."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalise_requirement(value: str) -> str:
    return "".join(value.split()).lower()


def verify_environment_pyproject(path: Path) -> dict[str, Any]:
    """Verify the immutable inputs used to produce the isolated uv resolution."""

    if path.is_symlink() or not path.is_file():
        raise LockAuditError(f"environment pyproject is missing or unsafe: {path}")
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise LockAuditError(f"cannot parse environment pyproject: {path}") from exc

    project = payload.get("project")
    if not isinstance(project, dict):
        raise LockAuditError("environment pyproject is missing [project]")
    if _normalise_requirement(str(project.get("requires-python", ""))) != (
        EXPECTED_REQUIRES_PYTHON
    ):
        raise LockAuditError("environment requires-python is not the frozen Python 3.11 lane")

    dependencies = project.get("dependencies")
    if not isinstance(dependencies, list) or not all(
        isinstance(item, str) for item in dependencies
    ):
        raise LockAuditError("environment dependencies must be a list of strings")
    normalised = {_normalise_requirement(item) for item in dependencies}
    if normalised != EXPECTED_DIRECT_DEPENDENCIES:
        raise LockAuditError(
            "environment direct dependencies differ from the frozen contract: "
            f"expected={sorted(EXPECTED_DIRECT_DEPENDENCIES)}, actual={sorted(normalised)}"
        )

    tool = payload.get("tool")
    uv = tool.get("uv") if isinstance(tool, dict) else None
    if not isinstance(uv, dict):
        raise LockAuditError("environment pyproject is missing [tool.uv]")
    if uv.get("package") is not False:
        raise LockAuditError("isolated provider must remain an unpackaged uv project")
    if uv.get("required-version") != f"=={EXPECTED_UV_VERSION}":
        raise LockAuditError("uv required-version is not frozen")
    exclude_newer = uv.get("exclude-newer")
    if not isinstance(exclude_newer, str) or not exclude_newer.endswith("Z"):
        raise LockAuditError("uv exclude-newer must be an explicit UTC timestamp")

    return {
        "path": str(path),
        "sha256": _sha256(path),
        "requires_python": EXPECTED_REQUIRES_PYTHON,
        "uv_version": EXPECTED_UV_VERSION,
        "exclude_newer": exclude_newer,
        "direct_dependencies": sorted(normalised),
    }


def _load_metadata(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size <= 0:
        raise LockAuditError(f"uv workspace metadata is missing or unsafe: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LockAuditError(f"cannot parse uv workspace metadata: {path}") from exc
    if not isinstance(payload, dict):
        raise LockAuditError("uv workspace metadata must be a JSON object")
    return payload


def _package_nodes(payload: dict[str, Any]) -> list[dict[str, Any]]:
    resolution = payload.get("resolution")
    if not isinstance(resolution, dict):
        raise LockAuditError("uv workspace metadata is missing resolution")
    nodes: list[dict[str, Any]] = []
    for node in resolution.values():
        if isinstance(node, dict) and node.get("kind") == "package":
            nodes.append(node)
    if not nodes:
        raise LockAuditError("uv workspace metadata contains no package nodes")
    return nodes


def _source_text(source: Any) -> str:
    return json.dumps(source, ensure_ascii=False, sort_keys=True).lower()


def verify_workspace_metadata(path: Path) -> dict[str, Any]:
    """Verify exact resolved versions and the BasicTS Git provenance from uv JSON metadata."""

    payload = _load_metadata(path)
    schema = payload.get("schema")
    if not isinstance(schema, dict) or not isinstance(schema.get("version"), str):
        raise LockAuditError("uv workspace metadata schema version is missing")
    if _normalise_requirement(str(payload.get("requires_python", ""))) != (
        EXPECTED_REQUIRES_PYTHON
    ):
        raise LockAuditError("metadata requires_python does not match the isolated lane")

    environment = payload.get("environment")
    python = environment.get("python") if isinstance(environment, dict) else None
    python_version = python.get("version") if isinstance(python, dict) else None
    implementation = python.get("implementation") if isinstance(python, dict) else None
    if not isinstance(python_version, str) or not python_version.startswith("3.11."):
        raise LockAuditError("metadata environment is not running Python 3.11")
    if implementation != "cpython":
        raise LockAuditError("metadata environment is not CPython")

    conflicts = payload.get("conflicts")
    if isinstance(conflicts, dict) and conflicts.get("sets"):
        raise LockAuditError("isolated BasicTS resolution contains workspace conflicts")

    nodes = _package_nodes(payload)
    resolved: dict[str, list[dict[str, Any]]] = {}
    for node in nodes:
        name = node.get("name")
        if isinstance(name, str):
            resolved.setdefault(name.lower(), []).append(node)

    package_evidence: dict[str, Any] = {}
    for name, expected_version in EXPECTED_RESOLVED_VERSIONS.items():
        matches = resolved.get(name, [])
        if not matches:
            raise LockAuditError(f"resolved package is missing: {name}")
        versions = {node.get("version") for node in matches}
        if versions != {expected_version}:
            raise LockAuditError(
                f"resolved version mismatch for {name}: "
                f"expected={expected_version}, actual={sorted(str(item) for item in versions)}"
            )
        package_evidence[name] = {
            "version": expected_version,
            "node_count": len(matches),
        }

    basicts_nodes = resolved["basicts"]
    expected_repository = EXPECTED_GIT_REPOSITORY.lower()
    for node in basicts_nodes:
        source_text = _source_text(node.get("source"))
        repository_matches = (
            expected_repository in source_text
            or f"{expected_repository}.git" in source_text
        )
        if not repository_matches:
            raise LockAuditError("BasicTS resolved source is not the frozen GitHub repository")
        if EXPECTED_UPSTREAM_REVISION not in source_text:
            raise LockAuditError("BasicTS resolved source is missing the frozen commit")
    package_evidence["basicts"]["repository"] = EXPECTED_GIT_REPOSITORY
    package_evidence["basicts"]["revision"] = EXPECTED_UPSTREAM_REVISION

    return {
        "path": str(path),
        "sha256": _sha256(path),
        "schema_version": schema["version"],
        "python_version": python_version,
        "python_implementation": implementation,
        "packages": package_evidence,
    }


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    os.close(descriptor)
    temporary_path = Path(temporary)
    try:
        temporary_path.write_text(text, encoding="utf-8")
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit the isolated BasicTS uv resolution")
    parser.add_argument("--pyproject", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = {
        "schema_version": "1.0",
        "status": "PASS",
        "scope": "BASICTS_UV_RESOLUTION_AUDIT",
        "environment": verify_environment_pyproject(args.pyproject),
        "resolution": verify_workspace_metadata(args.metadata),
    }
    _atomic_write_text(
        args.output,
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    _atomic_write_text(
        args.output.with_suffix(args.output.suffix + ".sha256"),
        f"{_sha256(args.output)}  {args.output.name}\n",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
