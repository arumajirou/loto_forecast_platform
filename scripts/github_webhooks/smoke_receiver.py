from __future__ import annotations

import argparse
import hashlib
import hmac
import json
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

from loto.github_webhooks.config import load_receiver_policy
from loto.github_webhooks.security import SecretKey, SecretRing
from loto.github_webhooks.service import ReceiverService
from loto.github_webhooks.store import WebhookStore

DELIVERY_ID = UUID("11111111-2222-4333-8444-555555555555")
FIXTURE_SECRET = hashlib.sha256(b"github-webhook-foundation-fixture").digest()


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build_manifest(output: Path) -> dict[str, object]:
    files = []
    for path in sorted(output.iterdir()):
        if path.name in {"ARTIFACT_MANIFEST.json", "SHA256SUMS"} or not path.is_file():
            continue
        data = path.read_bytes()
        files.append(
            {"path": path.name, "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        )
    return {"schema_version": 1, "files": files}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a signed local GitHub webhook smoke")
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.output.exists():
        raise SystemExit("output already exists")
    args.output.mkdir(parents=True)

    policy = load_receiver_policy(args.policy).model_copy(update={"enabled": True})
    payload = {
        "action": "opened",
        "repository": {
            "id": policy.repository.repository_id,
            "full_name": policy.repository.repository_full_name,
        },
        "sender": {"login": "fixture-user"},
        "issue": {
            "number": 1,
            "state": "open",
            "state_reason": None,
            "labels": [{"name": "test"}],
            "assignees": [],
            "user": {"login": "fixture-user"},
            "html_url": "https://github.com/arumajirou/loto_forecast_platform/issues/1",
        },
    }
    raw_body = canonical_json(payload)
    signature = "sha256=" + hmac.new(FIXTURE_SECRET, raw_body, hashlib.sha256).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "X-GitHub-Event": "issues",
        "X-GitHub-Delivery": str(DELIVERY_ID),
        "X-Hub-Signature-256": signature,
        "User-Agent": "GitHub-Hookshot/foundation-fixture",
    }

    with TemporaryDirectory(prefix="github-webhook-smoke-") as temporary:
        store = WebhookStore(
            Path(temporary) / "receiver.sqlite3",
            max_attempts=policy.max_attempts,
            base_backoff_seconds=policy.base_backoff_seconds,
            max_backoff_seconds=policy.max_backoff_seconds,
        )
        service = ReceiverService(
            policy=policy,
            secrets=SecretRing(SecretKey("fixture-active", FIXTURE_SECRET)),
            store=store,
        )
        received_at = datetime(2026, 8, 6, 9, 30, tzinfo=UTC)
        first = service.receive(
            raw_body=raw_body,
            raw_headers=headers,
            received_at=received_at,
            trace_id="1" * 32,
        )
        duplicate = service.receive(
            raw_body=raw_body,
            raw_headers=headers,
            received_at=received_at,
            trace_id="2" * 32,
        )
        report = {
            "schema_version": 1,
            "status": "PASS"
            if first.status_code == 202
            and duplicate.status_code == 200
            and store.delivery_count() == 1
            and store.outbox_count() == 1
            else "FAIL",
            "first": first.model_dump(mode="json"),
            "duplicate": duplicate.model_dump(mode="json"),
            "delivery_count": store.delivery_count(),
            "outbox_count": store.outbox_count(),
            "queue_depth": store.queue_depth(),
            "raw_payload_persisted": False,
            "signature_persisted": False,
            "secret_persisted": False,
        }
    write_json(args.output / "SMOKE_REPORT.json", report)
    manifest = build_manifest(args.output)
    write_json(args.output / "ARTIFACT_MANIFEST.json", manifest)
    lines = [f"{item['sha256']}  {item['path']}" for item in manifest["files"]]
    (args.output / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
