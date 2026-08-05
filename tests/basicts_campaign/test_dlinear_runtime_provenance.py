from __future__ import annotations

import base64
import hashlib
import importlib.util
import sys
import types
from dataclasses import dataclass
from pathlib import Path

import pytest

from loto.basicts_campaign import dlinear_runtime_provenance as provenance
from loto.basicts_campaign.dlinear_runtime_provenance import (
    DLINEAR_ARCH_MODULE,
    DLINEAR_CONFIG_MODULE,
    verify_dlinear_runtime_modules,
)
from loto.basicts_campaign.installed_provenance import InstalledProvenanceError


@dataclass(frozen=True)
class FakeHash:
    mode: str
    value: str


@dataclass(frozen=True)
class FakeEntry:
    path: str
    hash: FakeHash | None
    size: int | None

    def __str__(self) -> str:
        return self.path


@dataclass
class FakeDistribution:
    root: Path
    entries: list[FakeEntry] | None

    @property
    def files(self):
        return self.entries

    def locate_file(self, entry: FakeEntry) -> Path:
        return self.root / entry.path


def _hash(path: Path) -> FakeHash:
    digest = hashlib.sha256(path.read_bytes()).digest()
    value = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return FakeHash("sha256", value)


def _entry(path: Path, root: Path) -> FakeEntry:
    return FakeEntry(path.relative_to(root).as_posix(), _hash(path), path.stat().st_size)


def _class(name: str, module_name: str):
    return type(name, (), {"__module__": module_name})


def _install(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    mutate_entries=None,
    arch_origin: Path | None = None,
    config_origin: Path | None = None,
    arch_symbol_module: str = DLINEAR_ARCH_MODULE,
) -> tuple[Path, Path, FakeDistribution]:
    root = tmp_path / "site-packages"
    arch = root / "basicts/models/DLinear/arch/dlinear_arch.py"
    config = root / "basicts/models/DLinear/config/dlinear_config.py"
    arch.parent.mkdir(parents=True)
    config.parent.mkdir(parents=True)
    arch.write_text("class DLinear: pass\n", encoding="utf-8")
    config.write_text("class DLinearConfig: pass\n", encoding="utf-8")
    entries = [_entry(arch, root), _entry(config, root)]
    if mutate_entries:
        entries = mutate_entries(entries, arch, config)
    distribution = FakeDistribution(root, entries)
    monkeypatch.setattr(
        provenance.importlib.metadata,
        "distribution",
        lambda name: distribution,
    )

    origins = {
        DLINEAR_ARCH_MODULE: arch_origin or arch,
        DLINEAR_CONFIG_MODULE: config_origin or config,
    }
    specs = {
        name: importlib.util.spec_from_file_location(name, path)
        for name, path in origins.items()
    }
    monkeypatch.setattr(
        provenance.importlib.util,
        "find_spec",
        lambda name: specs[name],
    )

    modules = {}
    for module_name, path in origins.items():
        module = types.ModuleType(module_name)
        module.__file__ = str(path)
        if module_name == DLINEAR_ARCH_MODULE:
            module.DLinear = _class("DLinear", arch_symbol_module)
        else:
            module.DLinearConfig = _class("DLinearConfig", DLINEAR_CONFIG_MODULE)
        modules[module_name] = module
        monkeypatch.delitem(sys.modules, module_name, raising=False)

    def import_module(name: str):
        module = modules[name]
        sys.modules[name] = module
        return module

    monkeypatch.setattr(provenance.importlib, "import_module", import_module)
    return arch, config, distribution


def test_accepts_exact_dlinear_module_provenance(monkeypatch, tmp_path) -> None:
    arch, config, _ = _install(monkeypatch, tmp_path)

    evidence = verify_dlinear_runtime_modules()

    assert evidence["dlinear_module_provenance_status"] == "PASS"
    items = {item["label"]: item for item in evidence["dlinear_runtime_modules"]}
    assert items["dlinear_arch"]["distribution_path"] == str(arch.resolve())
    assert items["dlinear_config"]["distribution_path"] == str(config.resolve())
    assert all(item["record_status"] == "PASS" for item in items.values())


def test_rejects_missing_distribution_entry(monkeypatch, tmp_path) -> None:
    def mutate(entries, arch, config):
        return [entry for entry in entries if not entry.path.endswith("dlinear_arch.py")]

    _install(monkeypatch, tmp_path, mutate_entries=mutate)

    with pytest.raises(InstalledProvenanceError, match="distribution entry mismatch"):
        verify_dlinear_runtime_modules()


def test_rejects_record_hash_drift(monkeypatch, tmp_path) -> None:
    arch, _, _ = _install(monkeypatch, tmp_path)
    arch.write_text("tampered = True\n", encoding="utf-8")

    with pytest.raises(InstalledProvenanceError, match="RECORD SHA-256 mismatch"):
        verify_dlinear_runtime_modules()


def test_rejects_shadowed_import_spec(monkeypatch, tmp_path) -> None:
    shadow = tmp_path / "shadow/dlinear_arch.py"
    shadow.parent.mkdir()
    shadow.write_text("shadow = True\n", encoding="utf-8")
    _install(monkeypatch, tmp_path, arch_origin=shadow)

    with pytest.raises(InstalledProvenanceError, match="import origin is shadowed"):
        verify_dlinear_runtime_modules()


def test_rejects_preloaded_shadow_module(monkeypatch, tmp_path) -> None:
    _install(monkeypatch, tmp_path)
    shadow = tmp_path / "preloaded/dlinear_arch.py"
    shadow.parent.mkdir()
    shadow.write_text("shadow = True\n", encoding="utf-8")
    module = types.ModuleType(DLINEAR_ARCH_MODULE)
    module.__file__ = str(shadow)
    monkeypatch.setitem(sys.modules, DLINEAR_ARCH_MODULE, module)

    with pytest.raises(InstalledProvenanceError, match="preloaded module is shadowed"):
        verify_dlinear_runtime_modules()


def test_rejects_required_symbol_from_other_module(monkeypatch, tmp_path) -> None:
    _install(monkeypatch, tmp_path, arch_symbol_module="shadow.module")

    with pytest.raises(InstalledProvenanceError, match="defined by another module"):
        verify_dlinear_runtime_modules()


def test_rejects_symlinked_module_file(monkeypatch, tmp_path) -> None:
    arch, config, distribution = _install(monkeypatch, tmp_path)
    target = tmp_path / "target.py"
    target.write_text(arch.read_text(encoding="utf-8"), encoding="utf-8")
    arch.unlink()
    try:
        arch.symlink_to(target)
    except OSError:
        pytest.skip("symbolic links are unavailable")
    distribution.entries = [_entry(target, target.parent), _entry(config, distribution.root)]
    distribution.entries[0] = FakeEntry(
        "basicts/models/DLinear/arch/dlinear_arch.py",
        _hash(target),
        target.stat().st_size,
    )

    with pytest.raises(InstalledProvenanceError, match="symbolic link"):
        verify_dlinear_runtime_modules()
