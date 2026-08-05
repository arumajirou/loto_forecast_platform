from __future__ import annotations

import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _project(lane: str) -> dict[str, object]:
    path = ROOT / "environments" / f"gluonts-{lane}" / "pyproject.toml"
    return tomllib.loads(path.read_text(encoding="utf-8"))["project"]


def test_compatibility_lane_is_pinned_to_root_torch_contract() -> None:
    project = _project("compat")
    dependencies = set(project["dependencies"])
    assert "gluonts[torch]==0.16.3" in dependencies
    assert "torch==2.9.1" in dependencies
    assert "lightning>=2.2.2,<2.5" in dependencies


def test_latest_lane_is_isolated_from_root_torch_contract() -> None:
    project = _project("latest")
    dependencies = set(project["dependencies"])
    assert "gluonts[torch]==0.17.0" in dependencies
    assert "torch>=2.10,<3" in dependencies
    assert "lightning>=2.2.2,<2.7" in dependencies


def test_lanes_use_distinct_distribution_names() -> None:
    compat = _project("compat")
    latest = _project("latest")
    assert compat["name"] != latest["name"]
