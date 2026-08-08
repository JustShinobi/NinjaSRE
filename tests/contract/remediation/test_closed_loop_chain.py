"""One action, end to end, with the whole chain asserted field by field.

SC-011 asks that the audit record for one action carry what was proposed, what
resolved the level, what executed, what was verified, what the values were, and
what happened next. This is that assertion, and it is deliberately one test over
the real objects rather than six over doubles: the failure it exists to catch is
a field that stops being written because two modules disagreed about whose job
it was, and a suite of unit tests each mocking the other side cannot see it.

The primary story from the specification is what runs. A container's filesystem
fills; the deployment clears the reclaimable space; five minutes later the signal
has dropped to sixty per cent; the incident closes with the before and after
values and the time it took. Then the same container fills again, the clear does
not move the signal, and the incident escalates instead of closing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from config.constants.closed_loop import (
    CLOSED_LOOP_AUDIT_ACTION_VERIFIED,
    CLOSED_LOOP_AUDIT_RESOURCE_KIND,
)
from core.capability.metadata import SideEffectLevel
from platform.incidents.lifecycle import IncidentLifecycle, IncidentRaise
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import (
    IncidentOrigin,
    IncidentState,
    IncidentSubject,
    TenantScope,
)
from platform.persistence.ports.remediation_ledger import VerificationVerdict
from platform.persistence.ports.signal_store import Signal, SignalKind, signal_key
from platform.remediation.aftermath import VerificationAftermath, undo_payload
from platform.remediation.closed_loop import ClosedLoop, ClosedLoopAuditor
from platform.remediation.components import ComponentRegistry, RemediationComponents
from platform.remediation.declaration import (
    SignalDirection,
    VerificationDeclaration,
    VerificationSignal,
)
from platform.remediation.history import EffectivenessMemory
from platform.remediation.models import (
    RemediationAction,
    RemediationTarget,
    RollbackPlan,
    RollbackStep,
    StateSnapshot,
)
from platform.remediation.obligations import VerificationObligations
from platform.remediation.recurrence import RecurrenceRule, RecurrenceWatch
from platform.remediation.suspension import AutonomySuspensions
from platform.remediation.timeline import VERIFICATION_ACTOR, IncidentOutcomes

pytestmark = pytest.mark.contract

EPOCH = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
SETTLE = 180
SIGNAL = "filesystem.used_percent"


def at(seconds: float = 0.0) -> datetime:
    """Return a fixed instant offset by ``seconds``."""
    return EPOCH + timedelta(seconds=seconds)


@dataclass(slots=True)
class SignalHistory:
    """The narrow readback the verification needs, over a list of samples."""

    samples: list[Signal] = field(default_factory=list)

    def record(self, value: float, *, when: datetime, resource_id: str = "store-cove") -> None:
        """Append one numeric sample of the filesystem signal."""
        self.samples.append(
            Signal(
                signal_id=signal_key(SIGNAL, resource_id, when),
                name=SIGNAL,
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
    """A stand-in for the four components this chain never calls."""


DECLARATION = VerificationDeclaration(
    signals=(VerificationSignal(name=SIGNAL, direction=SignalDirection.DOWN, clears_at=80.0),),
    settle_seconds=SETTLE,
)


def a_registry() -> ComponentRegistry:
    """Return a registry whose one capability clears reclaimable space."""
    component = NoComponent()
    return ComponentRegistry().register(
        RemediationComponents(
            capability="clear_cache",
            reader=component,  # type: ignore[arg-type]
            applier=component,  # type: ignore[arg-type]
            generator=component,  # type: ignore[arg-type]
            verifier=component,  # type: ignore[arg-type]
            verification=DECLARATION,
        )
    )


def an_action(*, action_id: str) -> RemediationAction:
    """Return the action the deployment takes against a full filesystem."""
    return RemediationAction(
        action_id=action_id,
        capability="clear_cache",
        target=RemediationTarget(identifier="store-cove", environment="production"),
        side_effect_level=SideEffectLevel.WRITE_REVERSIBLE,
        requester="agent",
        intent="clear the reclaimable space on store-cove",
        run_id="run-1",
        team_node_id="team-payments",
    )


def a_plan(action: RemediationAction) -> RollbackPlan:
    """Return the plan the action's undo would run."""
    return RollbackPlan(
        plan_id=f"plan-{action.action_id}",
        action_id=action.action_id,
        target=str(action.target),
        recorded_state=StateSnapshot(
            target=str(action.target), observed_at=at(), values={"reclaimable": 0}
        ),
        summary="nothing to restore; a cache clear has no inverse",
        steps=(
            RollbackStep(
                ordinal=1,
                description="restore the cleared entries",
                capability="clear_cache",
            ),
        ),
        created_at=at(),
    )


