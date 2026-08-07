from __future__ import annotations

import hashlib
import json
import random
import re
import secrets
import statistics
from dataclasses import dataclass, field
from typing import Any

from ..contracts import (
    Capability,
    ChatRequest,
    LoadRequest,
    Message,
    ModelDescriptor,
)
from ..engines.base import InferenceEngine
from ..profiles import ProfileRegistry

BENCHMARK_VERSION = "profile-ab-smoke-v3"
DEFAULT_MINIMUM_ACHIEVEMENT_RATE = 0.80

PRIMARY_CRITERIA: dict[str, str] = {
    "instruction": "exact_match",
    "reasoning": "correctness",
    "coding": "behavior",
    "long_context": "marker_found",
    "structured": "schema_match",
    "tools": "arguments_match",
}
CONTRACT_CRITERIA: dict[str, str] = {
    "instruction": "exact_match",
    "reasoning": "format_compliance",
    "coding": "format_compliance",
    "long_context": "format_compliance",
    "structured": "json_parseable",
    "tools": "function_name_match",
}
DEFAULT_CRITICAL_TASK_FLOORS: dict[str, float] = {
    "instruction": 1.00,
    "reasoning": 0.80,
    "coding": 0.80,
    "long_context": 0.80,
    "structured": 0.80,
    "tools": 0.80,
}
_SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),
    re.compile(r"\bsk-[0-9A-Za-z_-]{12,}\b"),
)


def _mask_secrets(value: str) -> str:
    masked = value
    for pattern in _SECRET_PATTERNS:
        masked = pattern.sub("[SECRET_MASKED]", masked)
    return masked


def _excerpt(value: str | None, limit: int = 512) -> str | None:
    if value is None:
        return None
    masked = _mask_secrets(value)
    if len(masked) <= limit:
        return masked
    return masked[:limit] + "...[TRUNCATED]"


def _sha256_text(value: str | None) -> str | None:
    if value is None:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _median_or_infinity(value: Any) -> float:
    latency = value.get("median_latency_seconds")
    return float(latency) if latency is not None else float("inf")


@dataclass
class TaskAggregate:
    attempts: int = 0
    successes: int = 0
    latencies: list[float] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    errors: list[str] = field(default_factory=list)
    criteria_successes: dict[str, int] = field(default_factory=dict)
    trials: list[dict[str, Any]] = field(default_factory=list)

    def add(
        self,
        success: bool,
        response: Any | None = None,
        error: str | None = None,
        criteria: dict[str, bool] | None = None,
    ) -> None:
        self.attempts += 1
        self.successes += int(success)
        criteria = criteria or {"task_success": success}
        for name, passed in criteria.items():
            self.criteria_successes[name] = self.criteria_successes.get(name, 0) + int(passed)

        trial: dict[str, Any] = {
            "attempt": self.attempts,
            "success": success,
            "criteria": criteria,
        }
        if response is not None:
            if response.timings.total_seconds is not None:
                latency = float(response.timings.total_seconds)
                self.latencies.append(latency)
                trial["latency_seconds"] = latency
            self.prompt_tokens += response.usage.prompt_tokens
            self.completion_tokens += response.usage.completion_tokens
            self.cached_tokens += response.usage.cached_tokens
            trial.update(
                {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "cached_tokens": response.usage.cached_tokens,
                    "finish_reason": response.finish_reason,
                    "response_excerpt": _excerpt(response.content),
                    "response_sha256": _sha256_text(response.content),
                    "reasoning_excerpt": _excerpt(response.reasoning_content),
                    "reasoning_sha256": _sha256_text(response.reasoning_content),
                    "tool_call_count": len(response.tool_calls),
                }
            )
        if error:
            self.errors.append(error)
            trial["error"] = _excerpt(error, limit=256)
        self.trials.append(trial)

    def as_dict(self) -> dict[str, Any]:
        return {
            "attempts": self.attempts,
            "successes": self.successes,
            "success_rate": self.successes / self.attempts if self.attempts else 0.0,
            "criteria_success_rates": {
                name: count / self.attempts if self.attempts else 0.0
                for name, count in sorted(self.criteria_successes.items())
            },
            "median_latency_seconds": statistics.median(self.latencies) if self.latencies else None,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cached_tokens": self.cached_tokens,
            "cache_hit_rate": (
                self.cached_tokens / self.prompt_tokens
                if self.prompt_tokens
                else 0.0
            ),
            "errors": self.errors,
            "trials": self.trials,
        }


