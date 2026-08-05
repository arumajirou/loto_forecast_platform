from __future__ import annotations

import hashlib
import importlib.metadata
import json
import re
from typing import Any
from urllib.parse import urlsplit

EXPECTED_DISTRIBUTION_NAME = "BasicTS"
EXPECTED_REPOSITORY_URL = "https://github.com/GestaltCogTeam/BasicTS"
EXPECTED_UPSTREAM_REVISION = "c2bb6e31e591167e84459775a21a62e70a5893ce"
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")


class InstalledProvenanceError(RuntimeError):
    """Raised when installed BasicTS provenance is absent, unsafe, or unexpected."""


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


def _load_direct_url(distribution: importlib.metadata.Distribution) -> tuple[dict[str, Any], str]:
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


def verify_installed_basicts_provenance() -> dict[str, Any]:
    """Verify the installed BasicTS distribution came from the frozen Git revision."""

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
    }
