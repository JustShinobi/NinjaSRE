"""What one iteration leaves behind, and why it is this much.

The standard a turn record has to meet is offline replay: someone holding the
stored turns and nothing else can reconstruct the run — which capabilities were
offered, what the model asked for and why, what came back, what the context
budget dropped, and what a guardrail did about any of it.

That is why ``offered_capabilities`` is here alongside the calls. A record of
what the model *used* cannot distinguish "it never considered the metrics tool"
from "the metrics tool was not on the turn", and those two failures have
opposite fixes.

Everything is a dataclass with a JSON round trip. The trace store speaks JSON,
so a field that does not survive ``to_record``/``from_record`` is not in the
trace however carefully it was collected.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from core.capability.result import CapabilityErrorClass
from core.capability.telemetry import InvocationOutcome
from core.llm.types import FinishReason
from core.llm.usage import TokenCounts, UsageRecord


class BudgetActionKind(StrEnum):
    """What the context budget did to one evidence entry."""

    EVICTED = "evicted"
    TRUNCATED = "truncated"


class GuardrailActionKind(StrEnum):
    """A bound the loop enforced, named so the trace explains itself.

    Closed, and every member corresponds to a rule that can change the run's
    course. A guardrail that fired without a member here would be invisible in
    exactly the run where someone is asking why the agent stopped.
    """

    REPLAYED_DUPLICATE = "replayed_duplicate"
    STAGNATION_NUDGE = "stagnation_nudge"
    TOOL_ACCESS_STRIPPED = "tool_access_stripped"
    CALL_DENIED = "call_denied"
    ARGUMENTS_REWRITTEN = "arguments_rewritten"
    UNKNOWN_CAPABILITY = "unknown_capability"
    SUBAGENT_DEPTH_EXCEEDED = "subagent_depth_exceeded"
    ITERATION_CEILING_REACHED = "iteration_ceiling_reached"
    WALL_CLOCK_EXCEEDED = "wall_clock_exceeded"
    MESSAGE_QUEUED = "message_queued"
    HANDOFF_TIMED_OUT = "handoff_timed_out"
    #: The transcript was summarised to stay inside the model's usable context.
    TRANSCRIPT_COMPACTED = "transcript_compacted"
    #: Fewer capability schemas were carried than the loop holds, because the
    #: model demonstrated it cannot hold that many.
    SCHEMAS_NARROWED = "schemas_narrowed"
    #: A capability result was shortened for the model. The whole of it is on
    #: the evidence entry the reason names.
    RESULT_TRUNCATED = "result_truncated"
    #: The model's own output had to be repaired before the turn could be used.
    MODEL_OUTPUT_REPAIRED = "model_output_repaired"


@dataclass(frozen=True, slots=True)
class BudgetAction:
    """One eviction or truncation, with the size it saved.

    ``reason`` is prose on purpose. The value function's ordering is pinned by
    a golden test; what an operator needs in the trace is the sentence that
    says why *this* entry was the one to go.
    """

    kind: BudgetActionKind
    evidence_id: str
    tokens_before: int = 0
    tokens_after: int = 0
    reason: str = ""

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this action."""
        return {
            "kind": self.kind.value,
            "evidence_id": self.evidence_id,
            "tokens_before": self.tokens_before,
            "tokens_after": self.tokens_after,
            "reason": self.reason,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> BudgetAction:
        """Return the action a stored record describes."""
        return cls(
            kind=BudgetActionKind(record["kind"]),
            evidence_id=str(record["evidence_id"]),
            tokens_before=int(record.get("tokens_before", 0)),
            tokens_after=int(record.get("tokens_after", 0)),
            reason=str(record.get("reason", "")),
        )


@dataclass(frozen=True, slots=True)
class GuardrailAction:
    """One bound the loop enforced, and what it was enforced against."""

    kind: GuardrailActionKind
    target: str = ""
    reason: str = ""

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this action."""
        return {"kind": self.kind.value, "target": self.target, "reason": self.reason}

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> GuardrailAction:
        """Return the action a stored record describes."""
        return cls(
            kind=GuardrailActionKind(record["kind"]),
            target=str(record.get("target", "")),
            reason=str(record.get("reason", "")),
        )


@dataclass(frozen=True, slots=True)
class HookFailure:
    """A hook that raised, recorded rather than allowed to fail the turn."""

    point: str
    hook: str
    error: str

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this failure."""
        return {"point": self.point, "hook": self.hook, "error": self.error}

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> HookFailure:
        """Return the failure a stored record describes."""
        return cls(
            point=str(record["point"]),
            hook=str(record["hook"]),
            error=str(record.get("error", "")),
        )


@dataclass(frozen=True, slots=True)
class ToolExecution:
    """One capability call as it happened, including when it did not run.

    ``replayed`` separates a cache hit from a fresh call. Both are legitimate
    turns for the model; only one of them produced evidence, and the stagnation
    breaker is the code that has to tell them apart.
    """

    call_id: str
    capability: str
    arguments: dict[str, Any] = field(default_factory=dict)
    outcome: InvocationOutcome = InvocationOutcome.SUCCESS
    duration_seconds: float = 0.0
    replayed: bool = False
    denied: bool = False
    error_class: CapabilityErrorClass | None = None
    error_message: str = ""
    evidence_ids: tuple[str, ...] = ()

    @property
    def produced_fresh_evidence(self) -> bool:
        """Return whether this call added something the session did not have."""
        return not self.replayed and self.outcome is InvocationOutcome.SUCCESS

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this execution."""
        return {
            "call_id": self.call_id,
            "capability": self.capability,
            "arguments": self.arguments,
            "outcome": self.outcome.value,
            "duration_seconds": self.duration_seconds,
            "replayed": self.replayed,
            "denied": self.denied,
            "error_class": self.error_class.value if self.error_class else None,
            "error_message": self.error_message,
            "evidence_ids": list(self.evidence_ids),
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> ToolExecution:
        """Return the execution a stored record describes."""
        error_class = record.get("error_class")
        return cls(
            call_id=str(record["call_id"]),
            capability=str(record["capability"]),
            arguments=dict(record.get("arguments") or {}),
            outcome=InvocationOutcome(record.get("outcome", InvocationOutcome.SUCCESS.value)),
            duration_seconds=float(record.get("duration_seconds", 0.0)),
            replayed=bool(record.get("replayed", False)),
            denied=bool(record.get("denied", False)),
            error_class=CapabilityErrorClass(error_class) if error_class else None,
            error_message=str(record.get("error_message", "")),
            evidence_ids=tuple(str(item) for item in record.get("evidence_ids") or ()),
        )


def _usage_record(usage: UsageRecord) -> dict[str, Any]:
    """Return one usage record as JSON."""
    return {
        "provider_id": usage.provider_id,
        "model_id": usage.model_id,
        "tokens": {
            "input_tokens": usage.tokens.input_tokens,
            "output_tokens": usage.tokens.output_tokens,
            "cached_input_tokens": usage.tokens.cached_input_tokens,
            "cache_write_tokens": usage.tokens.cache_write_tokens,
            "reasoning_tokens": usage.tokens.reasoning_tokens,
            "estimated": usage.tokens.estimated,
        },
        "cost_usd": usage.cost_usd,
        "pricing_as_of": usage.pricing_as_of.isoformat() if usage.pricing_as_of else None,
    }


def _usage_from_record(record: Mapping[str, Any]) -> UsageRecord:
    """Return the usage a stored record describes."""
    tokens = record.get("tokens") or {}
    priced_on = record.get("pricing_as_of")
    return UsageRecord(
        provider_id=str(record.get("provider_id", "")),
        model_id=str(record.get("model_id", "")),
        tokens=TokenCounts(
            input_tokens=int(tokens.get("input_tokens", 0)),
            output_tokens=int(tokens.get("output_tokens", 0)),
            cached_input_tokens=int(tokens.get("cached_input_tokens", 0)),
            cache_write_tokens=int(tokens.get("cache_write_tokens", 0)),
            reasoning_tokens=int(tokens.get("reasoning_tokens", 0)),
            estimated=bool(tokens.get("estimated", False)),
        ),
        cost_usd=record.get("cost_usd"),
        pricing_as_of=date.fromisoformat(str(priced_on)) if priced_on else None,
    )


@dataclass(frozen=True, slots=True)
class Turn:
    """One model call, everything it triggered, and everything that bounded it."""

    index: int
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    duration_seconds: float = 0.0
    offered_capabilities: tuple[str, ...] = ()
    #: What the model said while it worked. Its own reasoning for this turn.
    rationale: str = ""
    #: Why the capabilities above were the ones on offer — the half of a turn
    #: that cannot be reconstructed from what was called. Distinct from
    #: ``rationale`` on purpose: a turn that only emitted tool calls says
    #: nothing, and a field carrying the model's silence would read as "the
    #: selection had no reason" to whoever opened it asking why something was
    #: missing.
    selection_rationale: str = ""
    provider_id: str = ""
    model_id: str = ""
    finish_reason: FinishReason = FinishReason.STOP
    executions: tuple[ToolExecution, ...] = ()
    usage: UsageRecord | None = None
    budget_actions: tuple[BudgetAction, ...] = ()
    guardrail_actions: tuple[GuardrailAction, ...] = ()
    hook_failures: tuple[HookFailure, ...] = ()

    @property
    def produced_fresh_evidence(self) -> bool:
        """Return whether any call in this turn added something new.

        This is the stagnation breaker's input. A turn of nothing but replays
        and denials is sterile however much text the model produced around it.
        """
        return any(execution.produced_fresh_evidence for execution in self.executions)

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this turn."""
        return {
            "index": self.index,
            "started_at": self.started_at.isoformat(),
            "duration_seconds": self.duration_seconds,
            "offered_capabilities": list(self.offered_capabilities),
            "rationale": self.rationale,
            "selection_rationale": self.selection_rationale,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "finish_reason": self.finish_reason.value,
            "executions": [execution.to_record() for execution in self.executions],
            "usage": _usage_record(self.usage) if self.usage else None,
            "budget_actions": [action.to_record() for action in self.budget_actions],
            "guardrail_actions": [action.to_record() for action in self.guardrail_actions],
            "hook_failures": [failure.to_record() for failure in self.hook_failures],
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> Turn:
        """Return the turn a stored record describes."""
        usage = record.get("usage")
        return cls(
            index=int(record["index"]),
            started_at=datetime.fromisoformat(str(record["started_at"])),
            duration_seconds=float(record.get("duration_seconds", 0.0)),
            offered_capabilities=tuple(
                str(name) for name in record.get("offered_capabilities") or ()
            ),
            rationale=str(record.get("rationale", "")),
            selection_rationale=str(record.get("selection_rationale", "")),
            provider_id=str(record.get("provider_id", "")),
            model_id=str(record.get("model_id", "")),
            finish_reason=FinishReason(record.get("finish_reason", FinishReason.STOP.value)),
            executions=tuple(
                ToolExecution.from_record(item) for item in record.get("executions") or ()
            ),
            usage=_usage_from_record(usage) if usage else None,
            budget_actions=tuple(
                BudgetAction.from_record(item) for item in record.get("budget_actions") or ()
            ),
            guardrail_actions=tuple(
                GuardrailAction.from_record(item) for item in record.get("guardrail_actions") or ()
            ),
            hook_failures=tuple(
                HookFailure.from_record(item) for item in record.get("hook_failures") or ()
            ),
        )


__all__ = [
    "BudgetAction",
    "BudgetActionKind",
    "GuardrailAction",
    "GuardrailActionKind",
    "HookFailure",
    "ToolExecution",
    "Turn",
]
