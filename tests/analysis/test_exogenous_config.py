from __future__ import annotations

import re
from pathlib import Path

import yaml


def test_exogenous_config_has_forbidden_target_columns():
    path = Path(__file__).parents[2] / "configs/accuracy_contribution/exogenous_groups.yaml"
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert config["schema_version"] == 3

    candidate = config["datasets"]["candidate"]
    assert "selected" in candidate["target_columns"]
    assert "selected" in candidate["always_excluded"]

    draw = config["datasets"]["draw"]
    forbidden = set(draw["forbidden_current_draw_columns"])
    assert {f"n{i}" for i in range(1, 8)} <= forbidden
    assert "num_sum" in forbidden

    patterns = [re.compile(pattern) for pattern in draw["forbidden_current_draw_patterns"]]
    assert any(pattern.fullmatch("hit_01") for pattern in patterns)
