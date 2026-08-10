from __future__ import annotations

import subprocess
import sys


def test_decoder_import_does_not_require_yaml() -> None:
    script = r'''
import builtins

original_import = builtins.__import__


def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name == "yaml" or name.startswith("yaml."):
        raise ModuleNotFoundError("yaml intentionally blocked by regression test")
    return original_import(name, globals, locals, fromlist, level)


builtins.__import__ = guarded_import

from loto.probabilistic.decoder import DecodeObjective

assert DecodeObjective.WITHIN_TAU.value == "within_tau"
'''
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_public_catalog_export_remains_lazy_and_available() -> None:
    import loto.probabilistic as probabilistic

    assert "catalog_counts" not in probabilistic.__dict__
    assert callable(probabilistic.catalog_counts)
    assert "catalog_counts" in probabilistic.__dict__
