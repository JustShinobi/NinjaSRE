"""Specialists: isolation, budget, fan-out, and what comes back.

The single most important assertion in this file is that a sub-agent's prompt
does not contain its parent's transcript. Everything else about the design —
the budget share, the capability subset, the structured finding — is an
optimisation of a thing that only works if that holds.
"""

from __future__ import annotations

import asyncio

import pytest

from config.constants.investigation import (
    MAX_PARALLEL_SUBAGENTS,
    SUBAGENT_TOKEN_BUDGET_RATIO,
)
from core.agent.react_loop import ReActLoop
from core.agent.runtime_port import RunRequest, RunStatus
from core.agent.session import Session
from core.agent.subagents.definition import (
    DEFAULT_SUBAGENTS,
    StaticSubAgents,
    SubAgent,
    SubAgentSource,
    default_subagent_source,
)
from core.agent.subagents.dispatch import (
    DISPATCH_CAPABILITY,
    SubAgentCatalogue,
    SubAgentRun,
    child_budget,
    dispatch_schema,
)
from core.agent.subagents.findings import (
    Finding,
    FindingEvidence,
    failed_finding,
    finding_from_answer,
    finding_from_structured,
)
from core.capability.telemetry import InvocationOutcome
from core.llm.types import ToolCall
from tests.unit.core.agent.conftest import (
    DEFAULT_TOOLS,
    LOG_SEARCH,
    METRIC_READ,
    ScriptedLLM,
    call_turn,
    text_turn,
)

pytestmark = pytest.mark.unit

PARENT_SECRET = "the parent transcript nobody downstream should ever see"

LOG_ANALYST = SubAgent(
    name="log-analyst",
    description="Reads logs at volume.",
    capabilities=("fixture_log_search",),
    max_iterations=2,
)
METRICS_ANALYST = SubAgent(
    name="metrics-analyst",
    description="Reads time series.",
    capabilities=("fixture_metric_read",),
    max_iterations=2,
)


def _dispatch(identifier: str, subagent: str, task: str = "look into it properly") -> ToolCall:
    return ToolCall(
        id=identifier,
        name=DISPATCH_CAPABILITY,
        arguments={"subagent": subagent, "task": task},
    )


# --- definitions (T032) --------------------------------------------------------


def test_a_specialist_must_narrow_the_catalogue_somehow() -> None:
    """A specialist with the parent's whole catalogue is not a specialist."""
    with pytest.raises(ValueError, match="capability subset"):
        SubAgent(name="everything", description="Anything at all.")


def test_a_specialist_name_follows_the_capability_naming_rule() -> None:
    with pytest.raises(ValueError, match="does not match"):
        SubAgent(name="Log Analyst", description="x", capabilities=("y",))


def test_a_specialist_may_not_out_budget_the_parent_loop() -> None:
    with pytest.raises(ValueError, match="max_iterations"):
        SubAgent(name="greedy", description="x", capabilities=("y",), max_iterations=10_000)


def test_a_subset_matches_by_name_or_by_domain() -> None:
    by_name = SubAgent(name="a", description="x", capabilities=("fixture_log_search",))
    by_domain = SubAgent(name="b", description="x", domains=("observability",))

    assert [tool.name for tool in by_name.subset(DEFAULT_TOOLS)] == ["fixture_log_search"]
    assert len(by_domain.subset(DEFAULT_TOOLS)) == len(DEFAULT_TOOLS)


def test_a_subset_follows_the_catalogue_order_rather_than_the_declaration() -> None:
    """Two dispatches of the same specialist send the same schemas in the same
    order, or a trajectory comparison is comparing the ordering."""
    definition = SubAgent(
        name="a", description="x", capabilities=("fixture_metric_read", "fixture_log_search")
    )

    assert [tool.name for tool in definition.subset((LOG_SEARCH, METRIC_READ))] == [
        "fixture_log_search",
        "fixture_metric_read",
    ]


# --- findings (T033) -----------------------------------------------------------


def test_a_finding_must_say_something() -> None:
    with pytest.raises(ValueError, match="headline"):
        Finding(subagent="log-analyst", headline="   ")


