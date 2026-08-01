from __future__ import annotations

import hashlib
import sys
import types
from pathlib import Path

lineage = types.ModuleType("loto.data.lineage")
lineage.sha256_file = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
data = types.ModuleType("loto.data")
data.lineage = lineage
sys.modules.setdefault("loto.data", data)
sys.modules.setdefault("loto.data.lineage", lineage)

from loto.models.catalog import ModelSpec  # noqa: E402
from loto.models.property_inspector import inspect_model_properties  # noqa: E402


class DemoModel:
    def __init__(self) -> None:
        self.custom_switch = "actual"

    def get_params(self, deep: bool = False):  # noqa: ARG002
        return {"n_estimators": 2, "custom_switch": self.custom_switch}


def test_inspector_exports_effective_parameter_map() -> None:
    spec = ModelSpec("demo", "tree", "builtin", "candidate", "DemoModel")
    result = inspect_model_properties(
        spec,
        DemoModel(),
        params={"n_estimators": 2, "custom_switch": "requested"},
    )
    assert result["effective_parameters"]["n_estimators"] == 2
    assert result["effective_parameters"]["custom_switch"] == "actual"
