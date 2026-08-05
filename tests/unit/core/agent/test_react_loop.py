"""The loop's ordinary behaviour: seeds, conclusions, degradation, and the trace.

The pathological cases live in ``test_guardrails``. This file is the other half
— what the loop does when nothing is going wrong, and what the trace it leaves
behind has to contain for a run to be reconstructable without it.
"""

from __future__ import annotations

import pytest

from config.constants.investigation import MAX_AGENT_TOOL_SCHEMAS
from core.agent.conclusion import Acceptance, RequirePlannedCapabilities
from core.agent.react_loop import CANONICAL_RUNTIME_NAME, ReActLoop
from core.agent.runtime_port import RunRequest, RunStatus, Runtime, SeedCall
from core.agent.seed_calls import SeedCatalogue, SeedPlan
from core.agent.session import Session, SessionStatus
from core.capability.telemetry import InvocationOutcome
from core.llm.types import Role, ToolCall
from tests.unit.core.agent.conftest import (
    DEFAULT_TOOLS,
    LOG_SEARCH,
    METRIC_READ,
    ScriptedLLM,
    call_turn,
    failed_turn,
    log_call,
    text_turn,
)

pytestmark = pytest.mark.unit


# --- the port -----------------------------------------------------------------


def test_the_loop_is_the_canonical_runtime() -> None:
    loop = ReActLoop(llm=ScriptedLLM([text_turn("done")]))

    assert isinstance(loop, Runtime)
    assert loop.is_canonical
    assert loop.name == CANONICAL_RUNTIME_NAME


def test_a_turn_may_not_carry_more_schemas_than_the_cap() -> None:
    """Selection caps this before the loop sees it; the loop refuses to be the
    place where a cap somebody forgot goes unnoticed."""
    too_many = tuple(LOG_SEARCH for _ in range(MAX_AGENT_TOOL_SCHEMAS + 1))

    with pytest.raises(ValueError, match=str(MAX_AGENT_TOOL_SCHEMAS)):
        ReActLoop(llm=ScriptedLLM([text_turn("done")]), tools=too_many)


def test_the_schemas_the_loop_adds_for_itself_count_against_the_cap() -> None:
    """Handoff and sub-agent dispatch are schemas on the turn like any other.
    Counting only the selected capabilities would put a well-configured
    deployment two over the bound on every turn."""
    from core.agent.handoff import NoHumanAvailable
    from core.agent.subagents.definition import SubAgent

    exactly_full = tuple(LOG_SEARCH for _ in range(MAX_AGENT_TOOL_SCHEMAS))
    specialist = SubAgent(name="a", description="x", capabilities=("fixture_log_search",))

    with pytest.raises(ValueError, match="handoff"):
        ReActLoop(
            llm=ScriptedLLM([text_turn("done")]),
            tools=exactly_full,
            handoff_channel=NoHumanAvailable(),
            subagents=(specialist,),
        )


# --- seed calls ---------------------------------------------------------------


async def test_seed_calls_run_before_the_models_first_turn() -> None:
    catalogue = SeedCatalogue(
        plans=(
            SeedPlan(
                alert_source="datadog",
                calls=(SeedCall(capability="fixture_log_search", arguments={"query": "seeded"}),),
            ),
        )
    )
    llm = ScriptedLLM([text_turn("The seeded evidence is enough.")])
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS, seed_catalogue=catalogue)

    result = await loop.run(RunRequest(objective="anything", alert_source="datadog"))

    assert [entry.capability for entry in result.evidence] == ["fixture_log_search"]
    first_request = llm.requests[0]
    assert any(message.tool_results for message in first_request.messages), (
        "the model's first turn already carries the seeded evidence"
    )


async def test_a_source_with_no_plan_starts_cold() -> None:
    llm = ScriptedLLM([text_turn("Nothing to go on.")])
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS, seed_catalogue=SeedCatalogue())

    result = await loop.run(RunRequest(objective="anything", alert_source="pagerduty"))

    assert result.evidence == ()


