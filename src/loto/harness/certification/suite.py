from __future__ import annotations

import json
import math
import secrets
from dataclasses import dataclass

from ..contracts import (
    Capability,
    ChatRequest,
    ChatResponse,
    HarnessStatus,
    LoadRequest,
    Message,
    ModelDescriptor,
)
from ..engines.base import InferenceEngine
from ..profiles import ProfileRegistry


@dataclass(frozen=True)
class CertificationStep:
    name: str
    status: HarnessStatus
    detail: str = ""


class CertificationSuite:
    def __init__(
        self,
        engine: InferenceEngine,
        *,
        profile_mode: str = "auto",
        profiles: ProfileRegistry | None = None,
    ) -> None:
        self.engine = engine
        self.profile_mode = profile_mode
        self.profiles = profiles or ProfileRegistry()
        self.descriptor: ModelDescriptor | None = None

    async def _chat(self, request: ChatRequest) -> ChatResponse:
        if self.descriptor is None:
            return await self.engine.chat(request)
        application = self.profiles.apply(
            request,
            self.descriptor,
            mode=self.profile_mode,
            task_type=request.task_type,
        )
        return await self.engine.chat(application.request)

    async def _chat_smoke(self, model: str) -> bool:
        response = await self._chat(
            ChatRequest(
                model=model,
                messages=[Message(role="user", content="Reply with exactly HARNESS_SMOKE_OK")],
                temperature=0,
                max_tokens=32,
                task_type="chat",
            )
        )
        return "HARNESS_SMOKE_OK" in response.content

    async def _context_probe(self, model: str, context: int, utilization: float) -> bool:
        marker = f"NEEDLE_{secrets.token_hex(8).upper()}"
        target_tokens = max(512, int(context * utilization) - 256)
        filler_count = max(1, target_tokens - 128)
        half = filler_count // 2
        filler_a = "alpha " * half
        filler_b = "omega " * (filler_count - half)
        prompt = (
            "Read the entire payload and return only the exact marker found in the middle.\n"
            f"{filler_a}\nMARKER={marker}\n{filler_b}"
        )
        response = await self._chat(
            ChatRequest(
                model=model,
                messages=[Message(role="user", content=prompt)],
                temperature=0,
                max_tokens=64,
                task_type="long_context",
            )
        )
        return marker in response.content

    async def _structured_probe(self, model: str) -> bool:
        response = await self._chat(
            ChatRequest(
                model=model,
                messages=[
                    Message(
                        role="user",
                        content=(
                            "Return exactly one JSON object with keys status and integer value; "
                            "status must be VERIFIED and value must be 7."
                        ),
                    )
                ],
                temperature=0,
                max_tokens=128,
                task_type="structured",
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "certification",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "status": {"const": "VERIFIED"},
                                "value": {"const": 7},
                            },
                            "required": ["status", "value"],
                            "additionalProperties": False,
                        },
                    },
                },
            )
        )
        try:
            return json.loads(response.content) == {"status": "VERIFIED", "value": 7}
        except json.JSONDecodeError:
            return False

    async def _tool_probe(self, model: str) -> bool:
        response = await self._chat(
            ChatRequest(
                model=model,
                messages=[Message(role="user", content="Call certification_echo with value 7.")],
                temperature=0,
                max_tokens=128,
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": "certification_echo",
                            "description": "Return the supplied integer",
                            "parameters": {
                                "type": "object",
                                "properties": {"value": {"type": "integer", "const": 7}},
                                "required": ["value"],
                                "additionalProperties": False,
                            },
                        },
                    }
                ],
                tool_choice="required",
                task_type="tools",
            )
        )
        for tool_call in response.tool_calls:
            function = tool_call.get("function") if isinstance(tool_call, dict) else None
            if isinstance(function, dict) and function.get("name") == "certification_echo":
                return True
        return False

    async def _embedding_probe(self, model: str) -> bool:
        payload = await self.engine.raw_post(
            "/v1/embeddings", {"model": model, "input": "search_query: harness certification"}
        )
        data = payload.get("data")
        if not isinstance(data, list) or not data or not isinstance(data[0], dict):
            return False
        vector = data[0].get("embedding")
        return (
            isinstance(vector, list)
            and len(vector) > 0
            and all(isinstance(value, (int, float)) and math.isfinite(value) for value in vector)
        )

    async def run(
        self,
        model: str,
        contexts: list[int] | None = None,
        *,
        deep_context: bool = False,
        context_utilization: float = 0.90,
        context_repetitions: int = 3,
    ) -> list[CertificationStep]:
        if not 0.50 <= context_utilization <= 0.95:
            raise ValueError("context utilization must be between 0.50 and 0.95")
        if not 1 <= context_repetitions <= 10:
            raise ValueError("context repetitions must be between 1 and 10")
        steps: list[CertificationStep] = []
        health = await self.engine.health()
        steps.append(CertificationStep("health", health.status, health.detail or ""))
        if health.status not in {HarnessStatus.VERIFIED, HarnessStatus.DEGRADED}:
            return steps

        models = await self.engine.discover()
        descriptor = next((item for item in models if item.key == model), None)
        steps.append(
            CertificationStep(
                "discover",
                HarnessStatus.VERIFIED if descriptor else HarnessStatus.FAILED,
                model,
            )
        )
        if descriptor is None:
            return steps
        self.descriptor = descriptor
        resolved_profile = self.profiles.resolve(descriptor)
        steps.append(
            CertificationStep(
                "profile_resolved",
                HarnessStatus.VERIFIED,
                f"profile={resolved_profile.profile_id};mode={self.profile_mode}",
            )
        )

        managed_externally = False
        successful_contexts: list[int] = []
        for context in contexts or [8192, 16384, 32768, 49152, 65536]:
            if context > descriptor.declared_context:
                steps.append(
                    CertificationStep(
                        f"load_{context}",
                        HarnessStatus.BLOCKED,
                        f"declared_context={descriptor.declared_context}",
                    )
                )
                break
            instance_id: str | None = None
            try:
                loaded = await self.engine.load(LoadRequest(model=model, context_length=context))
                instance_id = loaded.instance_id
                steps.append(
                    CertificationStep(
                        f"load_{context}",
                        loaded.status,
                        f"applied_context={loaded.context_length}",
                    )
                )
                probe_ok = False
                if Capability.EMBEDDING in descriptor.capabilities:
                    probe_ok = await self._embedding_probe(model)
                    steps.append(
                        CertificationStep(
                            f"embedding_{context}",
                            HarnessStatus.VERIFIED if probe_ok else HarnessStatus.FAILED,
                        )
                    )
                else:
                    probe_ok = await self._chat_smoke(model)
                    steps.append(
                        CertificationStep(
                            f"inference_{context}",
                            HarnessStatus.VERIFIED if probe_ok else HarnessStatus.FAILED,
                        )
                    )
                    if probe_ok and deep_context:
                        trial_results: list[bool] = []
                        for trial in range(1, context_repetitions + 1):
                            trial_ok = await self._context_probe(
                                model, loaded.context_length, context_utilization
                            )
                            trial_results.append(trial_ok)
                            steps.append(
                                CertificationStep(
                                    f"context_trial_{context}_{trial}",
                                    HarnessStatus.VERIFIED if trial_ok else HarnessStatus.FAILED,
                                    f"utilization={context_utilization}",
                                )
                            )
                        required_passes = math.ceil(context_repetitions * 0.8)
                        passed_trials = sum(trial_results)
                        context_ok = passed_trials >= required_passes
                        steps.append(
                            CertificationStep(
                                f"context_probe_{context}",
                                HarnessStatus.VERIFIED if context_ok else HarnessStatus.FAILED,
                                (
                                    f"utilization={context_utilization};"
                                    f"passed={passed_trials}/{context_repetitions};"
                                    f"required={required_passes}"
                                ),
                            )
                        )
                        probe_ok = probe_ok and context_ok
                if loaded.status == HarnessStatus.VERIFIED and probe_ok:
                    successful_contexts.append(loaded.context_length)
            except NotImplementedError:
                managed_externally = True
                steps.append(CertificationStep("load_managed_externally", HarnessStatus.DEGRADED))
                break
            except Exception as exc:
                steps.append(CertificationStep(f"load_{context}", HarnessStatus.FAILED, str(exc)))
                break
            finally:
                if instance_id:
                    try:
                        await self.engine.unload(instance_id)
                        steps.append(
                            CertificationStep(
                                f"unload_{context}", HarnessStatus.VERIFIED, instance_id
                            )
                        )
                    except Exception as exc:
                        steps.append(
                            CertificationStep(f"unload_{context}", HarnessStatus.FAILED, str(exc))
                        )

        final_instance: str | None = None
        if not managed_externally and successful_contexts:
            target = max(successful_contexts)
            try:
                loaded = await self.engine.load(LoadRequest(model=model, context_length=target))
                final_instance = loaded.instance_id
            except Exception as exc:
                steps.append(CertificationStep("final_load", HarnessStatus.FAILED, str(exc)))

        try:
            if Capability.EMBEDDING in descriptor.capabilities:
                return steps
            if not final_instance and not managed_externally:
                steps.append(
                    CertificationStep(
                        "capability_probe",
                        HarnessStatus.BLOCKED,
                        "no successfully loaded context",
                    )
                )
                return steps
            if Capability.JSON_SCHEMA in descriptor.capabilities:
                structured_ok = await self._structured_probe(model)
                steps.append(
                    CertificationStep(
                        "structured_output",
                        HarnessStatus.VERIFIED if structured_ok else HarnessStatus.FAILED,
                    )
                )
            if Capability.TOOLS in descriptor.capabilities:
                tool_ok = await self._tool_probe(model)
                steps.append(
                    CertificationStep(
                        "tool_call",
                        HarnessStatus.VERIFIED if tool_ok else HarnessStatus.FAILED,
                    )
                )
        except Exception as exc:
            steps.append(CertificationStep("capability_probe", HarnessStatus.FAILED, str(exc)))
        finally:
            if final_instance:
                try:
                    await self.engine.unload(final_instance)
                    steps.append(CertificationStep("final_unload", HarnessStatus.VERIFIED))
                except Exception as exc:
                    steps.append(CertificationStep("final_unload", HarnessStatus.FAILED, str(exc)))
        return steps
