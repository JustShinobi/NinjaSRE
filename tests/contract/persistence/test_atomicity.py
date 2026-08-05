"""Contract: the four-way write commits together or not at all (SC-001).

Acceptance scenario 2 is the reason this package has a unit of work rather than
twelve independently-obtained repositories. An investigation finishing writes its
trace, its episode, that episode's embedding, and the topology edges it
discovered. Three of those landing is worse than none: the corpus would hold an
episode whose evidence does not exist, and every later similarity search would
return it.
"""

from __future__ import annotations

import pytest
from conftest import EPOCH, at

from config.constants.persistence import EPISODE_VECTOR_NAMESPACE
from platform.persistence.ports import (
    AgentRun,
    Episode,
    EvidenceRecord,
    PersistenceGateway,
    TenantScope,
    TopologyEdge,
    UnitOfWork,
    VectorRecord,
)

pytestmark = pytest.mark.contract


class InducedFailure(RuntimeError):
    """Raised inside a unit of work to make it roll back."""


async def write_the_conclusion(uow: UnitOfWork) -> None:
    """Write a trace, an episode, its embedding, and its topology edges."""
    await uow.run_traces.start_run(AgentRun(run_id="run-1", trigger="alert", started_at=EPOCH))
    await uow.run_traces.record_evidence(
        EvidenceRecord(
            evidence_id="e-1",
            run_id="run-1",
            source="prometheus",
            evidence_type="metric",
            observed_at=at(1),
        )
    )
    await uow.episodes.save(
        Episode(
            episode_id="ep-1",
            title="Checkout 5xx",
            summary="Pool exhaustion under a retry storm.",
            signature="checkout-5xx",
            run_id="run-1",
            occurred_at=EPOCH,
            components=("checkout",),
        )
    )
    await uow.vectors.ensure(EPISODE_VECTOR_NAMESPACE, model="m", dimension=2)
    await uow.vectors.upsert(
        EPISODE_VECTOR_NAMESPACE, [VectorRecord(vector_id="ep-1", embedding=(1.0, 0.0))]
    )
    await uow.topology.upsert_edge(TopologyEdge(from_node_id="web", to_node_id="checkout"))


async def assert_nothing_landed(gateway: PersistenceGateway, scope: TenantScope) -> None:
    """Assert that none of the four writes is visible."""
    async with gateway.begin(scope) as uow:
        assert await uow.run_traces.get_run("run-1") is None
        assert await uow.episodes.get("ep-1") is None
        assert await uow.vectors.describe(EPISODE_VECTOR_NAMESPACE) is None
        assert (await uow.topology.direct_dependents("checkout")).nodes == ()


async def test_all_four_commit_together(gateway: PersistenceGateway, scope: TenantScope) -> None:
    async with gateway.begin(scope) as uow:
        await write_the_conclusion(uow)

    async with gateway.begin(scope) as uow:
        assert await uow.run_traces.get_run("run-1") is not None
        assert await uow.episodes.get("ep-1") is not None
        assert await uow.vectors.count(EPISODE_VECTOR_NAMESPACE) == 1
        assert [n.node_id for n in (await uow.topology.direct_dependents("checkout")).nodes] == [
            "web"
        ]


async def test_an_induced_failure_rolls_all_four_back(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """SC-001's second half, and the half a fake could fake."""
    with pytest.raises(InducedFailure):
        async with gateway.begin(scope) as uow:
            await write_the_conclusion(uow)
            raise InducedFailure("the process died between the third write and the fourth")

    await assert_nothing_landed(gateway, scope)


async def test_a_unit_can_abandon_itself_without_raising(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # "Nothing to do after all" is a normal outcome, not an error, and a caller
    # should not have to raise through its own call stack to express it.
    async with gateway.begin(scope) as uow:
        await write_the_conclusion(uow)
        uow.mark_rollback_only()
        assert uow.is_rollback_only is True

    await assert_nothing_landed(gateway, scope)


async def test_a_unit_reads_its_own_uncommitted_writes(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # Otherwise composing four writes would mean the second could not depend on
    # the first, and record_evidence could not check that its run exists.
    async with gateway.begin(scope) as uow:
        await write_the_conclusion(uow)

        assert await uow.episodes.get("ep-1") is not None
        assert await uow.run_traces.get_run("run-1") is not None


async def test_a_failed_unit_leaves_earlier_committed_work_alone(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # Rollback undoes the unit, not the history.
    async with gateway.begin(scope) as uow:
        await uow.run_traces.start_run(
            AgentRun(run_id="run-earlier", trigger="alert", started_at=EPOCH)
        )

    with pytest.raises(InducedFailure):
        async with gateway.begin(scope) as uow:
            await write_the_conclusion(uow)
            raise InducedFailure("boom")

    async with gateway.begin(scope) as uow:
        assert await uow.run_traces.get_run("run-earlier") is not None
        assert await uow.run_traces.get_run("run-1") is None


async def test_a_rolled_back_unit_does_not_lose_another_tenants_work(
    gateway: PersistenceGateway, scope: TenantScope, other_scope: TenantScope
) -> None:
    # A snapshot-and-swap implementation is the obvious way to get transactions
    # in memory, and the obvious way to get it wrong is to discard writes that
    # were never part of the failed unit.
    async with gateway.begin(other_scope) as uow:
        await uow.run_traces.start_run(
            AgentRun(run_id="run-elsewhere", trigger="alert", started_at=EPOCH)
        )

    with pytest.raises(InducedFailure):
        async with gateway.begin(scope) as uow:
            await write_the_conclusion(uow)
            raise InducedFailure("boom")

    async with gateway.begin(other_scope) as uow:
        assert await uow.run_traces.get_run("run-elsewhere") is not None


async def test_the_system_unit_of_work_is_transactional_too(
    gateway: PersistenceGateway,
) -> None:
    with pytest.raises(InducedFailure):
        async with gateway.begin_system() as system:
            await system.orgs.create_organisation("initech", "Initech")
            raise InducedFailure("boom")

    async with gateway.begin_system() as system:
        assert await system.orgs.get_organisation("initech") is None
