from __future__ import annotations

import hashlib
import importlib.metadata
from pathlib import Path

PACKAGE_NAME = "salesforce-merlion"
PACKAGE_VERSION = "2.0.4"
UPSTREAM_REVISION = "39507642dc3d7b8d04232e34e9f36b372cf4912d"
UPSTREAM_ARCHIVED = True
WHEEL_SHA256 = "3b50271ab371caa85c03b4a7ccb764c8e7eafb4b836d9e13026b49ee3ab06e89"
SDIST_SHA256 = "adc939ec07d95d64a97e6019c5e709dbf03d2eb7b7adc28d80ebfe8a5a84d2a8"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def installed_identity() -> dict[str, object]:
    version = importlib.metadata.version(PACKAGE_NAME)
    return {
        "package_name": PACKAGE_NAME,
        "expected_version": PACKAGE_VERSION,
        "installed_version": version,
        "version_match": version == PACKAGE_VERSION,
        "upstream_revision": UPSTREAM_REVISION,
        "upstream_archived": UPSTREAM_ARCHIVED,
        "wheel_sha256": WHEEL_SHA256,
        "sdist_sha256": SDIST_SHA256,
    }
