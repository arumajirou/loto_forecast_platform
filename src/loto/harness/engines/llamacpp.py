from __future__ import annotations

import asyncio
import os
from collections.abc import Sequence
from pathlib import Path
from typing import BinaryIO

from ..contracts import EngineKind, HarnessStatus, HealthReport
from ..errors import EngineUnavailable, UnsafeOperation
from .openai_compatible import OpenAICompatibleEngine


class LlamaCppEngine(OpenAICompatibleEngine):
    kind = EngineKind.LLAMACPP

    async def health(self) -> HealthReport:
        try:
            await self.http.request(
                "GET",
                f"{self.endpoint}/health",
                headers=self.headers,
                accepted={200, 503},
            )
            models = await self.http.request(
                "GET",
                f"{self.endpoint}/v1/models",
                headers=self.headers,
            )
            status = HarnessStatus.VERIFIED if models.get("data") else HarnessStatus.DEGRADED
            return HealthReport(engine=self.kind, endpoint=self.endpoint, status=status)
        except EngineUnavailable as exc:
            return HealthReport(
                engine=self.kind,
                endpoint=self.endpoint,
                status=HarnessStatus.BLOCKED,
                detail=str(exc),
            )

    async def discover(self):  # type: ignore[override]
        discovered = await super().discover()
        return [model.model_copy(update={"engine": self.kind}) for model in discovered]


class LlamaCppLaunchConfig:
    """Build a safe llama-server command without invoking a shell."""

    def __init__(
        self,
        *,
        binary: str,
        model: str | None = None,
        models_dir: str | None = None,
        alias: str | None = None,
        host: str = "127.0.0.1",
        port: int = 17302,
        context_size: int = 65536,
        batch_size: int = 2048,
        ubatch_size: int = 512,
        parallel: int = 1,
        cache_ram_mib: int = 16384,
        ctx_checkpoints: int = 32,
        cache_type_k: str = "q8_0",
        cache_type_v: str = "q8_0",
        extra_args: Sequence[str] = (),
    ) -> None:
        if bool(model) == bool(models_dir):
            raise ValueError("provide exactly one of model or models_dir")
        if host == "0.0.0.0" and os.getenv("HARNESS_ALLOW_PUBLIC_BIND") != "1":
            raise UnsafeOperation("public llama.cpp bind requires HARNESS_ALLOW_PUBLIC_BIND=1")
        self.binary = binary
        self.model = model
        self.models_dir = models_dir
        self.alias = alias
        self.host = host
        self.port = port
        self.context_size = context_size
        self.batch_size = batch_size
        self.ubatch_size = ubatch_size
        self.parallel = parallel
        self.cache_ram_mib = cache_ram_mib
        self.ctx_checkpoints = ctx_checkpoints
        self.cache_type_k = cache_type_k
        self.cache_type_v = cache_type_v
        self.extra_args = tuple(extra_args)

    def command(self) -> list[str]:
        binary = str(Path(self.binary).expanduser())
        command = [
            binary,
            "--host",
            self.host,
            "--port",
            str(self.port),
            "--ctx-size",
            str(self.context_size),
            "--batch-size",
            str(self.batch_size),
            "--ubatch-size",
            str(self.ubatch_size),
            "--parallel",
            str(self.parallel),
            "--cache-ram",
            str(self.cache_ram_mib),
            "--ctx-checkpoints",
            str(self.ctx_checkpoints),
            "--cache-type-k",
            self.cache_type_k,
            "--cache-type-v",
            self.cache_type_v,
            "--cache-idle-slots",
            "--jinja",
        ]
        if self.model:
            command.extend(["--model", str(Path(self.model).expanduser())])
        else:
            command.extend(["--models-dir", str(Path(self.models_dir or "").expanduser())])
        if self.alias:
            command.extend(["--alias", self.alias])
        command.extend(self.extra_args)
        return command


class LlamaCppProcessManager:
    def __init__(self, config: LlamaCppLaunchConfig, log_path: str | Path) -> None:
        self.config = config
        self.log_path = Path(log_path)
        self.process: asyncio.subprocess.Process | None = None
        self._log_handle: BinaryIO | None = None

    async def start(self) -> int:
        if self.process and self.process.returncode is None:
            return self.process.pid or -1
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_handle = self.log_path.open("ab")
        self.process = await asyncio.create_subprocess_exec(
            *self.config.command(),
            stdout=self._log_handle,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,
        )
        return self.process.pid or -1

    async def stop(self, timeout_seconds: float = 15) -> None:
        if not self.process or self.process.returncode is not None:
            return
        self.process.terminate()
        try:
            await asyncio.wait_for(self.process.wait(), timeout=timeout_seconds)
        except TimeoutError:
            self.process.kill()
            await self.process.wait()
        finally:
            if self._log_handle:
                self._log_handle.close()
                self._log_handle = None
