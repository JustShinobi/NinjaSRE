"""Composing episodic memory for one run: the search it reads and the episode it leaves.

The defect this closes is one defect wearing two faces. ``recall_similar_incidents``
returned "memory is not configured" on every investigation this deployment has ever
run, because nothing bound it a source. And the corpus it would have searched is
empty — no episodes, no vector index, no generation — because nothing installed the
hook that writes one at the end of a run.

Composing only the read half would be worse than leaving it alone. A bound source
over an empty corpus reports a successful, empty search, and the capability's own
docstring names that as the failure it exists to prevent: an investigation
concluding "no similar incidents" on the strength of a store nobody configured. So
both halves are composed here, from one ``MemoryService``, which is also what makes
the recall ledger the retriever fills the same one the episode reads at run end.

Three things decide what gets composed, and each has a way of being silently wrong:

**The team's own policy.** Reading and writing switch separately, and a team with
both off must get the *unbound* behaviour — an honest unavailability — rather than
a bound source answering "nothing found" for a corpus it was never allowed to read.

**The team's own scope.** A retriever refuses a scope with no team on it, because an
unscoped search is one that can return another team's incidents. A run that names no
team therefore composes nothing rather than composing something org-wide.

**The boot.** A composition nothing calls is the state this deployment was already
in, and a test of ``compose_memory`` alone would have passed for it.
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from typing import Any

import pytest

from capabilities.registry.catalogue import Registry
from gateway.http.memory_sources import compose_memory
from gateway.http.services import InvestigationStart
from gateway.http.state import GatewayState
from gateway.runtime.investigator import ReActInvestigationRunner, RunMemory
from platform.identity.tokens import TokenService
from platform.memory.models import RecallQuery
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports.config_repository import ConfigNode, ConfigNodeKind
from platform.persistence.ports.transaction import TenantScope

pytestmark = pytest.mark.unit

ORG = "acme"
PAYMENTS = "payments"
PLATFORM = "platform"


class _StubLLM:
    """Enough of a client to construct a service. Nothing here calls it."""

    provider_id = "scripted"
    model_id = "scripted-1"


async def _tree(store: FakePersistence, **values: Mapping[str, Any]) -> None:
    """Seed the organisation and two teams, with ``values`` set per node."""
    async with store.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme")
    async with store.begin(TenantScope(org_id=ORG)) as uow:
        for team in (PAYMENTS, PLATFORM):
            await uow.config.upsert(
                ConfigNode(
                    node_id=team,
                    kind=ConfigNodeKind.TEAM,
                    name=team,
                    parent_id=ORG,
                    values=dict(values.get(team, {})),
                )
            )


def _memory_off(*, read: bool = False, write: bool = False) -> Mapping[str, Any]:
    """Return the node values a team switching memory off has written."""
    return {"policies": {"memory": {"read_enabled": read, "write_enabled": write}}}


def _state(store: FakePersistence) -> GatewayState:
    """Return the state a composition root would hand the composer."""
    return GatewayState(
        gateway=store,
        tokens=TokenService(gateway=store),
        investigator=ReActInvestigationRunner(llm=None, registry=Registry()),  # type: ignore[arg-type]
    )


def _start(team: str, run_id: str = "run-1") -> InvestigationStart:
    return InvestigationStart(
        run_id=run_id,
        objective="checkout is saturating its replicas",
        team_node_id=team,
        principal_id="ana",
        org_id=ORG,
        alert_source="alertmanager",
    )


@pytest.fixture(autouse=True)
def a_model_that_is_never_called(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve the extraction role without standing up a provider.

    The composer asks for a client per run so a configuration reload is picked
    up; none of the tests in this file makes a call with it.
    """
    from gateway.http import memory_sources

    monkeypatch.setattr(memory_sources, "get_llm", lambda _role: _StubLLM())


async def _composed(state: GatewayState, request: InvestigationStart) -> RunMemory | None:
    """Return what the factory the composer attached builds for ``request``."""
    runner = state.investigator
    assert isinstance(runner, ReActInvestigationRunner)
    factory = runner.sources.memory
    assert factory is not None, "compose_memory attached no factory to the runner"
    return await factory(request)


# -- what gets composed --------------------------------------------------------


async def test_a_team_with_memory_on_gets_both_halves() -> None:
    """The read the agent calls and the write that fills the corpus it reads."""
    store = FakePersistence()
    await _tree(store)
    state = _state(store)

    assert compose_memory(state, org_id=ORG)

    memory = await _composed(state, _start(PAYMENTS))
    assert memory is not None, (
        "a team with memory enabled composed nothing. Every recall on this "
        "deployment reports that memory is not configured."
    )
    assert memory.recall is not None, "nothing answers a recall for a team that may read"
    assert memory.hooks is not None, (
        "no hook was composed to write the episode. Composing only the read half "
        "turns 'memory is not configured' into 'searched and found nothing'."
    )


