"""One iteration's record, and the standard it has to meet.

The standard is not "enough to debug with". It is that someone holding only the
stored turns can replay the run offline: which capabilities were offered, what
the model asked for, what came back, what the budget dropped, and what a
guardrail did about it.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from core.agent.turn import (
    BudgetAction,
    BudgetActionKind,
    GuardrailAction,
    GuardrailActionKind,
    HookFailure,
    ToolExecution,
    Turn,
)
from core.capability.result import CapabilityErrorClass
from core.capability.telemetry import InvocationOutcome
from core.llm.types import FinishReason
from core.llm.usage import TokenCounts, UsageRecord

pytestmark = pytest.mark.unit


def _turn() -> Turn:
    return Turn(
        index=2,
        started_at=datetime(2026, 8, 5, 12, 0, tzinfo=UTC),
        duration_seconds=1.25,
        offered_capabilities=("datadog_log_statistics", "record_hypothesis"),
        rationale="The error rate rose after the 12:02 deploy; checking the logs.",
        provider_id="anthropic",
        model_id="claude-opus-5",
        finish_reason=FinishReason.TOOL_CALLS,
        executions=(
            ToolExecution(
                call_id="c1",
                capability="datadog_log_statistics",
                arguments={"query": "service:checkout status:500"},
                outcome=InvocationOutcome.SUCCESS,
                duration_seconds=0.8,
                evidence_ids=("e1",),
            ),
            ToolExecution(
                call_id="c2",
                capability="datadog_log_statistics",
                arguments={"query": "service:checkout status:500"},
                outcome=InvocationOutcome.SUCCESS,
                duration_seconds=0.0,
                replayed=True,
                evidence_ids=("e1",),
            ),
            ToolExecution(
                call_id="c3",
                capability="grafana_query",
                arguments={},
                outcome=InvocationOutcome.FAILURE,
                duration_seconds=0.1,
                error_class=CapabilityErrorClass.TIMEOUT,
                error_message="grafana_query failed: TimeoutError",
            ),
        ),
        usage=UsageRecord(
            provider_id="anthropic",
            model_id="claude-opus-5",
            tokens=TokenCounts(input_tokens=1200, output_tokens=80),
            cost_usd=0.004,
        ),
        budget_actions=(
            BudgetAction(
                kind=BudgetActionKind.EVICTED,
                evidence_id="e0",
                tokens_before=900,
                tokens_after=0,
                reason="oldest uncited entry",
            ),
        ),
        guardrail_actions=(
            GuardrailAction(
                kind=GuardrailActionKind.REPLAYED_DUPLICATE,
                target="datadog_log_statistics",
                reason="identical arguments to call c1",
            ),
        ),
        hook_failures=(HookFailure(point="post_tool_use", hook="mask_output", error="KeyError"),),
    )


def test_a_turn_names_what_was_offered_not_only_what_was_called() -> None:
    """A selection nobody can see is a selection nobody can improve: the tools
    the model declined matter as much as the ones it used."""
    assert _turn().offered_capabilities == ("datadog_log_statistics", "record_hypothesis")


def test_a_replayed_call_is_marked_as_such() -> None:
    replayed = [execution for execution in _turn().executions if execution.replayed]

    assert [execution.call_id for execution in replayed] == ["c2"]


def test_a_turn_that_produced_no_fresh_evidence_says_so() -> None:
    turn = _turn()

    assert turn.produced_fresh_evidence is True

    sterile = Turn(
        index=3,
        started_at=datetime(2026, 8, 5, 12, 1, tzinfo=UTC),
        executions=(
            ToolExecution(
                call_id="c9",
                capability="datadog_log_statistics",
                arguments={},
                outcome=InvocationOutcome.SUCCESS,
                duration_seconds=0.0,
                replayed=True,
            ),
        ),
    )
    assert sterile.produced_fresh_evidence is False


def test_a_turn_round_trips_through_json() -> None:
    turn = _turn()

    restored = Turn.from_record(json.loads(json.dumps(turn.to_record())))

    assert restored == turn


def test_a_failed_execution_carries_its_classification() -> None:
    failed = _turn().executions[2]

    assert failed.outcome is InvocationOutcome.FAILURE
    assert failed.error_class is CapabilityErrorClass.TIMEOUT


def test_a_hook_failure_is_recorded_rather_than_raised() -> None:
    assert _turn().hook_failures[0].point == "post_tool_use"