@pytest.fixture
async def storage() -> FakePersistence:
    """Return an in-memory store with one organisation."""
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation("acme", "Acme Corp")
    return store


@pytest.fixture
def signals() -> SignalHistory:
    """Return an empty signal history."""
    return SignalHistory()


async def raise_incident(storage: FakePersistence, *, key: str, when: datetime) -> str:
    """Raise the incident the remediation is taken against, and return its id."""
    async with storage.begin(TenantScope(org_id="acme")) as unit:
        incident = await IncidentLifecycle(store=unit.incidents).raise_incident(
            IncidentRaise(
                correlation_key=key,
                title="store-cove is nearly full",
                summary="filesystem.used_percent is 95.65",
                origin=IncidentOrigin.DETECTOR,
                origin_id="datastore-near-full",
                severity="critical",
                subjects=(
                    IncidentSubject(
                        resource_id="store-cove",
                        detail="95.65% full",
                        evidence={SIGNAL: "95.65"},
                    ),
                ),
                team_node_id="team-payments",
            ),
            now=when,
        )
    return incident.incident_id


async def run_one(
    storage: FakePersistence,
    signals: SignalHistory,
    *,
    action_id: str,
    incident_id: str,
    executed_at: datetime,
    settled_at: datetime,
    after_value: float | None = None,
    threshold: int = 4,
):
    """Owe an obligation, sweep it, and return what the sweep concluded.

    ``after_value`` is recorded *between* the two, because that is when it
    happens: the signal the verification reads does not exist when the action
    runs, and a test that seeded it first would be measuring the future.
    """
    action = an_action(action_id=action_id)
    plan = a_plan(action)

    async with storage.begin(TenantScope(org_id="acme")) as unit:
        obligations = VerificationObligations(
            ledger=unit.remediation,
            signals=signals,
            registry=a_registry(),
            clock=lambda: executed_at,
        )
        before = await obligations.capture(action)
        await obligations.owe(
            action,
            before=before,
            executed_at=executed_at,
            autonomous=True,
            plan_id=plan.plan_id,
            incident_id=incident_id,
            condition_key="datastore-near-full",
            undo=undo_payload(action, plan),
        )

    if after_value is not None:
        signals.record(after_value, when=settled_at - timedelta(seconds=10))

    async with storage.begin(TenantScope(org_id="acme")) as unit:
        loop = ClosedLoop(
            obligations=VerificationObligations(
                ledger=unit.remediation,
                signals=signals,
                registry=a_registry(),
                clock=lambda: settled_at,
            ),
            aftermath=VerificationAftermath(
                ledger=unit.remediation,
                suspensions=AutonomySuspensions(audit=unit.audit, clock=lambda: settled_at),
                recurrence=RecurrenceWatch(
                    ledger=unit.remediation,
                    default_rule=RecurrenceRule(threshold=threshold, window_seconds=30 * 86_400),
                    clock=lambda: settled_at,
                ),
                listener=IncidentOutcomes(
                    incidents=IncidentLifecycle(store=unit.incidents),
                    clock=lambda: settled_at,
                ),
                clock=lambda: settled_at,
            ),
            memory=EffectivenessMemory(episodes=unit.episodes),
            auditor=ClosedLoopAuditor(audit=unit.audit),
            clock=lambda: settled_at,
        )
        return await loop.sweep(worker_id="worker-a", now=settled_at)


