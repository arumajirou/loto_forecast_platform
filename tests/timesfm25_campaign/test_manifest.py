from __future__ import annotations

from loto.adapters.timesfm25.contracts import Backend
from loto.timesfm25_campaign.backend_registry import BackendRegistry
from loto.timesfm25_campaign.model_manifest import load_default_manifest


def test_checkpoint_and_package_provenance_are_pinned() -> None:
    manifest = load_default_manifest()
    assert manifest.package_provenance.version == "2.0.2"
    assert len(manifest.package_provenance.wheel_sha256) == 64
    assert len(manifest.package_provenance.sdist_sha256) == 64
    for backend in (Backend.PYTORCH_NATIVE, Backend.TRANSFORMERS):
        row = manifest.backends[backend]
        assert len(row.revision) == 40
        assert len(row.weight_sha256) == 64


def test_backend_identity_is_fail_closed() -> None:
    registry = BackendRegistry(load_default_manifest())
    row = registry.resolve(Backend.PYTORCH_NATIVE)
    registry.validate_identity(Backend.PYTORCH_NATIVE, row.repo_id, row.revision)
