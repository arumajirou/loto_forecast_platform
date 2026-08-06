from __future__ import annotations

from typing import Any

from loto.probabilistic.kdpp_target_command_context import _command_context
from loto.probabilistic.kdpp_target_commands_history import _history_commands
from loto.probabilistic.kdpp_target_commands_raw import _raw_commands
from loto.probabilistic.kdpp_target_commands_runtime import _runtime_commands
from loto.probabilistic.kdpp_target_contracts import SCHEMA_VERSION, TargetExecutionPlan


def _commands(plan: TargetExecutionPlan) -> dict[str, Any]:
    context = _command_context(plan)
    commands = [
        *_raw_commands(plan, context),
        *_history_commands(plan, context),
        *_runtime_commands(plan, context),
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": plan.run_id,
        "database_credentials_embedded": False,
        "automatic_approval": False,
        "commands": commands,
    }


def _runbook(plan: TargetExecutionPlan) -> str:
    return f"""# k-DPP fixed-k target execution

Run ID: `{plan.run_id}`

## Immutable source identities

- exporter: `{plan.exporter.actual_head}` at `{plan.exporter.root}`
- k-DPP: `{plan.kdpp.actual_head}` at `{plan.kdpp.root}`

## Ordered stages

1. Execute the read-only five-game raw export.
2. Independently verify JSON and Parquet bytes.
3. Create the raw-history pending record.
4. Review query, snapshot, row counts, cutoffs, and ranges; approve explicitly.
5. Materialize the approved eight-file source handoff.
6. Record the source handoff in this control ledger.
7. Materialize the selected k-DPP Train-only bundle.
8. Create and independently approve the k-DPP history record.
9. Record the approved k-DPP bundle in this control ledger.
10. Run target-host prepare, two-process CPU execution, and formal verification.
11. Record CPU_FORMAL only after independent evidence revalidation.

`COMMANDS.json` contains exact argv arrays. Replace only reviewer and UTC placeholders.
Database credentials remain environment variables and are never written to this workspace.
Do not open Holdout or Prospective data. Do not mark any parent PR Ready or merge it.
"""
