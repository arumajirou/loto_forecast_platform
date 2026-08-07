from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import uvicorn

from .certification.suite import CertificationSuite
from .config import HarnessSettings
from .contracts import ChatRequest, HarnessStatus, Message
from .engines.base import InferenceEngine
from .engines.gemini import GeminiEngine
from .engines.llamacpp import LlamaCppEngine
from .engines.lmstudio import LMStudioEngine
from .engines.openai_compatible import OpenAICompatibleEngine
from .evaluation import ProfileABEvaluator
from .gateway.app import create_app
from .memory.mcp_server import main as memory_mcp_main
from .memory.mcp_server import main_http as memory_mcp_http_main
from .profiles import ProfileRegistry
from .registry import ModelRegistry


def build_engines(settings: HarnessSettings) -> dict[str, InferenceEngine]:
    engines: dict[str, InferenceEngine] = {}
    for model in settings.models:
        if not model.enabled:
            continue
        key = f"{model.engine.value}:{model.endpoint}"
        if key in engines:
            continue
        if model.engine.value == "lmstudio":
            api_key = os.getenv("LM_API_TOKEN")
            engine: InferenceEngine = LMStudioEngine(model.endpoint, api_key=api_key)
        elif model.engine.value == "llamacpp":
            api_key = os.getenv("LLAMACPP_API_KEY")
            engine = LlamaCppEngine(model.endpoint, api_key=api_key)
        elif model.engine.value == "gemini":
            api_key = os.getenv("GEMINI_API_KEY")
            engine = GeminiEngine(model.endpoint, api_key=api_key)
        else:
            api_key = os.getenv("OPENAI_COMPATIBLE_API_KEY")
            engine = OpenAICompatibleEngine(model.endpoint, api_key=api_key)
        engines[key] = engine
    return engines


async def _close_engines(engines: dict[str, InferenceEngine]) -> None:
    for engine in engines.values():
        await engine.close()


async def _doctor(settings: HarnessSettings) -> int:
    engines = build_engines(settings)
    result: list[dict[str, Any]] = []
    try:
        for key, engine in engines.items():
            report = await engine.health()
            item: dict[str, Any] = {"engine_key": key, **report.model_dump(mode="json")}
            if report.status == HarnessStatus.VERIFIED:
                try:
                    discovered = await engine.discover()
                    item["discovered_models"] = len(discovered)
                    item["model_keys"] = [model.key for model in discovered]
                except Exception as exc:
                    item["discovery_error"] = str(exc)
            result.append(item)
    finally:
        await _close_engines(engines)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result and all(item["status"] == "VERIFIED" for item in result) else 2


async def _discover(settings: HarnessSettings) -> int:
    engines = build_engines(settings)
    payload: dict[str, Any] = {}
    status = 0
    try:
        for key, engine in engines.items():
            try:
                payload[key] = [
                    descriptor.model_dump(mode="json")
                    for descriptor in await engine.discover()
                ]
            except Exception as exc:
                payload[key] = {"error": str(exc)}
                status = 2
    finally:
        await _close_engines(engines)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return status


def _safe_model_name(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.@-]+", "_", model)[:160]


def _write_json_report(path: Path, payload: dict[str, Any]) -> Path:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n"
    path.write_text(content, encoding="utf-8")
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{digest}  {path}\n", encoding="utf-8"
    )
    return path


async def _certify(
    settings: HarnessSettings,
    model_key: str,
    *,
    contexts: list[int] | None,
    deep_context: bool,
    context_utilization: float,
    context_repetitions: int,
    output: str | None,
    profile_mode: str,
) -> int:
    registry = ModelRegistry(settings.models)
    descriptor = registry.get(model_key)
    engines = build_engines(settings)
    engine = engines[f"{descriptor.engine.value}:{descriptor.endpoint}"]
    started_at = datetime.now().astimezone().isoformat()
    try:
        steps = await CertificationSuite(
            engine,
            profile_mode=profile_mode,
        ).run(
            model_key,
            contexts=contexts,
            deep_context=deep_context,
            context_utilization=context_utilization,
            context_repetitions=context_repetitions,
        )
    finally:
        await engine.close()

    requested_contexts = contexts or [8192, 16384, 32768, 49152, 65536]
    inference_verified_contexts = sorted(
        {
            int(step.name.rsplit("_", 1)[1])
            for step in steps
            if step.status == HarnessStatus.VERIFIED
            and (
                step.name.startswith("inference_")
                or step.name.startswith("embedding_")
            )
        }
    )
    deep_status = {
        int(step.name.removeprefix("context_probe_")): step.status
        for step in steps
        if step.name.startswith("context_probe_")
    }
    deep_verified_contexts = sorted(
        context
        for context, status in deep_status.items()
        if status == HarnessStatus.VERIFIED
    )
    failed_contexts = sorted(
        context
        for context, status in deep_status.items()
        if status in {HarnessStatus.FAILED, HarnessStatus.BLOCKED}
    )
    contiguous_verified: list[int] = []
    status_source = deep_status if deep_context else {
        context: (
            HarnessStatus.VERIFIED
            if context in inference_verified_contexts
            else HarnessStatus.FAILED
        )
        for context in requested_contexts
    }
    failure_seen = False
    non_monotonic = False
    for context in requested_contexts:
        status = status_source.get(context, HarnessStatus.FAILED)
        if status == HarnessStatus.VERIFIED and not failure_seen:
            contiguous_verified.append(context)
        elif status == HarnessStatus.VERIFIED and failure_seen:
            non_monotonic = True
        else:
            failure_seen = True
    payload = {
        "model": model_key,
        "engine": descriptor.engine.value,
        "endpoint": descriptor.endpoint,
        "started_at": started_at,
        "finished_at": datetime.now().astimezone().isoformat(),
        "deep_context": deep_context,
        "context_utilization": context_utilization,
        "context_repetitions": context_repetitions,
        "profile_mode": profile_mode,
        "requested_contexts": requested_contexts,
        "inference_verified_contexts": inference_verified_contexts,
        "deep_verified_contexts": deep_verified_contexts,
        "failed_contexts": failed_contexts,
        "non_monotonic_context_result": non_monotonic,
        "max_context_verified": max(contiguous_verified, default=0),
        "steps": [
            {"name": step.name, "status": step.status.value, "detail": step.detail}
            for step in steps
        ],
    }
    report_path = Path(output) if output else (
        Path(settings.artifact_root)
        / "certification"
        / _safe_model_name(model_key)
        / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    )
    report_path = _write_json_report(report_path, payload)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"report={report_path}")

    blocking = {
        HarnessStatus.FAILED,
        HarnessStatus.BLOCKED,
    }
    if not steps or any(step.status in blocking for step in steps):
        return 3
    if any(step.status == HarnessStatus.DEGRADED for step in steps):
        return 2
    return 0


