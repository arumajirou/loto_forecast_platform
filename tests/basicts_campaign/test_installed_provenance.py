from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from loto.basicts_campaign import installed_provenance
from loto.basicts_campaign.installed_provenance import (
    EXPECTED_UPSTREAM_REVISION,
    InstalledProvenanceError,
    verify_installed_basicts_provenance,
)


@dataclass(frozen=True)
class FakeFileHash:
    mode: str
    value: str


@dataclass(frozen=True)
class FakePackagePath:
    path: str
    hash: FakeFileHash | None
    size: int | None

    def __str__(self) -> str:
        return self.path


@dataclass
class FakeDistribution:
    direct_url: str | None
    root: Path
    entries: list[FakePackagePath] | None
    name: str = "BasicTS"
    version: str = "1.1.0"

    @property
    def metadata(self) -> dict[str, str]:
        return {"Name": self.name}

    @property
    def files(self) -> list[FakePackagePath] | None:
        return self.entries

    def locate_file(self, path: FakePackagePath) -> Path:
        return self.root / Path(str(path))

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


def _record_hash(path: Path) -> FakeFileHash:
    digest = hashlib.sha256(path.read_bytes()).digest()
    value = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return FakeFileHash("sha256", value)


def _entry(path: Path, root: Path) -> FakePackagePath:
    relative = path.relative_to(root).as_posix()
    return FakePackagePath(relative, _record_hash(path), path.stat().st_size)


def _install(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    direct_url: str | None,
    *,
    version: str = "1.1.0",
    include_files: bool = True,
    origin: Path | None = None,
    providers: list[str] | None = None,
    mutate_entries: Any = None,
) -> tuple[Path, Path, FakeDistribution]:
    root = tmp_path / "site-packages"
    package = root / "basicts"
    package.mkdir(parents=True)
    package_init = package / "__init__.py"
    package_init.write_text("__version__ = '1.1.0'\n", encoding="utf-8")

    dist_info = root / "BasicTS-1.1.0.dist-info"
    dist_info.mkdir()
    direct_url_path = dist_info / "direct_url.json"
    if direct_url is not None:
        direct_url_path.write_text(direct_url, encoding="utf-8")

    entries: list[FakePackagePath] | None
    if include_files:
        entries = [_entry(package_init, root)]
        if direct_url is not None:
            entries.append(_entry(direct_url_path, root))
        if mutate_entries is not None:
            entries = mutate_entries(entries, package_init, direct_url_path)
    else:
        entries = None

    distribution = FakeDistribution(
        direct_url,
        root,
        entries,
        version=version,
    )
    monkeypatch.setattr(
        installed_provenance.importlib.metadata,
        "distribution",
        lambda name: distribution,
    )
    monkeypatch.setattr(
        installed_provenance.importlib.metadata,
        "packages_distributions",
        lambda: {"basicts": providers if providers is not None else ["BasicTS"]},
    )
    resolved_origin = origin or package_init
    spec = importlib.util.spec_from_file_location(
        "basicts",
        resolved_origin,
        submodule_search_locations=[str(resolved_origin.parent)],
    )
    monkeypatch.setattr(
        installed_provenance.importlib.util,
        "find_spec",
        lambda name: spec,
    )
    monkeypatch.delitem(sys.modules, "basicts", raising=False)
    return package_init, direct_url_path, distribution


