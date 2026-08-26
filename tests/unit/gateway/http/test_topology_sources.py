"""Which graph an investigation traverses, decided per run and by the team's switch.

The topology capability reads a binding, and until this composition existed
nothing in the serving deployment ever set one. Every investigation that called
``query_service_topology`` got the same sentence back — the graph is not
configured — which is the honest answer to "nobody composed a source" and a
useless one to have on every run.

Three properties, and each is the difference between two answers an operator
would act on differently.

**A team that switched topology off is left unbound**, not bound over. The
capability is then absent from that run's catalogue rather than offered and
refusing, which is a tool slot and a model call that a switched-off store should
not cost. Binding a policy-disabled query path would spend both to arrive at the
same "no".

**A graph this deployment cannot reach is not bound over either.** An
unreachable graph and an unconfigured one are the same thing from the agent's
side — there is nowhere to look — and the run should not be offered a traversal
that cannot run.

**A bound source over an empty graph answers.** That is the whole point of
composing the read at all: "the graph holds nothing about checkout" is a finding
the investigation continues past, and "the graph is not configured" is not a
statement about checkout. Composing the read without the graph being populated
would turn the second into the first, so the pair is asserted together here.

The graph's tenancy is the *organisation* — Apache AGE has one graph per
database and every node id is prefixed with the org, which is what makes a
traversal unable to leave its tenant. So two runs traversing separate graphs is
asserted across organisations, where the boundary actually is, and the team is
what decides the switch and travels on the scope.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import pytest

from capabilities.tools.system.topology_query import binding as topology_binding
from capabilities.tools.system.topology_query.tool import query_service_topology
from config.prompts.knowledge import TOPOLOGY_EMPTY, TOPOLOGY_UNCONFIGURED
from core.capability.result import CapabilityErrorClass
from gateway.http.services import InvestigationStart
from gateway.http.state import GatewayState
from gateway.http.topology_sources import compose_topology_sources, topology_source_for
from platform.config_service.service import ConfigService
from platform.knowledge.topology.queries import TopologyQueries
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import TenantScope
from platform.persistence.ports.topology_graph import (
    EdgeKind,
    NodeKind,
    TopologyEdge,
    TopologyNode,
)

pytestmark = pytest.mark.unit

ORG = "acme"
OTHER_ORG = "globex"
PAYMENTS = f"{ORG}/payments"
SEARCH = f"{ORG}/search"
OTHER_TEAM = f"{OTHER_ORG}/payments"


@dataclass
class SpyRunner:
    """A runner that records what a composition root attached to it.

    The seam's own half — binding a factory's answer around one run and putting
    it back — is the runner's and has its own suite. What is asserted here is
    that this composition reaches that seam, by the keyword it takes.
    """

    attached: dict[str, Any] = field(default_factory=dict)

    def attach_sources(self, *, recall: Any = None, topology: Any = None) -> None:
        """Record the factories, the way the real runner merges them."""
        if recall is not None:
            self.attached["recall"] = recall
        if topology is not None:
            self.attached["topology"] = topology


def state_over(store: FakePersistence, investigator: Any = None) -> GatewayState:
    """Return a gateway state with only what this suite reads wired."""
    return GatewayState(
        gateway=store,
        tokens=None,  # type: ignore[arg-type]
        investigator=investigator,  # type: ignore[arg-type]
    )


def start(run_id: str, *, org_id: str = ORG, team_node_id: str = PAYMENTS) -> InvestigationStart:
    """Return one investigation, as the API would state it."""
    return InvestigationStart(
        run_id=run_id,
        objective="checkout is timing out",
        team_node_id=team_node_id,
        principal_id="ada",
        org_id=org_id,
    )


async def organisation(store: FakePersistence, org_id: str, name: str) -> None:
    """Create ``org_id`` and the configuration root that comes with it."""
    async with store.begin_system() as system:
        await system.orgs.create_organisation(org_id, name)


async def team(
    store: FakePersistence, node_id: str, *, org_id: str = ORG, topology: bool = True
) -> None:
    """Create a team node under ``org_id`` carrying its own topology switch."""
    service = ConfigService(gateway=store, scope=TenantScope(org_id=org_id))
    await service.create_node(node_id, name=node_id.rsplit("/", 1)[-1], parent_id=org_id)
    await service.set_settings(
        node_id,
        {"policies": {"knowledge": {"topology_enabled": topology}}},
        actor_id="ada",
    )


async def record_dependency(
    store: FakePersistence, org_id: str, *, service: str, dependent: str
) -> None:
    """Write ``dependent`` depends on ``service`` into ``org_id``'s graph."""
    async with store.begin(TenantScope(org_id=org_id)) as uow:
        for node_id in (service, dependent):
            await uow.topology.upsert_node(
                TopologyNode(node_id=node_id, kind=NodeKind.SERVICE, name=node_id)
            )
        await uow.topology.upsert_edge(
            TopologyEdge(from_node_id=dependent, to_node_id=service, kind=EdgeKind.DEPENDS_ON)
        )


# --- What gets composed, and what deliberately does not -----------------------


async def test_a_team_with_topology_enabled_gets_a_source_scoped_to_it() -> None:
    store = FakePersistence()
    try:
        await organisation(store, ORG, "Acme")
        await team(store, PAYMENTS)
        source = await topology_source_for(state_over(store), start("run-1"), org_id=ORG)
    finally:
        await store.close()

    assert isinstance(source, TopologyQueries)
    assert source.scope == TenantScope(org_id=ORG, team_node_id=PAYMENTS)
    assert source.policy.topology_enabled


