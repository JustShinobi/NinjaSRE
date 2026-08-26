"""The read sources meet the run: bound for it, and only for it.

The remediation gate and the question desk are already built per investigation,
for one reason each of them states out loud — they carry the identity of one run,
and one shared between runs attributes a change to the wrong person or closes the
wrong incident's question. Recall and topology carry the same identity and had no
such seam: a composition root bound them for the process at boot, or nothing
bound them at all.

This is the seam. The runner is handed factories, builds each run's own sources
from that run's request, binds them for the length of the run and puts back
whatever it displaced — including when the run raises, because a run that fails
still has to leave the process as it found it.

A runner given no factories touches neither binding. That is not an oversight
being tolerated: a deployment that binds its sources at boot, and every test that
binds one around a call, must keep behaving exactly as it did.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest

from capabilities.registry.catalogue import Registry
from capabilities.tools.system.memory_search import binding as memory_binding
from capabilities.tools.system.memory_search.tool import TOOL_NAME as RECALL
from capabilities.tools.system.topology_query import binding as topology_binding
from capabilities.tools.system.topology_query.tool import TOOL_NAME as TOPOLOGY
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
from gateway.runtime.investigator import ReActInvestigationRunner
from platform.guardrails.engine import GuardrailEngine
from platform.knowledge.topology.models import BlastRadius, DependencySet
from platform.knowledge.topology.queries import ServiceTopology
from platform.memory.retrieval import RecallResult
from platform.persistence.fakes import FakePersistence
from platform.runs.stream import RunEventBroker

pytestmark = pytest.mark.unit

ORG = "acme"
TEAM = "acme/payments"

#: A read that needs no binding, kept in the catalogue beside the ones that do.
#: A run narrowed down to nothing ends before the model is called, which would
#: leave the tests below asserting about a turn that never happened.
PROMETHEUS_READ = "prometheus_metric_statistics"


class _Recall:
    """A recall path that answers nothing and remembers which run built it."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id

    async def search(self, query: object) -> RecallResult:
        del query
        return RecallResult(searched=True)


class _Topology:
    """A topology path that answers nothing and remembers which run built it."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id

    async def query(self, service: str, *, depth: int = 2) -> ServiceTopology:
        return ServiceTopology(
            service=service,
            depth=depth,
            dependencies=DependencySet(origin=service, depth=depth),
            dependents=DependencySet(origin=service),
            blast_radius=BlastRadius(origin=service, max_depth=depth),
        )


@dataclass(slots=True)
class _WatchingLLM:
    """Concludes on the first turn, recording what was bound while it was called.

    Reading the binding from inside ``invoke`` is what makes this a test of the
    run rather than of the seam's bookkeeping: this is the only moment that
    proves the source was still bound while the loop was actually driving.
    """

    #: Awaited before answering, so two concurrent runs can be held open at once.
    hold: asyncio.Barrier | None = None
    seen_recall: list[Any] = field(default_factory=list)
    seen_topology: list[Any] = field(default_factory=list)
    requests: list[InvokeRequest] = field(default_factory=list)

    @property
    def provider_id(self) -> str:
        return "scripted"

    @property
    def model_id(self) -> str:
        return "scripted-1"

    async def invoke(self, request: InvokeRequest) -> InvokeResult:
        self.requests.append(request)
        if self.hold is not None:
            await self.hold.wait()
        self.seen_recall.append(memory_binding.current())
        self.seen_topology.append(topology_binding.current())
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
def leave_both_bindings_as_found() -> Iterator[None]:
    """Leave both bindings as they were found, so one test cannot arm the next."""
    held = [(each, each.current()) for each in (memory_binding, topology_binding)]
    yield
    for binding, previous in held:
        binding.restore(previous)


@pytest.fixture(autouse=True)
def everything_connected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Say the team has connected everything, without standing up a configuration tree.

    These capabilities need no integration, so what is being isolated here is the
    source binding and nothing else.
    """

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
    """Return a runner that can read the configuration tree and record nothing else."""
    store = FakePersistence()
    runner = ReActInvestigationRunner(llm=llm, registry=registry)  # type: ignore[arg-type]
    runner.attach_recording(gateway=store, guardrails=GuardrailEngine(), broker=RunEventBroker())
    return runner


async def test_a_run_reads_the_source_its_own_factory_built() -> None:
    """The factory is asked per investigation and handed that investigation."""
    asked: list[str] = []

    async def recall_for(request: InvestigationStart) -> _Recall:
        asked.append(request.run_id)
        return _Recall(request.run_id)

    llm = _WatchingLLM()
    runner = _runner(llm, _catalogue(RECALL))
    runner.attach_sources(recall=recall_for)

    await runner.investigate(_start("run-7"))

    assert asked == ["run-7"], (
        "the recall factory was not asked once for this run. A source built anywhere "
        "but per investigation is a source scoped to somebody else's team."
    )
    bound = llm.seen_recall[0]
    assert isinstance(bound, _Recall) and bound.run_id == "run-7", (
        "the loop ran with something other than this run's own recall path bound."
    )


async def test_the_capability_is_offered_because_this_run_bound_a_source() -> None:
    """The exclusion asks the binding, and the binding is now this run's.

    Without this the seam would be invisible: a source bound for the run but
    read after the catalogue was narrowed would leave the capability excluded and
    the whole composition pointless.
    """

    async def recall_for(request: InvestigationStart) -> _Recall:
        return _Recall(request.run_id)

    llm = _WatchingLLM()
    runner = _runner(llm, _catalogue(RECALL))
    runner.attach_sources(recall=recall_for)

    await runner.investigate(_start())

    assert llm.requests, "the loop never called the model, so nothing was offered"
    offered = tuple(schema.name for schema in llm.requests[0].tools)
    assert RECALL in offered, (
        f"{RECALL} was withheld from a run that had a source bound for it. The "
        f"exclusion is meant to name what this deployment cannot serve."
    )


