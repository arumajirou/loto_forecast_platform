from __future__ import annotations

import argparse
from pathlib import Path

from .p7_audit import audit_lane, build_target_audit, write_target_audit
from .p7_contract import CertificationStatus, EvidenceState


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description="Audit P6 target-machine evidence",
    )
    value.add_argument("--run-id", required=True)
    value.add_argument("--repo-root", required=True, type=Path)
    value.add_argument("--compat-artifact-root", required=True, type=Path)
    value.add_argument("--latest-artifact-root", required=True, type=Path)
    value.add_argument("--compat-return-code", required=True, type=int)
    value.add_argument("--latest-return-code", required=True, type=int)
    value.add_argument("--output-dir", required=True, type=Path)
    return value


def main() -> int:
    args = parser().parse_args()
    repo_root = args.repo_root.resolve()
    compat = audit_lane(
        lane="compat",
        artifact_root=args.compat_artifact_root.resolve(),
        bootstrap_return_code=args.compat_return_code,
        repo_root=repo_root,
        lane_root=repo_root / "environments/gluonts-compat",
    )
    latest = audit_lane(
        lane="latest",
        artifact_root=args.latest_artifact_root.resolve(),
        bootstrap_return_code=args.latest_return_code,
        repo_root=repo_root,
        lane_root=repo_root / "environments/gluonts-latest",
    )
    audit = build_target_audit(
        run_id=args.run_id,
        compat=compat,
        latest=latest,
    )
    identities = write_target_audit(args.output_dir.resolve(), audit)
    print(f"P7_EVIDENCE_STATE={audit.evidence_state.value}")
    print(f"P7_CERTIFICATION_STATUS={audit.certification_status.value}")
    print(f"P7_VERIFIED_MODEL_LIFECYCLES={audit.verified_model_lifecycles}")
    for key, value in identities.items():
        print(f"P7_{key.upper()}={value}")
    if audit.evidence_state is EvidenceState.INVALID:
        return 3
    if audit.certification_status is CertificationStatus.VERIFIED:
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
