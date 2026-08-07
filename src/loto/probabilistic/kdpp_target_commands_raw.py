from __future__ import annotations

from typing import Any

from loto.probabilistic.kdpp_target_contracts import TargetExecutionPlan


_RAW_CONFIRMATIONS = [
    "--confirm-source-query",
    "--confirm-database-snapshot",
    "--confirm-row-counts",
    "--confirm-cutoff-dates",
    "--confirm-position-ranges",
]
_RAW_MATERIALIZE_CODE = (
    "from pathlib import Path; "
    "from loto.toto2_campaign.history_handoff import materialize_approved_histories; "
    "import sys; materialize_approved_histories(*map(Path, sys.argv[1:5]))"
)


def _raw_commands(plan: TargetExecutionPlan, context: dict[str, Any]) -> list[dict[str, Any]]:
    exporter = context["exporter"]
    kdpp = context["kdpp"]
    prefix = context["exporter_prefix"]
    kdpp_prefix = context["kdpp_prefix"]
    return [
        {
            "stage": "raw-export",
            "cwd": str(exporter),
            "argv": [
                *prefix,
                str(exporter / "scripts/export_toto2_4m_raw_history.py"),
                "--output-root",
                str(context["export_root"]),
            ],
        },
        {
            "stage": "raw-verify",
            "cwd": str(exporter),
            "argv": [
                *prefix,
                str(exporter / "scripts/verify_toto2_4m_raw_history_export.py"),
                "--export-root",
                str(context["export_root"]),
                "--verification-output",
                str(context["verification"]),
            ],
        },
        {
            "stage": "raw-pending",
            "cwd": str(exporter),
            "argv": [
                *prefix,
                str(exporter / "scripts/manage_toto2_4m_history_approval.py"),
                "create-pending",
                "--export-root",
                str(context["export_root"]),
                "--verification",
                str(context["verification"]),
                "--output",
                str(context["raw_pending"]),
            ],
        },
        {
            "stage": "raw-human-approval",
            "cwd": str(exporter),
            "requires_human_review": True,
            "argv": [
                *prefix,
                str(exporter / "scripts/manage_toto2_4m_history_approval.py"),
                "approve",
                "--export-root",
                str(context["export_root"]),
                "--verification",
                str(context["verification"]),
                "--pending",
                str(context["raw_pending"]),
                "--output",
                str(context["raw_approved"]),
                "--reviewer",
                "<REVIEWER>",
                "--reviewed-at",
                "<UTC_TIMESTAMP>",
                "--approval-token",
                "APPROVE-TOTO2-HISTORY-EXPORT",
                *_RAW_CONFIRMATIONS,
            ],
        },
        {
            "stage": "source-handoff-materialize",
            "cwd": str(exporter),
            "argv": [
                *prefix,
                "-c",
                _RAW_MATERIALIZE_CODE,
                str(context["export_root"]),
                str(context["verification"]),
                str(context["raw_approved"]),
                str(context["source_handoff"]),
            ],
        },
        {
            "stage": "record-source-handoff",
            "cwd": str(kdpp),
            "argv": [
                *kdpp_prefix,
                str(kdpp / "scripts/manage_kdpp_fixed_k_target_execution.py"),
                "record-source",
                "--workspace",
                str(context["workspace"]),
                "--handoff",
                str(context["source_handoff"]),
            ],
        },
    ]
