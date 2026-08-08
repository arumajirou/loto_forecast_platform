from __future__ import annotations

from typing import Any

from loto.probabilistic.kdpp_target_contracts import TargetExecutionPlan

_KDPP_CONFIRMATIONS = [
    "--confirm-source-read-only",
    "--confirm-train-only",
    "--confirm-draw-order",
    "--confirm-row-count",
    "--confirm-game-geometry",
    "--confirm-cutoff",
    "--confirm-no-future-actuals",
    "--confirm-no-holdout",
    "--confirm-no-prospective",
]


def _history_commands(
    plan: TargetExecutionPlan,
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    del plan
    kdpp = context["kdpp"]
    prefix = context["kdpp_prefix"]
    script = str(kdpp / "scripts/materialize_kdpp_fixed_k_history.py")
    controller = str(kdpp / "scripts/manage_kdpp_fixed_k_target_execution.py")
    return [
        {
            "stage": "kdpp-history-materialize",
            "cwd": str(kdpp),
            "argv": context["materialize"],
        },
        {
            "stage": "kdpp-history-pending",
            "cwd": str(kdpp),
            "argv": [
                *prefix,
                script,
                "pending",
                "--bundle",
                str(context["bundle"]),
                "--output",
                str(context["kdpp_pending"]),
            ],
        },
        {
            "stage": "kdpp-history-human-approval",
            "cwd": str(kdpp),
            "requires_human_review": True,
            "argv": [
                *prefix,
                script,
                "approve",
                "--bundle",
                str(context["bundle"]),
                "--pending",
                str(context["kdpp_pending"]),
                "--output",
                str(context["kdpp_approved"]),
                "--reviewer",
                "<REVIEWER>",
                "--reviewed-at-utc",
                "<UTC_TIMESTAMP>",
                "--approval-token",
                "APPROVE-KDPP-HISTORY-BUNDLE",
                *_KDPP_CONFIRMATIONS,
            ],
        },
        {
            "stage": "record-kdpp-history",
            "cwd": str(kdpp),
            "argv": [
                *prefix,
                controller,
                "record-history",
                "--workspace",
                str(context["workspace"]),
                "--bundle",
                str(context["bundle"]),
                "--approval",
                str(context["kdpp_approved"]),
            ],
        },
    ]
