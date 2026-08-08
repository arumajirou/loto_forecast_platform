from __future__ import annotations

from pathlib import Path

from loto.adapters.timer_s1.contracts import UNPINNED, TimerS1Request
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
    try:
        manifest = load_manifest(path)
    except (OSError, UnicodeError, ValueError) as exc:
        raise ProvenanceError("MANIFEST_INVALID") from exc
    if not manifest.formal_pin_complete:
        raise ProvenanceError("FORMAL_PROVENANCE_UNPINNED")
    if UNPINNED in {
        request.model_revision,
        request.source_revision,
        request.config_sha256,
        request.weight_sha256,
        request.weight_manifest_sha256,
    }:
        raise ProvenanceError("REQUEST_PROVENANCE_UNPINNED")
    try:
        config_sha256 = manifest.artifact_sha256("config.json")
        weight_manifest_sha256 = manifest.artifact_sha256("model.safetensors.index.json")
        weight_sha256 = manifest.weight_set_sha256
        if weight_sha256 is None:
            raise ValueError("weight set hash is incomplete")
    except ValueError as exc:
        raise ProvenanceError("MANIFEST_REQUIRED_ARTIFACT_MISSING") from exc
    expected = {
        "model_revision": manifest.model_revision,
        "source_revision": manifest.source_revision,
        "config_sha256": config_sha256,
        "weight_manifest_sha256": weight_manifest_sha256,
        "weight_sha256": weight_sha256,
    }
    for field, value in expected.items():
        if getattr(request, field) != value:
            raise ProvenanceError(f"{field.upper()}_MISMATCH")
    return manifest
