"""Identity and CLI entry point for the GluonTS 0.16.3 compatibility provider."""

from __future__ import annotations

from typing import Sequence

LANE = "compat"
GLUONTS_VERSION = "0.16.3"
TORCH_CONSTRAINT = "==2.9.1"
PROVIDER_STATUS = "EXECUTION_PENDING"


def main(argv: Sequence[str] | None = None) -> int:
    """Load the CLI lazily so importing provider identity does not import GluonTS."""

    from .cli import main as cli_main

    return cli_main(argv)


__all__ = [
    "GLUONTS_VERSION",
    "LANE",
    "PROVIDER_STATUS",
    "TORCH_CONSTRAINT",
    "main",
]
