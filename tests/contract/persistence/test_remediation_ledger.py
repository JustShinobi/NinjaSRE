"""Contract: what a remediation did, whether it worked, and the patterns in that.

Five things a backend must never get wrong, and each one is a way the closed
loop stops being closed.

``claim_due`` hands one obligation to one worker. Two replicas asking at the
same instant divide the due obligations between them and never both receive
one, because two verifications of one action would read the same signals, reach
the same verdict, and roll the same change back twice.

An obligation survives the process that created it. That is the whole of
FR-003: verification is a durable row with a due time, not an in-process wait,
and a deployment restarted between the action and the check still checks.

``effectiveness`` aggregates without paging. "Has this worked here before" is
asked on the path of a proposal and answered over a year of history, and a
count assembled from pages would be a count of the first page.

A recurring problem is looked up by its pattern and only while it is live, for
the reason correlation looks up an incident that way: a pattern raised, dealt
with, and closed must not silently absorb next quarter's recurrence.

One tenant's ledger is invisible from another.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from conftest import at

from config.constants.closed_loop import MAX_EFFECTIVENESS_PAGE_SIZE
from platform.persistence.errors import BoundExceeded
from platform.persistence.ports import (
    EffectivenessQuery,
    PersistenceGateway,
    RecurringProblem,
    RemediationOutcome,
    TenantScope,
    VerificationState,
    VerificationVerdict,
)

pytestmark = pytest.mark.contract


def outcome(
    *,
    action_id: str = "action-1",
    capability: str = "clear_cache",
    resource_id: str = "store-cove",
    condition_key: str = "datastore-near-full",
    minutes: float = 0.0,
    due: float = 5.0,
    state: VerificationState = VerificationState.AWAITING,
    verdict: VerificationVerdict | None = None,
) -> RemediationOutcome:
    """Return one ledger row as the executor would write it."""
    return RemediationOutcome(
        action_id=action_id,
        capability=capability,
        resource_id=resource_id,
        condition_key=condition_key,
        team_node_id="team-payments",
        executed_at=at(minutes),
        due_at=at(due),
        settle_seconds=300,
        state=state,
        verdict=verdict,
        signal_names=("filesystem.used_percent",),
        before={"filesystem.used_percent": 95.65},
        autonomous=True,
        incident_id="incident-1",
    )


async def test_an_obligation_written_now_is_readable_after_the_process_that_wrote_it(
    gateway: PersistenceGateway,
    scope: TenantScope,
) -> None:
    """FR-003: the obligation is a row, so nothing about it lives in a process."""
    async with gateway.begin(scope) as unit:
        await unit.remediation.record(outcome())

    async with gateway.begin(scope) as unit:
        found = await unit.remediation.get("action-1")

    assert found is not None
    assert found.state is VerificationState.AWAITING
    assert found.due_at == at(5.0)
    assert found.before["filesystem.used_percent"] == pytest.approx(95.65)


async def test_two_workers_asking_at_once_divide_the_due_obligations(
    gateway: PersistenceGateway,
    scope: TenantScope,
) -> None:
    """NFR-001: claiming is atomic per obligation, or one action is verified twice."""
    async with gateway.begin(scope) as unit:
        await unit.remediation.record(outcome(action_id="action-1"))
        await unit.remediation.record(outcome(action_id="action-2"))

    async with gateway.begin(scope) as unit:
        first = await unit.remediation.claim_due(
            now=at(6.0), worker_id="worker-a", lease_seconds=60.0, limit=1
        )
        second = await unit.remediation.claim_due(
            now=at(6.0), worker_id="worker-b", lease_seconds=60.0, limit=10
        )

    claimed = {row.action_id for row in first} | {row.action_id for row in second}
    assert len(first) == 1
    assert claimed == {"action-1", "action-2"}
    assert not {row.action_id for row in first} & {row.action_id for row in second}


async def test_an_obligation_that_is_not_due_yet_is_not_claimed(
    gateway: PersistenceGateway,
    scope: TenantScope,
) -> None:
    """NFR-002: the settle period is the whole point, so a claim before it is a bug."""
    async with gateway.begin(scope) as unit:
        await unit.remediation.record(outcome())
        claimed = await unit.remediation.claim_due(
            now=at(1.0), worker_id="worker-a", lease_seconds=60.0
        )

    assert claimed == ()


async def test_a_lapsed_lease_makes_the_obligation_claimable_again(
    gateway: PersistenceGateway,
    scope: TenantScope,
) -> None:
    """A lease, not a lock: a worker that died must not hold an obligation forever."""
    async with gateway.begin(scope) as unit:
        await unit.remediation.record(outcome())
        await unit.remediation.claim_due(now=at(6.0), worker_id="worker-a", lease_seconds=60.0)

    async with gateway.begin(scope) as unit:
        again = await unit.remediation.claim_due(
            now=at(8.0), worker_id="worker-b", lease_seconds=60.0
        )

    assert [row.action_id for row in again] == ["action-1"]
    assert again[0].attempts == 2


async def test_a_verified_obligation_is_never_claimed_again(
    gateway: PersistenceGateway,
    scope: TenantScope,
) -> None:
    """A verdict is terminal. Re-verifying would compare against stale before values."""
    async with gateway.begin(scope) as unit:
        await unit.remediation.record(outcome())
        await unit.remediation.record(
            outcome(state=VerificationState.VERIFIED, verdict=VerificationVerdict.EFFECTIVE)
        )
        claimed = await unit.remediation.claim_due(
            now=at(60.0), worker_id="worker-a", lease_seconds=60.0
        )

    assert claimed == ()


async def test_effectiveness_counts_a_year_without_paging(
    gateway: PersistenceGateway,
    scope: TenantScope,
) -> None:
    """NFR-003: the aggregate is a count, not the first page of a listing."""
    async with gateway.begin(scope) as unit:
        for index in range(MAX_EFFECTIVENESS_PAGE_SIZE + 20):
            await unit.remediation.record(
                outcome(
                    action_id=f"action-{index}",
                    minutes=index,
                    state=VerificationState.VERIFIED,
                    verdict=(
                        VerificationVerdict.EFFECTIVE
                        if index % 2 == 0
                        else VerificationVerdict.INEFFECTIVE
                    ),
                )
            )

    async with gateway.begin(scope) as unit:
        summary = await unit.remediation.effectiveness(
            EffectivenessQuery(resource_ids=("store-cove",), capabilities=("clear_cache",))
        )

    assert summary.total == MAX_EFFECTIVENESS_PAGE_SIZE + 20
    assert summary.counts[VerificationVerdict.EFFECTIVE] == 60
    assert summary.counts[VerificationVerdict.INEFFECTIVE] == 60


async def test_effectiveness_is_sliced_by_resource_capability_and_condition(
    gateway: PersistenceGateway,
    scope: TenantScope,
) -> None:
    """FR-014: each dimension answers on its own, or history cannot be interrogated."""
    async with gateway.begin(scope) as unit:
        await unit.remediation.record(
            outcome(
                action_id="a",
                state=VerificationState.VERIFIED,
                verdict=VerificationVerdict.EFFECTIVE,
            )
        )
        await unit.remediation.record(
            outcome(
                action_id="b",
                resource_id="store-reef",
                state=VerificationState.VERIFIED,
                verdict=VerificationVerdict.INEFFECTIVE,
            )
        )
        await unit.remediation.record(
            outcome(
                action_id="c",
                capability="restart_workload",
                condition_key="pod-crashlooping",
                state=VerificationState.VERIFIED,
                verdict=VerificationVerdict.WORSENED,
            )
        )

        by_resource = await unit.remediation.effectiveness(
            EffectivenessQuery(resource_ids=("store-reef",))
        )
        by_capability = await unit.remediation.effectiveness(
            EffectivenessQuery(capabilities=("restart_workload",))
        )
        by_condition = await unit.remediation.effectiveness(
            EffectivenessQuery(condition_keys=("datastore-near-full",))
        )

    assert by_resource.total == 1
    assert by_capability.counts[VerificationVerdict.WORSENED] == 1
    assert by_condition.total == 2


async def test_a_listing_refuses_a_page_larger_than_the_bound(
    gateway: PersistenceGateway,
    scope: TenantScope,
) -> None:
    """Raising rather than clamping: a caller that asked for more must be told."""
    async with gateway.begin(scope) as unit:
        with pytest.raises(BoundExceeded):
            await unit.remediation.history(
                EffectivenessQuery(limit=MAX_EFFECTIVENESS_PAGE_SIZE + 1)
            )


async def test_a_recurring_problem_is_looked_up_by_pattern_while_it_is_live(
    gateway: PersistenceGateway,
    scope: TenantScope,
) -> None:
    """FR-017: the fifth occurrence lands on the live problem, not on a closed one."""
    problem = RecurringProblem(
        problem_id="problem-1",
        pattern_key="clear_cache@store-cove",
        capability="clear_cache",
        resource_id="store-cove",
        title="clear_cache keeps being applied to store-cove",
        summary="Four applications in thirty days.",
        raised_at=at(0.0),
        occurrences=4,
        window_seconds=2_592_000,
        action_ids=("action-1", "action-2", "action-3", "action-4"),
    )
    async with gateway.begin(scope) as unit:
        await unit.remediation.upsert_problem(problem)
        live = await unit.remediation.open_problem_for("clear_cache@store-cove")

    assert live is not None
    assert live.occurrences == 4

    async with gateway.begin(scope) as unit:
        await unit.remediation.upsert_problem(
            replace(problem, closed_at=at(10.0), close_reason="log rotation added")
        )
        gone = await unit.remediation.open_problem_for("clear_cache@store-cove")
        listed = await unit.remediation.problems(live_only=False)

    assert gone is None
    assert [item.problem_id for item in listed] == ["problem-1"]


async def test_one_tenant_never_sees_another_tenants_ledger(
    gateway: PersistenceGateway,
    scope: TenantScope,
    other_scope: TenantScope,
) -> None:
    """A remediation history is a record of what happened inside one organisation."""
    async with gateway.begin(scope) as unit:
        await unit.remediation.record(outcome())

    async with gateway.begin(other_scope) as unit:
        assert await unit.remediation.get("action-1") is None
        assert await unit.remediation.history(EffectivenessQuery()) == ()
