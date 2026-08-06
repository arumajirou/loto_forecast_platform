from __future__ import annotations

from pathlib import Path

from loto.adapters.timer_s1.contracts import TimerS1Request, UNPINNED
from loto.timer_s1_campaign.model_manifest import TimerS1ModelManifest, load_manifest


class ProvenanceError(ValueError):
    pass


def validate_provenance(request: TimerS1Request) -> TimerS1ModelManifest:
    if request.manifest_path is None:
        raise ProvenanceError("MANIFEST_REQUIRED")
    path = Path(request.manifest_path)
    if not path.is_absolute():
        raise ProvenanceError("MANIFEST_PATH_MUST_BE_ABSOLUTE")
    if not path.is_file() or path.is_symlink():
        raise ProvenanceError("MANIFEST_NOT_REGULAR_FILE")
    manifest = load_manifest(path)
    if not manifest.formal_pin_complete:
        raise ProvenanceError("FORMAL_PROVENANCE_UNPINNED")
    expected = {
        "model_revision": manifest.model_revision,
        "source_revision": manifest.source_revision,
    }
    for field, value in expected.items():
        if getattr(request, field) != value:
            raise ProvenanceError(f"{field.upper()}_MISMATCH")
    if UNPINNED in {
        request.model_revision,
        request.source_revision,
        request.config_sha256,
        request.weight_sha256,
        request.weight_manifest_sha256,
    }:
        raise ProvenanceError("REQUEST_PROVENANCE_UNPINNED")
    return manifest
