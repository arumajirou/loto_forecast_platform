from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import httpx

from ..errors import EngineUnavailable


class HttpJsonClient:
    def __init__(
        self,
        *,
        timeout_seconds: float = 120,
        retries: int = 2,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._retries = retries
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            transport=transport,
        )

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
        accepted: set[int] | None = None,
    ) -> dict[str, Any]:
        accepted_codes = accepted or {200}
        last_error: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                response = await self._client.request(
                    method,
                    url,
                    headers=headers,
                    json=json,
                )
                if response.status_code not in accepted_codes:
                    raise EngineUnavailable(
                        f"{method} {url} returned {response.status_code}: "
                        f"{response.text[:500]}"
                    )
                if not response.content:
                    return {}
                payload = response.json()
                if not isinstance(payload, dict):
                    raise EngineUnavailable(f"expected JSON object from {url}")
                return payload
            except (httpx.HTTPError, ValueError, EngineUnavailable) as exc:
                last_error = exc
                if attempt >= self._retries:
                    break
                await asyncio.sleep(0.2 * (2**attempt))
        raise EngineUnavailable(str(last_error)) from last_error

    async def stream_bytes(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
        accepted: set[int] | None = None,
    ) -> AsyncIterator[bytes]:
        accepted_codes = accepted or {200}
        try:
            async with self._client.stream(method, url, headers=headers, json=json) as response:
                if response.status_code not in accepted_codes:
                    body = (await response.aread()).decode("utf-8", errors="replace")
                    raise EngineUnavailable(
                        f"{method} {url} returned {response.status_code}: {body[:500]}"
                    )
                async for chunk in response.aiter_bytes():
                    if chunk:
                        yield chunk
        except httpx.HTTPError as exc:
            raise EngineUnavailable(str(exc)) from exc

    async def close(self) -> None:
        await self._client.aclose()