class ProfileABEvaluator:
    def __init__(
        self,
        engine: InferenceEngine,
        descriptor: ModelDescriptor,
        *,
        profiles: ProfileRegistry | None = None,
    ) -> None:
        self.engine = engine
        self.descriptor = descriptor
        self.profiles = profiles or ProfileRegistry()

    async def _invoke(
        self,
        request: ChatRequest,
        mode: str,
    ) -> tuple[Any, dict[str, Any]]:
        application = self.profiles.apply(
            request,
            self.descriptor,
            mode=mode,
            task_type=request.task_type,
        )
        response = await self.engine.chat(application.request)
        return response, {
            "profile_id": application.profile_id,
            "family": application.family,
            "mode": application.mode,
            "task_type": application.task_type,
            "changes": list(application.changes),
            "expected_effects": list(application.expected_effects),
            "request": application.request.model_dump(mode="json", exclude_none=True),
        }

    async def _exact(
        self,
        mode: str,
    ) -> tuple[bool, Any, dict[str, Any], dict[str, bool]]:
        response, applied = await self._invoke(
            ChatRequest(
                model=self.descriptor.key,
                messages=[Message(role="user", content="Reply with exactly PROFILE_AB_OK")],
                temperature=0.2,
                max_tokens=32,
                task_type="chat",
            ),
            mode,
        )
        success = response.content.strip() == "PROFILE_AB_OK"
        return success, response, applied, {"exact_match": success}

    async def _reasoning(
        self,
        mode: str,
    ) -> tuple[bool, Any, dict[str, Any], dict[str, bool]]:
        response, applied = await self._invoke(
            ChatRequest(
                model=self.descriptor.key,
                messages=[
                    Message(
                        role="user",
                        content=(
                            "Compute (17 + 29) * 3 - 8. "
                            "Return only the final integer."
                        ),
                    )
                ],
                temperature=0.2,
                max_tokens=128,
                task_type="reasoning",
            ),
            mode,
        )
        stripped = response.content.strip()
        integers = re.findall(r"(?<![\w.])-?\d+(?![\w.])", stripped)
        correctness = bool(integers and integers[-1] == "130")
        format_compliance = stripped == "130"
        success = correctness and format_compliance
        return success, response, applied, {
            "correctness": correctness,
            "format_compliance": format_compliance,
        }

    async def _coding(
        self,
        mode: str,
    ) -> tuple[bool, Any, dict[str, Any], dict[str, bool]]:
        response, applied = await self._invoke(
            ChatRequest(
                model=self.descriptor.key,
                messages=[
                    Message(
                        role="user",
                        content=(
                            "Fix this Python function. Return only the corrected function.\n"
                            "def add(a: int, b: int) -> int:\n"
                            "    return a - b"
                        ),
                    )
                ],
                temperature=0.2,
                max_tokens=256,
                task_type="coding",
            ),
            mode,
        )
        normalized = response.content.replace(" ", "")
        behavior = "returna+b" in normalized and "returna-b" not in normalized
        format_compliance = "defadd(" in normalized
        success = behavior and format_compliance
        return success, response, applied, {
            "behavior": behavior,
            "format_compliance": format_compliance,
        }

    async def _structured(
        self,
        mode: str,
    ) -> tuple[bool, Any, dict[str, Any], dict[str, bool]]:
        response, applied = await self._invoke(
            ChatRequest(
                model=self.descriptor.key,
                messages=[
                    Message(
                        role="user",
                        content="Return JSON with status=VERIFIED and value=7.",
                    )
                ],
                temperature=0.1,
                max_tokens=128,
                task_type="structured",
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "profile_ab",
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
            ),
            mode,
        )
        parseable = False
        schema_match = False
        try:
            parsed = json.loads(response.content)
            parseable = True
            schema_match = parsed == {"status": "VERIFIED", "value": 7}
        except json.JSONDecodeError:
            pass
        success = parseable and schema_match
        return success, response, applied, {
            "json_parseable": parseable,
            "schema_match": schema_match,
        }

    async def _tool(
        self,
        mode: str,
    ) -> tuple[bool, Any, dict[str, Any], dict[str, bool]]:
        response, applied = await self._invoke(
            ChatRequest(
                model=self.descriptor.key,
                messages=[Message(role="user", content="Call profile_echo with value 7.")],
                temperature=0.1,
                max_tokens=128,
                task_type="tools",
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": "profile_echo",
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
            ),
            mode,
        )
        name_match = False
        argument_match = False
        for call in response.tool_calls:
            if not isinstance(call, dict) or not isinstance(call.get("function"), dict):
                continue
            function = call["function"]
            if function.get("name") != "profile_echo":
                continue
            name_match = True
            arguments = function.get("arguments", {})
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {}
            argument_match = isinstance(arguments, dict) and arguments.get("value") == 7
        success = name_match and argument_match
        return success, response, applied, {
            "function_name_match": name_match,
            "arguments_match": argument_match,
        }

    async def _context(
        self,
        mode: str,
        context_tokens: int,
        utilization: float,
    ) -> tuple[bool, Any, dict[str, Any], dict[str, bool]]:
        marker = f"PROFILE_NEEDLE_{secrets.token_hex(6).upper()}"
        target = max(512, int(context_tokens * utilization) - 256)
        filler_count = max(1, target - 128)
        half = filler_count // 2
        prompt = (
            "Return exactly the identifier value inside the <target> element. "
            "Do not include XML tags, a MARKER= prefix, prose, Markdown, or code fences.\n"
            + "alpha " * half
            + f"\n<target>{marker}</target>\n"
            + "omega " * (filler_count - half)
        )
        response, applied = await self._invoke(
            ChatRequest(
                model=self.descriptor.key,
                messages=[Message(role="user", content=prompt)],
                temperature=0.2,
                max_tokens=64,
                task_type="long_context",
            ),
            mode,
        )
        marker_found = marker in response.content
        exact_marker = response.content.strip() == marker
        success = marker_found and exact_marker
        return success, response, applied, {
            "marker_found": marker_found,
            "format_compliance": exact_marker,
        }

    @staticmethod
    def _task_floor(task_name: str) -> float:
        return DEFAULT_CRITICAL_TASK_FLOORS.get(task_name, 0.80)

    @staticmethod
    def _mode_latency(result: dict[str, Any]) -> float:
        return sum(_median_or_infinity(task) for task in result["tasks"].values())

    @staticmethod
    def _mode_completion_tokens(result: dict[str, Any]) -> int:
        return sum(int(task["completion_tokens"]) for task in result["tasks"].values())

    @classmethod
    def _mode_rank(cls, name: str, result: dict[str, Any]) -> tuple[Any, ...]:
        task_rates = [float(task["success_rate"]) for task in result["tasks"].values()]
        minimum_task_rate = min(task_rates, default=0.0)
        return (
            float(result["achievement_rate"]),
            minimum_task_rate,
            float(result["stability_score"]),
            -cls._mode_latency(result),
            -cls._mode_completion_tokens(result),
            1 if name == "generic" else 0,
        )

    @classmethod
    def _recommend_mode_for_task(
        cls,
        task_name: str,
        results: dict[str, Any],
    ) -> str | None:
        eligible = {
            mode: result
            for mode, result in results.items()
            if result["tasks"].get(task_name, {}).get("success_rate", 0.0)
            >= cls._task_floor(task_name)
        }
        if not eligible:
            return None
        return max(
            eligible,
            key=lambda mode: (
                eligible[mode]["tasks"][task_name]["success_rate"],
                -_median_or_infinity(eligible[mode]["tasks"][task_name]),
                -eligible[mode]["tasks"][task_name]["completion_tokens"],
                1 if mode == "generic" else 0,
            ),
        )

    async def run(
        self,
        *,
        modes: list[str],
        repetitions: int = 3,
        context_tokens: int = 16384,
        context_utilization: float = 0.5,
        seed: int = 1,
    ) -> dict[str, Any]:
        if not 1 <= repetitions <= 20:
            raise ValueError("repetitions must be between 1 and 20")
        if not modes:
            raise ValueError("at least one mode is required")

        task_names = ["instruction", "reasoning", "coding", "long_context"]
        if Capability.CHAT in self.descriptor.capabilities:
            task_names.append("structured")
        if Capability.TOOLS in self.descriptor.capabilities:
            task_names.append("tools")

        aggregates: dict[str, dict[str, TaskAggregate]] = {
            mode: {task_name: TaskAggregate() for task_name in task_names}
            for mode in modes
        }
        applications: dict[str, dict[str, Any]] = {mode: {} for mode in modes}
        execution_order: list[dict[str, Any]] = []
        loaded_instance: str | None = None
        try:
            try:
                loaded = await self.engine.load(
                    LoadRequest(model=self.descriptor.key, context_length=context_tokens)
                )
                loaded_instance = loaded.instance_id
            except NotImplementedError:
                pass

            for repetition_index in range(repetitions):
                mode_order = list(modes)
                random.Random(seed + repetition_index).shuffle(mode_order)
                for mode_position, mode in enumerate(mode_order):
                    task_order = list(task_names)
                    random.Random(seed * 1000 + repetition_index * 100 + mode_position).shuffle(
                        task_order
                    )
                    execution_order.append(
                        {
                            "repetition": repetition_index + 1,
                            "mode": mode,
                            "task_order": task_order,
                        }
                    )
                    for task_name in task_order:
                        try:
                            if task_name == "instruction":
                                success, response, applied, criteria = await self._exact(mode)
                            elif task_name == "reasoning":
                                success, response, applied, criteria = await self._reasoning(mode)
                            elif task_name == "coding":
                                success, response, applied, criteria = await self._coding(mode)
                            elif task_name == "structured":
                                success, response, applied, criteria = await self._structured(mode)
                            elif task_name == "tools":
                                success, response, applied, criteria = await self._tool(mode)
                            else:
                                success, response, applied, criteria = await self._context(
                                    mode, context_tokens, context_utilization
                                )
                            aggregates[mode][task_name].add(
                                success,
                                response,
                                criteria=criteria,
                            )
                            applications[mode].setdefault(task_name, applied)
                        except Exception as exc:
                            aggregates[mode][task_name].add(False, error=str(exc))
        finally:
            if loaded_instance:
                await self.engine.unload(loaded_instance)

        weights = {
            "instruction": 0.10,
            "reasoning": 0.20,
            "coding": 0.25,
            "structured": 0.15,
            "tools": 0.15,
            "long_context": 0.15,
        }
        results: dict[str, Any] = {}
        for mode in modes:
            tasks = aggregates[mode]
            task_payload = {name: value.as_dict() for name, value in tasks.items()}
            attempts = sum(value.attempts for value in tasks.values())
            successes = sum(value.successes for value in tasks.values())
            rates = [
                value.successes / value.attempts
                for value in tasks.values()
                if value.attempts
            ]
            stability = (
                1.0 - statistics.pstdev(rates)
                if len(rates) > 1
                else (rates[0] if rates else 0.0)
            )
            available_weight = sum(weights[name] for name in tasks)
            achievement_rate = (
                sum(
                    weights[name] * (aggregate.successes / aggregate.attempts)
                    for name, aggregate in tasks.items()
                    if aggregate.attempts
                )
                / available_weight
                if available_weight
                else 0.0
            )
            failed_critical_tasks = [
                name
                for name, task in task_payload.items()
                if task["success_rate"] < self._task_floor(name)
            ]
            semantic_rates: dict[str, float] = {}
            contract_rates: dict[str, float] = {}
            task_failure_classification: dict[str, str] = {}
            for name, task in task_payload.items():
                criteria_rates = task.get("criteria_success_rates", {})
                semantic_key = PRIMARY_CRITERIA.get(name, "task_success")
                contract_key = CONTRACT_CRITERIA.get(name, "task_success")
                semantic_rate = float(
                    criteria_rates.get(semantic_key, task["success_rate"])
                )
                contract_rate = float(
                    criteria_rates.get(contract_key, task["success_rate"])
                )
                semantic_rates[name] = semantic_rate
                contract_rates[name] = contract_rate
                floor = self._task_floor(name)
                if semantic_rate >= floor and contract_rate >= floor:
                    classification = "VERIFIED"
                elif semantic_rate < floor and contract_rate < floor:
                    classification = "MODEL_AND_CONTRACT"
                elif semantic_rate < floor:
                    classification = "MODEL_CORRECTNESS"
                else:
                    classification = "OUTPUT_CONTRACT"
                task_failure_classification[name] = classification

            semantic_achievement_rate = (
                sum(weights[name] * semantic_rates[name] for name in tasks)
                / available_weight
                if available_weight
                else 0.0
            )
            contract_achievement_rate = (
                sum(weights[name] * contract_rates[name] for name in tasks)
                / available_weight
                if available_weight
                else 0.0
            )
            results[mode] = {
                "profile": self.profiles.resolve(self.descriptor).profile_id,
                "achievement_rate": achievement_rate,
                "semantic_achievement_rate": semantic_achievement_rate,
                "contract_achievement_rate": contract_achievement_rate,
                "stability_score": max(0.0, min(1.0, stability)),
                "minimum_task_success_rate": min(rates, default=0.0),
                "tasks": task_payload,
                "task_weights": {name: weights[name] for name in tasks},
                "critical_task_floors": {
                    name: self._task_floor(name) for name in tasks
                },
                "semantic_success_rates": semantic_rates,
                "contract_success_rates": contract_rates,
                "task_failure_classification": task_failure_classification,
                "failed_critical_tasks": failed_critical_tasks,
                "critical_tasks_meet_floor": not failed_critical_tasks,
                "raw_successes": successes,
                "raw_attempts": attempts,
                "applications": applications[mode],
            }

        baseline = results.get("generic")
        if baseline:
            for value in results.values():
                value["achievement_delta_vs_generic"] = (
                    value["achievement_rate"] - baseline["achievement_rate"]
                )

        best_observed_mode = max(
            results,
            key=lambda name: self._mode_rank(name, results[name]),
        ) if results else None
        eligible_modes = [
            mode
            for mode, result in results.items()
            if result["achievement_rate"] >= DEFAULT_MINIMUM_ACHIEVEMENT_RATE
            and result["critical_tasks_meet_floor"]
        ]
        best_mode = max(
            eligible_modes,
            key=lambda name: self._mode_rank(name, results[name]),
        ) if eligible_modes else None
        recommended_mode_by_task = {
            task_name: self._recommend_mode_for_task(task_name, results)
            for task_name in task_names
        }
        best_semantic_mode_by_task: dict[str, str | None] = {}
        for task_name in task_names:
            candidates = [
                mode
                for mode, result in results.items()
                if result["semantic_success_rates"].get(task_name, 0.0)
                >= self._task_floor(task_name)
            ]
            best_semantic_mode_by_task[task_name] = (
                max(
                    candidates,
                    key=lambda mode: (
                        results[mode]["semantic_success_rates"][task_name],
                        results[mode]["contract_success_rates"][task_name],
                        -_median_or_infinity(results[mode]["tasks"][task_name]),
                        1 if mode == "generic" else 0,
                    ),
                )
                if candidates
                else None
            )
        return {
            "benchmark_version": BENCHMARK_VERSION,
            "model": self.descriptor.key,
            "engine": self.descriptor.engine.value,
            "profile_id": self.profiles.resolve(self.descriptor).profile_id,
            "context_tokens": context_tokens,
            "context_utilization": context_utilization,
            "repetitions": repetitions,
            "seed": seed,
            "execution_order": execution_order,
            "results": results,
            "best_observed_mode": best_observed_mode,
            "best_mode": best_mode,
            "recommended_mode_by_task": recommended_mode_by_task,
            "best_semantic_mode_by_task": best_semantic_mode_by_task,
            "acceptance": {
                "candidate_beats_generic": bool(
                    best_mode
                    and best_mode != "generic"
                    and results[best_mode]["achievement_rate"]
                    > results.get("generic", {}).get("achievement_rate", -1)
                ),
                "minimum_achievement_rate": DEFAULT_MINIMUM_ACHIEVEMENT_RATE,
                "critical_task_floors": DEFAULT_CRITICAL_TASK_FLOORS,
                "eligible_modes": eligible_modes,
                "best_mode_meets_gate": bool(best_mode and best_mode in eligible_modes),
                "automatic_promotion_allowed": False,
                "human_approval_required": True,
            },
        }
