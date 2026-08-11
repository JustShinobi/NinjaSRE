"""What the operating context is worth, measured by switching it off and asking again.

The scenario is this cluster's own history, told from the other end. 054 proved
that *the signal map* reaches the host-side series for an LXC guest; this proves
that an agent which was simply **told the fact** reaches it too — which matters
because the map answers a question somebody already knew to ask, and the context
is what makes an investigation know to ask it.

Two arms over one deployment and one recorded estate. The only difference
between them is ``agents.operating_context.enabled``, which is the ablation
switch the field ships with: the same text, sent or not sent.

**With the context**, the run is told that a container's counters are the host's,
cites the host-side series for guest 100, and reads 0.94 — above any threshold an
operator would set.

**Without it**, the same run against the same estate asks the standard node
expression, cites the in-guest series, and reads 0.31 — which is the host's
utilisation, and is below every threshold. That is not a strawman: it is the
reading that let a container be OOM-killed four times while every dashboard said
there was memory to spare.

**The agent double is a policy, not a script**, exactly as
``test_ablation_value_scenario`` states it: it reads the system prompt the hook
actually built and decides from what is there. Nothing about the arms is written
into it — it behaves differently because it is *told* different things. That is
what makes the delta attributable to the mechanism rather than to the fixture.
What this measures is the mechanism, not how reliably a particular model
exploits one.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from typing import Any

import pytest

from config.prompts.operating_context import LXC_METRICS_FACT
from core.agent.react_loop import ReActLoop
from core.agent.runtime_port import RunRequest, RunResult
from core.capability.metadata import EvidenceType, SideEffectLevel, ToolMetadata
from core.capability.registered import RegisteredTool, build_registration
from core.capability.result import CapabilityResult, Evidence
from core.llm.types import (
    FinishReason,
    InvokeRequest,
    InvokeResult,
    StreamEvent,
    TokenEstimate,
    ToolCall,
)
from core.llm.usage import TokenCounts, UsageRecord
from core.pipeline.build import investigation_hooks
from platform.config_service.guidance import OperatingContextGuidance
from platform.config_service.schema import RootConfig

pytestmark = pytest.mark.synthetic

#: The guest from the cluster's own postmortem.
VMID = 100

#: What the guest is actually at, against the ceiling it is killed at.
GUEST_MEMORY_RATIO = 0.94

#: What an in-guest collector reports, which is the *host's* utilisation.
HOST_MEMORY_RATIO = 0.31

#: Above this a memory-pressure conclusion is drawn. One number, both arms.
ALARMING_RATIO = 0.90

#: The two ways to ask, and the two sources a claim can end up citing.
HOST_SIDE = "prometheus_guest_pressure_by_vmid"
IN_GUEST = "prometheus_node_pressure"

HOST_SIDE_SERIES = f'proxmox_lxc_memory_used{{id="lxc/{VMID}"}}'
IN_GUEST_SERIES = "node_memory_MemAvailable_bytes"


# --- the estate, as two capabilities that answer honestly ---------------------


def reading(name: str, *, ratio: float, series: str, summary: str) -> RegisteredTool:
    """Return one capability answering with the series it actually reads.

    Both are real registrations returning real evidence. Neither knows which
    arm it is in, and neither is switched off in either — the arms differ in
    which one the agent decides to call.
    """

    async def call() -> CapabilityResult:
        return CapabilityResult.ok(
            name,
            value={"series": series, "ratio": ratio},
            evidence=(
                Evidence(
                    source="prometheus",
                    evidence_type=EvidenceType.METRIC,
                    summary=f"{summary} — {ratio:.2f}",
                    reference=series,
                ),
            ),
        )

    return build_registration(
        metadata=ToolMetadata(
            name=name,
            display_name=name.replace("_", " ").title(),
            description=f"Read {summary}.",
            domain="observability",
            evidence_source="prometheus",
            evidence_type=EvidenceType.METRIC,
            side_effect_level=SideEffectLevel.READ,
            parallel_safe=True,
        ),
        call=call,
        source_module=__name__,
        source_qualname=f"reading.{name}",
        signature_source=call,
    )


def capabilities() -> tuple[RegisteredTool, ...]:
    """Return both readings, offered to both arms."""
    return (
        reading(
            HOST_SIDE,
            ratio=GUEST_MEMORY_RATIO,
            series=HOST_SIDE_SERIES,
            summary=f"memory used by guest {VMID} against its own ceiling, from the host",
        ),
        reading(
            IN_GUEST,
            ratio=HOST_MEMORY_RATIO,
            series=IN_GUEST_SERIES,
            summary="memory available as reported from inside the guest",
        ),
    )


# --- the agent ----------------------------------------------------------------


@dataclass(slots=True)
class PressurePolicyAgent:
    """Decide where to read memory pressure from, given only what the prompt says.

    The rule is a general one about prompts rather than a flag a fixture set: if
    the system prompt states that a container's counters are the host's and are
    keyed by the guest's number, ask the host-side series; otherwise ask the
    expression every node-exporter tutorial gives, which is what an
    investigation writes when nothing has told it anything.
    """

    calls: list[str] = field(default_factory=list)

    @property
    def provider_id(self) -> str:
        """Return the provider this double claims to be."""
        return "policy"

    @property
    def model_id(self) -> str:
        """Return the model this double claims to be."""
        return "policy-1"

    def _usage(self) -> UsageRecord:
        return UsageRecord(
            provider_id=self.provider_id,
            model_id=self.model_id,
            tokens=TokenCounts(input_tokens=300, output_tokens=90),
        )

    async def invoke(self, request: InvokeRequest) -> InvokeResult:
        """Return the next move: one reading, then a conclusion quoting it."""
        results = [result for message in request.messages for result in message.tool_results]
        if results:
            return InvokeResult(
                provider_id=self.provider_id,
                model_id=self.model_id,
                text=(f"The container was killed by its memory cgroup. {results[-1].content}"),
                finish_reason=FinishReason.STOP,
                usage=self._usage(),
            )

        wanted = HOST_SIDE if self._told_where_to_look(request.system or "") else IN_GUEST
        self.calls.append(wanted)
        return InvokeResult(
            provider_id=self.provider_id,
            model_id=self.model_id,
            tool_calls=(ToolCall(id="c1", name=wanted, arguments={}),),
            finish_reason=FinishReason.TOOL_CALLS,
            usage=self._usage(),
        )

    @staticmethod
    def _told_where_to_look(prompt: str) -> bool:
        """Return whether the prompt states the rule about where a guest's counters live."""
        lowered = prompt.lower()
        return "vmid" in lowered and "host" in lowered

    def stream(self, request: InvokeRequest) -> AsyncIterator[StreamEvent]:
        """Not streamed; the loop does not."""
        raise NotImplementedError("the loop does not stream")

    async def invoke_structured(
        self, request: InvokeRequest, schema: Mapping[str, Any]
    ) -> InvokeResult:
        """Return the same move; this scenario asks for no structured output."""
        return await self.invoke(request)

    def count_tokens(self, request: InvokeRequest) -> TokenEstimate:
        """Return a character estimate, which is all any bound here needs."""
        return TokenEstimate(tokens=len(str(request)) // 4, estimated=True)


# --- the two arms -------------------------------------------------------------


#: The document both arms resolve. The operator kept the fact the template
#: shipped, which is the whole path this feature builds.
SETTINGS: Mapping[str, Any] = {
    "sections": {"Where the signals really are": LXC_METRICS_FACT},
}


async def arm(*, context_on: bool) -> tuple[RunResult, PressurePolicyAgent]:
    """Run one investigation with the operating context switched on or off."""
    config = RootConfig.of({"agents": {"operating_context": {**SETTINGS, "enabled": context_on}}})
    guidance = OperatingContextGuidance.of(config.agents)
    agent = PressurePolicyAgent()
    loop = ReActLoop(
        llm=agent,
        tools=capabilities(),
        hooks=guidance.register(investigation_hooks()),
    )

    result = await loop.run(
        RunRequest(
            objective=f"Container {VMID} was killed. Establish whether it was under memory pressure.",
            system_prompt=config.agents.system_prompt_for("investigator"),
        )
    )
    return result, agent


def cited_series(result: RunResult) -> tuple[str, ...]:
    """Return the series every claim in this run rests on."""
    return tuple(entry.reference for entry in result.evidence)


def read_ratio(result: RunResult) -> float:
    """Return the memory ratio the run actually observed."""
    summaries = [entry.summary for entry in result.evidence]
    assert summaries, "the run gathered nothing, so there is nothing to compare"
    return float(summaries[0].rsplit("—", 1)[1])


# --- with the context ---------------------------------------------------------


async def test_with_the_context_the_run_reads_the_host_side_series() -> None:
    result, agent = await arm(context_on=True)

    assert agent.calls == [HOST_SIDE]
    assert cited_series(result) == (HOST_SIDE_SERIES,)
    assert read_ratio(result) == pytest.approx(GUEST_MEMORY_RATIO)


async def test_with_the_context_the_reading_crosses_the_threshold_a_conclusion_needs() -> None:
    result, _ = await arm(context_on=True)

    assert read_ratio(result) > ALARMING_RATIO


# --- with the context switched off --------------------------------------------


async def test_without_the_context_the_same_estate_answers_about_the_host() -> None:
    """The ablation arm. One switch, and the deployment is otherwise identical."""
    result, agent = await arm(context_on=False)

    assert agent.calls == [IN_GUEST]
    assert cited_series(result) == (IN_GUEST_SERIES,)
    assert read_ratio(result) == pytest.approx(HOST_MEMORY_RATIO)


async def test_without_the_context_the_reading_is_reassuring_and_wrong() -> None:
    result, _ = await arm(context_on=False)

    assert read_ratio(result) < ALARMING_RATIO


# --- the delta ----------------------------------------------------------------


async def test_the_fact_changes_which_source_the_pressure_claim_cites() -> None:
    """The number this scenario publishes.

    One scenario, two arms, one switch. With the operating context the claim
    rests on the guest's own ceiling and the run concludes memory pressure;
    without it, the same claim rests on the host's spare memory and the run
    concludes there was none. The mechanism's contribution here is one scenario
    from wrong to right, and it is not zero.
    """
    with_context, _ = await arm(context_on=True)
    without_context, _ = await arm(context_on=False)

    assert cited_series(with_context) != cited_series(without_context)

    correct_with = read_ratio(with_context) > ALARMING_RATIO
    correct_without = read_ratio(without_context) > ALARMING_RATIO

    assert (correct_with, correct_without) == (True, False), (
        "the operating context's contribution to this scenario is supposed to be "
        "the difference between diagnosing a memory-cgroup kill and concluding "
        "the container had memory to spare"
    )
