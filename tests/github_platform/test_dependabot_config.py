from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / ".github" / "dependabot.yml"
SENSITIVE_PYTHON_DEPENDENCIES = {
    "numpy",
    "pandas",
    "pydantic",
    "scikit-learn",
    "scipy",
    "neuralforecast",
    "torch",
    "triton",
    "transformers",
    "huggingface-hub",
    "pyarrow",
    "fastapi",
    "starlette",
    "httpx",
    "optuna-dashboard",
}


def _load_config() -> dict[str, object]:
    loaded = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _updates_by_ecosystem(config: dict[str, object]) -> dict[str, dict[str, object]]:
    updates = config.get("updates")
    assert isinstance(updates, list)
    result: dict[str, dict[str, object]] = {}
    for entry in updates:
        assert isinstance(entry, dict)
        ecosystem = entry.get("package-ecosystem")
        assert isinstance(ecosystem, str)
        assert ecosystem not in result
        result[ecosystem] = entry
    return result


def test_dependabot_config_has_only_approved_ecosystems() -> None:
    config = _load_config()
    assert config["version"] == 2
    assert set(_updates_by_ecosystem(config)) == {"uv", "github-actions"}


def test_dependabot_updates_are_weekly_and_bounded() -> None:
    updates = _updates_by_ecosystem(_load_config())
    expected_limits = {"uv": 3, "github-actions": 2}
    expected_times = {"uv": "09:00", "github-actions": "09:30"}

    for ecosystem, entry in updates.items():
        assert entry["directory"] == "/"
        assert entry["open-pull-requests-limit"] == expected_limits[ecosystem]
        schedule = entry["schedule"]
        assert isinstance(schedule, dict)
        assert schedule == {
            "interval": "weekly",
            "day": "monday",
            "time": expected_times[ecosystem],
            "timezone": "Asia/Tokyo",
        }


def test_compatibility_sensitive_dependencies_are_not_grouped() -> None:
    uv_entry = _updates_by_ecosystem(_load_config())["uv"]
    groups = uv_entry["groups"]
    assert isinstance(groups, dict)
    routine = groups["routine-python-minor-patch"]
    assert isinstance(routine, dict)
    assert routine["patterns"] == ["*"]
    assert set(routine["exclude-patterns"]) == SENSITIVE_PYTHON_DEPENDENCIES
    assert routine["update-types"] == ["minor", "patch"]


def test_action_updates_group_only_minor_and_patch_versions() -> None:
    actions_entry = _updates_by_ecosystem(_load_config())["github-actions"]
    groups = actions_entry["groups"]
    assert isinstance(groups, dict)
    routine = groups["routine-actions-minor-patch"]
    assert isinstance(routine, dict)
    assert routine == {"patterns": ["*"], "update-types": ["minor", "patch"]}


def test_configuration_has_no_auto_merge_or_private_registry_credentials() -> None:
    config = _load_config()
    raw = CONFIG_PATH.read_text(encoding="utf-8").lower()
    assert "auto-merge" not in raw
    assert "automerge" not in raw
    assert "registries" not in config
    assert "password" not in raw
    assert "token" not in raw