async def test_a_team_that_switched_topology_off_is_left_unbound() -> None:
    """The unbound behaviour, not an empty answer: the capability is not offered."""
    store = FakePersistence()
    try:
        await organisation(store, ORG, "Acme")
        await team(store, SEARCH, topology=False)
        source = await topology_source_for(
            state_over(store), start("run-2", team_node_id=SEARCH), org_id=ORG
        )
    finally:
        await store.close()

    assert source is None


async def test_one_teams_switch_does_not_decide_its_siblings() -> None:
    store = FakePersistence()
    try:
        await organisation(store, ORG, "Acme")
        await team(store, PAYMENTS)
        await team(store, SEARCH, topology=False)
        state = state_over(store)
        enabled = await topology_source_for(state, start("run-3"), org_id=ORG)
        disabled = await topology_source_for(state, start("run-4", team_node_id=SEARCH), org_id=ORG)
    finally:
        await store.close()

    assert enabled is not None
    assert disabled is None


async def test_a_graph_this_deployment_cannot_reach_is_not_bound_over() -> None:
    """Nowhere to look is nowhere to look; offering the traversal spends a turn."""
    store = FakePersistence(topology_available=False)
    try:
        await organisation(store, ORG, "Acme")
        await team(store, PAYMENTS)
        source = await topology_source_for(state_over(store), start("run-5"), org_id=ORG)
    finally:
        await store.close()

    assert source is None


async def test_a_run_that_names_no_organisation_binds_nothing() -> None:
    """A scope invented here would be one traversal from another tenant's graph."""
    store = FakePersistence()
    try:
        await organisation(store, ORG, "Acme")
        await team(store, PAYMENTS)
        source = await topology_source_for(state_over(store), start("run-6", org_id=""), org_id="")
    finally:
        await store.close()

    assert source is None


# --- One run's graph, and only that run's -------------------------------------


async def test_two_concurrent_runs_traverse_their_own_organisations_graph() -> None:
    """Both bound at once, on purpose: the failure being excluded needs the overlap."""
    store = FakePersistence()
    barrier = asyncio.Barrier(2)

    async def traverse(org_id: str, team_node_id: str) -> tuple[str, ...]:
        source = await topology_source_for(
            state_over(store),
            start(f"run-{org_id}", org_id=org_id, team_node_id=team_node_id),
            org_id=org_id,
        )
        assert source is not None
        previous = topology_binding.bind(source)
        try:
            # Both runs hold a binding from here until both have read, which is
            # the window a process-wide binding would collapse into one graph.
            await barrier.wait()
            bound = topology_binding.current()
            assert bound is not None
            answer = await bound.query("checkout")
            return answer.dependents.names()
        finally:
            topology_binding.restore(previous)

    try:
        await organisation(store, ORG, "Acme")
        await organisation(store, OTHER_ORG, "Globex")
        await team(store, PAYMENTS)
        await team(store, OTHER_TEAM, org_id=OTHER_ORG)
        await record_dependency(store, ORG, service="checkout", dependent="acme-web")
        await record_dependency(store, OTHER_ORG, service="checkout", dependent="globex-web")

        acme, globex = await asyncio.gather(
            traverse(ORG, PAYMENTS),
            traverse(OTHER_ORG, OTHER_TEAM),
        )
    finally:
        await store.close()

    assert acme == ("acme-web",)
    assert globex == ("globex-web",)


async def test_a_run_leaves_the_binding_as_it_found_it() -> None:
    """Nothing is bound after either run: the next one composes its own or has none."""
    store = FakePersistence()
    try:
        await organisation(store, ORG, "Acme")
        await team(store, PAYMENTS)
        source = await topology_source_for(state_over(store), start("run-7"), org_id=ORG)
        previous = topology_binding.bind(source)
        topology_binding.restore(previous)
    finally:
        await store.close()

    assert topology_binding.current() is None


# --- Empty is not unavailable -------------------------------------------------


async def test_an_empty_graph_answers_and_no_graph_at_all_refuses() -> None:
    """The pair the tool exists to keep apart, over a real composed source."""
    store = FakePersistence()
    try:
        await organisation(store, ORG, "Acme")
        await team(store, PAYMENTS)
        source = await topology_source_for(state_over(store), start("run-8"), org_id=ORG)
        assert source is not None

        previous = topology_binding.bind(source)
        try:
            answered = await query_service_topology("checkout")
        finally:
            topology_binding.restore(previous)

        previous = topology_binding.bind(None)
        try:
            refused = await query_service_topology("checkout")
        finally:
            topology_binding.restore(previous)
    finally:
        await store.close()

    assert answered.succeeded
    assert answered.value["text"] == TOPOLOGY_EMPTY.format(service="checkout")

    assert not refused.succeeded
    assert refused.error is not None
    assert refused.error.classification is CapabilityErrorClass.UNAVAILABLE
    assert refused.error.message == TOPOLOGY_UNCONFIGURED


# --- Reaching the runner ------------------------------------------------------


async def test_the_composed_factory_reaches_the_runner_through_the_seam() -> None:
    store = FakePersistence()
    runner = SpyRunner()
    try:
        await organisation(store, ORG, "Acme")
        await team(store, PAYMENTS)
        compose_topology_sources(state_over(store, runner), org_id=ORG)

        assert "topology" in runner.attached
        built = await runner.attached["topology"](start("run-9"))
    finally:
        await store.close()

    assert isinstance(built, TopologyQueries)
    assert built.scope == TenantScope(org_id=ORG, team_node_id=PAYMENTS)


async def test_a_deployment_with_no_runner_composes_nothing_and_does_not_fail() -> None:
    """A process with no investigation runtime is a state, not an error."""
    store = FakePersistence()
    try:
        compose_topology_sources(state_over(store, object()), org_id=ORG)
    finally:
        await store.close()