async def test_an_effective_action_closes_its_incident_with_before_and_after(
    storage: FakePersistence,
    signals: SignalHistory,
) -> None:
    """SC-001 and the primary story: it cleared, and the record says by how much."""
    incident_id = await raise_incident(storage, key="datastore-near-full", when=at(-60))
    signals.record(95.65, when=at(-30))

    outcome = await run_one(
        storage,
        signals,
        action_id="action-1",
        incident_id=incident_id,
        executed_at=at(0),
        settled_at=at(SETTLE + 20),
        after_value=60.0,
    )

    assert outcome.claimed == 1
    assert len(outcome.settled) == 1
    aftermath = outcome.settled[0]
    assert aftermath.verdict is VerificationVerdict.EFFECTIVE
    assert aftermath.resolved

    async with storage.begin(TenantScope(org_id="acme")) as unit:
        incident = await unit.incidents.get(incident_id)
        timeline = await unit.incidents.timeline(incident_id)

    assert incident is not None
    assert incident.state is IncidentState.RESOLVED
    kinds = [entry.kind.value for entry in timeline]
    assert "action_taken" in kinds
    assert "closed" in kinds
    closed = [entry for entry in timeline if entry.kind.value == "closed"][0]
    assert closed.actor == VERIFICATION_ACTOR
    assert "95.65 → 60" in closed.cause
    assert "resolved" in closed.cause


async def test_the_audit_record_carries_the_whole_chain_field_by_field(
    storage: FakePersistence,
    signals: SignalHistory,
) -> None:
    """SC-011 and T-035: one row, and every field asserted rather than sampled."""
    incident_id = await raise_incident(storage, key="datastore-near-full", when=at(-60))
    signals.record(95.65, when=at(-30))

    await run_one(
        storage,
        signals,
        action_id="action-1",
        incident_id=incident_id,
        executed_at=at(0),
        settled_at=at(SETTLE + 20),
        after_value=60.0,
    )

    async with storage.begin(TenantScope(org_id="acme")) as unit:
        rows = await unit.audit.query(
            action=CLOSED_LOOP_AUDIT_ACTION_VERIFIED,
            resource_kind=CLOSED_LOOP_AUDIT_RESOURCE_KIND,
        )
        stored = await unit.remediation.get("action-1")

    assert len(rows) == 1
    detail = rows[0].detail

    # What was proposed, and against what.
    assert detail["action_id"] == "action-1"
    assert detail["capability"] == "clear_cache"
    assert detail["resource_id"] == "store-cove"
    # What was verified, and the values it was verified from.
    assert detail["verdict"] == "effective"
    assert detail["before"] == {SIGNAL: pytest.approx(95.65)}
    assert detail["after"] == {SIGNAL: pytest.approx(60.0)}
    assert detail["settle_seconds"] == SETTLE
    # What happened next.
    assert detail["escalated"] is False
    assert detail["rollback"] == "not_required"
    assert detail["suspended"] is False
    assert detail["recurring_problem"] == ""

    # And the ledger row the surfaces read agrees with the audit row.
    assert stored is not None
    assert stored.verdict is VerificationVerdict.EFFECTIVE
    assert not stored.awaiting_verification
    assert stored.condition_key == "datastore-near-full"
    assert stored.autonomous


async def test_an_ineffective_action_escalates_rather_than_closing(
    storage: FakePersistence,
    signals: SignalHistory,
) -> None:
    """SC-002 and the second half of the primary story."""
    incident_id = await raise_incident(storage, key="datastore-near-full", when=at(-60))
    signals.record(95.65, when=at(-30))

    outcome = await run_one(
        storage,
        signals,
        action_id="action-1",
        incident_id=incident_id,
        executed_at=at(0),
        settled_at=at(SETTLE + 20),
        after_value=95.60,
    )

    assert outcome.settled[0].verdict is VerificationVerdict.INEFFECTIVE
    assert outcome.settled[0].escalated

    async with storage.begin(TenantScope(org_id="acme")) as unit:
        incident = await unit.incidents.get(incident_id)

    assert incident is not None
    assert incident.state is IncidentState.AWAITING_HUMAN
    assert not incident.is_closed


