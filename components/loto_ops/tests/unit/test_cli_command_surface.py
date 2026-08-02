"""Regression tests for the merged legacy and operations CLI surface."""

from __future__ import annotations

import argparse
import inspect

from loto_ops.artifacts.packager import ArtifactPackager
from loto_ops.cli import build_parser


def _commands(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)
    raise AssertionError("CLI parser has no subcommand action")


def test_merged_cli_contains_legacy_and_operations_commands() -> None:
    commands = _commands(build_parser())
    required = {
        "run",
        "export-handover",
        "import-handover",
        "preflight",
        "run-all",
        "run-all-fast",
        "webapp",
        "package",
    }
    assert required <= commands.keys()


def test_artifact_packager_api_matches_restored_cli() -> None:
    signature = inspect.signature(ArtifactPackager.create_zip)
    assert signature.parameters["run_id"].default is None
    assert "mode" in signature.parameters
