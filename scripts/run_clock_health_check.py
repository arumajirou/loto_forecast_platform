#!/usr/bin/env python3
"""Run the Clock Health Gate from fixed chronyc argv or retained text files."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

from loto.clock_health import (
    ChronycAdapter,
    ClockContinuityEvidence,
    ClockHealthPolicy,
    ClockHealthStatus,
    canonical_json,
    evaluate_clock_health,
    load_model_json,
    parse_chronyc_observation,
    verify_evidence_bundle,
    write_evidence_bundle,
)


def _utc_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise argparse.ArgumentTypeError("timestamp must be timezone-aware UTC")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("files", "chronyc"), required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--observation-id", default="clock-observation-v1")
    parser.add_argument("--decision-id", default="clock-decision-v1")
    parser.add_argument("--tracking-file", type=Path)
    parser.add_argument("--sources-file", type=Path)
    parser.add_argument("--observed-at-utc", type=_utc_datetime)
    parser.add_argument("--wall-delta-ns", type=int, default=1_000_000_000)
    parser.add_argument("--monotonic-delta-ns", type=int, default=1_000_000_000)
    parser.add_argument("--timeout-seconds", type=float, default=5.0)
    return parser


def _observe_files(args: argparse.Namespace, policy: ClockHealthPolicy):
    if args.tracking_file is None or args.sources_file is None:
        raise ValueError("files mode requires tracking and sources files")
    if args.observed_at_utc is None:
        raise ValueError("files mode requires observed-at-utc")
    if args.wall_delta_ns < 0 or args.monotonic_delta_ns < 0:
        raise ValueError("continuity deltas must be non-negative")
    tracking = args.tracking_file.read_bytes()
    sources = args.sources_file.read_bytes()
    ended = args.observed_at_utc
    elapsed_ns = max(args.wall_delta_ns, args.monotonic_delta_ns)
    started = ended - timedelta(microseconds=elapsed_ns / 1000)
    continuity = ClockContinuityEvidence.create(
        sample_id=f"{args.observation_id}-continuity",
        started_at_utc=started,
        ended_at_utc=ended,
        wall_delta_ns=args.wall_delta_ns,
        monotonic_delta_ns=args.monotonic_delta_ns,
        step_threshold_ns=policy.continuity_step_threshold_ns,
    )
    observation = parse_chronyc_observation(
        observation_id=args.observation_id,
        observed_at_utc=ended,
        tracking_raw=tracking,
        sources_raw=sources,
        continuity=continuity,
    )
    return observation, tracking, sources, b"", b""


def _observe_chronyc(args: argparse.Namespace, policy: ClockHealthPolicy):
    if args.timeout_seconds <= 0:
        raise ValueError("timeout must be positive")
    artifacts = ChronycAdapter().observe(
        observation_id=args.observation_id,
        timeout_seconds=args.timeout_seconds,
        continuity_step_threshold_ns=policy.continuity_step_threshold_ns,
    )
    return (
        artifacts.observation,
        artifacts.tracking_stdout,
        artifacts.sources_stdout,
        artifacts.tracking_stderr,
        artifacts.sources_stderr,
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        policy = load_model_json(args.policy, ClockHealthPolicy)
        if args.mode == "files":
            observation, tracking, sources, tracking_error, sources_error = _observe_files(
                args,
                policy,
            )
        else:
            observation, tracking, sources, tracking_error, sources_error = _observe_chronyc(
                args,
                policy,
            )
        decision = evaluate_clock_health(
            observation,
            policy,
            decision_id=args.decision_id,
            evaluated_at_utc=observation.observed_at_utc,
        )
        write_evidence_bundle(
            args.output_dir,
            observation=observation,
            decision=decision,
            policy=policy,
            tracking_stdout=tracking,
            sources_stdout=sources,
            tracking_stderr=tracking_error,
            sources_stderr=sources_error,
        )
        verify_evidence_bundle(args.output_dir)
        print(
            canonical_json(
                {
                    "status": decision.status.value,
                    "prediction_lock_allowed": decision.prediction_lock_allowed,
                    "observation_sha256": observation.observation_sha256,
                    "policy_sha256": policy.policy_sha256,
                    "decision_sha256": decision.decision_sha256,
                    "external_trust_established": False,
                    "output_dir": str(args.output_dir),
                }
            )
        )
        return 0 if decision.status == ClockHealthStatus.HEALTHY else 1
    except Exception:
        print(
            canonical_json(
                {
                    "status": "EXECUTION_FAILED",
                    "prediction_lock_allowed": False,
                    "external_trust_established": False,
                    "error_code": "clock-health-execution-failed",
                }
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
