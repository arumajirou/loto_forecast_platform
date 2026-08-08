#!/usr/bin/env python3
"""Resolve reviewed image tags to immutable manifest digests without pulling them."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy" / "observability"
VERSIONS_FILE = DEPLOY / "images.versions.env"
LOCK_ENV = DEPLOY / "images.lock.env"
LOCK_JSON = DEPLOY / "IMAGE_DIGESTS.lock.json"
KEYS = (
    "GRAFANA_IMAGE",
    "ALLOY_IMAGE",
    "PROMETHEUS_IMAGE",
    "LOKI_IMAGE",
    "TEMPO_IMAGE",
    "BUSYBOX_IMAGE",
)
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def read_versions(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key] = value
    expected = {f"{key}_TAG" for key in KEYS}
    if set(values) != expected:
        raise SystemExit(f"version inventory mismatch: expected={sorted(expected)}")
    return values


def inspect_raw(reference: str) -> bytes:
    command = ["docker", "buildx", "imagetools", "inspect", reference, "--raw"]
    completed = subprocess.run(command, check=True, capture_output=True)
    if not completed.stdout:
        raise SystemExit(f"empty manifest returned for {reference}")
    return completed.stdout


def repository_part(reference: str) -> str:
    last = reference.rsplit("/", 1)[-1]
    if "@" in reference or ":" not in last:
        raise SystemExit(f"reference must contain an exact tag and no digest: {reference}")
    return reference.rsplit(":", 1)[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--versions-file", type=Path, default=VERSIONS_FILE)
    parser.add_argument("--lock-env", type=Path, default=LOCK_ENV)
    parser.add_argument("--lock-json", type=Path, default=LOCK_JSON)
    args = parser.parse_args()

    versions = read_versions(args.versions_file)
    records: dict[str, dict[str, str]] = {}
    env_lines = ["# Generated. Do not edit or commit."]
    for key in KEYS:
        reference = versions[f"{key}_TAG"]
        raw = inspect_raw(reference)
        digest = f"sha256:{hashlib.sha256(raw).hexdigest()}"
        if not DIGEST_RE.fullmatch(digest):
            raise SystemExit(f"invalid resolved digest for {reference}")
        locked = f"{repository_part(reference)}@{digest}"
        records[key] = {"tag": reference, "digest": digest, "locked_ref": locked}
        env_lines.append(f"{key}={locked}")

    payload = {
        "schema_version": "1.0.0",
        "resolved_at_utc": datetime.now(UTC).isoformat(),
        "resolver": "docker buildx imagetools inspect --raw",
        "images": records,
    }
    args.lock_env.write_text("\n".join(env_lines) + "\n", encoding="utf-8")
    args.lock_json.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
