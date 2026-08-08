from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager
from typing import TypeVar

T = TypeVar("T")


class ResourceScheduler:
    """In-process bounded scheduler preserving eight workers with safe GPU slots."""

    def __init__(
        self,
        *,
        cpu_workers: int = 8,
        llm_gpu_slots: int = 1,
        embedding_gpu_slots: int = 1,
    ) -> None:
        if min(cpu_workers, llm_gpu_slots, embedding_gpu_slots) < 1:
            raise ValueError("resource slot counts must be positive")
        self._semaphores = {
            "cpu": asyncio.Semaphore(cpu_workers),
            "llm_gpu": asyncio.Semaphore(llm_gpu_slots),
            "embedding_gpu": asyncio.Semaphore(embedding_gpu_slots),
        }
        self._active = {key: 0 for key in self._semaphores}
        self._peaks = {key: 0 for key in self._semaphores}

    @asynccontextmanager
    async def slot(self, resource: str) -> AsyncIterator[None]:
        try:
            semaphore = self._semaphores[resource]
        except KeyError as exc:
            raise ValueError(f"unknown resource: {resource}") from exc
        async with semaphore:
            self._active[resource] += 1
            self._peaks[resource] = max(self._peaks[resource], self._active[resource])
            try:
                yield
            finally:
                self._active[resource] -= 1

    async def run(self, resource: str, awaitable: Awaitable[T]) -> T:
        async with self.slot(resource):
            return await awaitable

    def snapshot(self) -> dict[str, dict[str, int]]:
        return {
            key: {"active": self._active[key], "peak": self._peaks[key]} for key in self._semaphores
        }