def test_accepts_exact_git_provenance_record_and_import_origin(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package_init, direct_url_path, _ = _install(monkeypatch, tmp_path, _payload())

    evidence = verify_installed_basicts_provenance()

    assert evidence["installed_provenance_status"] == "PASS"
    assert evidence["installed_record_integrity_status"] == "PASS"
    assert evidence["import_origin_status"] == "PASS"
    assert evidence["direct_url_record_status"] == "PASS"
    assert evidence["package_init_record_status"] == "PASS"
    assert evidence["direct_url_commit_id"] == EXPECTED_UPSTREAM_REVISION
    assert evidence["import_spec_origin"] == str(package_init.resolve())
    assert evidence["direct_url_record_path"] == str(direct_url_path.resolve())
    assert evidence["import_provider_distributions"] == ["BasicTS"]
    assert len(evidence["import_origin_sha256"]) == 64


def test_rejects_missing_direct_url(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install(monkeypatch, tmp_path, None)

    with pytest.raises(InstalledProvenanceError, match="direct_url.json is missing"):
        verify_installed_basicts_provenance()


def test_rejects_wrong_repository(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install(
        monkeypatch,
        tmp_path,
        _payload(url="https://github.com/example/BasicTS.git"),
    )

    with pytest.raises(InstalledProvenanceError, match="repository mismatch"):
        verify_installed_basicts_provenance()


def test_rejects_wrong_commit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    payload = json.loads(_payload())
    payload["vcs_info"]["commit_id"] = "b" * 40
    _install(monkeypatch, tmp_path, json.dumps(payload))

    with pytest.raises(InstalledProvenanceError, match="commit mismatch"):
        verify_installed_basicts_provenance()


def test_rejects_non_git_vcs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    payload = json.loads(_payload())
    payload["vcs_info"]["vcs"] = "hg"
    _install(monkeypatch, tmp_path, json.dumps(payload))

    with pytest.raises(InstalledProvenanceError, match="VCS mismatch"):
        verify_installed_basicts_provenance()


def test_rejects_malformed_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install(monkeypatch, tmp_path, "{")

    with pytest.raises(InstalledProvenanceError, match="malformed"):
        verify_installed_basicts_provenance()


def test_rejects_editable_or_local_install(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install(monkeypatch, tmp_path, _payload(dir_info={"editable": True}))

    with pytest.raises(InstalledProvenanceError, match="non-editable VCS install"):
        verify_installed_basicts_provenance()


def test_rejects_requested_revision_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    payload = json.loads(_payload())
    payload["vcs_info"]["requested_revision"] = "main"
    _install(monkeypatch, tmp_path, json.dumps(payload))

    with pytest.raises(InstalledProvenanceError, match="requested_revision mismatch"):
        verify_installed_basicts_provenance()


def test_rejects_distribution_version_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install(monkeypatch, tmp_path, _payload(), version="1.0.0")

    with pytest.raises(InstalledProvenanceError, match="version mismatch"):
        verify_installed_basicts_provenance()


def test_rejects_missing_distribution_file_manifest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install(monkeypatch, tmp_path, _payload(), include_files=False)

    with pytest.raises(InstalledProvenanceError, match="file manifest is missing"):
        verify_installed_basicts_provenance()


def test_rejects_shadowed_import_origin(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    shadow = tmp_path / "shadow" / "basicts" / "__init__.py"
    shadow.parent.mkdir(parents=True)
    shadow.write_text("shadow = True\n", encoding="utf-8")
    _install(monkeypatch, tmp_path, _payload(), origin=shadow)

    with pytest.raises(InstalledProvenanceError, match="import origin is shadowed"):
        verify_installed_basicts_provenance()


def test_rejects_ambiguous_import_provider_mapping(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install(
        monkeypatch,
        tmp_path,
        _payload(),
        providers=["BasicTS", "shadow-package"],
    )

    with pytest.raises(InstalledProvenanceError, match="missing or ambiguous"):
        verify_installed_basicts_provenance()


def test_rejects_preloaded_shadow_module(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install(monkeypatch, tmp_path, _payload())
    shadow = tmp_path / "preloaded" / "basicts" / "__init__.py"
    shadow.parent.mkdir(parents=True)
    shadow.write_text("shadow = True\n", encoding="utf-8")
    module = types.ModuleType("basicts")
    module.__file__ = str(shadow)
    monkeypatch.setitem(sys.modules, "basicts", module)

    with pytest.raises(InstalledProvenanceError, match="loaded BasicTS module is shadowed"):
        verify_installed_basicts_provenance()


def test_rejects_package_init_record_hash_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package_init, _, _ = _install(monkeypatch, tmp_path, _payload())
    package_init.write_text("tampered = True\n", encoding="utf-8")

    with pytest.raises(InstalledProvenanceError, match="package_init RECORD SHA-256 mismatch"):
        verify_installed_basicts_provenance()


def test_rejects_direct_url_record_hash_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _, direct_url_path, distribution = _install(monkeypatch, tmp_path, _payload())
    changed = _payload(extra="tampered")
    direct_url_path.write_text(changed, encoding="utf-8")
    distribution.direct_url = changed

    with pytest.raises(InstalledProvenanceError, match="direct_url RECORD SHA-256 mismatch"):
        verify_installed_basicts_provenance()


def test_rejects_missing_record_hash(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def mutate(entries, package_init, direct_url_path):
        first = entries[0]
        entries[0] = FakePackagePath(first.path, None, first.size)
        return entries

    _install(monkeypatch, tmp_path, _payload(), mutate_entries=mutate)

    with pytest.raises(InstalledProvenanceError, match="RECORD SHA-256 is missing"):
        verify_installed_basicts_provenance()


def test_rejects_record_size_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def mutate(entries, package_init, direct_url_path):
        first = entries[0]
        entries[0] = FakePackagePath(first.path, first.hash, first.size + 1)
        return entries

    _install(monkeypatch, tmp_path, _payload(), mutate_entries=mutate)

    with pytest.raises(InstalledProvenanceError, match="RECORD size mismatch"):
        verify_installed_basicts_provenance()


def test_rejects_missing_direct_url_record_entry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def mutate(entries, package_init, direct_url_path):
        return [entry for entry in entries if not entry.path.endswith("direct_url.json")]

    _install(monkeypatch, tmp_path, _payload(), mutate_entries=mutate)

    with pytest.raises(InstalledProvenanceError, match="RECORD entry mismatch"):
        verify_installed_basicts_provenance()
