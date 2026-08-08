from __future__ import annotations

import json
from pathlib import Path

from loto.run_lifecycle import transition_matrix_as_dicts


def _expand(payload: dict[str, object]) -> list[dict[str, str]]:
    phases = payload["phase_order"]
    templates = payload["templates"]
    assert isinstance(phases, list)
    assert isinstance(templates, dict)
    non_terminal = [str(phase) for phase in phases if phase != "COMPLETE"]
    rows: list[dict[str, str]] = []

    start = templates["start"]
    succeed = templates["succeed"]
    outcomes = templates["execution_outcomes"]
    recoveries = templates["recoveries"]
    cancel = templates["cancel"]
    assert isinstance(start, dict)
    assert isinstance(succeed, dict)
    assert isinstance(outcomes, list)
    assert isinstance(recoveries, list)
    assert isinstance(cancel, dict)

    for index, phase in enumerate(non_terminal):
        phase_key = phase.lower()
        rows.append(
            {
                "rule_id": str(start["rule_id_pattern"]).format(phase=phase_key),
                "from_phase": phase,
                "from_status": str(start["from_status"]),
                "command_type": str(start["command_type"]),
                "to_phase": phase,
                "to_status": str(start["to_status"]),
                "description": str(start["description"]),
            }
        )
        target_phase = non_terminal[index + 1] if phase != "PROMOTE" else "COMPLETE"
        target_status = "PENDING" if phase != "PROMOTE" else "SUCCEEDED"
        rows.append(
            {
                "rule_id": str(succeed["rule_id_pattern"]).format(phase=phase_key),
                "from_phase": phase,
                "from_status": str(succeed["from_status"]),
                "command_type": str(succeed["command_type"]),
                "to_phase": target_phase,
                "to_status": target_status,
                "description": str(succeed["description"]),
            }
        )
        for outcome in outcomes:
            assert isinstance(outcome, dict)
            command = str(outcome["command_type"])
            rows.append(
                {
                    "rule_id": str(templates["execution_outcome_rule_id_pattern"]).format(
                        command=command.lower(), phase=phase_key
                    ),
                    "from_phase": phase,
                    "from_status": str(outcome["from_status"]),
                    "command_type": command,
                    "to_phase": phase,
                    "to_status": str(outcome["to_status"]),
                    "description": str(templates["execution_outcome_description"]),
                }
            )
        for recovery in recoveries:
            assert isinstance(recovery, dict)
            rows.append(
                {
                    "rule_id": str(recovery["rule_id_pattern"]).format(phase=phase_key),
                    "from_phase": phase,
                    "from_status": str(recovery["from_status"]),
                    "command_type": str(recovery["command_type"]),
                    "to_phase": phase,
                    "to_status": str(recovery["to_status"]),
                    "description": str(recovery["description"]),
                }
            )
        statuses = cancel["from_statuses"]
        assert isinstance(statuses, list)
        for status in statuses:
            status_value = str(status)
            rows.append(
                {
                    "rule_id": str(cancel["rule_id_pattern"]).format(
                        phase=phase_key, status=status_value.lower()
                    ),
                    "from_phase": phase,
                    "from_status": status_value,
                    "command_type": str(cancel["command_type"]),
                    "to_phase": phase,
                    "to_status": str(cancel["to_status"]),
                    "description": str(cancel["description"]),
                }
            )
    return sorted(rows, key=lambda row: row["rule_id"])


def test_machine_readable_transition_matrix_matches_code() -> None:
    root = Path(__file__).resolve().parents[2]
    payload = json.loads(
        (root / "configs/run_lifecycle/transition_matrix.v1.json").read_text(encoding="utf-8")
    )
    assert payload["schema_version"] == "1.0.0"
    assert payload["unknown_transition_policy"] == "FAIL_CLOSED"
    expanded = _expand(payload)
    assert expanded == transition_matrix_as_dicts()
    assert len(expanded) == len({row["rule_id"] for row in expanded}) == 140
