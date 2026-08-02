"""Custom ModelAPI adapter for Hermes Gateway (OpenAI-compatible endpoint).

This module provides a bridge between Inspect AI's evaluation framework and the
Hermes Gateway running at http://127.0.0.1:17200/v1. The adapter translates
Inspect AI's message format into OpenAI API calls and parses the responses back.

Usage:
    from inspect_ai import eval
    from inspect_bridge import HermesGatewayModel

    model = HermesGatewayModel(base_url="http://127.0.0.1:17200/v1", model="ornith35b_mtp")
    eval("tests/benchmarks/run_eval.py", model=model, tags=["benchmark"])
"""

import json
import logging
from dataclasses import dataclass
from typing import Any
from urllib import request as urllib_request

logger = logging.getLogger("loto_ops.benchmarks.inspect_bridge")


@dataclass
class HermesGatewayModel:
    """Custom ModelAPI adapter for Hermes Gateway.

    Inherits from inspect_ai.model.ModelAPI conceptually but provides
    a simplified interface that directly calls the OpenAI-compatible endpoint.
    """

    base_url: str
    model: str
    temperature: float = 0.7
    max_tokens: int = 4096

    def __post_init__(self) -> None:
        """Validate configuration."""
        if not self.base_url.endswith("/v1"):
            self.base_url = self.base_url.rstrip("/") + "/v1"
        logger.info(f"Initialized HermesGatewayModel: base_url={self.base_url}, model={self.model}")

    def format_prompt(self, messages: list[dict[str, str]]) -> str:
        """Convert Inspect AI message format to OpenAI format."""
        # Messages come as [{"role": "user", "content": "..."}, ...]
        return json.dumps(
            {"messages": messages, "temperature": self.temperature, "max_tokens": self.max_tokens}
        )

    async def generate(self, prompt: Any) -> Any:
        """Make API call to Hermes Gateway and return response."""
        try:
            # Parse the prompt back to extract messages
            data = json.loads(prompt)
            messages = data["messages"]

            # Build request payload
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
            }

            # Make HTTP request
            url = f"{self.base_url}/chat/completions"
            req = urllib_request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with urllib_request.urlopen(req, timeout=60) as response:
                response_data = json.loads(response.read().decode("utf-8"))

            # Parse response
            if "choices" in response_data and len(response_data["choices"]) > 0:
                choice = response_data["choices"][0]
                content = choice.get("message", {}).get("content", "")
                return {"content": content, "usage": response_data.get("usage", {})}
            else:
                logger.error(f"Unexpected response format: {response_data}")
                return {"content": "", "usage": {}}

        except Exception as e:
            logger.error(f"API call failed: {e}")
            return {"content": f"[ERROR] {e!s}", "usage": {}}


def match_score(response: Any, target: str) -> dict[str, Any]:
    """Scorer function that checks if response contains target string."""
    content = response.get("content", "")
    scored = target.lower() in content.lower()
    return {"score": 1.0 if scored else 0.0, "reason": "match" if scored else "no_match"}


def custom_scorer(response: Any, criteria: list[str]) -> dict[str, Any]:
    """Custom scorer that checks for multiple criteria in response."""
    content = response.get("content", "")
    results = []
    for criterion in criteria:
        found = criterion.lower() in content.lower()
        results.append({"criterion": criterion, "found": found})

    # Overall score is the ratio of found criteria
    score = sum(1 for r in results if r["found"]) / len(criteria) if criteria else 0.0
    return {"score": score, "details": results}
