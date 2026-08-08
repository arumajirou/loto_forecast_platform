from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, Protocol

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from .ensemble_conformal_contract import P10CampaignConfig, P10_MODEL_IDENTITIES


class MatrixTask(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    public_name: str
    seed: int
    fold_id: int


class MatrixResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    task: MatrixTask
    status: Literal["SUCCESS", "FAILED"]
    failure_class: str | None = None
    failure_message: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class MatrixRuntime(Protocol):
    def execute(self, task: MatrixTask) -> Mapping[str, Any]: ...


def run_p10_matrix(config: P10CampaignConfig, runtime: MatrixRuntime) -> tuple[MatrixResult, ...]:
    tasks = tuple(
        (
            MatrixTask(public_name=public_name, seed=seed, fold_id=fold_id)
            for public_name in P10_MODEL_IDENTITIES
            for seed in config.seeds
            for fold_id in config.fold_ids
        )
    )
    results: list[MatrixResult] = []
    for task in tasks:
        try:
            evidence = dict(runtime.execute(task))
        except Exception as error:
            results.append(
                MatrixResult(
                    task=task,
                    status="FAILED",
                    failure_class=type(error).__name__,
                    failure_message=str(error),
                )
            )
        else:
            results.append(MatrixResult(task=task, status="SUCCESS", evidence=evidence))
    return tuple(results)


def assert_frame_unchanged(before: pd.DataFrame, after: pd.DataFrame) -> None:
    pd.testing.assert_frame_equal(before, after, check_exact=True)
