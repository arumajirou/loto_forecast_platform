from __future__ import annotations

import json
import tomllib
from importlib import metadata
from pathlib import Path

from fastapi.testclient import TestClient

import loto
import loto.entrypoints as entrypoints_module
from loto.api.app import create_app
from loto.entrypoints import (
    auto_campaign_main,
    integrity_main,
    kpi_lab_main,
    loto3_main,
    loto_main,
)
from loto.verify.integrity import generate_manifest
from loto.version import (
    BUILD_INFO_SCHEMA_VERSION,
    VERSION_SOURCE,
    __version__,
    collect_build_info,
    installed_distribution_status,
    write_build_info,
)

ROOT = Path(__file__).resolve().parents[1]


def _missing_distribution(_name: str) -> str:
    raise metadata.PackageNotFoundError


def test_package_metadata_uses_the_canonical_version_source() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert "version" not in project["project"]
    assert "version" in project["project"]["dynamic"]
    assert project["tool"]["setuptools"]["dynamic"]["version"] == {
        "attr": "loto.version.__version__"
    }
    assert loto.__version__ == __version__


def test_console_scripts_expose_the_same_version(capsys) -> None:
    entrypoints = (
        (loto_main, "loto"),
        (loto3_main, "loto3"),
        (auto_campaign_main, "loto-auto-campaign"),
        (kpi_lab_main, "loto-lab"),
        (integrity_main, "loto-integrity"),
    )
    for entrypoint, program in entrypoints:
        assert entrypoint(["--version"]) == 0
        assert capsys.readouterr().out.strip() == f"{program} {__version__}"


def test_loto3_integrity_generate_injects_the_canonical_release(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_delegate(program: str, module_name: str, argv) -> int:
        captured.update(program=program, module_name=module_name, argv=list(argv))
        return 0

    monkeypatch.setattr(entrypoints_module, "_delegate", fake_delegate)

    assert loto3_main(["integrity", "generate", "--root", "."]) == 0
    assert captured == {
        "program": "loto3",
        "module_name": "loto.cli_v3",
        "argv": ["integrity", "generate", "--root", ".", "--release", __version__],
    }


def test_fastapi_and_dashboard_use_the_canonical_version(tmp_path) -> None:
    app = create_app(tmp_path)
    client = TestClient(app)

    assert app.version == __version__
    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert f"Loto Forecast Platform v{__version__}" in dashboard.text
    assert "v2.1</small>" not in dashboard.text


def test_source_checkout_without_installed_metadata_is_fail_safe(tmp_path) -> None:
    info = collect_build_info(
        repo_root=tmp_path,
        build_time=None,
        distribution_getter=_missing_distribution,
        generated_at="2026-08-06T04:30:00+00:00",
    )

    assert info.schema_version == BUILD_INFO_SCHEMA_VERSION
    assert info.package_version == __version__
    assert info.version_source == VERSION_SOURCE
    assert info.installed_distribution_version is None
    assert info.installed_distribution_status == "SOURCE_ONLY"
    assert info.git_commit == "UNAVAILABLE"
    assert info.git_dirty is None
    assert info.build_time is None
    assert info.generated_at == "2026-08-06T04:30:00+00:00"


def test_installed_distribution_mismatch_is_explicit() -> None:
    assert installed_distribution_status(__version__) == "MATCH"
    assert installed_distribution_status("0.0.0") == "MISMATCH"
    assert installed_distribution_status(None) == "SOURCE_ONLY"


def test_build_info_is_atomic_and_separates_build_from_generation_time(tmp_path) -> None:
    output = tmp_path / "BUILD_INFO.json"
    info = write_build_info(
        output,
        repo_root=tmp_path,
        build_time="2026-08-06T13:30:00+09:00",
        distribution_getter=lambda _name: __version__,
    )
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload == info.to_dict()
    assert payload["installed_distribution_status"] == "MATCH"
    assert payload["build_time"] == "2026-08-06T04:30:00+00:00"
    assert payload["generated_at"] != payload["build_time"]
    assert not (tmp_path / ".BUILD_INFO.json.tmp").exists()


def test_integrity_release_defaults_to_the_canonical_version(tmp_path) -> None:
    payload = generate_manifest(tmp_path, write=False)

    assert payload["release"] == __version__


def test_readme_does_not_encode_the_current_version_in_its_title() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert readme.splitlines()[0] == "# Loto Forecast Platform"
    assert "現在のpackage versionはREADMEへ手書きしません" in readme
