from __future__ import annotations

from typing import Any

import httpx

from ..contracts import (
    Capability,
    EngineKind,
    HarnessStatus,
    HealthReport,
    LoadedModel,
    LoadRequest,
    ModelDescriptor,
)
from ..errors import EngineUnavailable
from .openai_compatible import OpenAICompatibleEngine


class LMStudioEngine(OpenAICompatibleEngine):
    kind = EngineKind.LMSTUDIO

    def __init__(
        self,
        endpoint: str = "http://127.0.0.1:1234",
        api_key: str | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float = 300,
    ) -> None:
        super().__init__(
            endpoint,
            api_key,
            transport=transport,
            timeout_seconds=timeout_seconds,
        )

    async def health(self) -> HealthReport:
        try:
            await self.http.request(
                "GET",
                f"{self.endpoint}/api/v1/models",
                headers=self.headers,
            )
            return HealthReport(
                engine=self.kind,
                endpoint=self.endpoint,
                status=HarnessStatus.VERIFIED,
            )
        except EngineUnavailable as exc:
            return HealthReport(
                engine=self.kind,
                endpoint=self.endpoint,
                status=HarnessStatus.BLOCKED,
                detail=str(exc),
            )

    async def discover(self) -> list[ModelDescriptor]:
        payload = await self.http.request(
            "GET",
            f"{self.endpoint}/api/v1/models",
            headers=self.headers,
        )
        raw_items = payload.get("models")
        items = raw_items if isinstance(raw_items, list) else []
        result: list[ModelDescriptor] = []
        for item in items:
            if not isinstance(item, dict) or not item.get("key"):
                continue
            model_type = item.get("type")
            capabilities = (
                {Capability.EMBEDDING}
                if model_type == "embedding"
                else {Capability.CHAT}
            )
            capability_data = item.get("capabilities")
            if isinstance(capability_data, dict):
                if capability_data.get("trained_for_tool_use") is True:
                    capabilities.add(Capability.TOOLS)
                if capability_data.get("vision") is True:
                    capabilities.add(Capability.VISION)
                if isinstance(capability_data.get("reasoning"), dict):
                    capabilities.add(Capability.REASONING)
            elif isinstance(capability_data, list):
                for capability in capability_data:
                    normalized = str(capability).lower()
                    if normalized in {"tool_use", "tools"}:
                        capabilities.add(Capability.TOOLS)
                    elif normalized in {"vision", "image"}:
                        capabilities.add(Capability.VISION)
                    elif normalized == "reasoning":
                        capabilities.add(Capability.REASONING)
            quant = item.get("quantization")
            quant_name = quant.get("name") if isinstance(quant, dict) else quant
            raw_instances = item.get("loaded_instances")
            instances = (
                [value for value in raw_instances if isinstance(value, dict)]
                if isinstance(raw_instances, list)
                else []
            )
            result.append(
                ModelDescriptor(
                    key=str(item["key"]),
                    display_name=(
                        str(item["display_name"])
                        if item.get("display_name") is not None
                        else None
                    ),
                    engine=self.kind,
                    endpoint=self.endpoint,
                    architecture=(
                        str(item["architecture"])
                        if item.get("architecture") is not None
                        else None
                    ),
                    quantization=str(quant_name) if quant_name else None,
                    declared_context=int(item.get("max_context_length") or 8192),
                    capabilities=capabilities,
                    status=HarnessStatus.DISCOVERED,
                    loaded_instances=instances,
                )
            )
        return result

    async def load(self, request: LoadRequest) -> LoadedModel:
        body: dict[str, Any] = {
            "model": request.model,
            "context_length": request.context_length,
            "echo_load_config": True,
        }
        optional = {
            "eval_batch_size": request.eval_batch_size,
            "flash_attention": request.flash_attention,
            "num_experts": request.num_experts,
            "offload_kv_cache_to_gpu": request.offload_kv_cache_to_gpu,
        }
        body.update({key: value for key, value in optional.items() if value is not None})
        payload = await self.http.request(
            "POST",
            f"{self.endpoint}/api/v1/models/load",
            headers=self.headers,
            json=body,
        )
        raw_config = payload.get("load_config")
        config: dict[str, Any] = raw_config if isinstance(raw_config, dict) else {}
        raw_load_seconds = payload.get("load_time_seconds")
        load_seconds = (
            float(raw_load_seconds)
            if isinstance(raw_load_seconds, int | float)
            else None
        )
        return LoadedModel(
            model=request.model,
            instance_id=str(payload.get("instance_id") or request.model),
            context_length=int(config.get("context_length") or request.context_length),
            status=(
                HarnessStatus.VERIFIED
                if payload.get("status") == "loaded"
                else HarnessStatus.DEGRADED
            ),
            load_seconds=load_seconds,
            applied_config=config,
        )

    async def unload(self, instance_id: str) -> None:
        await self.http.request(
            "POST",
            f"{self.endpoint}/api/v1/models/unload",
            headers=self.headers,
            json={"instance_id": instance_id},
        )
