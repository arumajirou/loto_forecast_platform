from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from loto.coverage.instrumented_auto_game import run_game
from loto.coverage.instrumented_common import (
    EXPECTED_AUTO_RESEARCH_BLOB_SHA,
    absolute,
    module,
    source_pin,
)
from loto.coverage.ledger import (
    CoverageLedgerBlocked,
    CoverageLedgerPreflightError,
    CoverageLedgerRecorder,
    atomic_write_json,
    require_empty_output,
    require_regular_file,
)


def run_auto_research_with_ledger(
    config_path: str | Path,
    *,
    auto_module: Any | None = None,
    pd_module: Any | None = None,
    recorder_factory=CoverageLedgerRecorder,
    clock=None,
    auto_source: str | Path | None = None,
    expected_auto_blob_sha: str = EXPECTED_AUTO_RESEARCH_BLOB_SHA,
) -> dict[str, Any]:
    auto = auto_module or module("loto.coverage.auto_research")
    pd = pd_module or module("pandas")
    config = absolute(config_path)
    require_regular_file(config, label="auto research config")
    raw = auto._load_yaml(config)
    if raw.get("resume", True) is not False:
        raise CoverageLedgerPreflightError(
            "instrumented auto research requires explicit resume=false"
        )
    if raw.get("local_llm", {}).get("enabled", False):
        raise CoverageLedgerPreflightError(
            "instrumented auto research requires local_llm.enabled=false"
        )
    output = absolute(raw.get("output", "runs/auto-coverage-ledger"))
    root = Path(__file__).resolve().parents[3]
    audited = absolute(auto_source or root / "src/loto/coverage/auto_research.py")
    source_pin(
        source=audited,
        expected=expected_auto_blob_sha,
        label="auto research",
    )
    games_cfg = raw.get("games", {})
    if not games_cfg:
        raise CoverageLedgerPreflightError("auto research games mapping is empty")
    for game, game_cfg in games_cfg.items():
        if game in auto.GAME_GEOMETRY:
            require_regular_file(absolute(game_cfg["input"]), label=f"{game} input")
    require_empty_output(output)

    budget = auto.SearchBudget(**raw.get("budget", {}))
    started = time.time()
    state: dict[str, Any] = {"completed": {}, "started_at": started}
    summaries: dict[str, Any] = {}
    blocked = False
    for game, game_cfg in games_cfg.items():
        if game not in auto.GAME_GEOMETRY:
            summaries[game] = {"status": "UNSUPPORTED_GAME"}
            continue
        game_summary, game_blocked = run_game(
            game=game,
            game_cfg=game_cfg,
            raw=raw,
            auto=auto,
            pd=pd,
            output=output,
            budget=budget,
            state=state,
            started=started,
            recorder_factory=recorder_factory,
            clock=clock,
        )
        summaries[game] = game_summary
        blocked = blocked or game_blocked

    with (output / "experiments.jsonl").open("w", encoding="utf-8") as handle:
        for record in state["completed"].values():
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    summary = {
        "schema_version": "1.0.0",
        "status": final_status(summaries, blocked),
        "budget": asdict(budget),
        "games": summaries,
        "elapsed_seconds": time.time() - started,
        "resume": False,
        "local_llm_enabled": False,
        "protected_tests_evaluated": False,
        "protected_tests_materialized": False,
        "note": (
            "Search is bounded and fail-closed. Protected-test target rows were "
            "not parsed or materialized."
        ),
    }
    atomic_write_json(output / "auto_research_summary.json", summary)
    if blocked:
        raise CoverageLedgerBlocked("auto research was blocked by incomplete experiment evidence")
    return summary


def final_status(summaries: dict[str, Any], blocked: bool) -> str:
    if blocked:
        return "BLOCKED"
    if all(item.get("status") == "TARGET_MET" for item in summaries.values()):
        return "TARGET_MET_ALL"
    return "TARGET_NOT_MET_ALL"
