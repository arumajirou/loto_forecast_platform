from __future__ import annotations

from dataclasses import dataclass

from loto.adapters.timesfm25.contracts import Backend
from loto.timesfm25_campaign.model_manifest import BackendManifest, ModelManifest


@dataclass(frozen=True)
class BackendRegistry:
    manifest: ModelManifest

    def resolve(self, backend: Backend) -> BackendManifest:
        try:
            return self.manifest.backends[backend]
        except KeyError as exc:
            raise ValueError(f"backend is not registered: {backend}") from exc

    def validate_identity(self, backend: Backend, repo_id: str, revision: str) -> None:
        expected = self.resolve(backend)
        if repo_id != expected.repo_id:
            raise ValueError(f"repo_id mismatch for {backend}: {repo_id}")
        if revision != expected.revision:
            raise ValueError(f"revision mismatch for {backend}: {revision}")