async def _live_descriptor(
    descriptor: Any,
    engine: InferenceEngine,
) -> Any:
    try:
        discovered = await engine.discover()
    except Exception:
        return descriptor
    live = next((item for item in discovered if item.key == descriptor.key), None)
    if live is None:
        return descriptor
    return descriptor.model_copy(
        update={
            "display_name": live.display_name or descriptor.display_name,
            "architecture": live.architecture or descriptor.architecture,
            "quantization": live.quantization or descriptor.quantization,
            "declared_context": max(
                descriptor.declared_context,
                live.declared_context,
            ),
            "capabilities": descriptor.capabilities | live.capabilities,
            "loaded_instances": live.loaded_instances,
            "status": live.status,
        }
    )


def _absolute_artifact_path(settings: HarnessSettings, *parts: str) -> Path:
    return (Path.cwd() / settings.artifact_root / Path(*parts)).resolve()


def _profile_audit(
    settings: HarnessSettings,
    model_key: str,
    modes: list[str],
    output: str | None,
) -> int:
    descriptor = ModelRegistry(settings.models).get(model_key)
    profiles = ProfileRegistry()
    profile = profiles.resolve(descriptor)
    tasks = {
        "chat": ChatRequest(
            model=model_key,
            messages=[Message(role="user", content="Explain the harness briefly.")],
            max_tokens=256,
            task_type="chat",
        ),
        "reasoning": ChatRequest(
            model=model_key,
            messages=[Message(role="user", content="Reason carefully, then answer 17+29.")],
            max_tokens=256,
            task_type="reasoning",
        ),
        "tools": ChatRequest(
            model=model_key,
            messages=[Message(role="user", content="Call audit_echo with value 7.")],
            max_tokens=128,
            task_type="tools",
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "audit_echo",
                        "description": "Return an integer",
                        "parameters": {
                            "type": "object",
                            "properties": {"value": {"type": "integer"}},
                            "required": ["value"],
                        },
                    },
                }
            ],
            tool_choice="required",
        ),
    }
    applications: dict[str, Any] = {}
    for mode in modes:
        mode_payload: dict[str, Any] = {}
        for task_name, request in tasks.items():
            try:
                applied = profiles.apply(
                    request,
                    descriptor,
                    mode=mode,
                    task_type=task_name,
                )
                mode_payload[task_name] = {
                    "profile_id": applied.profile_id,
                    "family": applied.family,
                    "mode": applied.mode,
                    "changes": list(applied.changes),
                    "expected_effects": list(applied.expected_effects),
                    "request": applied.request.model_dump(mode="json", exclude_none=True),
                }
            except ValueError as exc:
                mode_payload[task_name] = {"status": "UNSUPPORTED", "detail": str(exc)}
        applications[mode] = mode_payload
    payload = {
        "model": model_key,
        "engine": descriptor.engine.value,
        "architecture": descriptor.architecture,
        "profile_id": profile.profile_id,
        "family": profile.family,
        "supported_modes": list(profile.supported_modes),
        "notes": list(profile.notes),
        "applications": applications,
    }
    report = Path(output).resolve() if output else _absolute_artifact_path(
        settings,
        "profile-audit",
        _safe_model_name(model_key),
        f"{datetime.now().strftime('%Y%m%d-%H%M%S')}.json",
    )
    report = _write_json_report(report, payload)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"report={report}")
    return 0


