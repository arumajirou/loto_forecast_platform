from __future__ import annotations

from loto.game.geometry import known_games
from loto.models.catalog_full import build_catalog
from loto.probabilistic.catalog import (
    build_unified_catalog_rows,
    list_probabilistic_model_specs,
)
from loto.probabilistic.native_registry import list_native_implementations


def test_unified_identity_inventory_is_collision_free_and_larger_than_broad_catalog() -> None:
    broad = build_catalog()
    probabilistic = list_probabilistic_model_specs()
    unified = build_unified_catalog_rows()

    broad_ids = {entry.model_id for entry in broad}
    probabilistic_ids = {entry.model_id for entry in probabilistic}
    unified_ids = {str(row["model_id"]) for row in unified}

    assert len(broad_ids) == len(broad)
    assert len(probabilistic_ids) == len(probabilistic)
    assert broad_ids.isdisjoint(probabilistic_ids)
    assert unified_ids == broad_ids | probabilistic_ids
    assert len(unified) == len(broad) + len(probabilistic)
    assert len(unified) > len(broad)


def test_probabilistic_native_registry_covers_probabilistic_identity_catalog() -> None:
    probabilistic_ids = {entry.model_id for entry in list_probabilistic_model_specs()}
    native_ids = {entry.model_id for entry in list_native_implementations()}

    assert native_ids == probabilistic_ids


def test_unified_model_game_cross_product_exceeds_identity_count() -> None:
    unified_count = len(build_unified_catalog_rows())
    game_count = len(known_games())

    assert game_count > 1
    assert unified_count * game_count > unified_count