def test_a_finding_round_trips_through_a_record() -> None:
    import json

    finding = Finding(
        subagent="log-analyst",
        headline="Errors began at 12:02.",
        established=("the 500s are all from checkout",),
        evidence=(FindingEvidence(summary="412 matches", source="datadog", reference="q:1"),),
        unresolved=("whether the deploy caused it",),
    )

    assert Finding.from_record(json.loads(json.dumps(finding.to_record()))) == finding


def test_a_finding_separates_what_it_could_not_determine() -> None:
    """A parent that cannot tell "the logs show no errors" from "I could not
    read the logs" will conclude the wrong thing from the same finding."""
    finding = Finding(
        subagent="log-analyst",
        headline="No errors found.",
        unresolved=("the 11:00-12:00 window; the log store timed out",),
    )

    rendered = finding.render()
    assert "Not established" in rendered
    assert "timed out" in rendered


def test_a_failed_specialist_does_not_look_like_a_successful_empty_one() -> None:
    finding = failed_finding("log-analyst", "ConnectionError: the log store is down")

    assert finding.failed
    assert "could not complete" in finding.headline
    assert finding.unresolved


def test_a_finding_from_an_answer_keeps_the_headline_first() -> None:
    finding = finding_from_answer(
        "log-analyst", "Errors began at 12:02.\n- all from checkout\n- none before", ()
    )

    assert finding.headline == "Errors began at 12:02."
    assert finding.established == ("all from checkout", "none before")


def test_a_structured_finding_survives_a_payload_missing_everything_optional() -> None:
    finding = finding_from_structured("log-analyst", {"headline": "Errors began at 12:02."})

    assert finding.headline == "Errors began at 12:02."
    assert finding.established == ()


# --- isolation (T034, SC-004) --------------------------------------------------


async def test_a_specialists_prompt_contains_no_part_of_its_parents_transcript() -> None:
    """SC-004. The assertion the whole design rests on."""
    llm = ScriptedLLM(
        [
            call_turn(_dispatch("d1", "log-analyst", "count 500s on checkout since 12:00")),
            text_turn("The specialist confirmed it."),
        ],
        repeat_last=False,
    )
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS, subagents=(LOG_ANALYST,))

    await loop.run(RunRequest(objective=PARENT_SECRET))

    child_requests = [
        request
        for request in llm.requests
        if request.system and "log-analyst specialist" in request.system
    ]
    assert child_requests, "the specialist never ran"
    for request in child_requests:
        assert PARENT_SECRET not in (request.system or "")
        for message in request.messages:
            assert PARENT_SECRET not in message.text


async def test_a_specialist_only_sees_the_capabilities_its_definition_names() -> None:
    llm = ScriptedLLM(
        [call_turn(_dispatch("d1", "log-analyst")), text_turn("done")], repeat_last=False
    )
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS, subagents=(LOG_ANALYST,))

    await loop.run(RunRequest(objective="anything"))

    child = next(
        request
        for request in llm.requests
        if request.system and "log-analyst specialist" in request.system
    )
    assert {schema.name for schema in child.tools} <= {
        "fixture_log_search",
        DISPATCH_CAPABILITY,
    }


def test_a_childs_budget_is_a_share_of_its_parents() -> None:
    parent = Session(id="run-1", context_budget_tokens=10_000)

    assert child_budget(parent, LOG_ANALYST) == int(10_000 * SUBAGENT_TOKEN_BUDGET_RATIO)


def test_a_child_of_an_unbudgeted_parent_is_unbudgeted_too() -> None:
    """Zero means "no budget of our own", and a share of that is still none —
    reading it as a literal zero would evict everything the child gathered."""
    assert child_budget(Session(id="run-1"), LOG_ANALYST) == 0


# --- findings as evidence (T037) -----------------------------------------------


