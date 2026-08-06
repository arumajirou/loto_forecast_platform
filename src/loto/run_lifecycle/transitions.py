"""Central, machine-readable run transition matrix."""

from __future__ import annotations

from .models import (
    DecisionEvidence,
    RunAggregate,
    RunCommand,
    RunCommandType,
    RunPhase,
    RunStatus,
    TransitionDecision,
    TransitionRule,
)

_PHASE_ORDER = tuple(RunPhase)
_TERMINAL_STATUSES = frozenset({RunStatus.CANCELLED, RunStatus.TERMINAL_FAILURE})


def _next_phase(phase: RunPhase) -> RunPhase:
    index = _PHASE_ORDER.index(phase)
    return _PHASE_ORDER[index + 1]


def _build_rules() -> tuple[TransitionRule, ...]:
    rules: list[TransitionRule] = []
    for phase in _PHASE_ORDER:
        if phase != RunPhase.COMPLETE:
            rules.append(
                TransitionRule(
                    rule_id=f"start-{phase.value.lower()}",
                    from_phase=phase,
                    from_status=RunStatus.PENDING,
                    command_type=RunCommandType.START,
                    to_phase=phase,
                    to_status=RunStatus.RUNNING,
                    description="Start pending phase execution.",
                )
            )
            target_phase = (
                RunPhase.COMPLETE if phase == RunPhase.PROMOTE else _next_phase(phase)
            )
            target_status = (
                RunStatus.SUCCEEDED if target_phase == RunPhase.COMPLETE else RunStatus.PENDING
            )
            rules.append(
                TransitionRule(
                    rule_id=f"succeed-{phase.value.lower()}",
                    from_phase=phase,
                    from_status=RunStatus.RUNNING,
                    command_type=RunCommandType.MARK_SUCCEEDED,
                    to_phase=target_phase,
                    to_status=target_status,
                    description="Finish the current phase and advance deterministically.",
                )
            )
        for command_type, status in (
            (RunCommandType.MARK_RETRYABLE_FAILURE, RunStatus.RETRYABLE_FAILURE),
            (RunCommandType.MARK_BLOCKED, RunStatus.BLOCKED),
            (RunCommandType.MARK_TIMED_OUT, RunStatus.TIMED_OUT),
            (RunCommandType.MARK_TERMINAL_FAILURE, RunStatus.TERMINAL_FAILURE),
        ):
            if phase != RunPhase.COMPLETE:
                rules.append(
                    TransitionRule(
                        rule_id=f"{command_type.value.lower()}-{phase.value.lower()}",
                        from_phase=phase,
                        from_status=RunStatus.RUNNING,
                        command_type=command_type,
                        to_phase=phase,
                        to_status=status,
                        description="Record explicit phase execution outcome.",
                    )
                )
        if phase != RunPhase.COMPLETE:
            rules.extend(
                (
                    TransitionRule(
                        rule_id=f"retry-{phase.value.lower()}",
                        from_phase=phase,
                        from_status=RunStatus.RETRYABLE_FAILURE,
                        command_type=RunCommandType.RETRY,
                        to_phase=phase,
                        to_status=RunStatus.RUNNING,
                        description="Retry a retryable failure.",
                    ),
                    TransitionRule(
                        rule_id=f"resume-blocked-{phase.value.lower()}",
                        from_phase=phase,
                        from_status=RunStatus.BLOCKED,
                        command_type=RunCommandType.RESUME,
                        to_phase=phase,
                        to_status=RunStatus.RUNNING,
                        description="Resume an explicitly unblocked phase.",
                    ),
                    TransitionRule(
                        rule_id=f"resume-timeout-{phase.value.lower()}",
                        from_phase=phase,
                        from_status=RunStatus.TIMED_OUT,
                        command_type=RunCommandType.RESUME,
                        to_phase=phase,
                        to_status=RunStatus.RUNNING,
                        description="Resume a timed-out phase after operator review.",
                    ),
                )
            )
        for status in (
            RunStatus.PENDING,
            RunStatus.RUNNING,
            RunStatus.RETRYABLE_FAILURE,
            RunStatus.BLOCKED,
            RunStatus.TIMED_OUT,
        ):
            if phase != RunPhase.COMPLETE:
                rules.append(
                    TransitionRule(
                        rule_id=f"cancel-{phase.value.lower()}-{status.value.lower()}",
                        from_phase=phase,
                        from_status=status,
                        command_type=RunCommandType.CANCEL,
                        to_phase=phase,
                        to_status=RunStatus.CANCELLED,
                        description="Cancel only through an explicit cancellation command.",
                    )
                )
    return tuple(rules)


