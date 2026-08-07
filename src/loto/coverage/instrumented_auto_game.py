from __future__ import annotations

import time
from typing import Any

from loto.coverage.instrumented_auto_support import (
    auto_prefix,
    auto_walk_forward,
)
from loto.coverage.instrumented_common import (
    absolute,
    frame_hash,
    make_evidence,
    run_id,
)
from loto.coverage.ledger import (
    CoverageLedgerBlocked,
    atomic_write_json,
)


def run_game(**ctx: Any) -> tuple[dict[str, Any], bool]:
    game = ctx["game"]
    game_cfg = ctx["game_cfg"]
    auto = ctx["auto"]
    pd = ctx["pd"]
    output = ctx["output"]
    budget = ctx["budget"]
    input_path = absolute(game_cfg["input"])
    (
        frame,
        source_total_rows,
        protected_test_start,
        calibration_start,
        validation_start,
        maximum,
    ) = auto_prefix(
        input_path=input_path,
        game=game,
        game_cfg=game_cfg,
        auto_module=auto,
        pd_module=pd,
    )
    count, _ = auto.GAME_GEOMETRY[game]
    columns = [f"n{index}" for index in range(1, count + 1)]
    data = frame[columns].apply(
        pd.to_numeric, errors="raise"
    ).to_numpy(dtype=int)
    evidence = make_evidence(
        frame=frame,
        dataset_id=f"coverage-{game}-accessible-prefix",
        dataset_sha256=frame_hash(frame),
        game=game,
        source_total_rows=source_total_rows,
        protected_test_start=protected_test_start,
        count=count,
    )
    queue = auto.build_grid(ctx["raw"], game)
    seeds = sorted({proposal.seed for proposal in queue}) or [0]
    game_output = output / "data_access" / game
    game_output.mkdir(parents=True, exist_ok=True)
    current_run_id = run_id(f"auto-coverage-{game}")
    recorder = ctx["recorder_factory"](
        run_id=current_run_id,
        output_dir=game_output,
        evidence=evidence,
        expected_seeds=seeds,
        clock=ctx["clock"],
    )
    results: list[dict[str, Any]] = []
    game_blocked = False
    while (
        queue
        and len(results) < budget.max_experiments
        and time.time() - ctx["started"] < budget.max_runtime_seconds
    ):
        proposal = queue.pop(0)
        record = execute_proposal(
            proposal=proposal,
            data=data,
            calibration_start=calibration_start,
            validation_start=validation_start,
            maximum=maximum,
            count=count,
            columns=columns,
            output=output,
            budget=budget,
            recorder=recorder,
            auto=auto,
            pd=pd,
        )
        results.append(record)
        ctx["state"]["completed"][proposal.experiment_id] = record
        atomic_write_json(output / "state.json", ctx["state"])
        if record["status"] == "FAILED":
            recorder.mark_gap(
                f"EXPERIMENT_FAILED:{proposal.experiment_id}"
            )
            game_blocked = True
            break
        target_met = (
            record["validation"]["row_within_tolerance"]
            >= budget.target_coverage
        )
        if target_met and budget.stop_when_target_met:
            break
    successful = [item for item in results if item["status"] == "SUCCEEDED"]
    best = select_best(successful)
    try:
        ledger = recorder.close()
    except CoverageLedgerBlocked:
        ledger = None
        game_blocked = True
    return (
        game_summary(
            best=best,
            budget=budget,
            current_run_id=current_run_id,
            results=results,
            successful=successful,
            source_total_rows=source_total_rows,
            protected_test_start=protected_test_start,
            data=data,
            ledger=ledger,
        ),
        game_blocked,
    )