async def test_a_finding_enters_the_parents_evidence_with_its_provenance() -> None:
    async def runner(definition: SubAgent, task: str, parent: Session) -> SubAgentRun:
        return SubAgentRun(
            finding=Finding(subagent=definition.name, headline="Errors began at 12:02.")
        )

    llm = ScriptedLLM(
        [call_turn(_dispatch("d1", "log-analyst")), text_turn("done")], repeat_last=False
    )
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS, subagents=(LOG_ANALYST,), subagent_runner=runner)

    result = await loop.run(RunRequest(objective="anything"))

    entry = result.evidence[0]
    assert entry.origin == "log-analyst"
    assert "log-analyst reported" in entry.summary
    assert result.turns[0].executions[0].evidence_ids == (entry.id,)


async def test_a_childs_guardrail_actions_reach_the_parents_trace() -> None:
    """A thin finding with no explanation is what a trace looks like when the
    specialist's bounds are dropped on the way back."""
    from core.agent.turn import GuardrailAction, GuardrailActionKind

    async def runner(definition: SubAgent, task: str, parent: Session) -> SubAgentRun:
        return SubAgentRun(
            finding=Finding(subagent=definition.name, headline="Ran out of iterations."),
            guardrail_actions=(
                GuardrailAction(
                    kind=GuardrailActionKind.ITERATION_CEILING_REACHED,
                    target="child",
                    reason="2 of 2",
                ),
            ),
        )

    llm = ScriptedLLM(
        [call_turn(_dispatch("d1", "log-analyst")), text_turn("done")], repeat_last=False
    )
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS, subagents=(LOG_ANALYST,), subagent_runner=runner)

    result = await loop.run(RunRequest(objective="anything"))

    ceilings = [
        action
        for turn in result.turns
        for action in turn.guardrail_actions
        if action.kind is GuardrailActionKind.ITERATION_CEILING_REACHED
    ]
    assert ceilings and ceilings[0].target.startswith("log-analyst:")


# --- fan-out and failure (T036) ------------------------------------------------


async def test_specialists_run_concurrently_up_to_the_fan_out_bound() -> None:
    live = 0
    peak = 0

    async def runner(definition: SubAgent, task: str, parent: Session) -> SubAgentRun:
        nonlocal live, peak
        live += 1
        peak = max(peak, live)
        await asyncio.sleep(0.02)
        live -= 1
        return SubAgentRun(finding=Finding(subagent=definition.name, headline="done"))

    many = tuple(
        SubAgent(name=f"analyst-{index}", description="x", capabilities=("fixture_log_search",))
        for index in range(MAX_PARALLEL_SUBAGENTS * 2)
    )
    llm = ScriptedLLM(
        [
            call_turn(
                *(
                    _dispatch(f"d{index}", f"analyst-{index}", f"task {index}")
                    for index in range(MAX_PARALLEL_SUBAGENTS * 2)
                )
            ),
            text_turn("done"),
        ],
        repeat_last=False,
    )
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS, subagents=many, subagent_runner=runner)

    result = await loop.run(RunRequest(objective="anything"))

    assert peak <= MAX_PARALLEL_SUBAGENTS
    assert len(result.turns[0].executions) == MAX_PARALLEL_SUBAGENTS * 2


async def test_a_specialist_that_raises_does_not_fail_the_parent() -> None:
    async def runner(definition: SubAgent, task: str, parent: Session) -> SubAgentRun:
        if definition.name == "log-analyst":
            raise ConnectionError("the log store is unreachable")
        return SubAgentRun(finding=Finding(subagent=definition.name, headline="latency rose"))

    llm = ScriptedLLM(
        [
            call_turn(
                _dispatch("d1", "log-analyst", "read the logs"),
                _dispatch("d2", "metrics-analyst", "read the metrics"),
            ),
            text_turn("One of two specialists reported."),
        ],
        repeat_last=False,
    )
    loop = ReActLoop(
        llm=llm,
        tools=DEFAULT_TOOLS,
        subagents=(LOG_ANALYST, METRICS_ANALYST),
        subagent_runner=runner,
    )

    result = await loop.run(RunRequest(objective="anything"))

    assert result.status is RunStatus.COMPLETED
    executions = {item.call_id: item for item in result.turns[0].executions}
    assert executions["d1"].outcome is InvocationOutcome.FAILURE
    assert executions["d2"].outcome is InvocationOutcome.SUCCESS
    assert any("could not complete" in entry.summary for entry in result.evidence)


