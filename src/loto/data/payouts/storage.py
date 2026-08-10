from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pandas as pd

from loto.data.payouts.contracts import PayoutFact


def write_payout_facts(facts: list[PayoutFact], output_dir: str | Path) -> dict[str, object]:
    """Materialize normalized payout facts without overwriting prior evidence."""
    if not facts:
        raise ValueError("facts must be non-empty")
    root = Path(output_dir)
    if root.exists():
        raise FileExistsError(f"refusing to overwrite normalized payout facts: {root}")
    root.mkdir(parents=True)

    records = [fact.model_dump(mode="json") for fact in facts]
    jsonl_path = root / "payout_facts.jsonl"
    with jsonl_path.open("x", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())

    parquet_path = root / "payout_facts.parquet"
    pd.DataFrame(records).to_parquet(parquet_path, index=False)

    manifest = {
        "schema_version": "payout-normalized-bundle-v1",
        "rows": len(records),
        "games": sorted({fact.game for fact in facts}),
        "source_raw_sha256": sorted({fact.raw_sha256 for fact in facts}),
        "files": ["payout_facts.jsonl", "payout_facts.parquet"],
    }
    manifest_path = root / "ARTIFACT_MANIFEST.json"
    with manifest_path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
        handle.flush()
        os.fsync(handle.fileno())

    artifact_paths = [jsonl_path, parquet_path, manifest_path]
    checksums = "".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in artifact_paths
    )
    sums_path = root / "SHA256SUMS"
    with sums_path.open("x", encoding="utf-8") as handle:
        handle.write(checksums)
        handle.flush()
        os.fsync(handle.fileno())

    return {
        "rows": len(records),
        "jsonl": str(jsonl_path),
        "parquet": str(parquet_path),
        "manifest": str(manifest_path),
        "sha256sums": str(sums_path),
    }