TRANSITION_RULES = _build_rules()
TRANSITION_MATRIX = {
    (rule.from_phase, rule.from_status, rule.command_type): rule for rule in TRANSITION_RULES
}


class TransitionEngine:
    """Pure fail-closed transition decision engine."""

    @staticmethod
    def is_terminal(aggregate: RunAggregate) -> bool:
        return aggregate.status in _TERMINAL_STATUSES or (
            aggregate.phase == RunPhase.COMPLETE and aggregate.status == RunStatus.SUCCEEDED
        )

    def decide(self, aggregate: RunAggregate, command: RunCommand) -> TransitionDecision:
        evidence = (
            DecisionEvidence(
                key="run_id_match",
                value=str(aggregate.run_id == command.run_id).lower(),
            ),
            DecisionEvidence(
                key="expected_revision_match",
                value=str(aggregate.revision == command.expected_revision).lower(),
            ),
            DecisionEvidence(
                key="phase_match",
                value=str(aggregate.phase == command.phase).lower(),
            ),
        )
        if aggregate.run_id != command.run_id:
            return self._reject(aggregate, command, "run-id-mismatch", evidence)
        if aggregate.revision != command.expected_revision:
            return self._reject(aggregate, command, "revision-mismatch", evidence)
        if aggregate.phase != command.phase:
            return self._reject(aggregate, command, "phase-mismatch", evidence)
        if self.is_terminal(aggregate):
            return self._reject(aggregate, command, "terminal-state-immutable", evidence)
        rule = TRANSITION_MATRIX.get((aggregate.phase, aggregate.status, command.command_type))
        if rule is None:
            return self._reject(aggregate, command, "unknown-transition", evidence)
        return TransitionDecision(
            allowed=True,
            reason_code="transition-allowed",
            current_phase=aggregate.phase,
            current_status=aggregate.status,
            current_revision=aggregate.revision,
            expected_revision=command.expected_revision,
            target_phase=rule.to_phase,
            target_status=rule.to_status,
            rule_id=rule.rule_id,
            evidence=evidence
            + (
                DecisionEvidence(key="matrix_rule", value=rule.rule_id),
                DecisionEvidence(key="explicit_command", value=command.command_type.value),
            ),
        )

    @staticmethod
    def _reject(
        aggregate: RunAggregate,
        command: RunCommand,
        reason_code: str,
        evidence: tuple[DecisionEvidence, ...],
    ) -> TransitionDecision:
        return TransitionDecision(
            allowed=False,
            reason_code=reason_code,
            current_phase=aggregate.phase,
            current_status=aggregate.status,
            current_revision=aggregate.revision,
            expected_revision=command.expected_revision,
            evidence=evidence,
        )


def transition_matrix_as_dicts() -> list[dict[str, str]]:
    """Return a stable machine-readable representation used by config parity tests."""

    rows = [
        {
            "rule_id": rule.rule_id,
            "from_phase": rule.from_phase.value,
            "from_status": rule.from_status.value,
            "command_type": rule.command_type.value,
            "to_phase": rule.to_phase.value,
            "to_status": rule.to_status.value,
            "description": rule.description,
        }
        for rule in TRANSITION_RULES
    ]
    return sorted(rows, key=lambda row: row["rule_id"])
