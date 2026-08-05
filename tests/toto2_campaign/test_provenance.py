from __future__ import annotations

import pytest

from loto.toto2_campaign.model_manifest import ARTIFACT_SHA256, MODEL_REVISION, REPO_ID
from loto.toto2_campaign.provenance import (
    ArtifactRecord,
    SnapshotEvidence,
    validate_snapshot_evidence,
)


def valid_evidence() -> SnapshotEvidence:
    return SnapshotEvidence(
        repo_id=REPO_ID,
        revision=MODEL_REVISION,
        files={
            name: ArtifactRecord(
                sha256=digest,
                size_bytes=16_582_848 if name == "model.safetensors" else 1,
            )
            for name, digest in ARTIFACT_SHA256.items()
        },
    )


def test_pinned_snapshot_evidence_passes() -> None:
    validate_snapshot_evidence(valid_evidence())


def test_changed_weight_hash_is_rejected() -> None:
    evidence = valid_evidence()
    files = dict(evidence.files)
    files["model.safetensors"] = ArtifactRecord(sha256="0" * 64, size_bytes=16_582_848)
    with pytest.raises(ValueError, match="SHA-256"):
        validate_snapshot_evidence(
            SnapshotEvidence(repo_id=evidence.repo_id, revision=evidence.revision, files=files)
        )
