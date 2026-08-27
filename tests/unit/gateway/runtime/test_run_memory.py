"""The run's memory meets the run: bound for the search, installed for the write.

Recall and topology are read sources, and a read source is bound and forgotten.
Memory is not only that. The same composition that answers a recall also has to
record the run that made it, because the corpus a later investigation searches is
built from nothing else — and the two halves have to come from one object, since
the ledger the retriever fills during the run is the one the episode reads at the
end to say which recalls the answer actually used.

So the seam that binds a run's sources yields what it composed, and the runtime
built inside that scope installs the write half on its own hook registry. A run
whose team switched reading off binds no source and is still recorded; a run whose
team switched both off composes nothing at all and reads an honest unavailability.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from typing import Any

import pytest

from capabilities.registry.catalogue import Registry
from capabilities.tools.system.memory_search import binding as memory_binding
from capabilities.tools.system.memory_search.tool import TOOL_NAME as RECALL
from core.agent.hooks.registry import HookRegistry
from core.agent.hooks.types import HookPoint
from core.capability.ports import ConfiguredIntegrations
from core.llm.types import (
    FinishReason,
    InvokeRequest,
    InvokeResult,
    StreamEvent,
    StreamEventKind,
)
from core.llm.usage import TokenCounts, UsageRecord
from gateway.http.services import InvestigationStart
from gateway.runtime import investigator as module
from gateway.runtime.investigator import ReActInvestigationRunner, RunMemory
from platform.guardrails.engine import GuardrailEngine
from platform.memory.retrieval import RecallResult
from platform.persistence.fakes import FakePersistence
from platform.runs.stream import RunEventBroker

pytestmark = pytest.mark.unit

ORG = "acme"
TEAM = "payments"

#: A read that needs no binding, so a run whose recall was withheld still has
#: something to be offered and still reaches the model.
PROMETHEUS_READ = "prometheus_metric_statistics"


class _Recall:
    """A recall path that answers nothing and remembers which run built it."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id

    async def search(self, query: object) -> RecallResult:
        del query
        return RecallResult(searched=True)


@dataclass(slots=True)
class _WatchingLLM:
    """Concludes on the first turn, recording what was bound while it was called."""

    seen_recall: list[Any] = field(default_factory=list)
    requests: list[InvokeRequest] = field(default_factory=list)

    @property
    def provider_id(self) -> str:
        return "scripted"

    @property
    def model_id(self) -> str:
        return "scripted-1"

    async def invoke_structured(
        self, request: InvokeRequest, schema: Mapping[str, Any]
    ) -> InvokeResult:
        """Answer intake and diagnosis without spending a turn of the script.

        A served investigation runs the six stages, so two of its model calls
        are structured ones this double was never scripted for. Answering with
        no structured output puts both stages on the path they document for a
        provider that did not answer — intake reads the input as an incident,
        diagnosis falls back to the conclusion text — and, because it neither
        records the request nor advances the script, it leaves the turns below
        to the loop, which is where this file's assertions are.
        """
        del request, schema
        return InvokeResult(provider_id=self.provider_id, model_id=self.model_id)

    async def invoke(self, request: InvokeRequest) -> InvokeResult:
        self.requests.append(request)
        self.seen_recall.append(memory_binding.current())
        return InvokeResult(
            provider_id=self.provider_id,
            model_id=self.model_id,
            text="Nothing further to gather.",
            finish_reason=FinishReason.STOP,
            usage=UsageRecord(
                provider_id=self.provider_id,
                model_id=self.model_id,
                tokens=TokenCounts(input_tokens=10, output_tokens=5),
            ),
        )

    async def stream(self, request: InvokeRequest) -> AsyncIterator[StreamEvent]:
        result = await self.invoke(request)
        yield StreamEvent(kind=StreamEventKind.TEXT_DELTA, text=result.text)
        yield StreamEvent(kind=StreamEventKind.FINISH, finish_reason=FinishReason.STOP)


@pytest.fixture(autouse=True)
def leave_the_binding_as_found() -> Any:
    """Leave the recall binding as it was found, so one test cannot arm the next."""
    previous = memory_binding.current()
    yield
    memory_binding.restore(previous)


