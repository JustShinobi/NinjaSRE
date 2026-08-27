"""An investigation finishes, and the next one can recall it.

Everything below drives the real runner over the real store, through the real
composition the boot performs. That is the point: every part of episodic memory
has existed and passed its own tests for a long time, and this deployment's corpus
is still empty — no episodes, no vector index, no generation — because no serving
path ever installed the hook that writes one.

So the assertion that matters is the round trip. Run one investigation to
completion, and run a second one afterwards: the source bound for the *second* run
finds what the *first* one left. Nothing here stubs a retriever or hands an episode
to a store by hand; the corpus is filled the only way a deployment can fill it,
which is by finishing an investigation.

The second assertion is the one that makes recall safe to switch on at all. Two
runs, two teams, one organisation and one physical store: the run investigating
the other team finds nothing, because the team filter is applied inside the index
*and* checked on every row that comes back.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import pytest

from capabilities.registry.catalogue import Registry
from capabilities.tools.system.memory_search import binding as memory_binding
from capabilities.tools.system.memory_search.tool import TOOL_NAME as RECALL
from core.capability.ports import ConfiguredIntegrations
from core.llm.types import (
    FinishReason,
    InvokeRequest,
    InvokeResult,
    StreamEvent,
    StreamEventKind,
)
from core.llm.usage import TokenCounts, UsageRecord
from gateway.http.memory_sources import compose_memory
from gateway.http.services import InvestigationStart
from gateway.http.state import GatewayState
from gateway.runtime import investigator as runtime
from gateway.runtime.investigator import ReActInvestigationRunner
from platform.guardrails.engine import GuardrailEngine
from platform.identity.tokens import TokenService
from platform.memory.models import RecallQuery
from platform.memory.retrieval import RecallResult
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports.config_repository import ConfigNode, ConfigNodeKind
from platform.persistence.ports.transaction import TenantScope
from platform.runs.stream import RunEventBroker

pytestmark = pytest.mark.unit

ORG = "acme"
PAYMENTS = "payments"
PLATFORM = "platform"

#: What the run concludes. Long enough to be extracted at all — a reply below the
#: floor is skipped as an investigation that reached no conclusion worth keeping.
CONCLUSION = (
    "The payments-api pods were OOMKilled after the checkout release raised the "
    "per-request buffer without raising the memory limit. Three restarts inside "
    "four minutes, each one at the same allocation, and the limit has been the "
    "same since March. Raising the limit to 1Gi cleared it and the error rate "
    "returned to baseline within a minute."
)

#: The words a later run searches on. The default embedder is lexical rather than
#: semantic, so a recall that shares no vocabulary with the episode is a recall
#: that legitimately matches nothing — and would make this test prove nothing.
QUERY = "OOMKilled payments-api memory limit"

EXTRACTED: Mapping[str, Any] = {
    "issue_type": "oom_kill",
    "issue_description": "payments-api OOMKilled after a release raised its per-request buffer",
    "severity": "high",
    "components": [{"name": "payments-api", "type": "service"}],
    "key_findings": [],
    "resolved": True,
    "root_cause": "the memory limit was never raised alongside the buffer",
    "summary": "OOMKilled payments-api cleared by raising the memory limit to 1Gi",
}


@dataclass(slots=True)
class _ScriptedLLM:
    """Concludes in one turn, and answers the extraction call that follows it.

    The same client serves both because the deployment resolves both from the
    same factory. ``during`` runs inside the model call, which is the only moment
    that proves a source was bound while the loop was actually driving.
    """

    during: Callable[[], Any] | None = None
    observed: list[Any] = field(default_factory=list)
    #: Awaited before answering, so two runs can be held open at the same time.
    hold: asyncio.Barrier | None = None

    @property
    def provider_id(self) -> str:
        return "scripted"

    @property
    def model_id(self) -> str:
        return "scripted-1"

    def _usage(self) -> UsageRecord:
        return UsageRecord(
            provider_id=self.provider_id,
            model_id=self.model_id,
            tokens=TokenCounts(input_tokens=10, output_tokens=5),
        )

    async def invoke(self, request: InvokeRequest) -> InvokeResult:
        del request
        if self.hold is not None:
            await self.hold.wait()
        if self.during is not None:
            self.observed.append(await self.during())
        return InvokeResult(
            provider_id=self.provider_id,
            model_id=self.model_id,
            text=CONCLUSION,
            finish_reason=FinishReason.STOP,
            usage=self._usage(),
        )

    async def invoke_structured(
        self, request: InvokeRequest, schema: Mapping[str, Any]
    ) -> InvokeResult:
        del request, schema
        return InvokeResult(
            provider_id=self.provider_id,
            model_id=self.model_id,
            structured=EXTRACTED,
            finish_reason=FinishReason.STOP,
            usage=self._usage(),
        )

    async def stream(self, request: InvokeRequest) -> AsyncIterator[StreamEvent]:
        result = await self.invoke(request)
        yield StreamEvent(kind=StreamEventKind.TEXT_DELTA, text=result.text)
        yield StreamEvent(kind=StreamEventKind.FINISH, finish_reason=FinishReason.STOP)


@pytest.fixture(autouse=True)
def leave_the_binding_as_found() -> Any:
    previous = memory_binding.current()
    yield
    memory_binding.restore(previous)


@pytest.fixture(autouse=True)
def everything_connected(monkeypatch: pytest.MonkeyPatch) -> None:
    async def availability(*_: Any, **__: Any) -> ConfiguredIntegrations:
        return ConfiguredIntegrations(integrations=("prometheus",))

    monkeypatch.setattr(runtime, "team_availability", availability)


async def _tree(store: FakePersistence) -> None:
    async with store.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme")
    async with store.begin(TenantScope(org_id=ORG)) as uow:
        for team in (PAYMENTS, PLATFORM):
            await uow.config.upsert(
                ConfigNode(node_id=team, kind=ConfigNodeKind.TEAM, name=team, parent_id=ORG)
            )


def _catalogue() -> Registry:
    from capabilities.registry import build_registry

    shipped = build_registry()
    found = shipped.tool(RECALL)
    assert found is not None
    return Registry(tools={RECALL: found})


def _start(team: str, run_id: str) -> InvestigationStart:
    return InvestigationStart(
        run_id=run_id,
        objective="payments-api is restarting",
        team_node_id=team,
        principal_id="ana",
        org_id=ORG,
        alert_source="alertmanager",
    )


def _deployment(
    store: FakePersistence, llm: _ScriptedLLM, monkeypatch: pytest.MonkeyPatch
) -> GatewayState:
    """Return a state whose runner has been composed exactly as the boot composes it."""
    from gateway.http import memory_sources

    monkeypatch.setattr(memory_sources, "get_llm", lambda _role: llm)

    runner = ReActInvestigationRunner(llm=llm, registry=_catalogue())  # type: ignore[arg-type]
    runner.attach_recording(gateway=store, guardrails=GuardrailEngine(), broker=RunEventBroker())
    state = GatewayState(gateway=store, tokens=TokenService(gateway=store), investigator=runner)
    assert compose_memory(state, org_id=ORG)
    return state


async def _recall_now() -> RecallResult:
    """Search with whatever this run has bound, from inside the model call."""
    source = memory_binding.current()
    assert source is not None, "the run reached the model with no recall path bound"
    return await source.search(RecallQuery(text=QUERY))


async def test_a_finished_investigation_leaves_an_episode_the_next_one_finds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The round trip, and the whole reason both halves ship together."""
    store = FakePersistence()
    await _tree(store)
    llm = _ScriptedLLM(during=_recall_now)
    state = _deployment(store, llm, monkeypatch)
    runner = state.investigator
    assert isinstance(runner, ReActInvestigationRunner)

    await runner.investigate(_start(PAYMENTS, "run-first"))
    await runner.investigate(_start(PAYMENTS, "run-second"))

    first, second = llm.observed
    assert first.searched and first.empty, (
        "the first run of a fresh deployment found something. Its corpus is empty, "
        "and an empty corpus is a successful search that matched nothing."
    )
    assert second.searched and not second.empty, (
        "the second investigation could not recall the first. An investigation that "
        "finishes has to leave an episode behind, or the corpus never fills and every "
        "recall this deployment ever runs searches nothing."
    )
    assert second.episodes[0].episode.issue_type == "oom_kill"
    assert second.episodes[0].episode.run_id == "run-first"


