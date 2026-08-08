from __future__ import annotations

import importlib
import tomllib
from pathlib import Path

from loto.reconciliation import package_verifier
from loto.reconciliation import portable_package_certification as pc


def test_hierarchicalforecast_certification_console_script_is_registered() -> None:
    project_root = Path(__file__).resolve().parents[1]
    payload = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))

    scripts = payload["project"]["scripts"]

    assert (
        scripts["loto-hierarchicalforecast-certify"]
        == "loto.reconciliation.portable_package_certification:main"
    )
    assert (
        scripts["loto-hierarchicalforecast-verify-package"]
        == "loto.reconciliation.package_verifier:main"
    )


def test_hierarchicalforecast_certification_console_target_resolves() -> None:
    certification_module, certification_attribute = (
        "loto.reconciliation.portable_package_certification:main".split(":", maxsplit=1)
    )
    verifier_module, verifier_attribute = "loto.reconciliation.package_verifier:main".split(
        ":", maxsplit=1
    )

    certification_callable = getattr(
        importlib.import_module(certification_module),
        certification_attribute,
    )
    verifier_callable = getattr(
        importlib.import_module(verifier_module),
        verifier_attribute,
    )

    assert certification_callable is pc.main
    assert verifier_callable is package_verifier.main
