from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from loto.game.geometry import known_games
from loto.models.catalog_full import build_catalog


def _load_runner_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_resource_aware_broad_campaign.py"
    spec = importlib.util.spec_from_file_location("resource_aware_broad_campaign", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_broad_matrix_expands_model_identities_into_model_game_pairs() -> None:
    module = _load_runner_module()
    catalog = build_catalog()
    games = list(known_games())

    tasks = module._build_tasks(catalog, games)

    assert catalog
    assert len({entry.model_id for entry in catalog}) == len(catalog)
    assert len(games) > 1
    assert len(tasks) == len(catalog) * len(games)
    assert len(tasks) > len(catalog)
    assert len({task.key for task in tasks}) == len(tasks)


def test_timellm_tasks_use_exclusive_gpu_lane() -> None:
    module = _load_runner_module()
    timellm = next(entry for entry in build_catalog() if entry.model_id == "nf-timellm")

    tasks = module._build_tasks([timellm], ["numbers4"])

    assert len(tasks) == 1
    assert tasks[0].resource_class == "EXCLUSIVE_GPU"
