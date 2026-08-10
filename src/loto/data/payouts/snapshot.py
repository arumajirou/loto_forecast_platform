from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

from loto.data.payouts.contracts import RawPayoutSnapshot


def materialize_raw_payout_snapshot(
    raw_bytes: bytes,
    output_dir: str | Path,
    *,
    source_url: str,
    observed_at: datetime,
    content_type: str,
    parser_version: str,
    raw_filename: str = "source.raw",
) -> RawPayoutSnapshot:
    """Write one immutable source snapshot and its metadata.

    The output directory must not already exist. This avoids turning a parser correction into an
    in-place rewrite of the original evidence. Callers create a new Run ID/path instead.
    """
    root = Path(output_dir)
    if root.exists():
        raise FileExistsError(f"refusing to overwrite payout snapshot: {root}")
    if Path(raw_filename).name != raw_filename or not raw_filename:
        raise ValueError("raw_filename must be a plain file name")
    root.mkdir(parents=True)
    raw_path = root / raw_filename
    with raw_path.open("xb") as handle:
        handle.write(raw_bytes)
        handle.flush()
        os.fsync(handle.fileno())
    digest = hashlib.sha256(raw_bytes).hexdigest()
    record = RawPayoutSnapshot(
        source_url=source_url,
        observed_at=observed_at,
        content_type=content_type,
        parser_version=parser_version,
        raw_filename=raw_filename,
        raw_sha256=digest,
        raw_bytes=len(raw_bytes),
    )
    metadata_path = root / "snapshot.json"
    metadata = json.dumps(record.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, indent=2)
    with metadata_path.open("x", encoding="utf-8") as handle:
        handle.write(metadata + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    sums = (
        f"{hashlib.sha256(raw_path.read_bytes()).hexdigest()}  {raw_filename}\n"
        f"{hashlib.sha256(metadata_path.read_bytes()).hexdigest()}  snapshot.json\n"
    )
    with (root / "SHA256SUMS").open("x", encoding="utf-8") as handle:
        handle.write(sums)
        handle.flush()
        os.fsync(handle.fileno())
    return record
