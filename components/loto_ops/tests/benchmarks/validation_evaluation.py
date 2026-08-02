"""Validation evaluation script — real Gateway measurements.

Connects to the OpenAI-compatible Hermes Gateway at http://127.0.0.1:17200/v1,
runs each task in validation_tasks.json under three MTP+Workflow configurations,
and records task_success / elapsed_seconds / input_tokens / output_tokens / retry_count.

Usage:
    python3 -m tests.benchmarks.validation_evaluation
"""

from __future__ import annotations

import json
import logging
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import urllib3

logger = logging.getLogger("loto_ops.benchmarks.validation_evaluation")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class TaskResult:
    task_id: str
    config_label: str  # e.g. "Config1_E"
    status: str  # "passed", "failed", "invalid", "contaminated", "not_run", "infrastructure_error", "validator_error"
    elapsed_seconds: float
    input_tokens: int
    output_tokens: int
    retry_count: int

    @property
    def task_success(self) -> bool:
        return self.status == "passed"


@dataclass
class ConfigRun:
    label: str
    results: list[TaskResult] = field(default_factory=list)

    @property
    def avg_success(self) -> float:
        valid_results = [r for r in self.results if r.status in {"passed", "failed"}]
        if not valid_results:
            return 0.0
        return statistics.mean([1.0 if r.status == "passed" else 0.0 for r in valid_results])

    @property
    def avg_elapsed(self) -> float:
        if not self.results:
            return 0.0
        return statistics.mean([r.elapsed_seconds for r in self.results])

    @property
    def avg_input_tokens(self) -> int:
        if not self.results:
            return 0
        return int(statistics.mean([r.input_tokens for r in self.results]))

    @property
    def avg_output_tokens(self) -> int:
        if not self.results:
            return 0
        return int(statistics.mean([r.output_tokens for r in self.results]))

    @property
    def avg_retry_count(self) -> float:
        if not self.results:
            return 0.0
        return statistics.mean([r.retry_count for r in self.results])

    @property
    def total_tokens(self) -> int:
        return self.avg_input_tokens + self.avg_output_tokens

    @property
    def valid_task_count(self) -> int:
        return len([r for r in self.results if r.status in {"passed", "failed"}])

    @property
    def excluded_counts(self) -> dict[str, int]:
        counts = {
            "invalid": 0,
            "contaminated": 0,
            "not_run": 0,
            "infrastructure_error": 0,
            "validator_error": 0,
        }
        for r in self.results:
            if r.status in counts:
                counts[r.status] += 1
        return counts


# ---------------------------------------------------------------------------
# Gateway client
# ---------------------------------------------------------------------------

GATEWAY_BASE = "http://127.0.0.1:17200/v1"
MODEL_NAME = "ornith35b_mtp"
MAX_TOKENS = 2048
TEMPERATURE = 0.3
MAX_RETRIES = 3
RETRY_BACKOFF = 1.0  # seconds


class GatewayClient:
    """Thin OpenAI-compatible client for Hermes Gateway."""

    def __init__(self, base_url: str = GATEWAY_BASE, model: str = MODEL_NAME) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    def chat(
        self, messages: list[dict[str, str]], n_draft: int = 0, workflow: str = "A"
    ) -> dict[str, Any]:
        """Call /chat/completions and return parsed response dict."""
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": TEMPERATURE,
            "max_tokens": MAX_TOKENS,
            "stream": False,
            "n_draft": n_draft,
            "workflow": workflow,
        }
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                http = urllib3.PoolManager(timeout=urllib3.Timeout(connect=5, read=90))
                resp = http.request(
                    "POST",
                    url,
                    body=json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json"},
                )
                if resp.status != 200:
                    logger.warning(f"HTTP {resp.status} on attempt {attempt}: {resp.data[:200]}")
                    if attempt == MAX_RETRIES:
                        raise RuntimeError(f"Gateway returned {resp.status}")
                    time.sleep(RETRY_BACKOFF * attempt)
                    continue
                data = json.loads(resp.data.decode())
                choice = data["choices"][0]
                content = choice.get("message", {}).get("content", "")
                usage = data.get("usage", {})
                return {"content": content, "usage": usage}
            except Exception as exc:
                logger.warning(f"API call failed (attempt {attempt}): {exc}")
                if attempt == MAX_RETRIES:
                    raise
                time.sleep(RETRY_BACKOFF * attempt)
        # unreachable
        raise RuntimeError("unreachable")


# ---------------------------------------------------------------------------
# Task loading
# ---------------------------------------------------------------------------