async def _profile_ab(
    settings: HarnessSettings,
    model_key: str,
    *,
    modes: list[str],
    repetitions: int,
    context_tokens: int,
    context_utilization: float,
    seed: int,
    output: str | None,
) -> int:
    registry = ModelRegistry(settings.models)
    configured = registry.get(model_key)
    engines = build_engines(settings)
    engine = engines[f"{configured.engine.value}:{configured.endpoint}"]
    try:
        descriptor = await _live_descriptor(configured, engine)
        payload = await ProfileABEvaluator(engine, descriptor).run(
            modes=modes,
            repetitions=repetitions,
            context_tokens=context_tokens,
            context_utilization=context_utilization,
            seed=seed,
        )
    finally:
        await engine.close()
    payload["started_from_config"] = configured.model_dump(mode="json")
    payload["finished_at"] = datetime.now().astimezone().isoformat()
    report = Path(output).resolve() if output else _absolute_artifact_path(
        settings,
        "profile-ab",
        _safe_model_name(model_key),
        f"{datetime.now().strftime('%Y%m%d-%H%M%S')}.json",
    )
    report = _write_json_report(report, payload)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"report={report}")
    acceptance = payload.get("acceptance", {})
    return 0 if acceptance.get("best_mode_meets_gate") else 3


def _parse_contexts(value: str | None) -> list[int] | None:
    if not value:
        return None
    contexts = sorted({int(item.strip()) for item in value.split(",") if item.strip()})
    if not contexts or any(context < 1024 for context in contexts):
        raise argparse.ArgumentTypeError("contexts must be comma-separated integers >= 1024")
    return contexts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="loto-harness")
    parser.add_argument(
        "--config",
        default=os.getenv("LOTO_HARNESS_CONFIG", "configs/harness/gateway.yaml"),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("serve")
    sub.add_parser("doctor")
    sub.add_parser("discover")
    certify = sub.add_parser("certify")
    certify.add_argument("model")
    certify.add_argument(
        "--contexts",
        help="comma-separated context sizes, for example 8192,16384,32768,65536",
    )
    certify.add_argument(
        "--deep-context",
        action="store_true",
        help="send a near-limit lost-in-the-middle needle prompt for each context",
    )
    certify.add_argument(
        "--context-utilization",
        type=float,
        default=0.90,
        help="fraction of each context used by the deep prompt (0.50 to 0.95)",
    )
    certify.add_argument(
        "--context-repetitions",
        type=int,
        default=3,
        help="number of near-limit needle trials per context (1 to 10)",
    )
    certify.add_argument(
        "--profile-mode",
        default="auto",
        help="generic, auto, fast, quality, reasoning, tools, or structured",
    )
    certify.add_argument("--output")
    audit = sub.add_parser("profile-audit")
    audit.add_argument("model")
    audit.add_argument("--modes", default="generic,fast,quality,reasoning,tools")
    audit.add_argument("--output")
    profile_ab = sub.add_parser("profile-ab")
    profile_ab.add_argument("model")
    profile_ab.add_argument("--modes", default="generic,fast,quality")
    profile_ab.add_argument("--repetitions", type=int, default=3)
    profile_ab.add_argument("--context-tokens", type=int, default=16384)
    profile_ab.add_argument("--context-utilization", type=float, default=0.50)
    profile_ab.add_argument("--seed", type=int, default=1)
    profile_ab.add_argument("--output")
    sub.add_parser("memory-mcp")
    sub.add_parser("memory-mcp-http")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "memory-mcp":
        memory_mcp_main()
        return
    if args.command == "memory-mcp-http":
        memory_mcp_http_main()
        return
    settings = HarnessSettings.from_yaml(Path(args.config))
    if args.command == "serve":
        app = create_app(settings, build_engines(settings))
        uvicorn.run(app, host=settings.host, port=settings.port)
        return
    if args.command == "doctor":
        raise SystemExit(asyncio.run(_doctor(settings)))
    if args.command == "discover":
        raise SystemExit(asyncio.run(_discover(settings)))
    if args.command == "profile-audit":
        modes = [item.strip() for item in args.modes.split(",") if item.strip()]
        raise SystemExit(_profile_audit(settings, args.model, modes, args.output))
    if args.command == "profile-ab":
        modes = [item.strip() for item in args.modes.split(",") if item.strip()]
        raise SystemExit(
            asyncio.run(
                _profile_ab(
                    settings,
                    args.model,
                    modes=modes,
                    repetitions=args.repetitions,
                    context_tokens=args.context_tokens,
                    context_utilization=args.context_utilization,
                    seed=args.seed,
                    output=args.output,
                )
            )
        )
    if args.command == "certify":
        contexts = _parse_contexts(args.contexts)
        raise SystemExit(
            asyncio.run(
                _certify(
                    settings,
                    args.model,
                    contexts=contexts,
                    deep_context=args.deep_context,
                    context_utilization=args.context_utilization,
                    context_repetitions=args.context_repetitions,
                    output=args.output,
                    profile_mode=args.profile_mode,
                )
            )
        )
    raise SystemExit(2)


if __name__ == "__main__":
    main()