def execute_proposal(**ctx: Any) -> dict[str, Any]:
    proposal = ctx["proposal"]
    started_at = time.time()
    record: dict[str, Any] = {
        "proposal": proposal.to_dict(),
        "started_at": started_at,
    }
    try:
        cal_actual, cal_pred = auto_walk_forward(
            data=ctx["data"],
            start=ctx["calibration_start"],
            end=ctx["validation_start"],
            proposal=proposal,
            maximum=ctx["maximum"],
            phase="calibration",
            recorder=ctx["recorder"],
            auto_module=ctx["auto"],
        )
        val_actual, val_pred = auto_walk_forward(
            data=ctx["data"],
            start=ctx["validation_start"],
            end=len(ctx["data"]),
            proposal=proposal,
            maximum=ctx["maximum"],
            phase="validation",
            recorder=ctx["recorder"],
            auto_module=ctx["auto"],
        )
        selected, trace = select_candidates(
            ctx=ctx,
            proposal=proposal,
            cal_actual=cal_actual,
            cal_pred=cal_pred,
            val_pred=val_pred,
        )
        calibration = ctx["auto"]._evaluate_general(
            cal_actual, selected, ctx["budget"].tolerance
        )
        validation = ctx["auto"]._evaluate_general(
            val_actual, selected, ctx["budget"].tolerance
        )
        candidate_path = (
            ctx["output"]
            / f"{proposal.game}-{proposal.experiment_id}-candidates.csv"
        )
        ctx["pd"].DataFrame(selected, columns=ctx["columns"]).to_csv(
            candidate_path, index=False
        )
        record.update(
            {
                "status": "SUCCEEDED",
                "calibration": calibration,
                "validation": validation,
                "candidate_count": len(selected),
                "trace": trace,
                "candidate_artifact": str(candidate_path),
                "elapsed_seconds": time.time() - started_at,
            }
        )
    except Exception as exc:
        record.update(
            {
                "status": "FAILED",
                "error": f"{type(exc).__name__}: {exc}",
                "elapsed_seconds": time.time() - started_at,
            }
        )
    return record


def select_candidates(**values: Any) -> tuple[list[Any], list[dict[str, Any]]]:
    ctx = values["ctx"]
    auto = ctx["auto"]
    proposal = values["proposal"]
    residuals = values["cal_actual"] - values["cal_pred"]
    center = auto.np.rint(auto.np.median(values["val_pred"], axis=0)).astype(int)
    pool = auto._candidate_pool(
        center,
        residuals,
        ctx["count"],
        ctx["maximum"],
        proposal,
    )
    selected, trace = auto._greedy_general(
        values["cal_actual"],
        pool,
        target=min(
            1.0,
            ctx["budget"].target_coverage + ctx["budget"].calibration_margin,
        ),
        tolerance=ctx["budget"].tolerance,
        max_candidates=min(ctx["budget"].max_candidates, proposal.pool_size),
        diversity=proposal.diversity_penalty,
    )
    if not selected:
        raise RuntimeError("no candidates selected")
    return selected, trace


def select_best(successful: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not successful:
        return None
    return sorted(
        successful,
        key=lambda item: (
            -item["validation"]["row_within_tolerance"],
            item["candidate_count"],
            item["validation"]["mean_best_mae"],
        ),
    )[0]


def game_summary(**ctx: Any) -> dict[str, Any]:
    best = ctx["best"]
    budget = ctx["budget"]
    ledger = ctx["ledger"]
    return {
        "status": (
            "TARGET_MET"
            if best
            and best["validation"]["row_within_tolerance"]
            >= budget.target_coverage
            else "TARGET_NOT_MET"
        ),
        "run_id": ctx["current_run_id"],
        "experiments": len(ctx["results"]),
        "successful": len(ctx["successful"]),
        "best": best,
        "source_total_rows": ctx["source_total_rows"],
        "accessible_rows": len(ctx["data"]),
        "protected_test": [
            ctx["protected_test_start"],
            ctx["source_total_rows"],
        ],
        "protected_test_evaluated": False,
        "protected_test_materialized": False,
        "data_access_status": None if ledger is None else ledger.status,
        "data_access_ledger": None if ledger is None else str(ledger.ledger_path),
        "data_access_ledger_sha256": (
            None if ledger is None else ledger.ledger_sha256
        ),
    }