async def test_the_request_may_add_seed_calls_of_its_own() -> None:
    llm = ScriptedLLM([text_turn("done")])
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS)

    result = await loop.run(
        RunRequest(
            objective="anything",
            seed_calls=(SeedCall(capability="fixture_metric_read", arguments={"series": "cpu"}),),
        )
    )

    assert [entry.capability for entry in result.evidence] == ["fixture_metric_read"]


def test_a_seed_plan_matches_its_source_case_insensitively() -> None:
    catalogue = SeedCatalogue(
        plans=(SeedPlan(alert_source="Datadog", calls=(SeedCall(capability="x"),)),)
    )

    assert catalogue.for_source("DATADOG")
    assert catalogue.for_source("  datadog ")
    assert catalogue.for_source("grafana") == ()


def test_a_plan_replaces_an_earlier_one_for_the_same_source() -> None:
    catalogue = SeedCatalogue(
        plans=(SeedPlan(alert_source="datadog", calls=(SeedCall(capability="old"),)),)
    ).with_plan(SeedPlan(alert_source="datadog", calls=(SeedCall(capability="new"),)))

    assert [call.capability for call in catalogue.for_source("datadog")] == ["new"]


# --- conclusions --------------------------------------------------------------


async def test_a_text_answer_concludes_the_run_by_default() -> None:
    llm = ScriptedLLM([text_turn("The 12:02 deploy introduced the regression.")])
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS)

    result = await loop.run(RunRequest(objective="anything"))

    assert result.status is RunStatus.COMPLETED
    assert result.answer == "The 12:02 deploy introduced the regression."
    assert result.session.status is SessionStatus.COMPLETED
    assert result.iterations == 1


async def test_a_strict_policy_refuses_an_early_stop_and_says_what_is_missing() -> None:
    llm = ScriptedLLM(
        [
            text_turn("It was the deploy."),
            call_turn(
                ToolCall(id="c1", name="fixture_metric_read", arguments={"series": "latency"})
            ),
            text_turn("Confirmed by the latency series: it was the deploy."),
        ],
        repeat_last=False,
    )
    loop = ReActLoop(
        llm=llm,
        tools=(LOG_SEARCH, METRIC_READ),
        conclusion=RequirePlannedCapabilities(planned=("fixture_metric_read",)),
    )

    result = await loop.run(RunRequest(objective="anything"))

    assert result.status is RunStatus.COMPLETED
    assert result.iterations == 3
    refusal = [
        message
        for message in result.session.transcript
        if message.role is Role.USER and "fixture_metric_read" in message.text
    ]
    assert refusal, "the model is told which planned capability it skipped"


def test_the_strict_policy_counts_an_attempt_rather_than_a_success() -> None:
    """Holding a run open until an unavailable vendor comes back trades one
    failure mode for a worse one."""
    from core.agent.turn import ToolExecution, Turn

    session = Session(id="run-1")
    session.turns.append(
        Turn(
            index=1,
            executions=(
                ToolExecution(
                    call_id="c1",
                    capability="fixture_metric_read",
                    outcome=InvocationOutcome.FAILURE,
                ),
            ),
        )
    )

    policy = RequirePlannedCapabilities(planned=("fixture_metric_read",))

    assert policy.accepts(session, "done") == Acceptance(accepted=True)


# --- degradation --------------------------------------------------------------


async def test_a_provider_failure_produces_a_partial_result_not_an_exception() -> None:
    llm = ScriptedLLM(
        [call_turn(log_call("c1")), failed_turn("the provider returned 503")],
        repeat_last=False,
    )
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS)

    result = await loop.run(RunRequest(objective="anything"))

    assert result.status is RunStatus.PARTIAL
    assert result.degraded
    assert result.failure == "the provider returned 503"
    assert result.session.status is SessionStatus.FAILED


