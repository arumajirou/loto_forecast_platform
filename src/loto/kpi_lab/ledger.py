"""Append-only, hash-chained ledger for every lab experiment.

Two properties matter for a search that is allowed to stop early.

Completeness
    Every experiment is recorded, including the ones after the stopping threshold is
    crossed and the ones that failed. A ledger that stops writing when the answer is found
    cannot be audited for selection effects, because the denominator is missing.
Tamper evidence
    Each entry carries the SHA-256 of the previous entry, so removing or editing a record
    breaks the chain at a detectable point. This is not security against a determined
    attacker with write access; it is protection against the ordinary failure of a
    disappointing run being quietly dropped.

Entries are JSON lines, so the file stays readable and appendable under interruption
without a database.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from loto.data.lineage import utc_now_iso

__all__ = ["LedgerEntry", "LedgerIntegrity", "ExperimentLedger", "GENESIS_HASH"]

GENESIS_HASH = "0" * 64
_SCHEMA_VERSION = "1.0.0"


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


@dataclass(frozen=True)
class LedgerEntry:
    """One immutable record in the chain."""

    sequence: int
    recorded_at: str
    event: str
    session_id: str
    payload: dict[str, Any]
    previous_hash: str
    entry_hash: str = ""
    schema_version: str = _SCHEMA_VERSION

    def compute_hash(self) -> str:
        body = {
            "sequence": self.sequence,
            "recorded_at": self.recorded_at,
            "event": self.event,
            "session_id": self.session_id,
            "payload": self.payload,
            "previous_hash": self.previous_hash,
            "schema_version": self.schema_version,
        }
        return hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LedgerIntegrity:
    """Verification verdict for a ledger file."""

    valid: bool
    n_entries: int
    first_broken_sequence: int | None
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ExperimentLedger:
    """Append-only JSONL ledger with a SHA-256 chain."""

    def __init__(self, path: str | Path, *, session_id: str) -> None:
        self.path = Path(path)
        self.session_id = session_id
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._sequence, self._last_hash = self._tail()

    # -- state --------------------------------------------------------------------------

    def _tail(self) -> tuple[int, str]:
        if not self.path.exists():
            return 0, GENESIS_HASH
        last_seq, last_hash = 0, GENESIS_HASH
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                last_seq = int(record["sequence"])
                last_hash = str(record["entry_hash"])
        return last_seq, last_hash

    @property
    def sequence(self) -> int:
        return self._sequence

    @property
    def head_hash(self) -> str:
        return self._last_hash

    # -- writing ------------------------------------------------------------------------

    def append(self, event: str, payload: dict[str, Any]) -> LedgerEntry:
        """Append one entry, flushed and fsynced so an interrupt cannot lose it."""
        entry = LedgerEntry(
            sequence=self._sequence + 1,
            recorded_at=utc_now_iso(),
            event=event,
            session_id=self.session_id,
            payload=payload,
            previous_hash=self._last_hash,
        )
        entry = LedgerEntry(
            sequence=entry.sequence,
            recorded_at=entry.recorded_at,
            event=entry.event,
            session_id=entry.session_id,
            payload=entry.payload,
            previous_hash=entry.previous_hash,
            entry_hash=entry.compute_hash(),
        )
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(_canonical(entry.to_dict()) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self._sequence = entry.sequence
        self._last_hash = entry.entry_hash
        return entry

    # -- reading ------------------------------------------------------------------------

    def __iter__(self) -> Iterator[LedgerEntry]:
        if not self.path.exists():
            return iter(())
        entries: list[LedgerEntry] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                entries.append(
                    LedgerEntry(
                        sequence=int(record["sequence"]),
                        recorded_at=str(record["recorded_at"]),
                        event=str(record["event"]),
                        session_id=str(record["session_id"]),
                        payload=dict(record["payload"]),
                        previous_hash=str(record["previous_hash"]),
                        entry_hash=str(record["entry_hash"]),
                        schema_version=str(record.get("schema_version", _SCHEMA_VERSION)),
                    )
                )
        return iter(entries)

    def events(self, event: str) -> list[LedgerEntry]:
        return [entry for entry in self if entry.event == event]

    def count(self, event: str | None = None) -> int:
        return sum(1 for entry in self if event is None or entry.event == event)

    def verify(self) -> LedgerIntegrity:
        """Recompute the chain and report the first divergence, if any."""
        previous = GENESIS_HASH
        n = 0
        for entry in self:
            n += 1
            if entry.previous_hash != previous:
                return LedgerIntegrity(
                    False, n, entry.sequence, "previous_hash does not match the chain"
                )
            if entry.compute_hash() != entry.entry_hash:
                return LedgerIntegrity(
                    False, n, entry.sequence, "entry_hash does not match recomputed body"
                )
            previous = entry.entry_hash
        return LedgerIntegrity(True, n, None, "chain intact")
