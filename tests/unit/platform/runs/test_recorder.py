"""What gets written down, and what is stopped from being written down."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime

import pytest
from conftest import PRINCIPAL, TEAM

from config.constants.runs import (
    MAX_TRACE_STRING_LENGTH,
    RUN_METADATA_INTERRUPTION,
    RUN_METADATA_PARENT,
    RUN_METADATA_PRINCIPAL,
    RUN_METADATA_SUBAGENT,
    RUN_METADATA_TEAM,
    TRIGGER_ALERT,
    TRIGGER_SCHEDULE,
    TRUNCATION_MARKER_KEY,
    TURN_PAYLOAD_RATIONALE,
    TURN_USAGE_COST,
)
from platform.guardrails.engine import GuardrailEngine
from platform.guardrails.rules import GuardrailAction, GuardrailRule, Ruleset
from platform.persistence.ports import RunStatus, ToolCallStatus, UnitOfWork
from platform.runs.events import TraceEventKind
from platform.runs.recorder import RecordedCall, RecordedTurn, RunRecorder


def recorder(uow: UnitOfWork, clock: Callable[[], datetime], **kwargs: object) -> RunRecorder:
    """Return a recorder over the unit of work, with predictable identifiers."""
    counter = iter(range(10_000))
    return RunRecorder(
        store=uow.run_traces,
        clock=clock,
        ids=lambda: f"id-{next(counter):04d}",
        **kwargs,  # type: ignore[arg-type]
    )


async def test_a_run_records_its_team_principal_and_trigger(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    run = await recorder(uow, clock).start_run(
        trigger=TRIGGER_ALERT, principal_id=PRINCIPAL, team_node_id=TEAM, alert_id="alert-9"
    )

    stored = await uow.run_traces.get_run(run.run_id)

    assert stored is not None
    assert stored.status is RunStatus.RUNNING
    assert stored.metadata[RUN_METADATA_TEAM] == TEAM
    assert stored.metadata[RUN_METADATA_PRINCIPAL] == PRINCIPAL
    assert stored.trigger == TRIGGER_ALERT
    assert stored.started_at is not None


async def test_starting_a_run_puts_it_in_the_log(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    run = await recorder(uow, clock).start_run(
        trigger=TRIGGER_SCHEDULE, principal_id="schedule-nightly", team_node_id=TEAM
    )

    events = await uow.run_traces.events_for_run(run.run_id)

    assert [event.kind for event in events] == [TraceEventKind.RUN_STARTED.value]


async def test_a_turn_records_its_model_usage_cost_and_rationale(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    writer = recorder(uow, clock)
    run = await writer.start_run(trigger=TRIGGER_ALERT, principal_id=PRINCIPAL, team_node_id=TEAM)

    turn = await writer.record_turn(
        RecordedTurn(
            run_id=run.run_id,
            index=0,
            model="claude-opus-5",
            prompt_tokens=1_200,
            completion_tokens=340,
            cost=0.042,
            duration_ms=1_800,
            selection_rationale="the alert names a Kubernetes workload",
            offered_capabilities=("kubernetes.list_pods", "loki.query"),
        )
    )

    assert turn.usage[TURN_USAGE_COST] == pytest.approx(0.042)
    assert turn.payload[TURN_PAYLOAD_RATIONALE] == "the alert names a Kubernetes workload"


async def test_a_capability_call_records_its_arguments_result_and_error_class(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    writer = recorder(uow, clock)
    run = await writer.start_run(trigger=TRIGGER_ALERT, principal_id=PRINCIPAL, team_node_id=TEAM)
    turn = await writer.record_turn(RecordedTurn(run_id=run.run_id, index=0, model="m"))

    call = await writer.record_call(
        RecordedCall(
            run_id=run.run_id,
            turn_id=turn.turn_id,
            name="kubernetes.list_pods",
            status=ToolCallStatus.FAILED,
            arguments={"namespace": "payments"},
            result={"error": "the API server timed out"},
            error="the API server timed out",
            error_class="upstream_unavailable",
            evidence_ids=("e-1",),
        )
    )

    assert call.status is ToolCallStatus.FAILED
    assert call.arguments["arguments"] == {"namespace": "payments"}
    assert call.arguments["error_class"] == "upstream_unavailable"
    assert call.evidence_ids == ("e-1",)


async def test_a_sub_agent_is_a_nested_run_of_its_own(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    # Flattening a sub-agent into the parent's trace would hide what it was
    # given and what it came back with, which is what auditing delegation means.
    writer = recorder(uow, clock)
    parent = await writer.start_run(
        trigger=TRIGGER_ALERT, principal_id=PRINCIPAL, team_node_id=TEAM
    )

    child = await writer.start_subagent_run(
        parent_run_id=parent.run_id,
        objective="check the database's connection pool",
        principal_id=PRINCIPAL,
        team_node_id=TEAM,
    )

    assert child.metadata[RUN_METADATA_PARENT] == parent.run_id
    assert child.metadata[RUN_METADATA_SUBAGENT] is True

    dispatched = [
        event
        for event in await uow.run_traces.events_for_run(parent.run_id)
        if event.kind == TraceEventKind.SUBAGENT_DISPATCHED.value
    ]
    assert dispatched[0].payload["child_run_id"] == child.run_id


async def test_guardrail_masking_and_budget_events_are_recorded(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    writer = recorder(uow, clock)
    run = await writer.start_run(trigger=TRIGGER_ALERT, principal_id=PRINCIPAL, team_node_id=TEAM)

    await writer.record_guardrail_action(
        run.run_id, kind="call_denied", target="kubernetes.delete_pod", reason="above read"
    )
    await writer.record_masking(run.run_id, detector="ip_address", occurrences=4)
    await writer.record_budget_eviction(
        run.run_id, evicted=("e-3", "e-4"), reason="the evidence budget was spent"
    )

    kinds = [event.kind for event in await uow.run_traces.events_for_run(run.run_id)]

    assert TraceEventKind.GUARDRAIL_ACTION.value in kinds
    assert TraceEventKind.MASKING_APPLIED.value in kinds
    assert TraceEventKind.BUDGET_EVICTION.value in kinds


async def test_masking_events_name_the_detector_and_never_the_value(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    writer = recorder(uow, clock)
    run = await writer.start_run(trigger=TRIGGER_ALERT, principal_id=PRINCIPAL, team_node_id=TEAM)

    event = await writer.record_masking(run.run_id, detector="ip_address", occurrences=2)

    assert set(event.payload) == {"detector", "occurrences"}


async def test_a_secret_in_a_payload_is_removed_before_it_is_stored(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    # A trace holding a credential is a second store nobody audits, kept for the
    # length of the retention window.
    ruleset = Ruleset(
        rules=(
            GuardrailRule(
                name="aws-access-key",
                patterns=(re.compile(r"AKIA[0-9A-Z]{16}"),),
                action=GuardrailAction.REDACT,
                replacement="[REDACTED]",
            ),
        )
    )
    writer = recorder(uow, clock, guardrails=GuardrailEngine(ruleset=ruleset))
    run = await writer.start_run(trigger=TRIGGER_ALERT, principal_id=PRINCIPAL, team_node_id=TEAM)
    turn = await writer.record_turn(RecordedTurn(run_id=run.run_id, index=0, model="m"))

    call = await writer.record_call(
        RecordedCall(
            run_id=run.run_id,
            turn_id=turn.turn_id,
            name="shell.run",
            arguments={"command": "export KEY=AKIAIOSFODNN7EXAMPLE"},
        )
    )

    assert "AKIAIOSFODNN7EXAMPLE" not in str(call.arguments)
    assert "[REDACTED]" in str(call.arguments)


async def test_an_oversized_result_is_truncated_with_a_marker(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    writer = recorder(uow, clock)
    run = await writer.start_run(trigger=TRIGGER_ALERT, principal_id=PRINCIPAL, team_node_id=TEAM)
    turn = await writer.record_turn(RecordedTurn(run_id=run.run_id, index=0, model="m"))

    call = await writer.record_call(
        RecordedCall(
            run_id=run.run_id,
            turn_id=turn.turn_id,
            name="loki.query",
            result={"lines": "x" * (MAX_TRACE_STRING_LENGTH * 4)},
        )
    )

    assert TRUNCATION_MARKER_KEY in call.arguments
    assert call.arguments[TRUNCATION_MARKER_KEY]["strings"] == 1


async def test_a_crashed_run_leaves_an_interrupted_record_saying_why(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    writer = recorder(uow, clock)
    run = await writer.start_run(
        trigger=TRIGGER_SCHEDULE, principal_id="schedule-dr", team_node_id=TEAM
    )
    await writer.record_turn(RecordedTurn(run_id=run.run_id, index=0, model="m"))

    marked = await writer.mark_interrupted(run.run_id, reason="the lease expired")

    stored = await uow.run_traces.get_run(run.run_id)
    trace = await uow.run_traces.replay(run.run_id)

    assert stored is not None
    assert stored.status is RunStatus.INTERRUPTED
    assert stored.finished_at is not None
    assert marked.metadata[RUN_METADATA_INTERRUPTION] == "the lease expired"
    # Usable: whatever it managed to record is still there.
    assert len(trace.turns) == 1
    assert any(event.kind == TraceEventKind.RUN_INTERRUPTED.value for event in trace.events)


async def test_an_empty_ruleset_engine_alters_nothing(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    # A recorder with guardrails configured must not rewrite ordinary text.
    writer = recorder(uow, clock, guardrails=GuardrailEngine(ruleset=Ruleset(rules=())))
    run = await writer.start_run(trigger=TRIGGER_ALERT, principal_id=PRINCIPAL, team_node_id=TEAM)
    turn = await writer.record_turn(
        RecordedTurn(
            run_id=run.run_id, index=0, model="m", selection_rationale="checkout is 5xxing"
        )
    )

    assert turn.payload[TURN_PAYLOAD_RATIONALE] == "checkout is 5xxing"


def test_a_disabled_rule_is_still_a_rule_the_engine_knows_about() -> None:
    # Guards the fixture above: an empty ruleset and a disabled one are
    # different, and the recorder is tested against the first.
    ruleset = Ruleset(rules=(GuardrailRule(name="off", enabled=False),))

    assert ruleset.enabled == ()
