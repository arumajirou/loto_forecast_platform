from __future__ import annotations

import base64
import hashlib
import importlib.util
import sys
import types
from dataclasses import dataclass
from pathlib import Path

import pytest

from loto.basicts_campaign import basicts_module_closure as provenance
from loto.basicts_campaign.basicts_module_closure import (
    CONFIGS_PACKAGE,
    DECOMPOSITION_MODULE,
    MODEL_CONFIG_MODULE,
    verify_dlinear_import_closure,
)
from loto.basicts_campaign.dlinear_runtime_provenance import (
    DLINEAR_ARCH_MODULE,
    DLINEAR_CONFIG_MODULE,
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
    entries: list[FakeEntry]

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


MODULE_PATHS = {
    "basicts": "basicts/__init__.py",
    "basicts.launcher": "basicts/launcher.py",
    "basicts.models": "basicts/models/__init__.py",
    "basicts.models.DLinear": "basicts/models/DLinear/__init__.py",
    "basicts.models.DLinear.arch": "basicts/models/DLinear/arch/__init__.py",
    DLINEAR_ARCH_MODULE: "basicts/models/DLinear/arch/dlinear_arch.py",
    "basicts.models.DLinear.config": "basicts/models/DLinear/config/__init__.py",
    DLINEAR_CONFIG_MODULE: "basicts/models/DLinear/config/dlinear_config.py",
    "basicts.modules": "basicts/modules/__init__.py",
    DECOMPOSITION_MODULE: "basicts/modules/decomposition.py",
    CONFIGS_PACKAGE: "basicts/configs/__init__.py",
    MODEL_CONFIG_MODULE: "basicts/configs/model_config.py",
}


def _install(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    remove_entry: str | None = None,
    shadow_spec: str | None = None,
    bad_decomposition_binding: bool = False,
):
    root = tmp_path / "site-packages"
    paths: dict[str, Path] = {}
    for module_name, relative in MODULE_PATHS.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {module_name}\n", encoding="utf-8")
        paths[module_name] = path

    entries = [_entry(path, root) for path in paths.values()]
    if remove_entry is not None:
        entries = [entry for entry in entries if entry.path != remove_entry]
    distribution = FakeDistribution(root, entries)
    monkeypatch.setattr(
        provenance.importlib.metadata,
        "distribution",
        lambda name: distribution,
    )

    basic_config = type("BasicTSModelConfig", (), {"__module__": MODEL_CONFIG_MODULE})
    dlinear_config = type(
        "DLinearConfig",
        (basic_config,),
        {"__module__": DLINEAR_CONFIG_MODULE},
    )
    moving_average = type("MovingAverageDecomposition", (), {"__module__": DECOMPOSITION_MODULE})
    dlinear = type("DLinear", (), {"__module__": DLINEAR_ARCH_MODULE})

    modules: dict[str, types.ModuleType] = {}
    for module_name, path in paths.items():
        module = types.ModuleType(module_name)
        module.__file__ = str(path)
        modules[module_name] = module
    modules[MODEL_CONFIG_MODULE].BasicTSModelConfig = basic_config
    modules[CONFIGS_PACKAGE].BasicTSModelConfig = basic_config
    modules[DLINEAR_CONFIG_MODULE].BasicTSModelConfig = basic_config
    modules[DLINEAR_CONFIG_MODULE].DLinearConfig = dlinear_config
    modules[DECOMPOSITION_MODULE].MovingAverageDecomposition = moving_average
    modules[DLINEAR_ARCH_MODULE].DLinear = dlinear
    modules[DLINEAR_ARCH_MODULE].MovingAverageDecomposition = (
        type("Shadow", (), {"__module__": "shadow"})
        if bad_decomposition_binding
        else moving_average
    )

    specs = {}
    for module_name, path in paths.items():
        origin = path
        if module_name == shadow_spec:
            origin = tmp_path / "shadow" / path.name
            origin.parent.mkdir(parents=True, exist_ok=True)
            origin.write_text("# shadow\n", encoding="utf-8")
        if path.name == "__init__.py":
            spec = importlib.util.spec_from_file_location(
                module_name,
                origin,
                submodule_search_locations=[str(origin.parent)],
            )
        else:
            spec = importlib.util.spec_from_file_location(module_name, origin)
        specs[module_name] = spec
    monkeypatch.setattr(
        provenance.importlib.util,
        "find_spec",
        lambda name: specs[name],
    )

    def import_module(name: str):
        for module_name, module in modules.items():
            monkeypatch.setitem(sys.modules, module_name, module)
        return modules[name]

    monkeypatch.setattr(
        provenance,
        "verify_dlinear_runtime_modules",
        lambda: _critical_evidence(import_module),
    )
    for name in MODULE_PATHS:
        monkeypatch.delitem(sys.modules, name, raising=False)
    return paths


def _critical_evidence(import_module) -> dict[str, object]:
    items = []
    for label, module_name, entry, symbol in (
        (
            "dlinear_arch",
            DLINEAR_ARCH_MODULE,
            "basicts/models/DLinear/arch/dlinear_arch.py",
            "DLinear",
        ),
        (
            "dlinear_config",
            DLINEAR_CONFIG_MODULE,
            "basicts/models/DLinear/config/dlinear_config.py",
            "DLinearConfig",
        ),
    ):
        module = import_module(module_name)
        item = getattr(module, symbol)
        items.append(
            {
                "label": label,
                "module_name": module_name,
                "required_symbol": symbol,
                "symbol_module": item.__module__,
                "distribution_entry": entry,
                "distribution_path": module.__file__,
                "import_spec_origin": module.__file__,
                "loaded_module_file": module.__file__,
                "record_status": "PASS",
                "record_hash_mode": "sha256",
                "record_hash_value": "C" * 43,
                "record_size_bytes": 1,
                "module_file_sha256": "d" * 64,
                "module_already_loaded": False,
            }
        )
    return {
        "dlinear_module_provenance_status": "PASS",
        "dlinear_runtime_modules": items,
    }


def test_accepts_complete_loaded_basicts_closure(monkeypatch, tmp_path) -> None:
    _install(monkeypatch, tmp_path)

    evidence = verify_dlinear_import_closure()

    assert evidence["dlinear_module_provenance_status"] == "PASS"
    assert evidence["basicts_module_closure_status"] == "PASS"
    assert evidence["dlinear_dependency_binding_status"] == "PASS"
    assert evidence["preloaded_basicts_modules"] == []
    assert evidence["loaded_basicts_module_count"] == len(MODULE_PATHS)
    assert {item["module_name"] for item in evidence["loaded_basicts_modules"]} == set(MODULE_PATHS)
    assert all(item["record_status"] == "PASS" for item in evidence["loaded_basicts_modules"])


def test_rejects_any_preloaded_basicts_module(monkeypatch, tmp_path) -> None:
    _install(monkeypatch, tmp_path)
    module = types.ModuleType("basicts")
    module.__file__ = str(tmp_path / "preloaded.py")
    monkeypatch.setitem(sys.modules, "basicts", module)

    with pytest.raises(InstalledProvenanceError, match="already loaded"):
        verify_dlinear_import_closure()


def test_rejects_transitive_module_missing_from_record(monkeypatch, tmp_path) -> None:
    _install(monkeypatch, tmp_path, remove_entry="basicts/launcher.py")

    with pytest.raises(InstalledProvenanceError, match="distribution entry mismatch"):
        verify_dlinear_import_closure()


def test_rejects_shadowed_transitive_spec(monkeypatch, tmp_path) -> None:
    _install(monkeypatch, tmp_path, shadow_spec=DECOMPOSITION_MODULE)

    with pytest.raises(InstalledProvenanceError, match="escaped the distribution root"):
        verify_dlinear_import_closure()


def test_rejects_dependency_object_mismatch(monkeypatch, tmp_path) -> None:
    _install(monkeypatch, tmp_path, bad_decomposition_binding=True)

    with pytest.raises(InstalledProvenanceError, match="decomposition dependency"):
        verify_dlinear_import_closure()


def test_rejects_transitive_record_hash_drift(monkeypatch, tmp_path) -> None:
    paths = _install(monkeypatch, tmp_path)
    paths["basicts.launcher"].write_text("tampered = True\n", encoding="utf-8")

    with pytest.raises(InstalledProvenanceError, match="RECORD SHA-256 mismatch"):
        verify_dlinear_import_closure()


def test_rejects_config_base_identity_drift(monkeypatch, tmp_path) -> None:
    _install(monkeypatch, tmp_path)
    original = provenance.verify_dlinear_runtime_modules

    def verify_critical():
        evidence = original()
        config = sys.modules[DLINEAR_CONFIG_MODULE]
        config.BasicTSModelConfig = type("OtherConfig", (), {"__module__": "shadow.config"})
        return evidence

    monkeypatch.setattr(provenance, "verify_dlinear_runtime_modules", verify_critical)

    with pytest.raises(InstalledProvenanceError, match="base dependency"):
        verify_dlinear_import_closure()
