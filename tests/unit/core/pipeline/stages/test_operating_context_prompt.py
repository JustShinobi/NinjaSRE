"""What the model is actually sent when a team has written operating context.

Acceptance 1, and it is asserted through a scripted ``core.llm`` client rather
than by reading configuration back: "the two reach the model" is a claim about a
provider request, and a test that inspected ``AgentsConfig`` would pass on a
deployment where nothing was ever wired up.

So this drives the real composition — configuration, the guidance hook, the real
``ReActLoop``, the real gather stage — and reads the ``system`` field off the
request the client was handed.
"""

from __future__ import annotations

import pytest

from config.prompts.investigation import DEFAULT_RUNTIME_SYSTEM_PROMPT, INTAKE_SYSTEM_PROMPT
from core.agent.hooks.types import HookPoint
from core.agent.react_loop import ReActLoop
from core.agent.runtime_port import RunRequest
from core.agent.subagents.definition import SubAgent
from core.agent.subagents.dispatch import DISPATCH_CAPABILITY
from core.llm.types import ToolCall
from core.pipeline.build import investigation_hooks
from core.pipeline.stages.gather_evidence import GatherEvidenceStage
from core.state.agent_state import AgentState, apply_state_updates
from platform.config_service.bindings import RuntimeBindings
from platform.config_service.guidance import OPERATING_CONTEXT_HOOK, OperatingContextGuidance
from platform.config_service.schema import RootConfig
from tests.unit.core.agent.conftest import DEFAULT_TOOLS, call_turn, text_turn
from tests.unit.core.agent.conftest import ScriptedLLM as AgentScriptedLLM
from tests.unit.core.pipeline.conftest import (
    ScriptedLLM,
    alertmanager_state,
    incident_classification,
)
from tests.unit.core.pipeline.stages.test_intake import _stage as intake_stage

pytestmark = pytest.mark.unit


OVERRIDE = "You are the payments team's investigator. Be terse."
LXC = "Container metrics come from the host's own series, keyed by vmid."

LOG_ANALYST = SubAgent(
    name="log-analyst",
    description="Reads logs at volume.",
    capabilities=("fixture_log_search",),
    max_iterations=2,
)


def bindings_for(**agents: object) -> RuntimeBindings:
    """Return the runtime bindings a node declaring ``agents`` resolves to."""
    config = RootConfig.of({"agents": agents})
    return RuntimeBindings(
        node_id="team-payments",
        config=config,
        operating_context=OperatingContextGuidance.of(config.agents),
    )


async def prepared() -> AgentState:
    """Return a state that has been through intake, ready for the loop."""
    state = alertmanager_state()
    return apply_state_updates(
        state, await intake_stage(ScriptedLLM(structured=[incident_classification()]))(state)
    )


async def system_prompt_sent(bindings: RuntimeBindings) -> str:
    """Return the ``system`` field of the first provider request one run makes."""
    llm = ScriptedLLM(text="The container was OOM-killed.")
    loop = ReActLoop(
        llm=llm,
        tools=(),
        hooks=bindings.operating_context.register(investigation_hooks()),
    )
    stage = GatherEvidenceStage(
        runtime=loop, system_prompt=bindings.system_prompt_for("investigator")
    )

    await stage(await prepared())

    return llm.requests[0].system or ""


# --- Acceptance 1 ------------------------------------------------------------


async def test_the_override_and_the_operating_context_both_reach_the_model() -> None:
    sent = await system_prompt_sent(
        bindings_for(
            prompts={"investigator": OVERRIDE},
            operating_context={"sections": {"signals": LXC}},
        )
    )

    assert OVERRIDE in sent
    assert LXC in sent


async def test_the_prompt_comes_first_and_the_facts_after_it() -> None:
    """Order is the framing: an estate description in front would reframe the run."""
    sent = await system_prompt_sent(
        bindings_for(
            prompts={"investigator": OVERRIDE},
            operating_context={"sections": {"signals": LXC}},
        )
    )

    assert sent.index(OVERRIDE) < sent.index(LXC)


