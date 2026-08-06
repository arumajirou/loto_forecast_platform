"""Console-script delegates with a shared lightweight version path."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable, Sequence
from typing import Any

from loto.version import __version__


def _arguments(argv: Sequence[str] | None) -> list[str]:
    return list(sys.argv[1:] if argv is None else argv)


def _delegate(
    program: str,
    module_name: str,
    argv: Sequence[str] | None,
) -> int:
    arguments = _arguments(argv)
    if "--version" in arguments or "-V" in arguments:
        print(f"{program} {__version__}")
        return 0
    module = importlib.import_module(module_name)
    target: Callable[[list[str] | None], Any] = getattr(module, "main")
    result = target(arguments)
    return int(result or 0)


def loto_main(argv: Sequence[str] | None = None) -> int:
    return _delegate("loto", "loto.cli", argv)


def loto3_main(argv: Sequence[str] | None = None) -> int:
    return _delegate("loto3", "loto.cli_v3", argv)


def auto_campaign_main(argv: Sequence[str] | None = None) -> int:
    return _delegate("loto-auto-campaign", "loto.auto_campaign.cli", argv)


def kpi_lab_main(argv: Sequence[str] | None = None) -> int:
    return _delegate("loto-lab", "loto.kpi_lab.cli", argv)


def integrity_main(argv: Sequence[str] | None = None) -> int:
    return _delegate("loto-integrity", "loto.verify.integrity", argv)
