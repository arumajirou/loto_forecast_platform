import asyncio
import json
from pathlib import Path

import pytest

from loto.harness.resources.leases import FileResourceLeaseManager
from loto.harness.resources.scheduler import ResourceScheduler


def test_scheduler_preserves_gpu_limit() -> None:
    async def scenario() -> None:
        scheduler = ResourceScheduler(cpu_workers=8, llm_gpu_slots=1, embedding_gpu_slots=1)

        async def task() -> None:
            async with scheduler.slot("llm_gpu"):
                await asyncio.sleep(0.01)

        await asyncio.gather(*(task() for _ in range(5)))
        assert scheduler.snapshot()["llm_gpu"]["peak"] == 1

    asyncio.run(scenario())


def test_file_lease_records_release(tmp_path: Path) -> None:
    manager = FileResourceLeaseManager(tmp_path)
    with manager.acquire("gpu:0", timeout_seconds=1) as path:
        data = json.loads(path.read_text())
        assert data["resource"] == "gpu:0"
    assert "released_at" in json.loads(path.read_text())


def test_file_lease_rejects_invalid_timeout(tmp_path: Path) -> None:
    manager = FileResourceLeaseManager(tmp_path)
    with pytest.raises(ValueError):
        with manager.acquire("gpu", timeout_seconds=0):
            pass
