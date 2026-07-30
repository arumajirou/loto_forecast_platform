"""Every v3 subcommand must emit JSON and a meaningful exit code."""
import json

import pytest

from loto.cli_v3 import main


def _run(capsys, argv):
    code = main(argv)
    out = capsys.readouterr().out
    return code, json.loads(out)


def test_games_lists_all_six(capsys):
    code, payload = _run(capsys, ["games"])
    assert code == 0 and len(payload) == 6
    assert payload["loto7"]["outcome_space"] == 10_295_472


def test_theory_all_games(capsys):
    code, payload = _run(capsys, ["theory"])
    assert code == 0 and len(payload) == 6


def test_theory_single_game(capsys):
    code, payload = _run(capsys, ["theory", "--game", "loto7"])
    assert code == 0
    assert payload["mae_floor"] == pytest.approx(3.8337, abs=1e-4)


def test_catalog_counts_are_self_consistent(capsys):
    code, payload = _run(capsys, ["catalog", "--counts"])
    subtotals = {k: v for k, v in payload.items() if not k.startswith("_") and k != "TOTAL"}
    assert code == 0 and sum(subtotals.values()) == payload["TOTAL"]


def test_catalog_library_filter(capsys):
    code, payload = _run(capsys, ["catalog", "--library", "statsforecast"])
    assert code == 0 and len(payload) == 41


def test_catalog_unpinned_filter(capsys):
    code, payload = _run(capsys, ["catalog", "--unpinned"])
    assert code == 0 and payload
    assert all(row["revision_status"] == "UNPINNED" for row in payload)


def test_catalog_csv_export(capsys, tmp_path):
    target = tmp_path / "catalog.csv"
    code, payload = _run(capsys, ["catalog", "--csv", str(target)])
    assert code == 0 and target.is_file()
    assert payload["rows"] == 174


def test_integrity_roundtrip(capsys, tmp_path):
    (tmp_path / "f.txt").write_text("x\n", encoding="utf-8")
    assert main(["integrity", "generate", "--root", str(tmp_path)]) == 0
    capsys.readouterr()
    code, payload = _run(capsys, ["integrity", "check", "--root", str(tmp_path)])
    assert code == 0 and payload["status"] == "VERIFIED"


def test_integrity_check_returns_nonzero_on_tampering(capsys, tmp_path):
    (tmp_path / "f.txt").write_text("x\n", encoding="utf-8")
    main(["integrity", "generate", "--root", str(tmp_path)])
    capsys.readouterr()
    (tmp_path / "f.txt").write_text("tampered\n", encoding="utf-8")
    code, payload = _run(capsys, ["integrity", "check", "--root", str(tmp_path)])
    assert code == 1 and payload["status"] == "MODIFIED"


def test_research_synthetic_run_reports_no_champion(capsys):
    code, payload = _run(capsys, [
        "research", "--game", "loto7", "--synthetic-rows", "180",
        "--folds", "3", "--test-size", "10", "--min-train-size", "80", "--n-boot", "150",
    ])
    assert code == 0
    assert payload["verdict"] == "NO_MODEL_BEATS_BASELINE"
    assert payload["champion"] is None
    assert payload["holdout_evaluated"] is False
    assert len(payload["protocol_hash"]) == 64


def test_research_writes_artifacts(capsys, tmp_path):
    code, payload = _run(capsys, [
        "research", "--game", "loto6", "--synthetic-rows", "180", "--folds", "3",
        "--test-size", "10", "--min-train-size", "80", "--n-boot", "100",
        "--output", str(tmp_path / "run"),
    ])
    assert code == 0
    assert "research_summary.json" in payload["artifacts"]
    assert "model_leaderboard.csv" in payload["artifacts"]


@pytest.mark.parametrize("game", ["mini", "bingo5", "numbers3", "numbers4"])
def test_research_runs_for_the_previously_unsupported_games(capsys, game):
    """v2.1.0 could only forecast loto7. These four are the regression that mattered."""
    code, payload = _run(capsys, [
        "research", "--game", game, "--synthetic-rows", "170", "--folds", "3",
        "--test-size", "10", "--min-train-size", "80", "--n-boot", "100",
    ])
    assert code == 0 and payload["status"] == "SUCCEEDED"


def test_hierarchy_reports_zero_coherence_error(capsys):
    code, payload = _run(capsys, ["hierarchy", "--game", "loto7", "--method", "ols"])
    assert code == 0 and payload["coherence_error"] < 1e-8


def test_unknown_game_is_rejected_by_argparse():
    with pytest.raises(SystemExit):
        main(["research", "--game", "toto"])