async def test_a_degraded_answer_preserves_the_evidence_gathered_so_far() -> None:
    llm = ScriptedLLM(
        [call_turn(log_call("c1")), failed_turn("the provider returned 503")],
        repeat_last=False,
    )
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS)

    result = await loop.run(RunRequest(objective="anything"))

    assert result.evidence, "the evidence gathered before the failure survives it"
    assert "fixture_log_search" in result.answer
    assert "did not finish" in result.answer


async def test_the_failed_turn_is_still_in_the_trace() -> None:
    """A model call that failed is a thing that happened, and a trace missing
    it reads as a run that simply stopped."""
    llm = ScriptedLLM([failed_turn("the provider returned 503")], repeat_last=False)
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS)

    result = await loop.run(RunRequest(objective="anything"))

    assert len(result.turns) == 1
    assert result.turns[0].finish_reason.value == "error"


# --- the trace ----------------------------------------------------------------


async def test_every_iteration_emits_a_turn() -> None:
    llm = ScriptedLLM(
        [call_turn(log_call("c1")), call_turn(log_call("c2", "different")), text_turn("done")],
        repeat_last=False,
    )
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS)

    result = await loop.run(RunRequest(objective="anything"))

    assert [turn.index for turn in result.turns] == [1, 2, 3]


async def test_a_turn_records_what_was_offered_and_what_was_called() -> None:
    llm = ScriptedLLM([call_turn(log_call("c1")), text_turn("done")], repeat_last=False)
    loop = ReActLoop(llm=llm, tools=(LOG_SEARCH, METRIC_READ))

    result = await loop.run(RunRequest(objective="anything"))

    first = result.turns[0]
    assert first.offered_capabilities == ("fixture_log_search", "fixture_metric_read")
    assert [execution.capability for execution in first.executions] == ["fixture_log_search"]
    assert first.rationale == ""
    assert first.usage is not None


async def test_the_run_is_reconstructable_from_its_stored_turns_alone() -> None:
    """SC-008. Replay means the record round-trips, not that it reads well."""
    import json

    llm = ScriptedLLM([call_turn(log_call("c1")), text_turn("done")], repeat_last=False)
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS)

    result = await loop.run(RunRequest(objective="anything"))
    restored = Session.from_record(json.loads(json.dumps(result.session.to_record())))

    assert restored.turns == result.session.turns
    assert restored.evidence == result.session.evidence
    assert restored.transcript == result.session.transcript


async def test_usage_accumulates_across_the_run() -> None:
    llm = ScriptedLLM([call_turn(log_call("c1")), text_turn("done")], repeat_last=False)
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS)

    result = await loop.run(RunRequest(objective="anything"))

    assert result.session.usage.call_count == 2
    assert result.tokens.output_tokens == 40


# --- sessions -----------------------------------------------------------------


async def test_a_run_uses_the_session_identifier_it_was_given() -> None:
    llm = ScriptedLLM([text_turn("done")])
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS)

    result = await loop.run(RunRequest(objective="anything", session_id="incident-42"))

    assert result.session.id == "incident-42"


async def test_resuming_a_session_continues_rather_than_restarting() -> None:
    llm = ScriptedLLM([call_turn(log_call("c1")), text_turn("done")], repeat_last=False)
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS)

    request = RunRequest(objective="anything")
    session = loop.new_session(request)
    session.iteration = 2

    result = await loop.resume(session)

    assert result.iterations == 4, "iterations continue from where the session left off"


async def test_an_unknown_capability_comes_back_as_a_structured_error() -> None:
    llm = ScriptedLLM(
        [
            call_turn(ToolCall(id="c1", name="fixture_not_a_real_tool", arguments={})),
            text_turn("Understood, that tool is not available."),
        ],
        repeat_last=False,
    )
    loop = ReActLoop(llm=llm, tools=(LOG_SEARCH,))

    result = await loop.run(RunRequest(objective="anything"))

    execution = result.turns[0].executions[0]
    assert execution.outcome is InvocationOutcome.FAILURE
    assert execution.denied
    assert "fixture_log_search" in execution.error_message
