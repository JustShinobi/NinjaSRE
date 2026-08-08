"""Verification is a row with a due time, and everything that follows from that.

The property this file exists for is SC-005: a deployment restarted between the
action and the check still checks. It is proven the only way that means
anything — by building the obligation through one object graph, discarding every
object, and settling it through a second one built over the same storage. A test
that reused the service would prove the service remembers, which is not the
claim.

The rest are the honesty properties. A signal that did not move enough is
``inconclusive`` end to end and not only in the comparison; a resource that went
absent is ``inconclusive`` rather than ``effective``; a settle period longer than
a run's wall-clock ceiling is fine, because nothing waits.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from config.constants.closed_loop import MAX_VERIFICATION_ATTEMPTS
from config.constants.investigation import RUN_WALL_CLOCK_SECONDS
from core.capability.metadata import SideEffectLevel
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import TenantScope
from platform.persistence.ports.remediation_ledger import (
    EffectivenessQuery,
    RemediationLedger,
    VerificationState,
    VerificationVerdict,
)
from platform.persistence.ports.signal_store import Signal, SignalKind, signal_key
from platform.remediation.components import ComponentRegistry, RemediationComponents
from platform.remediation.declaration import (
    SignalDirection,
    VerificationDeclaration,
    VerificationSignal,
)
from platform.remediation.models import RemediationAction, RemediationTarget
from platform.remediation.obligations import VerificationObligations

pytestmark = pytest.mark.unit

EPOCH = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
SETTLE = 300
CLEARS_AT = 80.0


def at(seconds: float = 0.0) -> datetime:
    """Return a fixed instant offset by ``seconds``."""
    return EPOCH + timedelta(seconds=seconds)


@dataclass(slots=True)
class SignalHistory:
    """The narrow readback the verification needs, over a list of samples."""

    samples: list[Signal] = field(default_factory=list)

    def record(self, name: str, resource_id: str, value: float, *, when: datetime) -> None:
        """Append one numeric sample."""
        self.samples.append(
            Signal(
                signal_id=signal_key(name, resource_id, when),
                name=name,
                resource_id=resource_id,
                source="poller:test",
                kind=SignalKind.NUMBER,
                observed_at=when,
                value=value,
                interval_seconds=60,
            )
        )

    async def latest(
        self,
        *,
        names: tuple[str, ...] = (),
        resource_ids: tuple[str, ...] = (),
    ) -> tuple[Signal, ...]:
        """Return the newest sample per ``(name, resource)``, however old it is."""
        newest: dict[tuple[str, str], Signal] = {}
        for sample in self.samples:
            if names and sample.name not in names:
                continue
            if resource_ids and sample.resource_id not in resource_ids:
                continue
            key = (sample.name, sample.resource_id)
            if key not in newest or sample.observed_at > newest[key].observed_at:
                newest[key] = sample
        return tuple(newest[key] for key in sorted(newest))


class NoComponent:
    """A stand-in for the four components verification never calls."""


def a_registry(declaration: VerificationDeclaration) -> ComponentRegistry:
    """Return a registry whose one capability declares ``declaration``."""
    component = NoComponent()
    return ComponentRegistry().register(
        RemediationComponents(
            capability="clear_cache",
            reader=component,  # type: ignore[arg-type]
            applier=component,  # type: ignore[arg-type]
            generator=component,  # type: ignore[arg-type]
            verifier=component,  # type: ignore[arg-type]
            verification=declaration,
        )
    )


def a_declaration(*, settle_seconds: int = SETTLE, clears_at: float | None = CLEARS_AT):
    """Return the declaration a filesystem-clearing capability makes."""
    return VerificationDeclaration(
        signals=(
            VerificationSignal(
                name="filesystem.used_percent",
                direction=SignalDirection.DOWN,
                clears_at=clears_at,
            ),
        ),
        settle_seconds=settle_seconds,
    )


def an_action(*, action_id: str = "action-1") -> RemediationAction:
    """Return the action a filesystem-clearing remediation proposes."""
    return RemediationAction(
        action_id=action_id,
        capability="clear_cache",
        target=RemediationTarget(identifier="store-cove", environment="production"),
        side_effect_level=SideEffectLevel.WRITE_REVERSIBLE,
        requester="agent",
        run_id="run-1",
        team_node_id="team-payments",
    )


@pytest.fixture
def signals() -> SignalHistory:
    """Return an empty signal history."""
    return SignalHistory()


@pytest.fixture
async def storage() -> FakePersistence:
    """Return an in-memory store with one organisation."""
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation("acme", "Acme Corp")
    return store


def obligations(
    storage_ledger: RemediationLedger,
    signals: SignalHistory,
    declaration: VerificationDeclaration,
) -> VerificationObligations:
    """Return the obligations service over one ledger and one signal history."""
    return VerificationObligations(
        ledger=storage_ledger,
        signals=signals,
        registry=a_registry(declaration),
        clock=lambda: at(0.0),
    )


async def test_the_before_values_are_captured_from_the_signals_as_they_stand(
    storage: FakePersistence,
    signals: SignalHistory,
) -> None:
    """T-006: read before the change, because a window read after contains it."""
    signals.record("filesystem.used_percent", "store-cove", 95.65, when=at(-60))

    async with storage.begin(TenantScope(org_id="acme")) as unit:
        service = obligations(unit.remediation, signals, a_declaration())
        before = await service.capture(an_action())

    assert before == {"filesystem.used_percent": pytest.approx(95.65)}


async def test_the_run_ends_without_waiting_and_the_obligation_carries_the_due_time(
    storage: FakePersistence,
    signals: SignalHistory,
) -> None:
    """T-007 and NFR-002: the settle period is a due time, not a sleep."""
    async with storage.begin(TenantScope(org_id="acme")) as unit:
        service = obligations(unit.remediation, signals, a_declaration())
        owed = await service.owe(
            an_action(),
            before={"filesystem.used_percent": 95.65},
            executed_at=at(0),
        )

    assert owed.state is VerificationState.AWAITING
    assert owed.awaiting_verification
    assert owed.due_at == at(SETTLE)
    assert owed.verdict is None


async def test_a_settle_period_longer_than_a_runs_wall_clock_ceiling_is_fine(
    storage: FakePersistence,
    signals: SignalHistory,
) -> None:
    """T-013: nothing holds the run open, so the ceiling is not a bound on this."""
    settle = int(RUN_WALL_CLOCK_SECONDS) + 600
    declaration = a_declaration(settle_seconds=settle)

    async with storage.begin(TenantScope(org_id="acme")) as unit:
        service = obligations(unit.remediation, signals, declaration)
        owed = await service.owe(
            an_action(), before={"filesystem.used_percent": 95.65}, executed_at=at(0)
        )

    assert owed.settle_seconds > RUN_WALL_CLOCK_SECONDS
    assert owed.due_at == at(settle)


async def test_verification_survives_the_process_that_owed_it(
    storage: FakePersistence,
    signals: SignalHistory,
) -> None:
    """SC-005 and T-009, with a real restart: nothing in memory carries over.

    The obligation is written through one object graph. Every object in it is
    then discarded — the service, the registry, the ledger handle — and a second
    graph is built over the same storage, exactly as a restarted replica would.
    """
    signals.record("filesystem.used_percent", "store-cove", 95.65, when=at(-60))

    async with storage.begin(TenantScope(org_id="acme")) as unit:
        before_restart = obligations(unit.remediation, signals, a_declaration())
        before = await before_restart.capture(an_action())
        await before_restart.owe(an_action(), before=before, executed_at=at(0))

    del before_restart

    signals.record("filesystem.used_percent", "store-cove", 61.0, when=at(SETTLE))

    async with storage.begin(TenantScope(org_id="acme")) as unit:
        after_restart = VerificationObligations(
            ledger=unit.remediation,
            signals=signals,
            registry=a_registry(a_declaration()),
            clock=lambda: at(SETTLE + 1),
        )
        claimed = await after_restart.claim(worker_id="worker-b")
        assert [row.action_id for row in claimed] == ["action-1"]
        verification = await after_restart.settle(claimed[0])

    assert verification.verdict is VerificationVerdict.EFFECTIVE
    assert verification.before == {"filesystem.used_percent": pytest.approx(95.65)}
    assert verification.after == {"filesystem.used_percent": pytest.approx(61.0)}


async def test_a_signal_that_stayed_where_it_was_is_ineffective_end_to_end(
    storage: FakePersistence,
    signals: SignalHistory,
) -> None:
    """SC-002: the condition still holds, so the action did not work."""
    signals.record("filesystem.used_percent", "store-cove", 95.65, when=at(-60))
    signals.record("filesystem.used_percent", "store-cove", 95.60, when=at(SETTLE))

    verification = await settle_one(storage, signals, a_declaration())

    assert verification.verdict is VerificationVerdict.INEFFECTIVE
    assert verification.verdict is not VerificationVerdict.EFFECTIVE


async def test_a_signal_that_did_not_move_enough_is_inconclusive_end_to_end(
    storage: FakePersistence,
    signals: SignalHistory,
) -> None:
    """T-011 and SC-006, through the whole path rather than in the comparison alone."""
    signals.record("workload.error_rate", "store-cove", 10.0, when=at(-60))
    signals.record("workload.error_rate", "store-cove", 9.95, when=at(SETTLE))

    declaration = VerificationDeclaration(
        signals=(VerificationSignal(name="workload.error_rate", direction=SignalDirection.DOWN),),
        settle_seconds=SETTLE,
    )
    verification = await settle_one(storage, signals, declaration)

    assert verification.verdict is VerificationVerdict.INCONCLUSIVE


async def test_a_resource_that_went_absent_is_inconclusive_not_effective(
    storage: FakePersistence,
    signals: SignalHistory,
) -> None:
    """T-031 and FR-022: its last reading predates the action and is not evidence.

    The resource's newest sample is the one taken before the change, which is
    exactly what a guest that vanished mid-incident leaves behind. Comparing
    against it would credit the action with the state it was trying to change.
    """
    signals.record("filesystem.used_percent", "store-cove", 95.65, when=at(-60))

    verification = await settle_one(
        storage, signals, a_declaration(), attempts=MAX_VERIFICATION_ATTEMPTS
    )

    assert verification.verdict is VerificationVerdict.INCONCLUSIVE
    assert verification.after == {}


async def test_a_silent_resource_is_deferred_before_it_is_concluded_about(
    storage: FakePersistence,
    signals: SignalHistory,
) -> None:
    """A metrics pipeline one poll behind must not become a verdict."""
    signals.record("filesystem.used_percent", "store-cove", 95.65, when=at(-60))

    async with storage.begin(TenantScope(org_id="acme")) as unit:
        service = obligations(unit.remediation, signals, a_declaration())
        await service.owe(an_action(), before={"filesystem.used_percent": 95.65}, executed_at=at(0))
        claimed = await service.claim(worker_id="worker-a", now=at(SETTLE + 1))
        deferred = await service.settle(claimed[0], now=at(SETTLE + 1))
        still_owed = await unit.remediation.get("action-1")

    assert not deferred.settled
    assert still_owed is not None
    assert still_owed.state is VerificationState.AWAITING
    assert still_owed.due_at == at(SETTLE * 2 + 1)


async def test_an_unverifiable_capability_is_settled_the_moment_it_is_recorded(
    storage: FakePersistence,
    signals: SignalHistory,
) -> None:
    """FR-006: awaiting a verification that can never happen is a lie on a screen."""
    declaration = VerificationDeclaration.unverifiable("a flag's effect has no signal here")

    async with storage.begin(TenantScope(org_id="acme")) as unit:
        service = obligations(unit.remediation, signals, declaration)
        owed = await service.owe(an_action(), before={}, executed_at=at(0))
        claimed = await service.claim(worker_id="worker-a", now=at(100_000))

    assert owed.verdict is VerificationVerdict.UNVERIFIABLE
    assert not owed.awaiting_verification
    assert owed.detail == "a flag's effect has no signal here"
    assert claimed == ()


async def test_the_five_outcomes_are_the_whole_set(
    storage: FakePersistence,
) -> None:
    """T-010 and FR-004: a sixth verdict is a specification change."""
    assert {member.value for member in VerificationVerdict} == {
        "effective",
        "ineffective",
        "worsened",
        "inconclusive",
        "unverifiable",
    }


async def test_the_verdict_lands_in_the_history_the_proposal_reads(
    storage: FakePersistence,
    signals: SignalHistory,
) -> None:
    """FR-013: recording is what makes any of this available later."""
    signals.record("filesystem.used_percent", "store-cove", 95.65, when=at(-60))
    signals.record("filesystem.used_percent", "store-cove", 61.0, when=at(SETTLE))

    await settle_one(storage, signals, a_declaration())

    async with storage.begin(TenantScope(org_id="acme")) as unit:
        summary = await unit.remediation.effectiveness(
            EffectivenessQuery(resource_ids=("store-cove",), capabilities=("clear_cache",))
        )

    assert summary.counts[VerificationVerdict.EFFECTIVE] == 1
    assert summary.success_ratio == pytest.approx(1.0)


async def settle_one(
    storage: FakePersistence,
    signals: SignalHistory,
    declaration: VerificationDeclaration,
    *,
    attempts: int = 1,
):
    """Owe one obligation and settle it, claiming ``attempts`` times first."""
    async with storage.begin(TenantScope(org_id="acme")) as unit:
        service = obligations(unit.remediation, signals, declaration)
        await service.owe(
            an_action(),
            before=await service.capture(an_action()),
            executed_at=at(0),
        )
        claimed: Sequence[object] = ()
        for attempt in range(attempts):
            claimed = await service.claim(
                worker_id=f"worker-{attempt}", now=at(SETTLE + 1 + attempt * SETTLE)
            )
            if attempt < attempts - 1:
                await service.settle(claimed[0], now=at(SETTLE + 1 + attempt * SETTLE))  # type: ignore[arg-type]
        return await service.settle(claimed[0], now=at(SETTLE + 1))  # type: ignore[arg-type]