async def test_both_sources_are_bound_for_the_run_that_asked_for_them() -> None:
    """Recall and topology are one seam, registered independently and bound together."""

    async def recall_for(request: InvestigationStart) -> _Recall:
        return _Recall(request.run_id)

    async def topology_for(request: InvestigationStart) -> _Topology:
        return _Topology(request.run_id)

    llm = _WatchingLLM()
    runner = _runner(llm, _catalogue(RECALL, TOPOLOGY))
    runner.attach_sources(recall=recall_for)
    runner.attach_sources(topology=topology_for)

    await runner.investigate(_start("run-9"))

    assert isinstance(llm.seen_recall[0], _Recall), "recall was not bound for the run"
    assert isinstance(llm.seen_topology[0], _Topology), (
        "registering topology separately dropped it, or dropped the recall factory "
        "registered before it"
    )
    offered = tuple(schema.name for schema in llm.requests[0].tools)
    assert RECALL in offered and TOPOLOGY in offered


async def test_the_binding_is_put_back_when_the_run_finishes() -> None:
    """What the deployment had bound before the run is what it has after it."""
    outer = _Recall("boot")
    memory_binding.bind(outer)

    async def recall_for(request: InvestigationStart) -> _Recall:
        return _Recall(request.run_id)

    runner = _runner(_WatchingLLM(), _catalogue(RECALL))
    runner.attach_sources(recall=recall_for)

    await runner.investigate(_start())

    assert memory_binding.current() is outer, (
        "a finished run left its own recall path bound. The next investigation in "
        "this process would search the finished run's team."
    )


async def test_the_binding_is_put_back_when_the_run_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed run leaves the process as it found it, which is the harder half.

    Restoring only on the way out of a successful return is the bug that looks
    fixed: the deployment that most needs the binding gone is the one whose run
    just died holding it.
    """

    class _ExplodingLoop:
        def __init__(self, **_: Any) -> None:
            pass

        async def run(self, request: object) -> Any:
            del request
            raise RuntimeError("the provider went away mid-run")

    monkeypatch.setattr(module, "ReActLoop", _ExplodingLoop)

    outer = _Recall("boot")
    memory_binding.bind(outer)

    async def recall_for(request: InvestigationStart) -> _Recall:
        return _Recall(request.run_id)

    runner = _runner(_WatchingLLM(), _catalogue(RECALL))
    runner.attach_sources(recall=recall_for)

    with pytest.raises(RuntimeError):
        await runner.investigate(_start())

    assert memory_binding.current() is outer, (
        "a run that raised kept its recall path bound to the process"
    )


async def test_two_concurrent_runs_each_read_their_own_source() -> None:
    """The failure this whole change exists for, driven through the runner.

    Both runs are held inside their model call at the same time — the barrier
    guarantees it — which is the interleaving three alerts landing inside 82
    milliseconds produces.
    """
    both_in_the_loop = asyncio.Barrier(2)

    async def recall_for(request: InvestigationStart) -> _Recall:
        return _Recall(request.run_id)

    async def drive(run_id: str) -> _WatchingLLM:
        llm = _WatchingLLM(hold=both_in_the_loop)
        runner = _runner(llm, _catalogue(RECALL))
        runner.attach_sources(recall=recall_for)
        await runner.investigate(_start(run_id))
        return llm

    first, second = await asyncio.gather(drive("run-a"), drive("run-b"))

    assert first.seen_recall[0].run_id == "run-a", (
        "one investigation read another's recall path while both were running. "
        "That is a search returning the other team's incidents."
    )
    assert second.seen_recall[0].run_id == "run-b"


async def test_a_runner_given_no_factories_leaves_the_binding_alone() -> None:
    """Composed nothing is still a working deployment, and still binds nothing.

    A runner that unbound on the way in would break every deployment that binds
    its sources at boot, and would turn the seam into a behaviour change for
    callers that never asked for one.
    """
    outer = _Recall("boot")
    memory_binding.bind(outer)

    llm = _WatchingLLM()
    runner = _runner(llm, _catalogue(RECALL))

    await runner.investigate(_start())

    assert llm.seen_recall[0] is outer, (
        "a runner with no factory of its own displaced the binding the deployment had already made"
    )
    offered = tuple(schema.name for schema in llm.requests[0].tools)
    assert RECALL in offered, "a process-wide binding stopped being enough to offer the read"
    assert memory_binding.current() is outer


async def test_a_factory_that_builds_nothing_leaves_the_capability_out() -> None:
    """A deployment that cannot scope a source for this run says so by binding none.

    Returning ``None`` is the honest answer for a run whose team has no corpus,
    and it has to reach the catalogue as an exclusion rather than as a tool that
    will spend a turn reporting its own absence.
    """

    async def no_recall(request: InvestigationStart) -> None:
        del request
        return None

    llm = _WatchingLLM()
    runner = _runner(llm, _catalogue(RECALL, PROMETHEUS_READ))
    runner.attach_sources(recall=no_recall)

    await runner.investigate(_start())

    assert llm.requests, "the loop never called the model, so nothing was offered"
    offered = tuple(schema.name for schema in llm.requests[0].tools)
    assert RECALL not in offered, (
        f"{RECALL} was offered with nothing bound behind it. Every call it can "
        f"receive comes back an unavailability, and the turn is spent either way."
    )
    assert PROMETHEUS_READ in offered, "narrowing that removes everything is not narrowing"