async def test_two_teams_never_recall_each_others_episodes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One store, one organisation, two teams — and a filter checked on every row."""
    store = FakePersistence()
    await _tree(store)
    llm = _ScriptedLLM(during=_recall_now)
    state = _deployment(store, llm, monkeypatch)
    runner = state.investigator
    assert isinstance(runner, ReActInvestigationRunner)

    await runner.investigate(_start(PAYMENTS, "run-payments"))
    await runner.investigate(_start(PLATFORM, "run-platform"))
    await runner.investigate(_start(PAYMENTS, "run-payments-again"))

    _, platform, payments_again = llm.observed
    assert platform.searched and platform.empty, (
        "a run investigating one team recalled another team's incident. That is the "
        "disclosure the team filter and the per-row check exist to prevent."
    )
    assert not payments_again.empty, "the team that wrote the episode stopped finding it"


async def test_two_concurrent_runs_read_their_own_teams_corpus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both runs held inside their model call at once, which is what this
    deployment produces when three alerts land inside 82 milliseconds."""
    store = FakePersistence()
    await _tree(store)

    seeding = _ScriptedLLM()
    state = _deployment(store, seeding, monkeypatch)
    runner = state.investigator
    assert isinstance(runner, ReActInvestigationRunner)
    await runner.investigate(_start(PAYMENTS, "run-seed"))

    both_in_the_loop = asyncio.Barrier(2)

    async def drive(team: str, run_id: str) -> _ScriptedLLM:
        llm = _ScriptedLLM(during=_recall_now, hold=both_in_the_loop)
        concurrent = _deployment(store, llm, monkeypatch)
        driver = concurrent.investigator
        assert isinstance(driver, ReActInvestigationRunner)
        await driver.investigate(_start(team, run_id))
        return llm

    payments, platform = await asyncio.gather(drive(PAYMENTS, "run-a"), drive(PLATFORM, "run-b"))

    assert not payments.observed[0].empty, (
        "the run investigating the team that owns the episode found nothing while "
        "another team's run was in flight beside it"
    )
    assert platform.observed[0].empty, (
        "one investigation read another team's corpus while both were running. That "
        "is a search returning the wrong team's incidents."
    )
