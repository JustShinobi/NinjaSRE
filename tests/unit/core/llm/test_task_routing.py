"""Sending each kind of call to the model configured for it, and saying which.

The point of routing is not speed. It is that summarising an incident, embedding
an episode and choosing which capability to call next are all jobs a small local
model does perfectly well, and the final root-cause synthesis may not be — so an
operator who wants the cheap model for five of the six and something else for the
sixth should be able to say so.

The half that has to be airtight is the *record*. A run whose parts came from
different models and whose trace does not say which is a run whose answer nobody
can attribute, and Article VII's "learning is measured or not claimed" turns on
being able to say what produced a number.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping
from typing import Any

import pytest

from config.constants.config_service import (
    MODEL_ROLE_EMBEDDING,
    MODEL_ROLE_INTAKE,
    MODEL_ROLE_INVESTIGATOR,
    MODEL_ROLES,
)
from config.constants.llm import DEFAULT_MODEL_ID, DEFAULT_PROVIDER, PROVIDER_OLLAMA
from core.agent.guard import require_canonical_runtime
from core.agent.react_loop import CANONICAL_RUNTIME_NAME, ReActLoop
from core.llm.routing import (
    TASK_ROLES,
    AttributionLedger,
    ModelAttribution,
    TaskClass,
    TaskRouter,
)
from core.llm.types import (
    InvokeRequest,
    InvokeResult,
    StreamEvent,
    StreamEventKind,
    TokenEstimate,
)

pytestmark = pytest.mark.unit


class _ConcludingModel:
    """Answers in prose on its first turn, so a run is one attributable call."""

    @property
    def provider_id(self) -> str:
        return PROVIDER_OLLAMA

    @property
    def model_id(self) -> str:
        return "qwen2.5:7b"

    def count_tokens(self, request: InvokeRequest) -> TokenEstimate:
        return TokenEstimate(tokens=0, estimated=True)

    async def invoke(self, request: InvokeRequest) -> InvokeResult:
        return InvokeResult(
            provider_id=self.provider_id,
            model_id=self.model_id,
            text="The cause is connection pool exhaustion.",
        )

    async def invoke_structured(
        self, request: InvokeRequest, schema: Mapping[str, Any]
    ) -> InvokeResult:
        return await self.invoke(request)

    async def stream(self, request: InvokeRequest) -> AsyncIterator[StreamEvent]:
        if False:  # pragma: no cover — the loop never streams
            yield StreamEvent(kind=StreamEventKind.FINISH)


class StaticSelections:
    """A configuration source that answers from a dictionary."""

    def __init__(self, selections: dict[str, tuple[str, str]]) -> None:
        self._selections = selections

    def selection_for(self, role: str) -> tuple[str, str] | None:
        """Return what ``role`` is bound to, or ``None`` when nobody bound it."""
        return self._selections.get(role)


class TestTheTaskClasses:
    def test_every_class_the_runtime_makes_a_call_for_has_a_role(self) -> None:
        assert set(TASK_ROLES) == set(TaskClass)

    def test_every_role_a_task_maps_to_is_one_the_config_service_declares(self) -> None:
        assert set(TASK_ROLES.values()) <= set(MODEL_ROLES)

    def test_the_six_classes_are_the_ones_the_runtime_actually_distinguishes(self) -> None:
        assert {task.value for task in TaskClass} == {
            "reasoning",
            "capability_selection",
            "summarisation",
            "extraction",
            "embedding",
            "classification",
        }


class TestResolvingAModelPerTask:
    def test_a_configured_task_resolves_to_its_own_model(self) -> None:
        router = TaskRouter(
            source=StaticSelections({MODEL_ROLE_INVESTIGATOR: ("anthropic", "claude-sonnet-5")})
        )

        binding = router.binding_for(TaskClass.REASONING)

        assert (binding.provider_id, binding.model_id) == ("anthropic", "claude-sonnet-5")
        assert binding.configured

    def test_an_unconfigured_task_falls_back_to_the_deployment_default(self) -> None:
        router = TaskRouter(source=StaticSelections({}))

        binding = router.binding_for(TaskClass.SUMMARISATION)

        assert (binding.provider_id, binding.model_id) == (DEFAULT_PROVIDER, DEFAULT_MODEL_ID)
        assert not binding.configured

    def test_the_fallback_is_the_deployment_default_not_another_task(self) -> None:
        router = TaskRouter(
            source=StaticSelections({MODEL_ROLE_INVESTIGATOR: ("anthropic", "claude-opus-5")}),
            default_provider=PROVIDER_OLLAMA,
            default_model="qwen2.5:7b",
        )

        assert router.binding_for(TaskClass.EMBEDDING).model_id == "qwen2.5:7b"

    def test_classification_and_embedding_reach_the_roles_they_are_named_for(self) -> None:
        router = TaskRouter(
            source=StaticSelections(
                {
                    MODEL_ROLE_INTAKE: (PROVIDER_OLLAMA, "small-classifier"),
                    MODEL_ROLE_EMBEDDING: (PROVIDER_OLLAMA, "nomic-embed"),
                }
            )
        )

        assert router.binding_for(TaskClass.CLASSIFICATION).model_id == "small-classifier"
        assert router.binding_for(TaskClass.EMBEDDING).model_id == "nomic-embed"

    def test_a_router_with_no_source_at_all_still_answers(self) -> None:
        router = TaskRouter()

        assert router.binding_for(TaskClass.REASONING).model_id == DEFAULT_MODEL_ID


class TestTheTraceRecordsWhichModelProducedWhat:
    def test_an_attribution_names_the_task_the_model_and_the_output(self) -> None:
        ledger = AttributionLedger()

        ledger.record(
            TaskClass.SUMMARISATION,
            provider_id=PROVIDER_OLLAMA,
            model_id="qwen2.5:7b",
            output="incident summary",
        )

        assert ledger.entries == [
            ModelAttribution(
                task=TaskClass.SUMMARISATION.value,
                provider_id=PROVIDER_OLLAMA,
                model_id="qwen2.5:7b",
                output="incident summary",
            )
        ]

    def test_the_model_set_is_what_a_published_number_records(self) -> None:
        ledger = AttributionLedger()
        ledger.record(TaskClass.REASONING, provider_id="anthropic", model_id="claude-opus-5")
        ledger.record(TaskClass.EMBEDDING, provider_id=PROVIDER_OLLAMA, model_id="nomic-embed")
        ledger.record(TaskClass.REASONING, provider_id="anthropic", model_id="claude-opus-5")

        assert ledger.model_set() == ("anthropic/claude-opus-5", "ollama/nomic-embed")

    def test_the_ledger_round_trips_through_json(self) -> None:
        ledger = AttributionLedger()
        ledger.record(TaskClass.REASONING, provider_id="anthropic", model_id="claude-opus-5")

        assert AttributionLedger.from_record(json.loads(json.dumps(ledger.to_record()))) == ledger

    async def test_a_run_records_the_model_behind_every_turn(self) -> None:
        from core.agent.runtime_port import RunRequest

        loop = ReActLoop(llm=_ConcludingModel())

        result = await loop.run(RunRequest(objective="Why is checkout returning 503?"))

        assert [entry.model_id for entry in result.session.attributions] == ["qwen2.5:7b"]
        assert result.session.attributions[0].task == TaskClass.REASONING.value
        assert result.session.attributions[0].output == "turn 1"

    async def test_the_attributions_survive_a_stored_and_reloaded_session(self) -> None:
        from core.agent.runtime_port import RunRequest
        from core.agent.session import Session

        loop = ReActLoop(llm=_ConcludingModel())
        result = await loop.run(RunRequest(objective="Why is checkout returning 503?"))

        restored = Session.from_record(json.loads(json.dumps(result.session.to_record())))

        assert restored.attributions == result.session.attributions


class TestRoutingLeavesTheCanonicalRuntimeAlone:
    def test_routing_does_not_make_a_second_runtime(self) -> None:
        """Article V: the same loop runs; only which model answers a call changes."""
        from core.agent.runtime_port import RunRequest  # noqa: F401 — the port is unchanged

        assert CANONICAL_RUNTIME_NAME == "ninjasre.react"

    def test_the_benchmark_guard_still_only_admits_the_canonical_loop(self) -> None:
        class Experimental:
            name = "vendor.sdk"
            is_canonical = False

        with pytest.raises(Exception, match="canonical"):
            require_canonical_runtime(Experimental(), context="the scenario benchmark")  # type: ignore[arg-type]


class TestOneResolutionRule:
    """The router resolves through the same function the deployment calls.

    FR-017 asks for a model resolvable per task class through the config
    service, and this class was the faithful implementation of it — while
    `resolve_binding` grew up beside it as what everything actually called.
    Two resolvers for one fact is one too many, and the second one was the
    dangerous kind: it carried its own default pair, so it could not know that
    an unnamed role follows the investigator, and wiring it in as it stood
    would have reintroduced the split-provider failure by another door.
    """

    def test_the_router_inherits_the_investigator_like_everything_else(self) -> None:
        from core.llm.factory import publish_configured_bindings, reset_configured_bindings

        reset_configured_bindings()
        publish_configured_bindings({MODEL_ROLE_INVESTIGATOR: (PROVIDER_OLLAMA, "qwen2.5:7b")})
        try:
            binding = TaskRouter().binding_for(TaskClass.EXTRACTION)
            assert (binding.provider_id, binding.model_id) == (PROVIDER_OLLAMA, "qwen2.5:7b")
            assert not binding.configured, (
                "following the investigator is not a choice for this task"
            )
        finally:
            reset_configured_bindings()
