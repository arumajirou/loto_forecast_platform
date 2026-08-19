"""Frozen canonical input snapshot shared by TAJ-21 baseline and full OOF evidence."""

from __future__ import annotations

from typing import Final

BASELINE_REFERENCE_GIT_COMMIT: Final = "6654a29d747d029af343b2a0ff05fd207db0b7a8"
BASELINE_REFERENCE_SHA256SUMS: Final = (
    "c11343b1d11c6cc0359ea0d6b7299a608e12f8018b9c82dfe1ca1ed907a4eda3"
)

FROZEN_SIX_GAME_SNAPSHOT: Final[dict[str, dict[str, object]]] = {
    "bingo5": {
        "rows": 480,
        "sha256": "f2a4292f6ec9cb96892a10f260bf8028f118148e2786ebd8324629b0823ce05d",
        "encoding": "cp932",
        "separator": ",",
    },
    "loto6": {
        "rows": 2123,
        "sha256": "0fcdeec71dddcace32bb2753e9ac5d31249f2a370b148710ee8e6272e9d3394b",
        "encoding": "cp932",
        "separator": ",",
    },
    "loto7": {
        "rows": 687,
        "sha256": "0add2bd72db958728eaef660772b3c390ba7e23cb02014fc00f620748aa8208b",
        "encoding": "cp932",
        "separator": ",",
    },
    "mini": {
        "rows": 1397,
        "sha256": "040fc2d380036597dbf9ffa266bf29ad14fa03aa8861c39524f5787d154225dc",
        "encoding": "cp932",
        "separator": ",",
    },
    "numbers3": {
        "rows": 7036,
        "sha256": "d7e084ec510e529e09928aa3dfa267d8157878a1f6d772d2f8a374342df4becd",
        "encoding": "cp932",
        "separator": ",",
    },
    "numbers4": {
        "rows": 7036,
        "sha256": "e362d40ba2d3c6d39d77713722b7184e93ebadcd2e67563a9c18e1c020915d44",
        "encoding": "cp932",
        "separator": ",",
    },
}


def validate_snapshot_item(
    game: str,
    *,
    rows: int,
    sha256: str,
    encoding: str,
    separator: str,
) -> None:
    """Fail closed if an input differs from the formally frozen baseline snapshot."""

    expected = FROZEN_SIX_GAME_SNAPSHOT.get(game)
    if expected is None:
        raise ValueError(f"game is not in TAJ-21 frozen snapshot: {game}")
    observed = {
        "rows": rows,
        "sha256": sha256,
        "encoding": encoding,
        "separator": separator,
    }
    if observed != expected:
        raise ValueError(
            f"{game}: input differs from TAJ-21 frozen baseline snapshot; "
            f"expected={expected} observed={observed}"
        )
