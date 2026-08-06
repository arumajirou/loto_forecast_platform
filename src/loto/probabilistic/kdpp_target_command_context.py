from __future__ import annotations

from pathlib import Path
from typing import Any

from loto.probabilistic.kdpp_target_contracts import TargetExecutionPlan


def _command_context(plan: TargetExecutionPlan) -> dict[str, Any]:
    workspace = Path(plan.workspace)
    exporter = Path(plan.exporter.root)
    kdpp = Path(plan.kdpp.root)
    context: dict[str, Any] = {
        "workspace": workspace,
        "exporter": exporter,
        "kdpp": kdpp,
        "export_root": workspace / "external" / "raw-export",
        "verification": workspace / "external" / "raw-verification.json",
        "raw_pending": workspace / "reviews" / "raw.pending.json",
        "raw_approved": workspace / "reviews" / "raw.approved.json",
        "source_handoff": workspace / "artifacts" / "source-handoff",
        "bundle": workspace / "artifacts" / "kdpp-history",
        "kdpp_pending": workspace / "reviews" / "kdpp.pending.json",
        "kdpp_approved": workspace / "reviews" / "kdpp.approved.json",
        "runtime": workspace / "artifacts" / "runtime",
    }
    context["exporter_prefix"] = [
        "env",
        "PYTHONDONTWRITEBYTECODE=1",
        f"PYTHONPATH={exporter / 'src'}",
        plan.exporter.python_executable,
    ]
    context["kdpp_prefix"] = [
        "env",
        "PYTHONDONTWRITEBYTECODE=1",
        f"PYTHONPATH={kdpp / 'src'}",
        plan.kdpp.python_executable,
    ]
    materialize = [
        *context["kdpp_prefix"],
        str(kdpp / "scripts/materialize_kdpp_fixed_k_history.py"),
        "materialize",
        "--source-handoff",
        str(context["source_handoff"]),
        "--output-dir",
        str(context["bundle"]),
        "--game",
        plan.game,
    ]
    if plan.position is not None:
        materialize.extend(["--position", str(plan.position)])
    context["materialize"] = materialize
    return context
