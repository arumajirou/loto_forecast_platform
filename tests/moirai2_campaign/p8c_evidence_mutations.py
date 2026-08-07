from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loto.moirai2_campaign.runtime_evidence_gate import (
    sha256_file,
    write_sha256_manifest,
)
from tests.moirai2_campaign.p8c_evidence_fixtures_core import _write_json

def _reseal(root: Path) -> None:
    (root / "SHA256SUMS").unlink(missing_ok=True)
    manifest_path = root / "ARTIFACT_MANIFEST.json"
    manifest_path.unlink(missing_ok=True)
    files = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    )
    _write_json(
        manifest_path,
        {
            "schema_version": "moirai2-p8-runtime-campaign-artifacts-v1",
            "files": files,
            "file_count": len(files),
        },
    )
    write_sha256_manifest(root, root / "SHA256SUMS")


def _rewrite_response_and_evidence(
    root: Path,
    *,
    case_name: str,
    label: str,
    response: dict[str, Any],
) -> None:
    response_path = root / f"cases/{case_name}/{label}/response.json"
    _write_json(response_path, response)
    evidence_path = root / f"cases/{case_name}/{label}/run_evidence.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["response"] = response
    evidence["response_sha256"] = sha256_file(response_path)
    _write_json(evidence_path, evidence)


