#!/usr/bin/env python3
"""Build one certified adaptive-GPU resource profile from characterization evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"evidence is not a JSON object: {path}")
    return payload


def _write_atomic(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--min-samples", type=int, default=3)
    parser.add_argument("--evidence", type=Path, action="append", required=True)
    return parser.parse_args()


def _identity_tuple(payload: dict[str, Any]) -> tuple[object, ...]:
    gpu = payload["gpu"]
    llm = payload["llm"]
    foundation = payload["foundation"]
    return (
        gpu["uuid"],
        gpu["index"],
        llm["alias"],
        llm["runtime"],
        llm["context_length"],
        foundation["repo_id"],
        foundation["revision"],
        foundation["runtime_lane"],
    )


def main() -> int:
    args = _parse_args()
    evidence = [_load(path) for path in args.evidence]
    if len(evidence) < args.min_samples:
        raise RuntimeError(
            f"need at least {args.min_samples} characterization runs, got {len(evidence)}"
        )
    if any(item.get("status") != "PASS" for item in evidence):
        raise RuntimeError("all characterization evidence must have status=PASS")

    identities = {_identity_tuple(item) for item in evidence}
    if len(identities) != 1:
        raise RuntimeError("characterization evidence does not share one exact identity tuple")

    first = evidence[0]
    gpu = first["gpu"]
    llm = first["llm"]
    foundation = first["foundation"]
    peaks = [int(item["external_peak_vram_mib"]) for item in evidence]
    run_ids = [str(item["run_id"]) for item in evidence]
    process_names = sorted(
        {
            str(name)
            for item in evidence
            for name in item["llm"].get("baseline_process_names", [])
        }
    )
    code_hashes = {
        item.get("code_sha256")
        for item in evidence
        if isinstance(item.get("code_sha256"), str)
    }
    if len(code_hashes) > 1:
        raise RuntimeError("characterization evidence has inconsistent code SHA-256 values")
    code_sha256 = next(iter(code_hashes)) if len(code_hashes) == 1 else None

    profile = {
        "profile_id": args.profile_id,
        "certified": True,
        "gpu": {
            "uuid": gpu["uuid"],
            "index": int(gpu["index"]),
        },
        "llm": {
            "alias": llm["alias"],
            "runtime": llm["runtime"],
            "context_length": int(llm["context_length"]),
            "process_names": process_names,
        },
        "foundation": {
            "repo_id": foundation["repo_id"],
            "revision": foundation["revision"],
            "runtime_lane": foundation["runtime_lane"],
        },
        "evidence": {
            "external_peak_vram_mib": max(peaks),
            "sample_count": len(evidence),
            "certification_run_ids": run_ids,
            "code_sha256": code_sha256,
        },
    }

    registry: dict[str, Any]
    if args.registry.is_file():
        registry = _load(args.registry)
        if registry.get("schema_version") != 1 or not isinstance(
            registry.get("profiles"), list
        ):
            raise RuntimeError("existing registry is not schema_version=1")
    else:
        registry = {"schema_version": 1, "profiles": []}

    profiles = [
        item
        for item in registry["profiles"]
        if isinstance(item, dict) and item.get("profile_id") != args.profile_id
    ]
    profiles.append(profile)
    registry["profiles"] = sorted(profiles, key=lambda item: str(item["profile_id"]))
    _write_atomic(args.registry, registry)
    args.registry.with_suffix(args.registry.suffix + ".sha256").write_text(
        f"{_sha256_file(args.registry)}  {args.registry.name}\n",
        encoding="utf-8",
    )
    print(json.dumps(profile, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