async def test_the_shipped_prompt_survives_when_nobody_overrode_it() -> None:
    """The point of the whole field: adding facts does not cost the shipped prompt."""
    sent = await system_prompt_sent(bindings_for(operating_context={"sections": {"signals": LXC}}))

    assert DEFAULT_RUNTIME_SYSTEM_PROMPT in sent
    assert LXC in sent


async def test_what_the_model_gets_is_byte_identical_to_what_a_preview_would_show() -> None:
    """Acceptance 6 rests on this: the screen renders the deployment's own assembly."""
    bindings = bindings_for(
        prompts={"investigator": OVERRIDE},
        operating_context={"sections": {"signals": LXC}},
    )

    assert await system_prompt_sent(bindings) == bindings.system_prompt_for("investigator")


async def test_a_deployment_that_configured_none_of_this_sends_exactly_what_it_sent_before() -> (
    None
):
    """The no-configuration deployment pays nothing — not a heading, not a newline."""
    assert await system_prompt_sent(bindings_for()) == DEFAULT_RUNTIME_SYSTEM_PROMPT


async def test_a_context_switched_off_sends_exactly_the_same_thing() -> None:
    """The ablation lever, from the operator's end: same deployment, one switch."""
    off = bindings_for(operating_context={"sections": {"signals": LXC}, "enabled": False})

    assert await system_prompt_sent(off) == DEFAULT_RUNTIME_SYSTEM_PROMPT


async def test_the_hook_registers_under_a_name_an_ablation_can_remove() -> None:
    """Article VII: the contribution has to be isolable without a second build."""
    bindings = bindings_for(operating_context={"sections": {"signals": LXC}})
    hooks = bindings.operating_context.register(investigation_hooks())

    named = {hook.name for hook in hooks.hooks_at(HookPoint.ON_RUN_START)}
    assert OPERATING_CONTEXT_HOOK in named


# --- The specialists investigate too -----------------------------------------


async def test_a_specialist_reasons_about_the_same_estate_as_its_parent() -> None:
    """A sub-agent runs in its own session, built from its own prompt.

    Appending at composition time would have reached the investigator and left
    every specialist reading the same evidence with none of the facts that say
    how to read it. The hook fires per session, so it reaches both.
    """
    llm = AgentScriptedLLM(
        [
            call_turn(
                ToolCall(
                    id="d1",
                    name=DISPATCH_CAPABILITY,
                    arguments={"subagent": "log-analyst", "task": "count the 500s"},
                )
            ),
            text_turn("The specialist confirmed it."),
        ],
        repeat_last=True,
    )
    bindings = bindings_for(operating_context={"sections": {"signals": LXC}})
    loop = ReActLoop(
        llm=llm,
        tools=DEFAULT_TOOLS,
        subagents=(LOG_ANALYST,),
        hooks=bindings.operating_context.register(investigation_hooks()),
    )

    await loop.run(RunRequest(objective="why is checkout failing"))

    child_prompts = [
        request.system or ""
        for request in llm.requests
        if "log-analyst specialist" in (request.system or "")
    ]
    assert child_prompts, "the specialist never ran"
    assert all(LXC in prompt for prompt in child_prompts)


# --- T-005: the roles that do not investigate --------------------------------


async def test_intake_does_not_receive_the_operating_context() -> None:
    """Classification does not reason about the estate and runs on every alert."""
    bindings = bindings_for(operating_context={"sections": {"signals": LXC}})
    llm = ScriptedLLM(structured=[incident_classification()])

    await intake_stage(llm)(alertmanager_state())

    assert llm.requests[0].system == INTAKE_SYSTEM_PROMPT
    assert LXC not in (llm.requests[0].system or "")
    assert bindings.system_prompt_for("intake") == bindings.prompt_for("intake")
