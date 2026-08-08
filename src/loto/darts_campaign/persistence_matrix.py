from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from .persistence_certification import PersistenceReport, certify_persistence
from .persistence_contract import (
    PersistenceCampaignConfig,
    PersistenceEvidence,
    PersistenceSpec,
    PersistenceTask,
)


class PersistenceMatrixResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task: PersistenceTask
    status: Literal["CERTIFIED", "FAILED"]
    failure_class: str | None = None
    failure_message: str | None = None
    report: PersistenceReport | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PersistenceRuntime(Protocol):
    def execute(self, task: PersistenceTask, spec: PersistenceSpec) -> PersistenceEvidence: ...


def build_persistence_tasks(config: PersistenceCampaignConfig) -> tuple[PersistenceTask, ...]:
    return tuple(
        PersistenceTask(
            model_id=spec.model_id,
            family=spec.family,
            public_name=spec.public_name,
            method=method,
        )
        for spec in config.specs
        for method in spec.methods
    )


def run_persistence_matrix(
    config: PersistenceCampaignConfig,
    runtime: PersistenceRuntime,
) -> tuple[PersistenceMatrixResult, ...]:
    spec_by_id = {spec.model_id: spec for spec in config.specs}
    results: list[PersistenceMatrixResult] = []
    for task in build_persistence_tasks(config):
        spec = spec_by_id[task.model_id]
        try:
            evidence = runtime.execute(task, spec)
            report = certify_persistence(spec, evidence)
        except Exception as error:
            results.append(
                PersistenceMatrixResult(
                    task=task,
                    status="FAILED",
                    failure_class=type(error).__name__,
                    failure_message=str(error),
                )
            )
            continue
        results.append(
            PersistenceMatrixResult(
                task=task,
                status=("CERTIFIED" if report.status == "PERSISTENCE_CERTIFIED" else "FAILED"),
                failure_class=(
                    None if report.status == "PERSISTENCE_CERTIFIED" else "CERTIFICATION_FAILED"
                ),
                failure_message=(
                    None
                    if report.status == "PERSISTENCE_CERTIFIED"
                    else "one or more persistence checks failed"
                ),
                report=report,
                metadata={
                    "artifact_manifest_sha256": report.artifact_manifest_sha256,
                    "evidence_sha256": report.evidence_sha256,
                },
            )
        )
    return tuple(results)