def load_validation_tasks() -> list[dict[str, Any]]:
    """Load tasks from validation_tasks.json, falling back to sample tasks."""
    from pathlib import Path as P

    candidates = [
        P("/mnt/e/env/ts/shared-ai-memory/benchmarks/validation_tasks.json"),
        P("/mnt/e/env/ts/loto_ops/tests/benchmarks/validation_tasks.json"),
    ]
    for p in candidates:
        if p.exists():
            with p.open() as f:
                return json.load(f)
    # Fallback sample tasks
    logger.warning("No validation_tasks.json found — using sample tasks")
    return [
        {
            "id": "SAMPLE-001",
            "title": "Sample task 1",
            "description": "Return the string 'hello world' exactly.",
            "target_files": [],
            "verification": "",
            "expected": "hello world",
        },
        {
            "id": "SAMPLE-002",
            "title": "Sample task 2",
            "description": "Return the string 'token_efficient' exactly.",
            "target_files": [],
            "verification": "",
            "expected": "token_efficient",
        },
    ]


# ---------------------------------------------------------------------------
# Evaluation logic
# ---------------------------------------------------------------------------

# Config definitions — the three configurations to test
CONFIGS = {
    "Config1_E": {
        "n_draft": 2,
        "workflow": "E",
        "description": "MTP保守的 + Workflow E (再試行最適化)",
    },
    "Config2_F": {
        "n_draft": 2,
        "workflow": "F",
        "description": "MTP保守的 + Workflow F (バランス・ハイブリッド)",
    },
    "Config3_A": {
        "n_draft": 0,
        "workflow": "A",
        "description": "MTP無効化 + Workflow A (基準ベースライン)",
    },
}


def _build_prompt(task: dict[str, Any]) -> str:
    """Construct the prompt for a validation task."""
    task_id = task.get("id", task.get("task_id", "UNKNOWN"))
    title = task.get("title", task.get("category", ""))
    description = task.get("description", task.get("instruction", ""))
    target_files = task.get("target_files", task.get("allowed_files", []))
    verification = task.get("verification", "")
    if not verification and task.get("test_command"):
        verification = " ".join(task["test_command"])
    if not verification:
        verification = "N/A"

    return (
        f"# Task {task_id}\n"
        f"Title: {title}\n"
        f"Description: {description}\n"
        f"Target files: {', '.join(target_files) if isinstance(target_files, list) else target_files}\n"
        f"Verification: {verification}\n\n"
        f"Respond with ONLY the exact expected answer — no explanation, no markdown."
    )


def _extract_expected(task: dict[str, Any]) -> str | None:
    """Extract the expected string for matching.

    If the task has an explicit 'expected' field, use that.
    Otherwise, derive the expected answer from the task description/title.
    """
    if task.get("expected"):
        return task["expected"]
    if task.get("success_conditions"):
        return task["success_conditions"][0]
    return task.get("title", task.get("category", ""))


def run_config(
    client: GatewayClient,
    tasks: list[dict[str, Any]],
    config_label: str,
    n_draft: int,
    workflow: str,
) -> ConfigRun:
    """Run all tasks under a single configuration and return aggregated results."""
    run = ConfigRun(label=config_label)
    for task in tasks:
        task_id = task.get("id", task.get("task_id", "UNKNOWN"))
        description = task.get("description", task.get("instruction", ""))

        # Check invalid
        if task_id == "UNKNOWN" or not description:
            run.results.append(
                TaskResult(
                    task_id=task_id,
                    config_label=config_label,
                    status="invalid",
                    elapsed_seconds=0.0,
                    input_tokens=0,
                    output_tokens=0,
                    retry_count=0,
                )
            )
            continue

        # Check contaminated
        if task.get("status") == "contaminated" or "contaminated" in str(task_id).lower():
            run.results.append(
                TaskResult(
                    task_id=task_id,
                    config_label=config_label,
                    status="contaminated",
                    elapsed_seconds=0.0,
                    input_tokens=0,
                    output_tokens=0,
                    retry_count=0,
                )
            )
            continue

        prompt = _build_prompt(task)
        messages = [{"role": "user", "content": prompt}]
        expected = _extract_expected(task)

        start = time.perf_counter()
        retry_count = 0
        status_label = "failed"
        input_tokens = 0
        output_tokens = 0
        elapsed = 0.0

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = client.chat(messages, n_draft=n_draft, workflow=workflow)
                content = resp.get("content", "")

                if content.startswith("[ERROR]"):
                    if "Connection" in content or "Timeout" in content:
                        raise ConnectionError(content)
                    else:
                        raise ValueError(content)

                usage = resp.get("usage", {})
                input_tokens = usage.get("prompt_tokens", 0)
                output_tokens = usage.get("completion_tokens", 0)
                elapsed = time.perf_counter() - start

                # Check success
                status_label = "passed" if expected and expected in content else "failed"

                run.results.append(
                    TaskResult(
                        task_id=task_id,
                        config_label=config_label,
                        status=status_label,
                        elapsed_seconds=elapsed,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        retry_count=retry_count,
                    )
                )
                break
            except (ConnectionError, TimeoutError) as exc:
                logger.error(
                    f"Task {task_id} attempt {attempt} failed with infrastructure error: {exc}"
                )
                retry_count += 1
                if attempt == MAX_RETRIES:
                    elapsed = time.perf_counter() - start
                    run.results.append(
                        TaskResult(
                            task_id=task_id,
                            config_label=config_label,
                            status="infrastructure_error",
                            elapsed_seconds=elapsed,
                            input_tokens=0,
                            output_tokens=0,
                            retry_count=retry_count,
                        )
                    )
                else:
                    time.sleep(RETRY_BACKOFF * attempt)
            except Exception as exc:
                logger.error(
                    f"Task {task_id} attempt {attempt} failed with validator/other error: {exc}"
                )
                retry_count += 1
                if attempt == MAX_RETRIES:
                    elapsed = time.perf_counter() - start
                    run.results.append(
                        TaskResult(
                            task_id=task_id,
                            config_label=config_label,
                            status="validator_error",
                            elapsed_seconds=elapsed,
                            input_tokens=0,
                            output_tokens=0,
                            retry_count=retry_count,
                        )
                    )
                else:
                    time.sleep(RETRY_BACKOFF * attempt)

    return run