@pytest.fixture(autouse=True)
def everything_connected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Say the team has connected everything, without a configuration tree."""

    async def availability(*_: Any, **__: Any) -> ConfiguredIntegrations:
        return ConfiguredIntegrations(integrations=("prometheus",))

    monkeypatch.setattr(module, "team_availability", availability)


def _catalogue(*names: str) -> Registry:
    """Return a registry holding the named shipped capabilities and nothing else."""
    from capabilities.registry import build_registry

    shipped = build_registry()
    held = {}
    for name in names:
        found = shipped.tool(name)
        assert found is not None, f"{name} is no longer in the shipped catalogue"
        held[name] = found
    return Registry(tools=held)


def _start(run_id: str = "run-1") -> InvestigationStart:
    return InvestigationStart(
        run_id=run_id,
        objective="checkout is saturating its replicas",
        team_node_id=TEAM,
        principal_id="ana",
        org_id=ORG,
        alert_source="alertmanager",
    )


def _runner(llm: Any, registry: Registry) -> ReActInvestigationRunner:
    runner = ReActInvestigationRunner(llm=llm, registry=registry)  # type: ignore[arg-type]
    runner.attach_recording(
        gateway=FakePersistence(), guardrails=GuardrailEngine(), broker=RunEventBroker()
    )
    return runner


async def test_the_runs_own_recall_path_is_bound_while_the_loop_drives() -> None:
    """One composition per investigation, built from that investigation's request."""
    asked: list[str] = []

    async def memory_for(request: InvestigationStart) -> RunMemory:
        asked.append(request.run_id)
        return RunMemory(recall=_Recall(request.run_id))

    llm = _WatchingLLM()
    runner = _runner(llm, _catalogue(RECALL))
    runner.attach_sources(memory=memory_for)

    await runner.investigate(_start("run-7"))

    assert asked == ["run-7"], "memory was composed anywhere but per investigation"
    bound = llm.seen_recall[0]
    assert isinstance(bound, _Recall) and bound.run_id == "run-7"
    offered = tuple(schema.name for schema in llm.requests[0].tools)
    assert RECALL in offered, f"{RECALL} was withheld from a run that had a source bound"


async def test_the_write_half_is_installed_on_the_runs_own_registry() -> None:
    """The corpus fills, or the read composed above searches nothing forever."""
    installed: list[HookRegistry] = []

    async def write_the_episode(session: object, result: object) -> None:
        del session, result

    def install(hooks: HookRegistry) -> HookRegistry:
        installed.append(hooks)
        hooks.register(HookPoint.ON_RUN_END, write_the_episode, name="memory.on_run_end")
        return hooks

    async def memory_for(request: InvestigationStart) -> RunMemory:
        del request
        return RunMemory(recall=_Recall("run-1"), hooks=install)

    runner = _runner(_WatchingLLM(), _catalogue(RECALL))
    runner.attach_sources(memory=memory_for)

    await runner.investigate(_start())

    assert installed, (
        "nothing installed the episode write on the run's hooks. An investigation "
        "that finishes leaves nothing behind, and every recall composed above it "
        "searches an empty corpus."
    )
    attached = tuple(hook.name for hook in installed[0].hooks_at(HookPoint.ON_RUN_END))
    assert attached == ("memory.on_run_end",)


async def test_a_team_that_may_write_but_not_read_is_offered_no_recall() -> None:
    """A capability with nothing behind it spends a turn to report its own absence."""

    async def memory_for(request: InvestigationStart) -> RunMemory:
        del request
        return RunMemory(recall=None, hooks=lambda hooks: hooks)

    llm = _WatchingLLM()
    runner = _runner(llm, _catalogue(RECALL, PROMETHEUS_READ))
    runner.attach_sources(memory=memory_for)

    await runner.investigate(_start())

    offered = tuple(schema.name for schema in llm.requests[0].tools)
    assert RECALL not in offered
    assert PROMETHEUS_READ in offered, "narrowing that removes everything is not narrowing"


async def test_a_team_with_memory_off_leaves_the_capability_unbound() -> None:
    """Unbound is the honest answer, and it is not the same as an empty one."""

    async def no_memory(request: InvestigationStart) -> None:
        del request
        return None

    llm = _WatchingLLM()
    runner = _runner(llm, _catalogue(RECALL, PROMETHEUS_READ))
    runner.attach_sources(memory=no_memory)

    await runner.investigate(_start())

    assert llm.seen_recall[0] is None
    offered = tuple(schema.name for schema in llm.requests[0].tools)
    assert RECALL not in offered


async def test_the_binding_is_put_back_when_the_run_finishes() -> None:
    """What the deployment had bound before the run is what it has after it."""
    outer = _Recall("boot")
    memory_binding.bind(outer)

    async def memory_for(request: InvestigationStart) -> RunMemory:
        return RunMemory(recall=_Recall(request.run_id))

    runner = _runner(_WatchingLLM(), _catalogue(RECALL))
    runner.attach_sources(memory=memory_for)

    await runner.investigate(_start())

    assert memory_binding.current() is outer


def test_composing_memory_and_a_bare_recall_source_is_refused() -> None:
    """Two composers for one binding is a wiring mistake, and a silent precedence
    between them is one nobody would find from a run's behaviour."""

    async def memory_for(request: InvestigationStart) -> None:
        del request
        return None

    async def recall_for(request: InvestigationStart) -> None:
        del request
        return None

    runner = _runner(_WatchingLLM(), _catalogue(RECALL))
    runner.attach_sources(memory=memory_for)

    with pytest.raises(ValueError, match="recall"):
        runner.attach_sources(recall=recall_for)
