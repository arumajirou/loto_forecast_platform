"""KPI laboratory: a bounded, falsifiable search for coverage improvement.

The lab exists to answer one question and to stop: does any forecasting model produce a
better L-infinity coverage pool than a data-free covering construction, at the same ticket
count, on draws it has never seen?

It is built so that the answer "no" is as reportable as the answer "yes". Three of its five
successful terminal states are negative results, because a loop that only halts on success
will, given enough attempts, halt on noise.

Layout
------
:mod:`loto.kpi_lab.kpi`
    KPI definitions with a mandatory ticket denominator, and a cost model that refuses to
    derive a return from a coverage figure.
:mod:`loto.kpi_lab.arms`
    Arm A (reference, data-free) and Arm B (model), plus the paired comparison.
:mod:`loto.kpi_lab.stopping`
    Anytime-valid e-process replacing threshold-triggered early stopping.
:mod:`loto.kpi_lab.negative_controls`
    Negative and positive controls, run every iteration.
:mod:`loto.kpi_lab.proposer`
    Grid and hardened local-LLM proposers. LLM output is untrusted data.
:mod:`loto.kpi_lab.ledger`
    Append-only hash-chained record of every experiment.
:mod:`loto.kpi_lab.state_machine`
    The machine itself, with its terminal states.
"""

from __future__ import annotations

from loto.kpi_lab.arms import (
    ArmComparison,
    ArmResult,
    build_model_arm,
    build_reference_arm,
    compare_arms,
)
from loto.kpi_lab.kpi import (
    CostEstimate,
    CostModel,
    KpiDefinition,
    KpiMeasurement,
    coverage_efficiency,
    kpi_definition_hash,
)
from loto.kpi_lab.ledger import ExperimentLedger, LedgerEntry, LedgerIntegrity
from loto.kpi_lab.metrics import METRIC_NAMES, LabMetrics, metrics_available
from loto.kpi_lab.negative_controls import (
    NEGATIVE_CONTROLS,
    POSITIVE_CONTROLS,
    ControlResult,
    ControlSuiteReport,
    run_control_suite,
)
from loto.kpi_lab.proposer import (
    PARAMETER_SPACE,
    GridProposer,
    LlmProposer,
    Proposal,
    ProposerResult,
    validate_proposal,
)
from loto.kpi_lab.state_machine import (
    SUCCESSFUL_TERMINALS,
    TERMINAL_STATES,
    ExperimentRecord,
    KpiLab,
    LabConfig,
    LabReport,
    SealedWindowAccessError,
    SearchBudget,
)
from loto.kpi_lab.stopping import EProcess, EProcessState, StoppingDecision, paired_e_process

__all__ = [
    "METRIC_NAMES",
    "NEGATIVE_CONTROLS",
    "PARAMETER_SPACE",
    "POSITIVE_CONTROLS",
    "SUCCESSFUL_TERMINALS",
    "TERMINAL_STATES",
    "ArmComparison",
    "ArmResult",
    "ControlResult",
    "ControlSuiteReport",
    "CostEstimate",
    "CostModel",
    "EProcess",
    "EProcessState",
    "ExperimentLedger",
    "ExperimentRecord",
    "GridProposer",
    "KpiDefinition",
    "KpiLab",
    "KpiMeasurement",
    "LabConfig",
    "LabMetrics",
    "LabReport",
    "LedgerEntry",
    "LedgerIntegrity",
    "LlmProposer",
    "Proposal",
    "ProposerResult",
    "SealedWindowAccessError",
    "SearchBudget",
    "StoppingDecision",
    "build_model_arm",
    "build_reference_arm",
    "compare_arms",
    "coverage_efficiency",
    "kpi_definition_hash",
    "metrics_available",
    "paired_e_process",
    "run_control_suite",
    "validate_proposal",
]
