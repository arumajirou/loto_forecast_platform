from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest

from loto.basicts_campaign import installed_provenance
from loto.basicts_campaign.installed_provenance import (
    EXPECTED_UPSTREAM_REVISION,
    InstalledProvenanceError,
    verify_installed_basicts_provenance,
)


@dataclass
class FakeDistribution:
    direct_url: str | None
    name: str = "BasicTS"
    version: str = "1.1.0"

    @property
    def metadata(self) -> dict[str, str]:
        return {"Name": self.name}

    def read_text(self, filename: str) -> str | None:
        assert filename == "direct_url.json"
        return self.direct_url


def _payload(**updates: Any) -> str:
    payload: dict[str, Any] = {
        "url": "https://github.com/GestaltCogTeam/BasicTS.git",
        "vcs_info": {
            "vcs": "git",
            "requested_revision": EXPECTED_UPSTREAM_REVISION,
            "commit_id": EXPECTED_UPSTREAM_REVISION,
        },
    }
    payload.update(updates)
    return json.dumps(payload)


def _install(monkeypatch: pytest.MonkeyPatch, direct_url: str | None) -> None:
    monkeypatch.setattr(
        installed_provenance.importlib.metadata,
        "distribution",
        lambda name: FakeDistribution(direct_url),
    )


def test_accepts_exact_git_provenance(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _payload())

    evidence = verify_installed_basicts_provenance()

    assert evidence["installed_provenance_status"] == "PASS"
    assert evidence["direct_url_commit_id"] == EXPECTED_UPSTREAM_REVISION
    assert evidence["direct_url_repository"].endswith("/BasicTS")
    assert len(evidence["direct_url_sha256"]) == 64


def test_rejects_missing_direct_url(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, None)

    with pytest.raises(InstalledProvenanceError, match="direct_url.json is missing"):
        verify_installed_basicts_provenance()


def test_rejects_wrong_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _payload(url="https://github.com/example/BasicTS.git"))

    with pytest.raises(InstalledProvenanceError, match="repository mismatch"):
        verify_installed_basicts_provenance()


def test_rejects_wrong_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.loads(_payload())
    payload["vcs_info"]["commit_id"] = "b" * 40
    _install(monkeypatch, json.dumps(payload))

    with pytest.raises(InstalledProvenanceError, match="commit mismatch"):
        verify_installed_basicts_provenance()


def test_rejects_non_git_vcs(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.loads(_payload())
    payload["vcs_info"]["vcs"] = "hg"
    _install(monkeypatch, json.dumps(payload))

    with pytest.raises(InstalledProvenanceError, match="VCS mismatch"):
        verify_installed_basicts_provenance()


def test_rejects_malformed_json(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, "{")

    with pytest.raises(InstalledProvenanceError, match="malformed"):
        verify_installed_basicts_provenance()


def test_rejects_editable_or_local_install(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _payload(dir_info={"editable": True}))

    with pytest.raises(InstalledProvenanceError, match="non-editable VCS install"):
        verify_installed_basicts_provenance()


def test_rejects_requested_revision_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.loads(_payload())
    payload["vcs_info"]["requested_revision"] = "main"
    _install(monkeypatch, json.dumps(payload))

    with pytest.raises(InstalledProvenanceError, match="requested_revision mismatch"):
        verify_installed_basicts_provenance()
