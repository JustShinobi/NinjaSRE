"""The probe measures what a model does, rather than repeating what it claims.

Three models are driven through the whole suite here: one that tool calls, one
that answers instead, and one whose usable context stops well below the figure
its descriptor advertises. Every one of them is a scripted client — the point of
the probe is that a deployment can find this out cheaply, and a test that needed
a live model would not be able to prove it does.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from typing import Any

import pytest

from config.constants.investigation import MAX_AGENT_TOOL_SCHEMAS
from config.constants.llm import CHARACTERS_PER_TOKEN_ESTIMATE, PROVIDER_OLLAMA
from core.llm.failures import FailureClass
from core.llm.probe import (
    Behaviour,
    BehaviourStatus,
    ModelIdentity,
    ModelProbe,
    ProbeCache,
    probe_model,
)
from core.llm.types import (
    FinishReason,
    InvokeRequest,
    InvokeResult,
    StreamEvent,
    StreamEventKind,
    TokenEstimate,
    ToolCall,
)

MODEL = "qwen2.5:7b"
ADVERTISED = 32_768


@dataclass
class ScriptedModel:
    """A local model with the behaviours a probe is trying to find out about.

    ``usable_context_tokens`` is the real limit; ``ADVERTISED`` is what the
    registry row claims. A quantised build routinely has the first well below
    the second, which is the case this whole class exists to reproduce.
    """

    calls_tools: bool = True
    honours_schema: bool = True
    streams: bool = True
    usable_context_tokens: int = ADVERTISED
    schema_limit: int = MAX_AGENT_TOOL_SCHEMAS
    requests: list[InvokeRequest] = field(default_factory=list)

    @property
    def provider_id(self) -> str:
        return PROVIDER_OLLAMA

    @property
    def model_id(self) -> str:
        return MODEL

    def count_tokens(self, request: InvokeRequest) -> TokenEstimate:
        characters = len(request.system or "") + sum(
            len(message.text) for message in request.messages
        )
        for tool in request.tools:
            characters += len(tool.name) + len(tool.description) + len(str(dict(tool.parameters)))
        return TokenEstimate(tokens=characters // CHARACTERS_PER_TOKEN_ESTIMATE, estimated=True)

    async def invoke(self, request: InvokeRequest) -> InvokeResult:
        self.requests.append(request)
        if self.count_tokens(request).tokens > self.usable_context_tokens:
            return InvokeResult(
                provider_id=self.provider_id,
                model_id=self.model_id,
                finish_reason=FinishReason.ERROR,
                partial=True,
                failure=FailureClass.CONTEXT_EXCEEDED,
                failure_message="prompt is too long for this build",
            )
        if request.tools and self.calls_tools and len(request.tools) <= self.schema_limit:
            wanted = list(request.tools)
            asked = min(len(wanted), 2 if "both" in request.messages[-1].text else 1)
            return InvokeResult(
                provider_id=self.provider_id,
                model_id=self.model_id,
                tool_calls=tuple(
                    ToolCall(id=f"c{index}", name=tool.name, arguments={"token": "probe"})
                    for index, tool in enumerate(wanted[:asked])
                ),
                finish_reason=FinishReason.TOOL_CALLS,
            )
        return InvokeResult(
            provider_id=self.provider_id,
            model_id=self.model_id,
            text="I would look at the pods.",
        )

    async def invoke_structured(
        self, request: InvokeRequest, schema: Mapping[str, Any]
    ) -> InvokeResult:
        if not self.honours_schema:
            return InvokeResult(provider_id=self.provider_id, model_id=self.model_id, text="ok")
        return InvokeResult(
            provider_id=self.provider_id,
            model_id=self.model_id,
            structured={"status": "ok", "checked": True},
        )

    async def stream(self, request: InvokeRequest) -> AsyncIterator[StreamEvent]:
        if not self.streams:
            yield StreamEvent(kind=StreamEventKind.FINISH, finish_reason=FinishReason.STOP)
            return
        yield StreamEvent(kind=StreamEventKind.TEXT_DELTA, text="one two ")
        yield StreamEvent(kind=StreamEventKind.FINISH, finish_reason=FinishReason.STOP)


async def _probe(model: ScriptedModel) -> ModelProbe:
    return await probe_model(model, advertised_context_tokens=ADVERTISED)


class TestTheProbeClassifiesAModel:
    async def test_a_tool_calling_model_is_usable_for_an_investigation(self) -> None:
        probe = await _probe(ScriptedModel())

        assert probe.status_of(Behaviour.TOOL_CALLING) is BehaviourStatus.PASSED
        assert probe.usable_for_investigation
        assert probe.unusable_because == ()

    async def test_a_model_that_answers_instead_of_calling_is_refused_by_behaviour(self) -> None:
        probe = await _probe(ScriptedModel(calls_tools=False))

        assert probe.status_of(Behaviour.TOOL_CALLING) is BehaviourStatus.FAILED
        assert not probe.usable_for_investigation
        assert Behaviour.TOOL_CALLING.value in " ".join(probe.unusable_because)

    async def test_a_model_whose_usable_context_is_below_its_advertised_figure(self) -> None:
        model = ScriptedModel(usable_context_tokens=6_000)

        probe = await _probe(model)

        assert probe.advertised_context_tokens == ADVERTISED
        assert probe.usable_context_tokens < ADVERTISED
        # Measured, not guessed: the figure has to be near the real limit rather
        # than merely "less than what the vendor said".
        assert 4_000 <= probe.usable_context_tokens <= 6_000

    async def test_the_measured_context_is_reported_even_when_it_matches(self) -> None:
        probe = await _probe(ScriptedModel())

        assert probe.usable_context_tokens > 0
        assert probe.status_of(Behaviour.USABLE_CONTEXT) is BehaviourStatus.PASSED


class TestTheProbeReportsPerModel:
    async def test_every_required_behaviour_appears_in_the_report(self) -> None:
        probe = await _probe(ScriptedModel())

        assert {result.behaviour for result in probe.behaviours} == set(Behaviour)

    async def test_a_failing_behaviour_names_itself_in_the_refusal(self) -> None:
        probe = await _probe(ScriptedModel(honours_schema=False))

        assert probe.status_of(Behaviour.SCHEMA_ADHERENCE) is BehaviourStatus.FAILED
        assert not probe.usable_for_investigation
        assert any(Behaviour.SCHEMA_ADHERENCE.value in reason for reason in probe.unusable_because)

    async def test_streaming_is_reported_and_is_not_required(self) -> None:
        probe = await _probe(ScriptedModel(streams=False))

        assert probe.status_of(Behaviour.STREAMING) is not BehaviourStatus.PASSED
        assert probe.usable_for_investigation

    async def test_the_demonstrated_schema_limit_is_never_above_the_ceiling(self) -> None:
        probe = await _probe(ScriptedModel(schema_limit=4))

        assert probe.max_tool_schemas <= MAX_AGENT_TOOL_SCHEMAS
        assert probe.max_tool_schemas <= 8

    async def test_the_report_round_trips_through_json(self) -> None:
        probe = await _probe(ScriptedModel())

        assert ModelProbe.from_record(probe.to_record()) == probe


class TestTheProbeCache:
    def test_a_probe_is_returned_for_the_identity_it_was_taken_against(self) -> None:
        cache = ProbeCache()
        identity = ModelIdentity(PROVIDER_OLLAMA, MODEL, fingerprint="sha256:aaa")
        probe = ModelProbe(identity=identity, behaviours=())

        cache.put(probe)

        assert cache.get(identity) is probe

    def test_a_model_changed_underneath_the_deployment_invalidates_its_probe(self) -> None:
        cache = ProbeCache()
        stored = ModelIdentity(PROVIDER_OLLAMA, MODEL, fingerprint="sha256:aaa")
        cache.put(ModelProbe(identity=stored, behaviours=()))

        repulled = ModelIdentity(PROVIDER_OLLAMA, MODEL, fingerprint="sha256:bbb")

        assert cache.get(repulled) is None
        assert cache.get(stored) is None

    def test_the_cache_is_bounded(self) -> None:
        cache = ProbeCache(max_entries=2)
        for index in range(3):
            cache.put(
                ModelProbe(identity=ModelIdentity(PROVIDER_OLLAMA, f"m{index}"), behaviours=())
            )

        assert cache.get(ModelIdentity(PROVIDER_OLLAMA, "m0")) is None
        assert cache.get(ModelIdentity(PROVIDER_OLLAMA, "m2")) is not None


class TestWhatTheWholeEndpointCanDo:
    async def test_every_model_the_endpoint_serves_is_reported_separately(self) -> None:
        from core.llm.probe import ProbeTarget, probe_endpoint

        report = await probe_endpoint(
            (
                ProbeTarget(ScriptedModel(), ADVERTISED),
                ProbeTarget(ScriptedModel(calls_tools=False), ADVERTISED),
            ),
        )

        assert len(report.models) == 2
        assert len(report.usable) == 1
        assert len(report.unusable) == 1

    async def test_the_refusal_names_the_behaviour_in_the_rendered_report(self) -> None:
        from core.llm.probe import ProbeTarget, probe_endpoint

        report = await probe_endpoint((ProbeTarget(ScriptedModel(calls_tools=False), ADVERTISED),))

        rendered = report.render()
        assert Behaviour.TOOL_CALLING.value in rendered
        assert "unusable" in rendered

    async def test_a_context_smaller_than_advertised_is_reported_as_such(self) -> None:
        from core.llm.probe import ProbeTarget, probe_endpoint

        report = await probe_endpoint(
            (ProbeTarget(ScriptedModel(usable_context_tokens=6_000), ADVERTISED),)
        )

        assert str(ADVERTISED) in report.render()
        assert report.models[0].overstated_context

    async def test_a_cached_model_is_not_probed_again(self) -> None:
        from core.llm.probe import ProbeTarget, probe_endpoint

        cache = ProbeCache()
        first = ScriptedModel()
        await probe_endpoint((ProbeTarget(first, ADVERTISED, fingerprint="sha:a"),), cache=cache)
        calls = len(first.requests)

        second = ScriptedModel()
        await probe_endpoint((ProbeTarget(second, ADVERTISED, fingerprint="sha:a"),), cache=cache)

        assert calls > 0
        assert second.requests == []

    async def test_a_model_pulled_again_is_probed_again(self) -> None:
        from core.llm.probe import ProbeTarget, probe_endpoint

        cache = ProbeCache()
        await probe_endpoint(
            (ProbeTarget(ScriptedModel(), ADVERTISED, fingerprint="sha:a"),), cache=cache
        )

        repulled = ScriptedModel()
        await probe_endpoint((ProbeTarget(repulled, ADVERTISED, fingerprint="sha:b"),), cache=cache)

        assert repulled.requests


class TestAnUnusableModelCannotBeSelected:
    async def test_selecting_an_unusable_model_raises_and_names_the_behaviour(self) -> None:
        from core.llm.probe import ModelUnusableError, require_usable

        probe = await _probe(ScriptedModel(calls_tools=False))

        with pytest.raises(ModelUnusableError) as raised:
            require_usable(probe)

        assert Behaviour.TOOL_CALLING.value in str(raised.value)
        assert MODEL in str(raised.value)
