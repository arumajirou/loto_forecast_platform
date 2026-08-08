from pathlib import Path

import pytest
import yaml

from loto.harness.config import ContextSettings, HarnessSettings
from loto.harness.errors import ConfigurationError


def test_default_context_budget_is_exact() -> None:
    ContextSettings().validate_budget()


def test_bad_context_budget_is_rejected() -> None:
    settings = ContextSettings(exact_source_tokens=1)
    with pytest.raises(ConfigurationError):
        settings.validate_budget()


def test_gateway_config_loads() -> None:
    root = Path(__file__).parents[2]
    config_path = root / "configs/harness/gateway.yaml"
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    settings = HarnessSettings.from_yaml(config_path)
    assert settings.host == raw["host"]
    assert settings.port == raw["port"]
    assert settings.host == "127.0.0.1"
    assert 1 <= settings.port <= 65535
    assert settings.models
    assert settings.security.allowed_roots == [str(root.resolve())]


def test_relative_allowed_roots_resolve_from_config_directory(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    config_dir = tmp_path / "config"
    repo_root.mkdir()
    config_dir.mkdir()
    config_path = config_dir / "gateway.yaml"
    config_path.write_text(
        "security:\n  allowed_roots:\n  - ../repo\n",
        encoding="utf-8",
    )

    settings = HarnessSettings.from_yaml(config_path)

    assert settings.security.allowed_roots == [str(repo_root.resolve())]
