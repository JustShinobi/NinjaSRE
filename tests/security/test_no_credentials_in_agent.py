"""SC-001. The defining test: run an investigation, then hunt for the credential.

Article IV is a claim about where a secret is *not*. Every other test in this
feature checks that a mechanism works; this one checks that the mechanism was
the only path, by seeding a credential that exists nowhere else and then
searching the six places the constitution names — process environment,
filesystem, prompt, tool arguments, transcript, persisted trace — plus the
streamed events a console would render.

The investigation is the real one: six stages, the canonical loop, a real
integration client on the real proxy. Only the model and the network are
doubles, and the network double is what proves the credential *did* reach
Datadog. A run that failed to authenticate would satisfy every negative
assertion here and mean nothing.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from capabilities.registry.planning import CatalogueRanker
from config.constants.paths import REPO_ROOT
from core.agent.react_loop import ReActLoop
from core.llm.types import (
    InvokeRequest,
    InvokeResult,
    StreamEvent,
    TokenEstimate,
    ToolCall,
)
from core.pipeline.build import build_pipeline, investigation_hooks
from core.pipeline.lifecycle import PipelineRun
from core.pipeline.ports import FixedCatalogueResolver, InMemoryIncidentIndex, StaticCatalogue
from core.pipeline.state_factory import initial_state
from core.pipeline.streaming import EventStream, RecordingSink
from tests.security.conftest import (
    CAPABILITY,
    SENTINEL_API_KEY,
    SENTINEL_APP_KEY,
    SENTINELS,
    ProxyStack,
    alert,
    find_sentinels,
    team,
)
from tests.synthetic.conftest import LoopTurn, ScenarioLLM

pytestmark = pytest.mark.security

#: The seven packages that ship. ``tests/`` holds the sentinel by definition —
#: it is declared in this suite — so scanning it would report the test itself.
SHIPPED_PACKAGES = (
    "capabilities",
    "config",
    "core",
    "gateway",
    "integrations",
    "platform",
    "surfaces",
)

_INTAKE = {
    "is_incident": True,
    "confidence": 0.95,
    "reason": "an alert is firing on a production service",
    "alert_name": "HighErrorRate",
    "severity": "critical",
    "summary": "checkout error rate above 5%",
    "components": ["checkout"],
    "error_text": "",
}

_DIAGNOSIS = {
    "root_cause": "the checkout container exceeded its memory limit",
    "root_cause_category": "resource_exhaustion",
    "summary": "The container was OOM-killed and requests failed while it restarted.",
    "causal_chain": ["memory use grew past the limit", "the kernel killed the container"],
    "claims": [{"statement": "checkout was OOM-killed during the window", "evidence_ids": ["e1"]}],
    "remediation_steps": ["raise the checkout memory limit"],
    "confidence": 0.85,
}


@dataclass(slots=True)
class RecordingLLM:
    """A provider double that keeps every request, because prompts are a hiding place.

    Wraps ``ScenarioLLM`` rather than subclassing it — the inner double is a
    slotted dataclass, and the recording list is state it does not declare.
    """

    inner: ScenarioLLM
    requests: list[InvokeRequest] = field(default_factory=list)

    @property
    def provider_id(self) -> str:
        return self.inner.provider_id

    @property
    def model_id(self) -> str:
        return self.inner.model_id

    async def invoke(self, request: InvokeRequest) -> InvokeResult:
        self.requests.append(request)
        return await self.inner.invoke(request)

    async def stream(self, request: InvokeRequest) -> AsyncIterator[StreamEvent]:
        self.requests.append(request)
        async for event in self.inner.stream(request):
            yield event

    async def invoke_structured(
        self, request: InvokeRequest, schema: Mapping[str, Any]
    ) -> InvokeResult:
        self.requests.append(request)
        return await self.inner.invoke_structured(request, schema)

    def count_tokens(self, request: InvokeRequest) -> TokenEstimate:
        return self.inner.count_tokens(request)


@dataclass(frozen=True, slots=True)
class Investigation:
    """One finished run, plus everything an inspector can reach afterwards."""

    run: PipelineRun
    llm: RecordingLLM
    sink: RecordingSink


async def investigate(stack: ProxyStack) -> Investigation:
    """Run the whole pipeline over the capability that reaches Datadog."""
    llm = RecordingLLM(
        inner=ScenarioLLM(
            structured=[_INTAKE, _DIAGNOSIS],
            turns=[
                LoopTurn(
                    tool_calls=(
                        ToolCall(
                            id="c1",
                            name=CAPABILITY,
                            arguments={"query": "service:checkout status:error"},
                        ),
                    )
                ),
                LoopTurn(text="Checkout was OOM-killed inside the incident window [e1]."),
            ],
        )
    )
    sink = RecordingSink()
    tools = (stack.tool(),)
    pipeline = build_pipeline(
        llm=llm,
        runtime=ReActLoop(llm=llm, tools=tools, hooks=investigation_hooks()),
        resolver=FixedCatalogueResolver(
            StaticCatalogue(tools=tools, declarations=tuple(t.metadata for t in tools))
        ),
        ranker=CatalogueRanker(),
        incidents=InMemoryIncidentIndex(),
        stream=EventStream("run-redteam", (sink,)),
        strict=True,
    )
    run = await pipeline.run(initial_state(alert(), team(), run_id="run-redteam"))
    return Investigation(run, llm, sink)


# -- the positive control -----------------------------------------------------


async def test_the_credential_reached_the_vendor(stack: ProxyStack) -> None:
    """Without this, every assertion below would pass on a run that did nothing."""
    await investigate(stack)

    assert stack.sender.sent, "the capability never issued a request through the proxy"
    outbound = stack.sender.sent[0]
    assert outbound.headers["DD-API-KEY"] == SENTINEL_API_KEY
    assert outbound.headers["DD-APPLICATION-KEY"] == SENTINEL_APP_KEY


async def test_the_investigation_actually_concluded(stack: ProxyStack) -> None:
    """A run that halted before the tool call would prove nothing either."""
    investigation = await investigate(stack)

    assert investigation.run.succeeded
    assert len(investigation.run.state.evidence) == 1


# -- the six places Article IV names ------------------------------------------


async def test_no_credential_is_in_the_process_environment(stack: ProxyStack) -> None:
    await investigate(stack)

    leaked = [name for name, value in os.environ.items() if any(s in value for s in SENTINELS)]
    assert leaked == [], f"the credential reached these environment variables: {leaked}"


async def test_no_credential_is_on_the_filesystem(stack: ProxyStack, tmp_path: Path) -> None:
    """Nothing the run wrote, and nothing that ships, contains the value."""
    await investigate(stack)

    written = [path for path in tmp_path.rglob("*") if path.is_file() and _contains_sentinel(path)]
    assert written == [], f"the credential was written to {written}"

    shipped = [
        path
        for package in SHIPPED_PACKAGES
        for path in (REPO_ROOT / package).rglob("*.py")
        if _contains_sentinel(path)
    ]
    assert shipped == [], f"the credential is baked into {shipped}"


async def test_no_credential_is_in_a_prompt(stack: ProxyStack) -> None:
    """Every request the model saw, structured and free-form alike."""
    investigation = await investigate(stack)

    assert investigation.llm.requests, "the run never called the model"
    assert find_sentinels(investigation.llm.requests) == ()


async def test_no_credential_is_in_a_tool_argument(stack: ProxyStack) -> None:
    investigation = await investigate(stack)

    arguments = [entry.arguments for entry in investigation.run.state.evidence.entries]
    assert arguments, "the run recorded no tool call"
    assert find_sentinels(arguments) == ()


async def test_no_credential_is_in_the_transcript(stack: ProxyStack) -> None:
    investigation = await investigate(stack)

    assert find_sentinels(investigation.run.state.chat.to_record()) == ()


async def test_no_credential_is_in_the_persisted_trace(stack: ProxyStack) -> None:
    """The whole run record, and every audit line the proxy wrote beside it."""
    investigation = await investigate(stack)

    assert find_sentinels(investigation.run.state.to_record()) == ()
    assert find_sentinels(investigation.sink.records()) == ()

    async with stack.gateway.begin(stack.scope) as uow:
        events = await uow.audit.query(limit=100)
    assert events, "the proxy recorded no resolution"
    assert find_sentinels([event.detail for event in events]) == ()


async def test_the_capability_result_carries_no_credential(stack: ProxyStack) -> None:
    """The value the model reads back is the last hop into the agent's reach."""
    investigation = await investigate(stack)

    assert find_sentinels(investigation.run.state.evidence.to_record()) == ()


def _contains_sentinel(path: Path) -> bool:
    """Return whether ``path`` holds either sentinel."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return SENTINEL_API_KEY in text or SENTINEL_APP_KEY in text
