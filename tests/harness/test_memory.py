from pathlib import Path

from loto.harness.memory.models import ClaimType, MemoryClaim, MemoryEvent
from loto.harness.memory.sqlite_store import SQLiteMemoryStore


def test_append_only_memory_and_status(tmp_path: Path) -> None:
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    try:
        event = MemoryEvent(
            event_id="e1",
            project="loto",
            task_id="t1",
            event_type="TEST_RESULT",
            payload={"status": "PASS", "exit_code": 0},
            source="pytest",
        )
        store.append_event(event)
        store.append_claim(
            MemoryClaim(
                claim_id="c1",
                project="loto",
                task_id="t1",
                claim_type=ClaimType.TEST_RESULT,
                statement="harness tests pass",
                source_event_id="e1",
                verified=True,
            )
        )
        hits = store.search_events("loto", "PASS")
        assert hits[0]["payload"]["exit_code"] == 0
        status = store.task_status("loto", "t1")
        assert status["claim_count"] == 1
        assert status["verified_claim_count"] == 1
    finally:
        store.close()
