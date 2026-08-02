"""MTP (Multi-Token Prediction) comparison evaluation script.

Compares inference speed and quality across different MTP settings.
Connects to the Hermes Gateway (http://127.0.0.1:17200/v1) and measures
the impact of the `n_draft` parameter on token generation.

Usage:
    cd /mnt/e/env/ts/loto_ops && source ./activate_env.sh
    python3 -m tests.benchmarks.mtp_comparison

Output:
    Saves results to /mnt/e/env/ts/loto_ops/.ai/reports/08_mtp_evaluation.md
"""

import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib import request as urllib_request

GATEWAY_URL = "http://127.0.0.1:17200/v1"
TASKS_FILE = Path(__file__).parent.parent.parent / "runs" / "task_list.json"


@dataclass
class MTPConfig:
    """MTP configuration variant."""

    name: str
    n_draft: int
    description: str


# Define MTP configurations to compare
CONFIGS = [
    MTPConfig(name="A_no_mtp", n_draft=0, description="MTP無効 (draft=0)"),
    MTPConfig(name="B_conservative", n_draft=2, description="MTP有効・保守的 (draft=2)"),
    MTPConfig(name="C_default", n_draft=4, description="MTP有効・現在設定 (draft=4)"),
]


@dataclass
class MetricResult:
    """Single measurement result."""

    elapsed_seconds: float
    generated_tokens: int
    tokens_per_sec: float
    json_corrupted: bool
    factual_accuracy: float
    mtp_config: str


def load_tasks() -> list[str]:
    """Load development tasks from task_list.json."""
    if TASKS_FILE.exists():
        with open(TASKS_FILE, encoding="utf-8") as f:
            data = json.load(f)
            # Extract task prompts
            tasks = []
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and "prompt" in item:
                        tasks.append(item["prompt"])
            return tasks
    return []


def call_gateway(prompt: str, model: str = "ornith35b_mtp", n_draft: int = 0) -> tuple[dict, float]:
    """Call the Hermes Gateway with specified MTP settings.

    Returns:
        Tuple of (response_data, elapsed_seconds)
    """
    url = f"{GATEWAY_URL}/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": 512,
        "n_draft": n_draft,  # MTP draft tokens parameter
    }

    start_time = time.time()
    try:
        req = urllib_request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib_request.urlopen(req, timeout=30) as response:
            response_data = json.loads(response.read().decode("utf-8"))
            elapsed = time.time() - start_time
            return response_data, elapsed
    except Exception as e:
        elapsed = time.time() - start_time
        return {"error": str(e)}, elapsed


def parse_response(response_data: dict) -> tuple[int, str]:
    """Parse response and extract token count and content."""
    if "error" in response_data:
        return 0, ""

    if "choices" in response_data and len(response_data["choices"]) > 0:
        choice = response_data["choices"][0]
        content = choice.get("message", {}).get("content", "")
        usage = response_data.get("usage", {})
        generated_tokens = usage.get("completion_tokens", 0)
        return generated_tokens, content
    return 0, ""


def check_json_validity(content: str) -> bool:
    """Check if the response content contains valid JSON or tool calls if it claims to be JSON, or is corrupted."""
    if not content or content.startswith("[ERROR]"):
        return True  # Corrupted if error

    content_stripped = content.strip()
    if content_stripped.startswith("{") or content_stripped.startswith("["):
        try:
            json.loads(content_stripped)
            return False  # Valid JSON
        except json.JSONDecodeError:
            return not ('"tool_calls"' in content_stripped or '"function"' in content_stripped)
    return False


def evaluate_factual_accuracy(response_content: str, expected: str) -> float:
    """Evaluate factual accuracy by checking if expected content is present."""
    if not expected or not response_content:
        return 0.0

    expected_lower = expected.lower()
    response_lower = response_content.lower()

    if expected_lower in response_lower:
        return 1.0

    words = expected.split()
    if len(words) < 3:
        return 0.0

    matches = sum(1 for word in words if word.lower() in response_lower)
    return matches / len(words)


