#!/usr/bin/env python3
"""Resolve current Hugging Face model HEAD commits into a fail-closed manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from huggingface_hub import HfApi
from huggingface_hub.errors import HfHubHTTPError

FULL_COMMIT_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("manifest root must be an object")
    return data


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--revision", default="main")
    parser.add_argument(
        "--verified-at",
        help=("Fixed ISO-8601 UTC verification timestamp. Defaults to the current time."),
    )
    args = parser.parse_args()

    template = load_json(args.template)
    pins = template.get("pins")

    if not isinstance(pins, list) or not pins:
        raise SystemExit("BLOCKED: template has no pins")

    api = HfApi()
    if args.verified_at:
        try:
            parsed_verified_at = datetime.fromisoformat(args.verified_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise SystemExit(f"BLOCKED: invalid --verified-at timestamp: {exc}") from exc

        if parsed_verified_at.tzinfo is None:
            raise SystemExit("BLOCKED: --verified-at must include a timezone")

        verified_at = parsed_verified_at.astimezone(UTC).isoformat()
    else:
        verified_at = datetime.now(UTC).isoformat()
    resolved: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    seen_model_ids: set[str] = set()
    seen_repo_ids: set[str] = set()

    for pin in pins:
        if not isinstance(pin, dict):
            errors.append(
                {
                    "model_id": "",
                    "repo_id": "",
                    "error": "pin entry must be an object",
                }
            )
            continue

        model_id = str(pin.get("model_id", "")).strip()
        repo_id = str(pin.get("repo_id", "")).strip()

        if not model_id or not repo_id:
            errors.append(
                {
                    "model_id": model_id,
                    "repo_id": repo_id,
                    "error": "model_id and repo_id are required",
                }
            )
            continue

        if model_id in seen_model_ids:
            errors.append(
                {
                    "model_id": model_id,
                    "repo_id": repo_id,
                    "error": "duplicate model_id",
                }
            )
            continue

        if repo_id in seen_repo_ids:
            errors.append(
                {
                    "model_id": model_id,
                    "repo_id": repo_id,
                    "error": "duplicate repo_id",
                }
            )
            continue

        seen_model_ids.add(model_id)
        seen_repo_ids.add(repo_id)

        try:
            info = api.model_info(
                repo_id=repo_id,
                revision=args.revision,
                files_metadata=False,
            )
        except HfHubHTTPError as exc:
            errors.append(
                {
                    "model_id": model_id,
                    "repo_id": repo_id,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        except Exception as exc:
            errors.append(
                {
                    "model_id": model_id,
                    "repo_id": repo_id,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue

        resolved_repo_id = str(getattr(info, "id", "") or repo_id)
        revision = str(getattr(info, "sha", "") or "").lower()
        last_modified = getattr(info, "last_modified", None)

        if resolved_repo_id.lower() != repo_id.lower():
            errors.append(
                {
                    "model_id": model_id,
                    "repo_id": repo_id,
                    "error": (f"repository identity mismatch: API returned {resolved_repo_id!r}"),
                }
            )
            continue

        if not FULL_COMMIT_RE.fullmatch(revision):
            errors.append(
                {
                    "model_id": model_id,
                    "repo_id": repo_id,
                    "error": f"invalid full commit id returned: {revision!r}",
                }
            )
            continue

        source = f"https://huggingface.co/{repo_id}/commit/{revision}"

        resolved.append(
            {
                "model_id": model_id,
                "repo_id": repo_id,
                "revision": revision,
                "source": source,
                "verified_at": verified_at,
            }
        )

        evidence_rows.append(
            {
                "model_id": model_id,
                "requested_repo_id": repo_id,
                "resolved_repo_id": resolved_repo_id,
                "requested_revision": args.revision,
                "resolved_revision": revision,
                "last_modified": (
                    last_modified.isoformat()
                    if hasattr(last_modified, "isoformat")
                    else str(last_modified or "")
                ),
                "source": source,
                "verified_at": verified_at,
            }
        )

    evidence = {
        "schema_version": 1,
        "generated_at": verified_at,
        "requested_revision": args.revision,
        "template": str(args.template),
        "template_sha256": sha256_file(args.template),
        "expected_pins": len(pins),
        "resolved_pins": len(resolved),
        "failed_pins": len(errors),
        "results": evidence_rows,
        "errors": errors,
    }

    write_json(args.evidence, evidence)

    if errors or len(resolved) != len(pins):
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "expected": len(pins),
                    "resolved": len(resolved),
                    "failed": len(errors),
                    "evidence": str(args.evidence),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2

    output = {
        "schema_version": template.get("schema_version", 1),
        "generated_at": verified_at,
        "pins": sorted(resolved, key=lambda row: row["model_id"]),
    }
    write_json(args.output, output)

    print(
        json.dumps(
            {
                "status": "PASS",
                "pins": len(resolved),
                "output": str(args.output),
                "output_sha256": sha256_file(args.output),
                "evidence": str(args.evidence),
                "evidence_sha256": sha256_file(args.evidence),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
