from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "github_projects" / "governance.py"
SPEC_PATH = ROOT / "configs" / "github_projects" / "governance_v1.yaml"


def _load_module():
    spec = importlib.util.spec_from_file_location("github_projects_governance", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_governance_spec_is_strict_and_complete() -> None:
    module = _load_module()
    governance = module.load_spec(SPEC_PATH)
    assert governance.project.authority == "governance_only"
    assert governance.project.visibility == "PRIVATE"
    assert len(governance.fields) == 11
    assert len(governance.views) == 7
    assert len(governance.workflows) == 4


def test_owner_plan_uses_project_scope_and_no_mutating_action_workflow() -> None:
    module = _load_module()
    governance = module.load_spec(SPEC_PATH)
    plan = module.owner_plan(governance)
    commands = "\n".join(plan["commands"])
    assert "gh auth refresh -s project" in commands
    assert "gh project create" in commands
    assert "gh project link" in commands
    assert "gh project field-create" in commands
    assert "gh workflow" not in commands
    assert plan["status"] == "OWNER_UI_OR_API_ACTION_REQUIRED"


def test_status_and_evidence_states_remain_distinct() -> None:
    module = _load_module()
    governance = module.load_spec(SPEC_PATH)
    fields = {field.name: field for field in governance.fields}
    assert "Failed" in fields["Status"].options
    assert "Blocked" in fields["Status"].options
    assert "FAILED" in fields["Evidence Status"].options
    assert "PARTIALLY_VERIFIED" in fields["Evidence Status"].options
    assert "VERIFIED" in fields["Evidence Status"].options


def test_unknown_or_incomplete_spec_fails_closed(tmp_path: Path) -> None:
    module = _load_module()
    raw = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))
    raw["unexpected"] = True
    raw["fields"] = [field for field in raw["fields"] if field["name"] != "Risk"]
    bad_spec = tmp_path / "bad.yaml"
    bad_spec.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    with pytest.raises(ValidationError):
        module.load_spec(bad_spec)


def test_rendered_plan_is_deterministic_and_contains_no_secret_material() -> None:
    module = _load_module()
    governance = module.load_spec(SPEC_PATH)
    plan = module.owner_plan(governance)
    first = json.dumps(plan, sort_keys=True)
    second = json.dumps(module.owner_plan(governance), sort_keys=True)
    assert first == second
    lowered = first.lower()
    assert "token" not in lowered
    assert "password" not in lowered
    assert "secret" not in lowered
    assert "callback" not in lowered
