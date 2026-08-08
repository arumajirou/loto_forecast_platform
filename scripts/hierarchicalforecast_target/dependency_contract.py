"""Validate the locked dependency contract before environment provisioning."""

from __future__ import annotations

import argparse
import json
import re
import tomllib
from pathlib import Path
from typing import Any

from .constants import TARGET_VERSION, CertificationError
from .integrity import require_regular_file, sha_file

_REQUIRED_DEV_TOOLS = frozenset({"mypy", "pydantic", "pytest", "pytest-cov", "ruff"})
_NAME_PATTERN = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def _normalise_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _requirement_name(requirement: object) -> str:
    if not isinstance(requirement, str):
        raise CertificationError("dependency declarations must be strings")
    match = _NAME_PATTERN.match(requirement)
    if match is None:
        raise CertificationError(f"invalid dependency declaration: {requirement!r}")
    return _normalise_name(match.group(1))


def _load_toml(path: Path, label: str) -> dict[str, Any]:
    require_regular_file(path, label)
    try:
        with path.open("rb") as stream:
            payload = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise CertificationError(f"invalid {label}: {exc}") from exc
    if not isinstance(payload, dict):
        raise CertificationError(f"{label} root must be a table")
    return payload


def _dependency_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(row, str) for row in value):
        raise CertificationError(f"{label} must be a list of requirement strings")
    return list(value)


def verify_dependency_contract(root: Path) -> dict[str, object]:
    """Verify project declarations and the exact locked HierarchicalForecast version."""

    if root.is_symlink():
        raise CertificationError(f"repository root must not be a symbolic link: {root}")
    root = root.resolve()
    pyproject_path = root / "pyproject.toml"
    lock_path = root / "uv.lock"
    pyproject = _load_toml(pyproject_path, "pyproject.toml")
    lock = _load_toml(lock_path, "uv.lock")

    project = pyproject.get("project")
    if not isinstance(project, dict):
        raise CertificationError("pyproject project table is missing")
    project_name = project.get("name")
    requires_python = project.get("requires-python")
    if not isinstance(project_name, str) or not project_name:
        raise CertificationError("project name is missing")
    if not isinstance(requires_python, str):
        raise CertificationError("project requires-python is missing")
    if ">=3.11" not in requires_python or "<3.14" not in requires_python:
        raise CertificationError("project Python range does not cover the formal 3.13 runtime")

    optional = project.get("optional-dependencies")
    if not isinstance(optional, dict):
        raise CertificationError("project optional dependencies are missing")
    dev = _dependency_list(optional.get("dev"), "dev extra")
    full = _dependency_list(optional.get("full"), "full extra")
    dev_names = {_requirement_name(row) for row in dev}
    missing_tools = sorted(_REQUIRED_DEV_TOOLS - dev_names)
    if missing_tools:
        raise CertificationError(f"dev extra lacks formal quality tools: {missing_tools}")

    hierarchical_declarations = [
        row for row in full if _requirement_name(row) == "hierarchicalforecast"
    ]
    if len(hierarchical_declarations) != 1:
        raise CertificationError(
            "full extra must contain exactly one HierarchicalForecast declaration"
        )

    lock_requires_python = lock.get("requires-python")
    if not isinstance(lock_requires_python, str):
        raise CertificationError("uv.lock requires-python is missing")
    if ">=3.11" not in lock_requires_python or "<3.14" not in lock_requires_python:
        raise CertificationError("uv.lock Python range does not cover the formal 3.13 runtime")

    packages = lock.get("package")
    if not isinstance(packages, list):
        raise CertificationError("uv.lock package list is missing")
    locked_versions = sorted(
        {
            str(row.get("version"))
            for row in packages
            if isinstance(row, dict)
            and _normalise_name(str(row.get("name", ""))) == "hierarchicalforecast"
        }
    )
    if locked_versions != [TARGET_VERSION]:
        raise CertificationError(
            "uv.lock must resolve only hierarchicalforecast=="
            f"{TARGET_VERSION}; observed={locked_versions}"
        )

    root_rows = [
        row
        for row in packages
        if isinstance(row, dict)
        and _normalise_name(str(row.get("name", ""))) == _normalise_name(project_name)
    ]
    if len(root_rows) != 1:
        raise CertificationError("uv.lock project package identity is ambiguous")
    locked_optional = root_rows[0].get("optional-dependencies")
    if not isinstance(locked_optional, dict):
        raise CertificationError("uv.lock project optional dependencies are missing")
    locked_full = locked_optional.get("full")
    if not isinstance(locked_full, list):
        raise CertificationError("uv.lock full optional dependency set is missing")
    locked_full_names = {
        _normalise_name(str(row.get("name", ""))) for row in locked_full if isinstance(row, dict)
    }
    if "hierarchicalforecast" not in locked_full_names:
        raise CertificationError("uv.lock full extra omits HierarchicalForecast")

    declaration = hierarchical_declarations[0]
    exact_declaration = declaration.replace(" ", "") == (f"hierarchicalforecast=={TARGET_VERSION}")
    return {
        "status": "VERIFIED",
        "formal_success": True,
        "target_version": TARGET_VERSION,
        "declared_requirement": declaration,
        "declaration_exact": exact_declaration,
        "locked_versions": locked_versions,
        "formal_lock_exact": True,
        "project_requires_python": requires_python,
        "lock_requires_python": lock_requires_python,
        "required_dev_tools": sorted(_REQUIRED_DEV_TOOLS),
        "pyproject_sha256": sha_file(pyproject_path),
        "uv_lock_sha256": sha_file(lock_path),
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--repo-root", type=Path, default=Path.cwd())
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        report = verify_dependency_contract(args.repo_root)
        exit_code = 0
    except Exception as exc:
        report = {
            "status": "FAILED_DEPENDENCY_CONTRACT",
            "formal_success": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
        exit_code = 2
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code
