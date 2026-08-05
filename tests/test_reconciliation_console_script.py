from __future__ import annotations

import importlib
import tomllib
from pathlib import Path

from loto.reconciliation import portable_package_certification as pc


def test_hierarchicalforecast_certification_console_script_is_registered() -> None:
    project_root = Path(__file__).resolve().parents[1]
    payload = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))

    target = payload["project"]["scripts"]["loto-hierarchicalforecast-certify"]

    assert target == "loto.reconciliation.portable_package_certification:main"


def test_hierarchicalforecast_certification_console_target_resolves() -> None:
    module_name, attribute = (
        "loto.reconciliation.portable_package_certification:main".split(":", maxsplit=1)
    )
    callable_object = getattr(importlib.import_module(module_name), attribute)

    assert callable_object is pc.main
