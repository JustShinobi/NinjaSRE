"""What the closed loop tells the gate before it acts without a human.

Three facts the deployment learned by acting, and one shared consequence: the
action goes to a person instead of running. That the consequence is a downgrade
rather than a refusal is the assertion worth reading twice — a suspended
resource is exactly the one somebody has to be able to fix, and a gate that
refused outright would have made the safe state unfixable.

The last test is the one FR-006 is about. Whether an action nobody can verify
may run unattended is not a default here: it is read off the deployment's
autonomy policy, and both answers are exercised.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.capability.metadata import SideEffectLevel
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import TenantScope
from platform.persistence.ports.remediation_ledger import RecurringProblem
from platform.remediation.components import ComponentRegistry, RemediationComponents
from platform.remediation.declaration import (
    SignalDirection,
    VerificationDeclaration,
    VerificationSignal,
)
from platform.remediation.guards import ClosedLoopGuards, Guard
from platform.remediation.models import RemediationAction, RemediationTarget
from platform.remediation.suspension import AutonomySuspensions

pytestmark = pytest.mark.unit

EPOCH = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def at(seconds: float = 0.0) -> datetime:
    """Return a fixed instant offset by ``seconds``."""
    return EPOCH + timedelta(seconds=seconds)


class NoComponent:
    """A stand-in for the four components a guard never calls."""


def a_registry() -> ComponentRegistry:
    """Return a registry with one verifiable capability and one that is not."""
    component = NoComponent()
    return ComponentRegistry().register_all(
        (
            RemediationComponents(
                capability="scale_workload",
                reader=component,  # type: ignore[arg-type]
                applier=component,  # type: ignore[arg-type]
                generator=component,  # type: ignore[arg-type]
                verifier=component,  # type: ignore[arg-type]
                verification=VerificationDeclaration(
                    signals=(
                        VerificationSignal(
                            name="workload.ready_replicas", direction=SignalDirection.UP
                        ),
                    ),
                    settle_seconds=300,
                ),
            ),
            RemediationComponents(
                capability="toggle_feature_flag",
                reader=component,  # type: ignore[arg-type]
                applier=component,  # type: ignore[arg-type]
                generator=component,  # type: ignore[arg-type]
                verifier=component,  # type: ignore[arg-type]
                verification=VerificationDeclaration.unverifiable(
                    "a flag's effect appears in whatever the flag guards"
                ),
            ),
        )
    )


def an_action(*, capability: str = "scale_workload") -> RemediationAction:
    """Return an action against ``checkout-api``."""
    return RemediationAction(
        action_id="action-1",
        capability=capability,
        target=RemediationTarget(identifier="checkout-api", environment="production"),
        side_effect_level=SideEffectLevel.WRITE_REVERSIBLE,
        requester="agent",
        team_node_id="team-payments",
    )


@pytest.fixture
async def storage() -> FakePersistence:
    """Return an in-memory store with one organisation."""
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation("acme", "Acme Corp")
    return store


def guards_over(storage: FakePersistence, *, allow_unverifiable: bool = False) -> ClosedLoopGuards:
    """Return the guards over one deployment's storage."""
    return ClosedLoopGuards(
        gateway=storage,
        scope=TenantScope(org_id="acme"),
        registry=a_registry(),
        allow_unverifiable=allow_unverifiable,
    )


async def test_nothing_the_loop_knows_permits_an_ordinary_action(
    storage: FakePersistence,
) -> None:
    """The ordinary path must be silent, or the guards become the reason for everything."""
    assert (await guards_over(storage).check(an_action())) == Guard()


async def test_a_suspended_resource_sends_the_action_to_a_human(
    storage: FakePersistence,
) -> None:
    """SC-004's other half: autonomy stops there, and only there."""
    async with storage.begin(TenantScope(org_id="acme")) as unit:
        await AutonomySuspensions(audit=unit.audit, clock=lambda: at()).suspend(
            "checkout-api",
            reason="scale_workload made things worse and the rollback failed.",
            action_id="action-0",
        )

    guard = await guards_over(storage).check(an_action())

    assert not guard.permitted
    assert "suspended" in guard.reason
    assert "rollback failed" in guard.reason


async def test_clearing_the_suspension_lets_the_deployment_act_again(
    storage: FakePersistence,
) -> None:
    """T-017: autonomy resumes only after a person clears it, and then it does."""
    async with storage.begin(TenantScope(org_id="acme")) as unit:
        suspensions = AutonomySuspensions(audit=unit.audit, clock=lambda: at())
        await suspensions.suspend("checkout-api", reason="the rollback failed")

    assert not (await guards_over(storage).check(an_action())).permitted

    async with storage.begin(TenantScope(org_id="acme")) as unit:
        await AutonomySuspensions(audit=unit.audit, clock=lambda: at(3600)).clear(
            "checkout-api", principal_id="ada", reason="restored by hand and healthy"
        )

    assert (await guards_over(storage).check(an_action())).permitted


async def test_a_live_recurring_problem_suppresses_autonomous_repetition(
    storage: FakePersistence,
) -> None:
    """FR-019: the pattern is raised, so repeating it is not the answer."""
    problem = RecurringProblem(
        problem_id="problem-1",
        pattern_key="scale_workload@checkout-api",
        capability="scale_workload",
        resource_id="checkout-api",
        title="scale_workload keeps being applied to checkout-api",
        summary="Four applications in thirty days.",
        raised_at=at(),
        occurrences=4,
        window_seconds=2_592_000,
    )
    async with storage.begin(TenantScope(org_id="acme")) as unit:
        await unit.remediation.upsert_problem(problem)

    guard = await guards_over(storage).check(an_action())

    assert not guard.permitted
    assert "recurring problem" in guard.reason
    assert "problem-1" in guard.reason


async def test_closing_the_problem_lifts_the_suppression(storage: FakePersistence) -> None:
    """FR-019: the suppression is clearable, and closing it is what clears it."""
    from dataclasses import replace

    problem = RecurringProblem(
        problem_id="problem-1",
        pattern_key="scale_workload@checkout-api",
        capability="scale_workload",
        resource_id="checkout-api",
        title="scale_workload keeps being applied to checkout-api",
        summary="Four applications in thirty days.",
        raised_at=at(),
        occurrences=4,
        window_seconds=2_592_000,
    )
    async with storage.begin(TenantScope(org_id="acme")) as unit:
        await unit.remediation.upsert_problem(problem)
    async with storage.begin(TenantScope(org_id="acme")) as unit:
        await unit.remediation.upsert_problem(
            replace(problem, closed_at=at(7200), close_reason="raised the replica floor")
        )

    assert (await guards_over(storage).check(an_action())).permitted


async def test_an_unverifiable_action_needs_a_human_unless_policy_says_otherwise(
    storage: FakePersistence,
) -> None:
    """FR-006: it is a policy decision, and the shipped default is the strict one."""
    action = an_action(capability="toggle_feature_flag")

    refused = await guards_over(storage).check(action)
    permitted = await guards_over(storage, allow_unverifiable=True).check(action)

    assert not refused.permitted
    assert "declares no signal" in refused.reason
    assert "has not decided" in refused.reason
    assert permitted.permitted


async def test_a_guard_that_refuses_without_a_reason_is_unrepresentable() -> None:
    """An unexplained downgrade leaves a reviewer with nothing to review."""
    with pytest.raises(ValueError, match="must say why"):
        Guard(permitted=False)
