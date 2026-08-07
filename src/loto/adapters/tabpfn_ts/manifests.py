from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


TABPFN_TS_PACKAGE_VERSION = "1.2.0"
TABPFN_TS_WHEEL_SHA256 = "3358d222a3056190dc7862d5a9e8a7e7a311d374a1f2d6bc1b3f342201bfbd8f"
TABPFN_TS_SDIST_SHA256 = "c94d0f63c0f921be56e91b9c50724ef49e2b95df72fa22d960c4d52df1d3f2db"
TABPFN_TS_UPSTREAM_REVISION = "a756ae3fb3af82c903c39e1cd71864ff5252bc4d"

V2_REPO_ID = "Prior-Labs/TabPFN-v2-reg"
V2_REVISION = "4972a65a1b30806315c6f92499959ffbfc69a673"
V2_WEIGHT_FILENAME = "tabpfn-v2-regressor.ckpt"
V2_WEIGHT_SHA256 = "2ab5a07d5c41dfe6db9aa7ae106fc6de898326c2765be66505a07e2868c10736"

TS3_WEIGHT_FILENAME = "tabpfn-v3-regressor-v3_20260506_timeseries.ckpt"


class CheckpointLane(StrEnum):
    V2_REG_LEGACY = "v2_reg_legacy"
    TS3_CURRENT = "ts3_current"


class ExecutionStatus(StrEnum):
    READY = "READY"
    BLOCKED_PENDING_CHECKPOINT_HASH_AND_LICENSE_REVIEW = (
        "BLOCKED_PENDING_CHECKPOINT_HASH_AND_LICENSE_REVIEW"
    )


class PackageManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    package: str
    version: str
    wheel_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sdist_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    code_license: str


class CheckpointManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    lane: CheckpointLane
    execution_status: ExecutionStatus
    repo_id: str | None
    revision: str | None
    filename: str
    sha256: str | None
    weight_license: str | None
    attribution_required: bool | None
    license_acceptance_required: bool
    production_champion_eligible: bool
    pretraining_data_overlap: str = "UNKNOWN"


PACKAGE_MANIFEST = PackageManifest(
    package="tabpfn-time-series",
    version=TABPFN_TS_PACKAGE_VERSION,
    wheel_sha256=TABPFN_TS_WHEEL_SHA256,
    sdist_sha256=TABPFN_TS_SDIST_SHA256,
    source_revision=TABPFN_TS_UPSTREAM_REVISION,
    code_license="Apache-2.0",
)

LANE_MANIFESTS: dict[CheckpointLane, CheckpointManifest] = {
    CheckpointLane.V2_REG_LEGACY: CheckpointManifest(
        lane=CheckpointLane.V2_REG_LEGACY,
        execution_status=ExecutionStatus.READY,
        repo_id=V2_REPO_ID,
        revision=V2_REVISION,
        filename=V2_WEIGHT_FILENAME,
        sha256=V2_WEIGHT_SHA256,
        weight_license="Prior Labs License 1.1",
        attribution_required=True,
        license_acceptance_required=True,
        production_champion_eligible=False,
    ),
    CheckpointLane.TS3_CURRENT: CheckpointManifest(
        lane=CheckpointLane.TS3_CURRENT,
        execution_status=ExecutionStatus.BLOCKED_PENDING_CHECKPOINT_HASH_AND_LICENSE_REVIEW,
        repo_id=None,
        revision=None,
        filename=TS3_WEIGHT_FILENAME,
        sha256=None,
        weight_license=None,
        attribution_required=None,
        license_acceptance_required=True,
        production_champion_eligible=False,
    ),
}


def lane_manifest(lane: CheckpointLane) -> CheckpointManifest:
    return LANE_MANIFESTS[lane]


def require_executable_lane(lane: CheckpointLane) -> CheckpointManifest:
    manifest = lane_manifest(lane)
    if manifest.execution_status is not ExecutionStatus.READY:
        raise RuntimeError(manifest.execution_status.value)
    if not manifest.sha256 or not manifest.weight_license:
        raise RuntimeError("executable lane is missing checkpoint or license provenance")
    return manifest