def run_all_configs(tasks: list[dict[str, Any]]) -> dict[str, ConfigRun]:
    """Run all three configurations and return results."""
    client = GatewayClient()
    results = {}
    for config_label, config in CONFIGS.items():
        logger.info(
            f"Running {config_label} (n_draft={config['n_draft']}, workflow={config['workflow']})"
        )
        run = run_config(client, tasks, config_label, config["n_draft"], config["workflow"])
        results[config_label] = run
        logger.info(f"  -> {len(run.results)} tasks completed, avg_success={run.avg_success:.3f}")
    return results


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def generate_report(all_results: dict[str, ConfigRun]) -> str:
    """Generate a markdown report of the evaluation results."""
    lines = [
        "# MTP Setting + Workflow Selection Evaluation Report",
        "",
        "**Generated**: 2026-07-19",
        "**Evaluator**: tests/benchmarks/validation_evaluation.py",
        "**Gateway**: http://127.0.0.1:17200/v1 (ornith35b_mtp)",
        "",
        "## Configuration Matrix",
        "",
    ]

    # Build comparison table
    lines.append(
        "| Config | Description | Valid Tasks | Success Rate | TPS | Input Tokens | Output Tokens | Avg Retries | Excluded (inv/cont/nr/inf/val) |"
    )
    lines.append(
        "|--------|-------------|-------------|--------------|-----|-------------|-------------|-------------|--------------------------------|"
    )

    for label in ["Config1_E", "Config2_F", "Config3_A"]:
        run = all_results[label]
        total_tokens = run.avg_input_tokens + run.avg_output_tokens
        tps = round(run.avg_elapsed * 1000 / max(total_tokens, 1), 2) if run.avg_elapsed > 0 else 0
        success_rate_str = f"{run.avg_success:.2%}" if run.valid_task_count > 0 else "N/A"
        ex = run.excluded_counts
        ex_str = f"{ex['invalid']}/{ex['contaminated']}/{ex['not_run']}/{ex['infrastructure_error']}/{ex['validator_error']}"
        lines.append(
            f"| {label} | {CONFIGS[label]['description']} | "
            f"{run.valid_task_count} | {success_rate_str} | {tps} | {run.avg_input_tokens} | "
            f"{run.avg_output_tokens} | {run.avg_retry_count:.1f} | {ex_str} |"
        )

    lines.extend(
        [
            "",
            "## Pareto Analysis",
            "",
            "Criteria:",
            "1. **Success Rate**: Higher is better",
            "2. **Token Efficiency**: Lower token consumption per task",
            "3. **Speed**: Lower elapsed time",
            "4. **Robustness**: Lower retry count indicates stability",
            "",
        ]
    )

    # Find best config
    best = max(all_results.values(), key=lambda r: r.avg_success)
    success_rate_str = f"{best.avg_success:.2%}" if best.valid_task_count > 0 else "N/A"
    lines.append(f"### Recommended: {best.label}")
    lines.append(f"- Highest success rate: {success_rate_str}")
    lines.append(f"- Average tokens per task: {best.total_tokens}")
    lines.append(f"- Average elapsed: {best.avg_elapsed:.3f}s")
    lines.append(f"- Average retries: {best.avg_retry_count:.1f}")
    lines.extend(
        [
            "",
            "## Next Phase (Sealed Set Evaluation)",
            "",
            "1. Apply selected configuration to sealed validation set",
            "2. Compare against baseline metrics",
            "3. Final approval for Phase 11 deployment",
            "",
            "---",
            "_validation_selection.md_",
        ]
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    tasks = load_validation_tasks()
    logger.info(f"Loaded {len(tasks)} tasks")

    all_results = run_all_configs(tasks)

    # Generate and save report
    report = generate_report(all_results)
    report_path = Path("/mnt/e/env/ts/loto_ops/.ai/reports/10_validation_selection.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w") as f:
        f.write(report)
    logger.info(f"Report saved to {report_path}")


if __name__ == "__main__":
    main()
