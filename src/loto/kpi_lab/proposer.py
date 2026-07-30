"""Experiment proposers, including a hardened local-LLM proposer.

Threat model for the LLM proposer
--------------------------------
An LLM asked to propose experiment configurations is an *untrusted input source*. Its
output may be malformed, out of range, or shaped by content that reached it from anywhere
in its context. Treating that output as configuration means an attacker who can influence
the model's context can influence what the lab executes.

Consequences enforced here:

* Output is parsed as JSON only. No ``eval``, no ``exec``, no ``import`` driven by model
  output, and no resolution of strings into callables, modules, or filesystem paths.
* Every field is checked against an explicit allowlist. Unknown keys are rejected outright
  rather than ignored, because silently dropping a key hides the fact that the model tried
  to set something it should not have.
* Numeric fields are clamped to declared ranges, and the clamp is logged.
* Fields that feed ``protocol_hash`` or the KPI definition are structurally unreachable:
  they are simply not part of the proposal schema, so no model output can move the goalposts
  mid-run.
* The model's stated confidence or reasoning never affects acceptance. Proposals are
  accepted or rejected by schema; whether the resulting experiment is a *win* is decided
  only by the e-process in :mod:`loto.kpi_lab.stopping`.
* Endpoint failure returns an ``UNAVAILABLE`` status with the exact error and the caller
  falls back to grid search *explicitly*. Constitution principle II forbids the silent
  substitution that would otherwise make an unreachable LLM look like a working one.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

__all__ = [
    "PARAMETER_SPACE",
    "ProposalStatus",
    "Proposal",
    "ProposalRejection",
    "ProposerResult",
    "validate_proposal",
    "GridProposer",
    "LlmProposer",
]

ProposalStatus = Literal["ACCEPTED", "REJECTED", "UNAVAILABLE"]
_SCHEMA_VERSION = "1.0.0"


@dataclass(frozen=True)
class ParameterSpec:
    """Allowlist entry: the only shapes a proposal field may take."""

    kind: Literal["int", "float", "choice"]
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[str, ...] = ()

    def coerce(self, value: Any) -> tuple[Any, str | None]:
        """Return ``(value, clamp_note)``. Raises ``ValueError`` when unusable."""
        if self.kind == "choice":
            text = str(value)
            if text not in self.choices:
                raise ValueError(f"value {text!r} not in choices {list(self.choices)}")
            return text, None
        try:
            number = int(value) if self.kind == "int" else float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"value {value!r} is not a {self.kind}") from exc
        note = None
        if self.minimum is not None and number < self.minimum:
            note = f"clamped from {number} up to minimum {self.minimum}"
            number = int(self.minimum) if self.kind == "int" else float(self.minimum)
        if self.maximum is not None and number > self.maximum:
            note = f"clamped from {number} down to maximum {self.maximum}"
            number = int(self.maximum) if self.kind == "int" else float(self.maximum)
        return number, note


#: The complete proposal surface. Anything absent here cannot be set by a proposer.
#:
#: Deliberately excluded: ``n_tickets``, ``tolerance``, ``target_coverage``, ``alpha``,
#: ``max_false_positive_rate``, dataset paths, split boundaries, seeds used for sealing,
#: model revisions. Those belong to the KPI definition and the evaluation protocol, and a
#: proposer that could change them could reach the target by redefining it.
PARAMETER_SPACE: dict[str, ParameterSpec] = {
    "point_method": ParameterSpec(
        kind="choice",
        choices=(
            "last",
            "mean",
            "median",
            "ewm",
            "rolling_mean",
            "seasonal_naive",
            "drift",
        ),
    ),
    "window": ParameterSpec(kind="int", minimum=2, maximum=500),
    "halflife": ParameterSpec(kind="float", minimum=0.5, maximum=200.0),
    "pool_size": ParameterSpec(kind="int", minimum=10, maximum=200_000),
    "per_position_top": ParameterSpec(kind="int", minimum=1, maximum=40),
    "beam_width": ParameterSpec(kind="int", minimum=1, maximum=200_000),
    "diversity_penalty": ParameterSpec(kind="float", minimum=0.0, maximum=1.0),
    "residual_scale": ParameterSpec(kind="float", minimum=0.0, maximum=10.0),
    "selection": ParameterSpec(
        kind="choice", choices=("greedy_max", "greedy_min_cover", "topk")
    ),
    "proposal_seed": ParameterSpec(kind="int", minimum=0, maximum=2**31 - 1),
}


@dataclass(frozen=True)
class Proposal:
    """A validated experiment configuration."""

    proposal_id: str
    source: str
    parameters: dict[str, Any]
    clamp_notes: tuple[str, ...] = field(default_factory=tuple)
    rationale: str | None = None
    schema_version: str = _SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["clamp_notes"] = list(self.clamp_notes)
        return payload


@dataclass(frozen=True)
class ProposalRejection:
    """A rejected proposal and the exact reason, kept for audit."""

    source: str
    reason: str
    raw: str
    schema_version: str = _SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProposerResult:
    """Batch outcome. ``status`` distinguishes "nothing valid" from "unreachable"."""

    status: ProposalStatus
    proposals: tuple[Proposal, ...] = field(default_factory=tuple)
    rejections: tuple[ProposalRejection, ...] = field(default_factory=tuple)
    error: str | None = None
    endpoint: str | None = None
    schema_version: str = _SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "proposals": [p.to_dict() for p in self.proposals],
            "rejections": [r.to_dict() for r in self.rejections],
            "error": self.error,
            "endpoint": self.endpoint,
            "schema_version": self.schema_version,
        }


def validate_proposal(
    raw: Any, *, source: str, proposal_id: str
) -> tuple[Proposal | None, ProposalRejection | None]:
    """Validate one untrusted proposal against :data:`PARAMETER_SPACE`.

    Unknown keys are a rejection, not a warning: a proposer attempting to set something
    outside the space is a signal worth surfacing.
    """
    text = json.dumps(raw, default=str)[:2000]
    if not isinstance(raw, Mapping):
        return None, ProposalRejection(source, "proposal is not an object", text)
    rationale = raw.get("rationale")
    if rationale is not None and not isinstance(rationale, str):
        return None, ProposalRejection(source, "rationale must be a string", text)
    unknown = [
        key for key in raw if key not in PARAMETER_SPACE and key != "rationale"
    ]
    if unknown:
        return None, ProposalRejection(
            source,
            f"unknown keys rejected: {sorted(unknown)}; allowed={sorted(PARAMETER_SPACE)}",
            text,
        )
    params: dict[str, Any] = {}
    notes: list[str] = []
    for key, spec in PARAMETER_SPACE.items():
        if key not in raw:
            continue
        try:
            value, note = spec.coerce(raw[key])
        except ValueError as exc:
            return None, ProposalRejection(source, f"{key}: {exc}", text)
        params[key] = value
        if note:
            notes.append(f"{key}: {note}")
    if not params:
        return None, ProposalRejection(source, "proposal set no allowed parameters", text)
    if "point_method" not in params:
        return None, ProposalRejection(source, "point_method is required", text)
    return (
        Proposal(
            proposal_id=proposal_id,
            source=source,
            parameters=params,
            clamp_notes=tuple(notes),
            rationale=(rationale[:500] if isinstance(rationale, str) else None),
        ),
        None,
    )


class GridProposer:
    """Deterministic grid over the allowed space. The fallback and the control.

    Because it is deterministic and data-independent, a run driven purely by this proposer
    is exactly reproducible, which makes it the right baseline for judging whether the LLM
    proposer contributes anything.
    """

    def __init__(self, space: Mapping[str, Sequence[Any]] | None = None) -> None:
        self.space: dict[str, list[Any]] = {
            "point_method": ["last", "mean", "median", "ewm", "seasonal_naive"],
            "window": [5, 10, 25, 50, 100],
            "pool_size": [2000, 8000, 20000],
            "per_position_top": [3, 5, 9],
            "diversity_penalty": [0.0, 0.05, 0.2],
            "selection": ["greedy_max"],
        }
        if space:
            self.space.update({k: list(v) for k, v in space.items()})
        self._cursor = 0

    def _combinations(self) -> list[dict[str, Any]]:
        import itertools

        keys = sorted(self.space)
        return [
            dict(zip(keys, values, strict=True))
            for values in itertools.product(*(self.space[k] for k in keys))
        ]

    def propose(self, *, count: int = 1, **_: Any) -> ProposerResult:
        combos = self._combinations()
        proposals: list[Proposal] = []
        rejections: list[ProposalRejection] = []
        while len(proposals) < count and self._cursor < len(combos):
            raw = combos[self._cursor]
            pid = f"grid-{self._cursor:06d}"
            self._cursor += 1
            proposal, rejection = validate_proposal(raw, source="grid", proposal_id=pid)
            if proposal:
                proposals.append(proposal)
            elif rejection:
                rejections.append(rejection)
        status: ProposalStatus = "ACCEPTED" if proposals else "REJECTED"
        return ProposerResult(
            status=status, proposals=tuple(proposals), rejections=tuple(rejections)
        )

    @property
    def exhausted(self) -> bool:
        return self._cursor >= len(self._combinations())


class LlmProposer:
    """Local-LLM proposer with schema validation and no code path from output to execution.

    The prompt states the allowed keys and ranges, but the prompt is not the enforcement --
    :func:`validate_proposal` is. A model that ignores the instructions produces rejections,
    never an out-of-range experiment.
    """

    SYSTEM_PROMPT = (
        "You propose configurations for a lottery coverage experiment. "
        "Reply with a JSON array of objects and nothing else: no prose, no markdown "
        "fences. Each object may set only these keys, within these ranges:\n"
        "{allowed}\n"
        "You may add an optional string field 'rationale'. Any other key causes the "
        "whole proposal to be rejected. You cannot change the ticket budget, the "
        "tolerance, the target coverage, the significance level, or the data splits."
    )

    def __init__(
        self,
        *,
        endpoint: str,
        model: str = "local",
        timeout_seconds: float = 60.0,
        max_proposals: int = 8,
        temperature: float = 0.7,
    ) -> None:
        self.endpoint = endpoint
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_proposals = max_proposals
        self.temperature = temperature

    def _allowed_description(self) -> str:
        lines = []
        for key, spec in sorted(PARAMETER_SPACE.items()):
            if spec.kind == "choice":
                lines.append(f"- {key}: one of {list(spec.choices)}")
            else:
                lines.append(
                    f"- {key}: {spec.kind} in [{spec.minimum}, {spec.maximum}]"
                )
        return "\n".join(lines)

    def _build_user_prompt(self, context: Mapping[str, Any]) -> str:
        """Context is summarised numerically; no free text from prior turns is forwarded."""
        safe = {
            "game": str(context.get("game", "")),
            "n_experiments_done": int(context.get("n_experiments_done", 0)),
            "budget_remaining": int(context.get("budget_remaining", 0)),
            "best_coverage": float(context.get("best_coverage", 0.0)),
            "reference_coverage": float(context.get("reference_coverage", 0.0)),
            "n_tickets": int(context.get("n_tickets", 0)),
            "tolerance": int(context.get("tolerance", 1)),
        }
        return (
            "Propose up to "
            f"{self.max_proposals} configurations as a JSON array. Context: "
            + json.dumps(safe, sort_keys=True)
        )

    def propose(
        self,
        *,
        count: int = 1,
        context: Mapping[str, Any] | None = None,
        **_: Any,
    ) -> ProposerResult:
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "stream": False,
            "messages": [
                {
                    "role": "system",
                    "content": self.SYSTEM_PROMPT.format(
                        allowed=self._allowed_description()
                    ),
                },
                {"role": "user", "content": self._build_user_prompt(context or {})},
            ],
        }
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
            # Constitution II: report unavailability with the exact error; do not pretend
            # the proposer worked and do not silently switch to grid here.
            return ProposerResult(
                status="UNAVAILABLE", error=f"{type(exc).__name__}: {exc}", endpoint=self.endpoint
            )

        try:
            envelope = json.loads(body)
            content = envelope["choices"][0]["message"]["content"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            return ProposerResult(
                status="REJECTED",
                error=f"unparseable response envelope: {type(exc).__name__}: {exc}",
                endpoint=self.endpoint,
                rejections=(
                    ProposalRejection("llm", "response envelope not understood", body[:2000]),
                ),
            )

        text = content.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
            text = text.strip()
        try:
            items = json.loads(text)
        except json.JSONDecodeError as exc:
            return ProposerResult(
                status="REJECTED",
                error=f"content is not JSON: {exc}",
                endpoint=self.endpoint,
                rejections=(ProposalRejection("llm", "content is not JSON", text[:2000]),),
            )
        if isinstance(items, Mapping):
            items = [items]
        if not isinstance(items, list):
            return ProposerResult(
                status="REJECTED",
                error="content is neither an object nor an array",
                endpoint=self.endpoint,
                rejections=(ProposalRejection("llm", "not an array", text[:2000]),),
            )

        proposals: list[Proposal] = []
        rejections: list[ProposalRejection] = []
        for index, raw in enumerate(items[: self.max_proposals]):
            proposal, rejection = validate_proposal(
                raw, source="llm", proposal_id=f"llm-{index:04d}"
            )
            if proposal:
                proposals.append(proposal)
            elif rejection:
                rejections.append(rejection)
            if len(proposals) >= count:
                break
        return ProposerResult(
            status="ACCEPTED" if proposals else "REJECTED",
            proposals=tuple(proposals),
            rejections=tuple(rejections),
            endpoint=self.endpoint,
            error=None if proposals else "no proposal passed validation",
        )