def run_mtp_comparison() -> list[MetricResult]:
    """Run MTP comparison across all configurations, using alternating sequence A, B, B, A..."""
    tasks = load_tasks()
    if not tasks:
        print("No tasks found in task_list.json")
        return []

    results = []

    # Sequence of configurations to run in alternating order to offset thermal/load bias
    sequence = [
        "A_no_mtp",
        "B_conservative",
        "B_conservative",
        "A_no_mtp",
        "A_no_mtp",
        "B_conservative",
        "B_conservative",
        "A_no_mtp",
    ]

    config_map = {c.name: c for c in CONFIGS}

    print("\n=== Executing Alternating MTP Comparison Run (A, B, B, A, A, B...) ===")

    for idx, config_name in enumerate(sequence):
        config = config_map.get(config_name)
        if not config:
            continue

        task_idx = idx % len(tasks)
        task = tasks[task_idx]
        print(f"  Step {idx + 1} - Testing: {config.name} | Task {task_idx + 1}: {task[:40]}...")

        response_data, elapsed = call_gateway(task, "ornith35b_mtp", config.n_draft)
        generated_tokens, content = parse_response(response_data)
        tokens_per_sec = generated_tokens / elapsed if elapsed > 0 else 0

        # Check JSON validity
        json_corrupted = check_json_validity(content)

        # Evaluate factual accuracy
        factual_accuracy = evaluate_factual_accuracy(content, task)

        result = MetricResult(
            elapsed_seconds=elapsed,
            generated_tokens=generated_tokens,
            tokens_per_sec=tokens_per_sec,
            json_corrupted=json_corrupted,
            factual_accuracy=factual_accuracy,
            mtp_config=config.name,
        )
        results.append(result)

        print(
            f"    Tokens: {generated_tokens}, TPS: {tokens_per_sec:.2f}, Accepted: {response_data.get('timings', {}).get('draft_n_accepted', 0)}"
        )

    return results


def aggregate_metrics(results: list[MetricResult]) -> dict[str, Any]:
    """Aggregate metrics by MTP configuration."""
    aggregated = {}

    for result in results:
        config = result.mtp_config
        if config not in aggregated:
            aggregated[config] = {
                "count": 0,
                "total_elapsed": 0,
                "total_tokens": 0,
                "total_tps": 0,
                "json_corrupted_count": 0,
                "accuracy_sum": 0,
            }

        agg = aggregated[config]
        agg["count"] += 1
        agg["total_elapsed"] += result.elapsed_seconds
        agg["total_tokens"] += result.generated_tokens
        agg["total_tps"] += result.tokens_per_sec
        if result.json_corrupted:
            agg["json_corrupted_count"] += 1
        agg["accuracy_sum"] += result.factual_accuracy

    # Calculate averages
    for config, data in aggregated.items():
        count = data["count"]
        if count > 0:
            aggregated[config] = {
                "count": count,
                "avg_elapsed": data["total_elapsed"] / count,
                "avg_tps": data["total_tps"] / count,
                "total_tokens": data["total_tokens"],
                "json_corruption_rate": data["json_corrupted_count"] / count,
                "avg_accuracy": data["accuracy_sum"] / count,
            }

    return aggregated


def generate_report(aggregated: dict, configs: list[MTPConfig]) -> str:
    """Generate markdown report."""
    report = "# MTP (Multi-Token Prediction) 比較評価レポート\n\n"
    report += f"## 評価日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    report += "## 比較設定\n\n"
    report += "| 設定名 | MTP Draft数 | 説明 |\n"
    report += "|--------|-------------|------|\n"
    for config in configs:
        report += f"| {config.name} | {config.n_draft} | {config.description} |\n"
    report += "\n"

    report += "## 集計結果\n\n"
    report += "| MTP設定 | 平均TPS | 平均遅延(秒) | JSON破損率 | 正確性 |\n"
    report += "|--------|---------|-------------|-----------|--------|\n"

    for config in configs:
        data = aggregated.get(config.name, {})
        avg_tps = data.get("avg_tps", 0)
        avg_elapsed = data.get("avg_elapsed", 0)
        corruption_rate = data.get("json_corruption_rate", 0)
        accuracy = data.get("avg_accuracy", 0)

        report += f"| {config.name} | {avg_tps:.2f} | {avg_elapsed:.3f} | {corruption_rate:.2%} | {accuracy:.2f} |\n"

    report += "\n## 分析\n\n"
    report += "### メリット\n"
    report += "- MTP有効化による推論速度の向上\n"
    report += "- ドラフトトークンによる事前予測で速度改善\n\n"

    report += "### デメリット\n"
    report += "- 構文崩壊率の増加可能性\n"
    report += "- メモリ使用量の増加\n"
    report += "- プロキシ層のオーバーヘッド\n\n"

    report += "## 結論\n\n"
    report += "MTPの有効化により速度向上が期待されるが、構文崩壊率とのトレードオフを考慮する必要がある。\n"

    return report


def save_report(report: str, output_path: Path) -> None:
    """Save report to file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\nReport saved to: {output_path}")


def main():
    """Main entry point."""
    print("=" * 80)
    print("MTP (Multi-Token Prediction) Comparison Evaluation")
    print("=" * 80)

    # Run comparison
    results = run_mtp_comparison()

    if not results:
        print("No results collected. Exiting.")
        return

    # Aggregate metrics
    aggregated = aggregate_metrics(results)

    # Generate report
    report = generate_report(aggregated, CONFIGS)

    # Save report
    output_path = Path(__file__).parent.parent.parent / ".ai" / "reports" / "08_mtp_evaluation.md"
    save_report(report, output_path)

    print("\nEvaluation completed successfully.")


if __name__ == "__main__":
    main()
