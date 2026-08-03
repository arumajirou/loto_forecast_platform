from __future__ import annotations

import json

from loto.cli_v3 import main


def test_cli_catalog_and_plan(capsys) -> None:
    assert main(["probabilistic", "catalog-list"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["counts"]["probabilistic_models"] == 72
    assert len(payload["models"]) == 72

    assert main(["probabilistic", "plan", "--config", "configs/probabilistic/smoke.yaml"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["trials_allowed"] == 72


def test_cli_native_coverage(capsys) -> None:
    assert main(["probabilistic", "native-coverage"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["coverage"]["models"] == 72
    assert payload["coverage"]["all_primary_paths_declared"] is True
    assert len(payload["implementations"]) == 72