async def test_a_team_with_memory_switched_off_composes_nothing() -> None:
    """Off means unbound, which is an unavailability — never an empty answer."""
    store = FakePersistence()
    await _tree(store, payments=_memory_off())
    state = _state(store)
    compose_memory(state, org_id=ORG)

    assert await _composed(state, _start(PAYMENTS)) is None, (
        "a team that switched memory off got a source bound anyway. Its "
        "investigations would read 'this failure is new to the team' from a "
        "corpus they are not allowed to consult."
    )


async def test_a_team_that_may_write_but_not_read_binds_no_search() -> None:
    """The ablation worth running: a corpus that fills while nobody consults it."""
    store = FakePersistence()
    await _tree(store, payments=_memory_off(read=False, write=True))
    state = _state(store)
    compose_memory(state, org_id=ORG)

    memory = await _composed(state, _start(PAYMENTS))

    assert memory is not None
    assert memory.recall is None, (
        "recall was bound for a team that switched reading off. The capability "
        "would be offered, spend a turn, and come back an unavailability."
    )
    assert memory.hooks is not None, "the corpus stopped filling when reading was switched off"


async def test_a_run_that_names_no_team_composes_nothing() -> None:
    """An unscoped episode is one every team can retrieve, and an unscoped search
    is one that returns another team's incidents."""
    store = FakePersistence()
    await _tree(store)
    state = _state(store)
    compose_memory(state, org_id=ORG)

    assert await _composed(state, _start("")) is None


async def test_a_team_the_configuration_tree_does_not_hold_composes_nothing() -> None:
    """An unread policy is not permission, and memory may never fail a run."""
    store = FakePersistence()
    await _tree(store)
    state = _state(store)
    compose_memory(state, org_id=ORG)

    assert await _composed(state, _start("nobody")) is None


async def test_each_run_gets_a_source_scoped_to_its_own_team() -> None:
    """Two runs, two teams, two scopes — resolved from each run's own request."""
    store = FakePersistence()
    await _tree(store)
    state = _state(store)
    compose_memory(state, org_id=ORG)

    first = await _composed(state, _start(PAYMENTS, "run-a"))
    second = await _composed(state, _start(PLATFORM, "run-b"))

    assert first is not None and second is not None
    assert first.recall is not None and second.recall is not None
    assert first.recall is not second.recall
    scopes = tuple(
        found.recall.retriever.scope.team_node_id  # type: ignore[union-attr]
        for found in (first, second)
    )
    assert scopes == (PAYMENTS, PLATFORM), (
        f"one run's recall path is scoped to {scopes}. A retriever scoped to one "
        f"team and read by a run investigating another is a search with the wrong "
        f"team in it."
    )


async def test_an_empty_corpus_is_a_search_that_ran(monkeypatch: pytest.MonkeyPatch) -> None:
    """The line the whole composition rests on, over the real store.

    A team that has never written an episode has no vector namespace at all.
    That has to come back as a *successful* empty search — "this failure is new
    to the team" — and never as an unavailability, which is what every
    deployment's first weeks would otherwise report.
    """
    store = FakePersistence()
    await _tree(store)
    state = _state(store)
    compose_memory(state, org_id=ORG)

    memory = await _composed(state, _start(PAYMENTS))
    assert memory is not None and memory.recall is not None

    result = await memory.recall.search(RecallQuery(text="OOMKilled on payments-api"))

    assert result.searched, (
        "an empty corpus reported that the search did not run. The agent would be "
        "told there was nowhere to look when the truth is that nothing has happened yet."
    )
    assert result.empty


async def test_a_deployment_whose_runner_takes_no_sources_composes_nothing() -> None:
    """A stand-in runner is still a working deployment, and still binds nothing."""
    store = FakePersistence()
    await _tree(store)
    state = GatewayState(
        gateway=store,
        tokens=TokenService(gateway=store),
        investigator=object(),  # type: ignore[arg-type]
    )

    assert not compose_memory(state, org_id=ORG)


# -- the joint -----------------------------------------------------------------


def test_the_boot_composes_memory() -> None:
    """A composition nothing calls is the state this deployment was already in."""
    from gateway.http import lifespan

    assert "compose_memory" in inspect.getsource(lifespan)
