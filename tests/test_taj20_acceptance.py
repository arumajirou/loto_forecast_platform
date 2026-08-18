from __future__ import annotations

import hashlib
from pathlib import Path

from tools.runtime_audit.taj20_acceptance import (
    EXPECTED_BROAD_PAIRS,
    EXPECTED_PROBABILISTIC_PAIRS,
    EXPECTED_UNIFIED_PAIRS,
    _rows_by_expected_matrix,
    _verify_sha256s,
)


def _rows(models: set[str], games: set[str]) -> list[dict[str, str]]:
    return [
        {
            "model_id": model_id,
            "game": game,
            "normalized_status": "RUNTIME_SMOKE_SUCCEEDED",
        }
        for model_id in sorted(models)
        for game in sorted(games)
    ]


def test_matrix_checker_accepts_exact_cross_products() -> None:
    games = {f"g{i}" for i in range(6)}
    broad = {f"b{i}" for i in range(174)}
    probabilistic = {f"p{i}" for i in range(76)}
    unified = broad | probabilistic
    assert _rows_by_expected_matrix(
        _rows(broad, games),
        model_ids=broad,
        games=games,
        expected_pairs=EXPECTED_BROAD_PAIRS,
        label="broad",
    )["pass"]
    assert _rows_by_expected_matrix(
        _rows(probabilistic, games),
        model_ids=probabilistic,
        games=games,
        expected_pairs=EXPECTED_PROBABILISTIC_PAIRS,
        label="probabilistic",
    )["pass"]
    assert _rows_by_expected_matrix(
        _rows(unified, games),
        model_ids=unified,
        games=games,
        expected_pairs=EXPECTED_UNIFIED_PAIRS,
        label="unified",
    )["pass"]


def test_matrix_checker_rejects_silent_skip() -> None:
    games = {f"g{i}" for i in range(6)}
    probabilistic = {f"p{i}" for i in range(76)}
    rows = _rows(probabilistic, games)
    rows.pop()
    result = _rows_by_expected_matrix(
        rows,
        model_ids=probabilistic,
        games=games,
        expected_pairs=EXPECTED_PROBABILISTIC_PAIRS,
        label="probabilistic",
    )
    assert result["pass"] is False
    assert len(result["missing_keys"]) == 1


def test_matrix_checker_rejects_duplicate() -> None:
    games = {f"g{i}" for i in range(6)}
    probabilistic = {f"p{i}" for i in range(76)}
    rows = _rows(probabilistic, games)
    rows.append(dict(rows[0]))
    result = _rows_by_expected_matrix(
        rows,
        model_ids=probabilistic,
        games=games,
        expected_pairs=EXPECTED_PROBABILISTIC_PAIRS,
        label="probabilistic",
    )
    assert result["pass"] is False
    assert result["duplicate_keys"]


def test_sha256_verifier_rejects_path_escape(
    tmp_path: Path,
) -> None:
    root = tmp_path / "evidence"
    root.mkdir()

    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")

    digest = hashlib.sha256(outside.read_bytes()).hexdigest()

    (root / "SHA256SUMS").write_text(
        f"{digest}  ../outside.txt\n",
        encoding="utf-8",
    )

    ok, failures = _verify_sha256s(root)

    assert ok is False
    assert failures == ["path escapes root: ../outside.txt"]
