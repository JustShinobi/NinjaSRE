"""``InvestigationRecorder``: the seam that writes reasoning onto a timeline, in order.

Three things this file proves, each with its own assertion:

- the five steps a caller records land on the incident's own timeline,
  interleaved with its lifecycle entries, in the order they were called;
- the seam itself refuses a step recorded after a later one already
  happened — the ordering guarantee is a property of using this object, not
  an accident of whichever caller happens to get it right;
- ``receipt`` has no parameter a caller could put a credential's value into.
"""

from __future__ import annotations

import inspect

import pytest

from gateway.runtime.recording import InvestigationRecorder, RecordedOutOfOrder
from platform.incidents.lifecycle import IncidentLifecycle, IncidentRaise
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import (
    IncidentOrigin,
    IncidentSubject,
    PersistenceGateway,
    TenantScope,
    TimelineKind,
)

pytestmark = pytest.mark.unit


@pytest.fixture
async def gateway() -> PersistenceGateway:
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation("acme", "Acme")
    return store


def _a_raise() -> IncidentRaise:
    return IncidentRaise(
        correlation_key="alert:instance-down:host-1",
        title="InstanceDown",
        summary="host-1 stopped responding to scrapes",
        origin=IncidentOrigin.ALERT,
        origin_id="alertmanager",
        severity="critical",
        subjects=(IncidentSubject(resource_id="host-1", detail="down"),),
        cause="the exporter on host-1 stopped responding",
    )


async def test_the_five_steps_land_on_the_timeline_in_the_order_called(
    gateway: PersistenceGateway,
) -> None:
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        lifecycle = IncidentLifecycle(store=uow.incidents)
        incident = await lifecycle.raise_incident(_a_raise(), now=_at(0))
        recorder = InvestigationRecorder(
            lifecycle=lifecycle, incident_id=incident.incident_id, clock=_ticking_clock()
        )

        await recorder.receipt(
            labels={"alertname": "InstanceDown"}, credential_name="delivery token am-cluster"
        )
        await recorder.hypotheses(("the host is down", "the exporter crashed"))
        evidence = await recorder.evidence(
            query='up{instance="host-1:9100"}', result="0", conclusion="the exporter is silent"
        )
        await recorder.diagnosis(
            "the exporter on host-1 stopped responding",
            supporting_evidence_ids=(evidence.entry_id,),
        )
        await recorder.report_delivered(("#sre-oncall",))

        history = await lifecycle.timeline(incident.incident_id)

    assert [item.kind for item in history] == [
        TimelineKind.OPENED,
        TimelineKind.ALERT_RECEIVED,
        TimelineKind.HYPOTHESES_DRAWN,
        TimelineKind.EVIDENCE,
        TimelineKind.DIAGNOSIS,
        TimelineKind.REPORT_DELIVERED,
    ]


async def test_evidence_may_be_recorded_more_than_once_in_a_row(
    gateway: PersistenceGateway,
) -> None:
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        lifecycle = IncidentLifecycle(store=uow.incidents)
        incident = await lifecycle.raise_incident(_a_raise(), now=_at(0))
        recorder = InvestigationRecorder(
            lifecycle=lifecycle, incident_id=incident.incident_id, clock=_ticking_clock()
        )

        await recorder.hypotheses(("the exporter crashed",))
        await recorder.evidence(query="q1", result="r1")
        await recorder.evidence(query="q2", result="r2")

        history = await lifecycle.timeline(incident.incident_id)

    evidence_entries = [item for item in history if item.kind is TimelineKind.EVIDENCE]
    assert [item.query for item in evidence_entries] == ["q1", "q2"]


async def test_recording_hypotheses_after_evidence_is_refused(
    gateway: PersistenceGateway,
) -> None:
    """The claim under test is ordering: the seam itself must stop this, not the caller's care."""
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        lifecycle = IncidentLifecycle(store=uow.incidents)
        incident = await lifecycle.raise_incident(_a_raise(), now=_at(0))
        recorder = InvestigationRecorder(
            lifecycle=lifecycle, incident_id=incident.incident_id, clock=_ticking_clock()
        )
        await recorder.evidence(query="q1", result="r1")

        with pytest.raises(RecordedOutOfOrder, match="hypotheses"):
            await recorder.hypotheses(("too late",))


async def test_recording_anything_after_the_report_went_out_is_refused(
    gateway: PersistenceGateway,
) -> None:
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        lifecycle = IncidentLifecycle(store=uow.incidents)
        incident = await lifecycle.raise_incident(_a_raise(), now=_at(0))
        recorder = InvestigationRecorder(
            lifecycle=lifecycle, incident_id=incident.incident_id, clock=_ticking_clock()
        )
        await recorder.diagnosis("the exporter is down", supporting_evidence_ids=())
        await recorder.report_delivered(("#sre-oncall",))

        with pytest.raises(RecordedOutOfOrder, match="report delivery"):
            await recorder.hypotheses(("far too late",))


async def test_skipping_a_step_that_never_happened_is_allowed(
    gateway: PersistenceGateway,
) -> None:
    """Not every investigation draws hypotheses explicitly before its first query."""
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        lifecycle = IncidentLifecycle(store=uow.incidents)
        incident = await lifecycle.raise_incident(_a_raise(), now=_at(0))
        recorder = InvestigationRecorder(
            lifecycle=lifecycle, incident_id=incident.incident_id, clock=_ticking_clock()
        )

        await recorder.receipt(labels={}, credential_name="delivery token am-cluster")
        # No call to .hypotheses() here.
        entry = await recorder.evidence(query="q1", result="r1")

    assert entry.kind is TimelineKind.EVIDENCE


async def test_a_diagnosis_with_no_supporting_evidence_reaches_the_timeline_as_a_hypothesis(
    gateway: PersistenceGateway,
) -> None:
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        lifecycle = IncidentLifecycle(store=uow.incidents)
        incident = await lifecycle.raise_incident(_a_raise(), now=_at(0))
        recorder = InvestigationRecorder(
            lifecycle=lifecycle, incident_id=incident.incident_id, clock=_ticking_clock()
        )

        entry = await recorder.diagnosis("host-1 might be down", supporting_evidence_ids=())
        history = await lifecycle.timeline(incident.incident_id)

    assert entry.kind is TimelineKind.HYPOTHESES_DRAWN
    assert TimelineKind.DIAGNOSIS not in {item.kind for item in history}


def test_receipt_has_no_parameter_a_caller_could_put_a_secret_value_into() -> None:
    """Structural, not behavioural: the signature itself is the guarantee.

    If a future change added a ``token_value`` (or similarly named) parameter
    here, this test breaks the moment it is added — before anybody has to
    notice a leak downstream to catch it.
    """
    parameters = set(inspect.signature(InvestigationRecorder.receipt).parameters)

    assert parameters == {"self", "labels", "credential_name"}


def _at(offset_seconds: float):  # noqa: ANN202 - internal test helper, see _ticking_clock
    from datetime import UTC, datetime, timedelta

    return datetime(2026, 3, 1, 12, 0, tzinfo=UTC) + timedelta(seconds=offset_seconds)


def _ticking_clock():  # noqa: ANN202 - returns Callable[[], datetime]
    """Return a clock that advances one second on every call.

    Distinct, strictly increasing instants — never ``datetime.now()`` — so a
    test's assertions about order never depend on how fast the machine runs.
    """
    state = {"n": 0}

    def clock():  # noqa: ANN202
        state["n"] += 1
        return _at(state["n"])

    return clock
