from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

EXPECTED_DISTRIBUTION_NAME = "BasicTS"
EXPECTED_DISTRIBUTION_VERSION = "1.1.0"
EXPECTED_IMPORT_NAME = "basicts"
EXPECTED_PACKAGE_INIT = "basicts/__init__.py"
EXPECTED_REPOSITORY_URL = "https://github.com/GestaltCogTeam/BasicTS"
EXPECTED_UPSTREAM_REVISION = "c2bb6e31e591167e84459775a21a62e70a5893ce"
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")


class InstalledProvenanceError(RuntimeError):
    """Raised when installed BasicTS provenance is absent, unsafe, or unexpected."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalise_distribution_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _normalise_repository_url(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise InstalledProvenanceError("direct_url.url is missing")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.hostname != "github.com":
        raise InstalledProvenanceError(f"unexpected BasicTS repository URL: {value!r}")
    if parsed.username or parsed.password or parsed.port or parsed.query or parsed.fragment:
        raise InstalledProvenanceError(f"unsafe BasicTS repository URL: {value!r}")
    path = parsed.path.rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    normalised = f"https://github.com{path}"
    if normalised != EXPECTED_REPOSITORY_URL:
        raise InstalledProvenanceError(
            "BasicTS repository mismatch: "
            f"expected {EXPECTED_REPOSITORY_URL}, got {normalised}"
        )
    return normalised


def _load_direct_url(
    distribution: importlib.metadata.Distribution,
) -> tuple[dict[str, Any], str]:
    raw = distribution.read_text("direct_url.json")
    if raw is None:
        raise InstalledProvenanceError("BasicTS direct_url.json is missing")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InstalledProvenanceError("BasicTS direct_url.json is malformed") from exc
    if not isinstance(payload, dict):
        raise InstalledProvenanceError("BasicTS direct_url.json must contain an object")
    return payload, raw


def _distribution_package_init(
    distribution: importlib.metadata.Distribution,
) -> tuple[Path, str]:
    files = distribution.files
    if files is None:
        raise InstalledProvenanceError("BasicTS distribution file manifest is missing")
    candidates = [
        file
        for file in files
        if str(file).replace("\\", "/") == EXPECTED_PACKAGE_INIT
    ]
    if len(candidates) != 1:
        raise InstalledProvenanceError(
            "BasicTS distribution package entry mismatch: "
            f"expected one {EXPECTED_PACKAGE_INIT}, got {len(candidates)}"
        )
    package_init = Path(distribution.locate_file(candidates[0]))
    if package_init.is_symlink() or package_init.parent.is_symlink():
        raise InstalledProvenanceError("BasicTS distribution package path is a symbolic link")
    if not package_init.is_file():
        raise InstalledProvenanceError("BasicTS distribution package __init__.py is missing")
    return package_init.resolve(strict=True), EXPECTED_PACKAGE_INIT


def _provider_distributions() -> list[str]:
    providers = importlib.metadata.packages_distributions().get(EXPECTED_IMPORT_NAME)
    if not isinstance(providers, list) or len(providers) != 1:
        raise InstalledProvenanceError(
            "BasicTS import-to-distribution mapping is missing or ambiguous"
        )
    if not all(isinstance(item, str) and item for item in providers):
        raise InstalledProvenanceError("BasicTS import provider mapping is invalid")
    expected = _normalise_distribution_name(EXPECTED_DISTRIBUTION_NAME)
    if _normalise_distribution_name(providers[0]) != expected:
        raise InstalledProvenanceError(
            "BasicTS import provider mismatch: "
            f"expected {EXPECTED_DISTRIBUTION_NAME}, got {providers[0]!r}"
        )
    return providers


def _verify_import_origin(
    distribution: importlib.metadata.Distribution,
) -> dict[str, Any]:
    package_init, package_entry = _distribution_package_init(distribution)
    providers = _provider_distributions()
    try:
        spec = importlib.util.find_spec(EXPECTED_IMPORT_NAME)
    except (ImportError, AttributeError, ValueError) as exc:
        raise InstalledProvenanceError("cannot resolve BasicTS import spec") from exc
    if spec is None or not isinstance(spec.origin, str) or not spec.origin:
        raise InstalledProvenanceError("BasicTS import spec origin is missing")
    if spec.origin in {"built-in", "frozen"}:
        raise InstalledProvenanceError("BasicTS import spec is not a filesystem package")

    import_origin = Path(spec.origin)
    if import_origin.is_symlink() or import_origin.parent.is_symlink():
        raise InstalledProvenanceError("BasicTS import origin is a symbolic link")
    if not import_origin.is_file():
        raise InstalledProvenanceError("BasicTS import origin is not a regular file")
    resolved_origin = import_origin.resolve(strict=True)
    if resolved_origin != package_init:
        raise InstalledProvenanceError(
            "BasicTS import origin is shadowed: "
            f"expected {package_init}, got {resolved_origin}"
        )

    locations = spec.submodule_search_locations
    if locations is None:
        raise InstalledProvenanceError("BasicTS import spec is not a package")
    resolved_locations: list[Path] = []
    for location in locations:
        if not isinstance(location, str) or not location:
            raise InstalledProvenanceError("BasicTS package search location is invalid")
        path = Path(location)
        if path.is_symlink():
            raise InstalledProvenanceError("BasicTS package search location is a symbolic link")
        if not path.is_dir():
            raise InstalledProvenanceError("BasicTS package search location is missing")
        resolved_locations.append(path.resolve(strict=True))
    if resolved_locations != [package_init.parent]:
        raise InstalledProvenanceError(
            "BasicTS package search locations differ from the installed distribution"
        )

    loaded = sys.modules.get(EXPECTED_IMPORT_NAME)
    if loaded is not None:
        loaded_file = getattr(loaded, "__file__", None)
        if not isinstance(loaded_file, str) or not loaded_file:
            raise InstalledProvenanceError("loaded BasicTS module file is missing")
        loaded_path = Path(loaded_file)
        if loaded_path.is_symlink() or not loaded_path.is_file():
            raise InstalledProvenanceError("loaded BasicTS module file is unsafe")
        if loaded_path.resolve(strict=True) != package_init:
            raise InstalledProvenanceError("loaded BasicTS module is shadowed")

    return {
        "import_origin_status": "PASS",
        "import_name": EXPECTED_IMPORT_NAME,
        "import_provider_distributions": providers,
        "distribution_package_entry": package_entry,
        "distribution_package_init": str(package_init),
        "import_spec_origin": str(resolved_origin),
        "import_submodule_search_locations": [
            str(location) for location in resolved_locations
        ],
        "import_origin_sha256": _sha256(package_init),
        "module_already_loaded": loaded is not None,
    }


def verify_installed_basicts_provenance() -> dict[str, Any]:
    """Verify installed BasicTS Git provenance and import-origin binding."""

    try:
        distribution = importlib.metadata.distribution(EXPECTED_DISTRIBUTION_NAME)
    except importlib.metadata.PackageNotFoundError as exc:
        raise InstalledProvenanceError("BasicTS is not installed") from exc

    distribution_name = distribution.metadata.get("Name")
    if distribution_name != EXPECTED_DISTRIBUTION_NAME:
        raise InstalledProvenanceError(
            "BasicTS distribution name mismatch: "
            f"expected {EXPECTED_DISTRIBUTION_NAME}, got {distribution_name!r}"
        )
    if distribution.version != EXPECTED_DISTRIBUTION_VERSION:
        raise InstalledProvenanceError(
            "BasicTS distribution version mismatch: "
            f"expected {EXPECTED_DISTRIBUTION_VERSION}, got {distribution.version!r}"
        )

    payload, raw = _load_direct_url(distribution)
    if "dir_info" in payload or "archive_info" in payload:
        raise InstalledProvenanceError("BasicTS provenance is not a non-editable VCS install")
    if payload.get("subdirectory") is not None:
        raise InstalledProvenanceError("BasicTS provenance unexpectedly uses a subdirectory")

    repository = _normalise_repository_url(payload.get("url"))
    vcs_info = payload.get("vcs_info")
    if not isinstance(vcs_info, dict):
        raise InstalledProvenanceError("BasicTS direct_url.json lacks vcs_info")
    vcs = vcs_info.get("vcs")
    if vcs != "git":
        raise InstalledProvenanceError(f"BasicTS VCS mismatch: expected git, got {vcs!r}")

    commit_id = vcs_info.get("commit_id")
    if not isinstance(commit_id, str) or COMMIT_PATTERN.fullmatch(commit_id) is None:
        raise InstalledProvenanceError("BasicTS commit_id is invalid")
    if commit_id != EXPECTED_UPSTREAM_REVISION:
        raise InstalledProvenanceError(
            "BasicTS commit mismatch: "
            f"expected {EXPECTED_UPSTREAM_REVISION}, got {commit_id}"
        )

    requested_revision = vcs_info.get("requested_revision")
    if requested_revision != EXPECTED_UPSTREAM_REVISION:
        raise InstalledProvenanceError(
            "BasicTS requested_revision mismatch: "
            f"expected {EXPECTED_UPSTREAM_REVISION}, got {requested_revision!r}"
        )

    return {
        "installed_provenance_status": "PASS",
        "distribution_name": distribution_name,
        "distribution_version": distribution.version,
        "direct_url_repository": repository,
        "direct_url_vcs": vcs,
        "direct_url_commit_id": commit_id,
        "direct_url_requested_revision": requested_revision,
        "direct_url_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        **_verify_import_origin(distribution),
    }