# --- refusals ------------------------------------------------------------------


async def test_an_unknown_specialist_is_refused_with_the_list_of_real_ones() -> None:
    llm = ScriptedLLM(
        [call_turn(_dispatch("d1", "no-such-analyst")), text_turn("Understood.")],
        repeat_last=False,
    )
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS, subagents=(LOG_ANALYST,))

    result = await loop.run(RunRequest(objective="anything"))

    execution = result.turns[0].executions[0]
    assert execution.denied
    assert "log-analyst" in execution.error_message


async def test_a_dispatch_missing_its_task_is_refused_rather_than_guessed_at() -> None:
    llm = ScriptedLLM(
        [
            call_turn(
                ToolCall(id="d1", name=DISPATCH_CAPABILITY, arguments={"subagent": "log-analyst"})
            ),
            text_turn("Understood."),
        ],
        repeat_last=False,
    )
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS, subagents=(LOG_ANALYST,))

    result = await loop.run(RunRequest(objective="anything"))

    assert result.turns[0].executions[0].denied


async def test_a_specialist_with_nothing_to_call_is_refused() -> None:
    unavailable = SubAgent(
        name="cloud-inspector", description="x", capabilities=("nothing_configured_here",)
    )
    llm = ScriptedLLM(
        [call_turn(_dispatch("d1", "cloud-inspector")), text_turn("Understood.")],
        repeat_last=False,
    )
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS, subagents=(unavailable,))

    result = await loop.run(RunRequest(objective="anything"))

    assert "no capabilities available" in result.turns[0].executions[0].error_message


async def test_dispatch_is_not_offered_when_no_specialist_is_configured() -> None:
    llm = ScriptedLLM([text_turn("done")])
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS)

    await loop.run(RunRequest(objective="anything"))

    assert DISPATCH_CAPABILITY not in {schema.name for schema in llm.requests[0].tools}


async def test_dispatch_is_offered_when_specialists_are_configured() -> None:
    llm = ScriptedLLM([text_turn("done")])
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS, subagents=(LOG_ANALYST,))

    await loop.run(RunRequest(objective="anything"))

    schema = next(item for item in llm.requests[0].tools if item.name == DISPATCH_CAPABILITY)
    assert schema.parameters["properties"]["subagent"]["enum"] == ["log-analyst"]


# --- the shipped set (T038) and the source port (T039) -------------------------


def test_six_specialists_ship_by_default() -> None:
    assert [item.name for item in DEFAULT_SUBAGENTS] == [
        "log-analyst",
        "metrics-analyst",
        "k8s-debugger",
        "cloud-inspector",
        "code-historian",
        "memory-recaller",
    ]


def test_every_shipped_specialist_declares_what_it_returns() -> None:
    for definition in DEFAULT_SUBAGENTS:
        assert definition.returns, f"{definition.name} does not say what it hands back"
        assert definition.domains, f"{definition.name} would match nothing in a fresh deployment"


def test_the_source_is_a_port_a_team_configuration_can_fill() -> None:
    assert isinstance(default_subagent_source(), SubAgentSource)
    assert isinstance(StaticSubAgents(), SubAgentSource)
    assert default_subagent_source().definitions() == DEFAULT_SUBAGENTS


def test_a_catalogue_answers_by_name_case_insensitively() -> None:
    catalogue = SubAgentCatalogue(definitions=DEFAULT_SUBAGENTS)

    assert catalogue.get("LOG-ANALYST") is not None
    assert catalogue.get(" metrics-analyst ") is not None
    assert catalogue.get("nothing") is None


def test_the_dispatch_schema_names_every_configured_specialist() -> None:
    schema = dispatch_schema(SubAgentCatalogue(definitions=DEFAULT_SUBAGENTS))

    assert schema.parameters["properties"]["subagent"]["enum"] == [
        item.name for item in DEFAULT_SUBAGENTS
    ]
    assert "cannot see any of it" in schema.parameters["properties"]["task"]["description"]