async def test_the_fourth_occurrence_raises_a_pattern_beside_the_incidents(
    storage: FakePersistence,
    signals: SignalHistory,
) -> None:
    """SC-007 end to end: four incidents, one problem, and it is not an incident."""
    signals.record(95.65, when=at(-30))

    for index in range(4):
        executed = at(index * 10_000)
        settled = at(index * 10_000 + SETTLE + 20)
        incident_id = await raise_incident(
            storage, key=f"datastore-near-full-{index}", when=executed - timedelta(seconds=60)
        )
        signals.record(95.65, when=executed - timedelta(seconds=5))
        outcome = await run_one(
            storage,
            signals,
            action_id=f"action-{index}",
            incident_id=incident_id,
            executed_at=executed,
            settled_at=settled,
            after_value=60.0,
        )
        raised = outcome.settled[0].problem

    assert raised is not None
    assert raised.occurrences == 4
    assert raised.pattern_key == "clear_cache@store-cove"
    assert raised.suppressing

    async with storage.begin(TenantScope(org_id="acme")) as unit:
        problems = await unit.remediation.problems()
        incidents = await unit.incidents.query(_all_incidents())

    # Four incidents, all closed by their own effective verification, and one
    # problem that is not among them.
    assert len(problems) == 1
    assert len(incidents) == 4
    assert all(incident.state is IncidentState.RESOLVED for incident in incidents)
    assert problems[0].problem_id not in {incident.incident_id for incident in incidents}


def _all_incidents():
    """Return the query that lists every incident, closed ones included."""
    from platform.persistence.ports import IncidentQuery

    return IncidentQuery(limit=50)


async def test_one_obligation_failing_does_not_stop_the_others(
    storage: FakePersistence,
    signals: SignalHistory,
) -> None:
    """The ones behind a broken reader are the ones nobody has looked at yet."""

    @dataclass(slots=True)
    class HalfBrokenSignals:
        """A readback that raises for one resource and answers for the other."""

        good: SignalHistory

        async def latest(
            self,
            *,
            names: tuple[str, ...] = (),
            resource_ids: tuple[str, ...] = (),
        ) -> tuple[Signal, ...]:
            """Raise for the broken resource, answer for the rest."""
            if "store-reef" in resource_ids:
                raise RuntimeError("the metrics provider is unreachable")
            return await self.good.latest(names=names, resource_ids=resource_ids)

    signals.record(95.65, when=at(-30))
    signals.record(60.0, when=at(SETTLE + 10))
    broken = HalfBrokenSignals(good=signals)

    async with storage.begin(TenantScope(org_id="acme")) as unit:
        obligations = VerificationObligations(
            ledger=unit.remediation,
            signals=broken,
            registry=a_registry(),
            clock=lambda: at(0),
        )
        for action_id, target in (("action-1", "store-cove"), ("action-2", "store-reef")):
            action = RemediationAction(
                action_id=action_id,
                capability="clear_cache",
                target=RemediationTarget(identifier=target, environment="production"),
                side_effect_level=SideEffectLevel.WRITE_REVERSIBLE,
                requester="agent",
            )
            await obligations.owe(action, before={SIGNAL: 95.65}, executed_at=at(0))

    async with storage.begin(TenantScope(org_id="acme")) as unit:
        loop = ClosedLoop(
            obligations=VerificationObligations(
                ledger=unit.remediation,
                signals=broken,
                registry=a_registry(),
                clock=lambda: at(SETTLE + 20),
            ),
            aftermath=VerificationAftermath(ledger=unit.remediation, clock=lambda: at(SETTLE + 20)),
            clock=lambda: at(SETTLE + 20),
        )
        outcome = await loop.sweep(worker_id="worker-a", now=at(SETTLE + 20))

    assert outcome.claimed == 2
    assert outcome.failed == ("action-2",)
    assert [item.outcome.action_id for item in outcome.settled] == ["action-1"]
