"""Whether a new incident joins an investigation already looking at its subject.

One person shut down one container and this deployment opened five incidents
and ran five investigations — 260,000 tokens spent reasoning about the same
shutdown five times, none of the five knowing the other four existed. Four of
them resolved to the same estate resource; the fifth resolved to a different
one and was four days old.

That last detail is the whole design. The relation is not "these alerts arrived
together" — the fifth arrived together with the rest and was unrelated. It is
"these alerts are about the same thing", and the estate already answers that:
alert resolution recorded which resource each incident is about before any of
this runs.

So the rule is a shared subject, and it is deliberately not a shared *parent*.
Two conditions on one node are two problems with two answers, and folding them
together is the failure ``platform/incidents/correlation`` warns about in its
own first paragraph — grouping too aggressively hides a second cause.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from platform.incidents.joining import investigation_to_join
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports.incident_store import (
    Incident,
    IncidentOrigin,
    IncidentState,
    IncidentSubject,
)
from platform.persistence.ports.run_trace_store import AgentRun, RunStatus
from platform.persistence.ports.transaction import TenantScope

pytestmark = pytest.mark.unit

ORG = "acme"
SCOPE = TenantScope(org_id=ORG)
NOW = datetime(2026, 8, 26, 5, 24, tzinfo=UTC)

#: The container somebody shut down.
REDIS = "res-7a73b8aa"
#: A different container, which happens to sit on the same node.
OTHER = "res-cf2b2c02"


def _incident(
    incident_id: str,
    *,
    subject: str,
    run_ids: tuple[str, ...] = (),
    state: IncidentState = IncidentState.OPEN,
    opened_at: datetime = NOW,
) -> Incident:
    return Incident(
        incident_id=incident_id,
        public_id=incident_id,
        correlation_key=f"alert:alertmanager:{incident_id}",
        title=incident_id,
        summary=incident_id,
        origin=IncidentOrigin.ALERT,
        origin_id="alertmanager",
        severity="critical",
        state=state,
        opened_at=opened_at,
        subjects=(IncidentSubject(resource_id=subject, detail="", observed_at=opened_at),),
        run_ids=run_ids,
    )


async def _store() -> FakePersistence:
    """Return an in-memory gateway with the one organisation these tests use."""
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme")
    return store


async def _seed(
    store: FakePersistence,
    *,
    incidents: tuple[Incident, ...],
    runs: tuple[AgentRun, ...] = (),
) -> None:
    async with store.begin(SCOPE) as uow:
        for incident in incidents:
            await uow.incidents.upsert(incident)
        for run in runs:
            await uow.run_traces.start_run(run)


async def _join(store: FakePersistence, incident: Incident) -> str:
    async with store.begin(SCOPE) as uow:
        found = await investigation_to_join(
            incident, incidents=uow.incidents, runs=uow.run_traces, now=NOW
        )
    return "" if found is None else found.run_id


async def test_an_alert_on_a_subject_under_investigation_joins_it() -> None:
    """The second symptom of one failure does not open a second investigation."""
    store = await _store()
    running = _incident("first", subject=REDIS, run_ids=("run-live",))
    arriving = _incident("second", subject=REDIS)
    await _seed(
        store,
        incidents=(running, arriving),
        runs=(
            AgentRun(
                run_id="run-live",
                trigger="alert",
                status=RunStatus.RUNNING,
                started_at=NOW - timedelta(seconds=20),
            ),
        ),
    )

    assert await _join(store, arriving) == "run-live", (
        "a second alert about the resource an investigation is already looking at "
        "started an investigation of its own. That is the same failure reasoned "
        "about twice, at twice the cost, by two runs that cannot see each other."
    )


async def test_an_alert_about_a_different_resource_does_not_join() -> None:
    """Arriving together is not a relation.

    The fifth incident in the measured burst arrived inside the same minute as
    the other four and was about a container stopped four days earlier. A rule
    keyed on arrival would have folded it in.
    """
    store = await _store()
    running = _incident("first", subject=REDIS, run_ids=("run-live",))
    unrelated = _incident("fifth", subject=OTHER)
    await _seed(
        store,
        incidents=(running, unrelated),
        runs=(
            AgentRun(
                run_id="run-live",
                trigger="alert",
                status=RunStatus.RUNNING,
                started_at=NOW - timedelta(seconds=20),
            ),
        ),
    )

    assert await _join(store, unrelated) == ""


async def test_a_finished_run_is_never_handed_evidence() -> None:
    """Nothing can be added to an investigation that has already reported.

    It can be cited — the answer exists and the arriving incident points at it
    rather than re-deriving it — but a message queued for a run nobody is
    driving is delivered at a turn boundary that will never come.
    """
    store = await _store()
    over = _incident("first", subject=REDIS, run_ids=("run-done",))
    arriving = _incident("second", subject=REDIS)
    await _seed(
        store,
        incidents=(over, arriving),
        runs=(
            AgentRun(
                run_id="run-done",
                trigger="alert",
                status=RunStatus.COMPLETED,
                started_at=NOW - timedelta(minutes=2),
                finished_at=NOW - timedelta(minutes=1),
            ),
        ),
    )

    async with store.begin(SCOPE) as uow:
        found = await investigation_to_join(
            arriving, incidents=uow.incidents, runs=uow.run_traces, now=NOW
        )

    assert found is not None
    assert found.answered is True, "a finished run was reported as one that can still take evidence"


async def test_an_incident_never_joins_its_own_investigation() -> None:
    """The incident that started the run is not a second incident about it."""
    store = await _store()
    itself = _incident("first", subject=REDIS, run_ids=("run-live",))
    await _seed(
        store,
        incidents=(itself,),
        runs=(
            AgentRun(
                run_id="run-live",
                trigger="alert",
                status=RunStatus.RUNNING,
                started_at=NOW - timedelta(seconds=20),
            ),
        ),
    )

    assert await _join(store, itself) == ""


async def test_a_closed_incident_is_not_a_live_investigation() -> None:
    """A resolved incident's run is not something to add evidence to."""
    store = await _store()
    closed = _incident(
        "first",
        subject=REDIS,
        run_ids=("run-live",),
        state=IncidentState.RESOLVED,
    )
    arriving = _incident("second", subject=REDIS)
    await _seed(
        store,
        incidents=(closed, arriving),
        runs=(
            AgentRun(
                run_id="run-live",
                trigger="alert",
                status=RunStatus.RUNNING,
                started_at=NOW - timedelta(seconds=20),
            ),
        ),
    )

    assert await _join(store, arriving) == ""


# --- An investigation that has already answered ------------------------------
#
# Three of the five alerts in the measured burst arrived fifteen seconds after
# the investigation of the first one had reported. There was nothing live to
# join, so each started its own — and each re-derived, at full cost, an answer
# that had existed for fifteen seconds.
#
# A finished run is not something evidence can be added to. It is something an
# incident can be pointed at.


async def test_an_answer_from_moments_ago_is_pointed_at_rather_than_redone() -> None:
    store = await _store()
    answered = _incident("first", subject=REDIS, run_ids=("run-answered",))
    arriving = _incident("second", subject=REDIS)
    await _seed(
        store,
        incidents=(answered, arriving),
        runs=(
            AgentRun(
                run_id="run-answered",
                trigger="alert",
                status=RunStatus.COMPLETED,
                started_at=NOW - timedelta(minutes=1),
                finished_at=NOW - timedelta(seconds=15),
                summary="the container was stopped by hand",
            ),
        ),
    )

    async with store.begin(SCOPE) as uow:
        found = await investigation_to_join(
            arriving, incidents=uow.incidents, runs=uow.run_traces, now=NOW
        )

    assert found is not None, (
        "an alert arriving fifteen seconds after the answer started its own "
        "investigation. The answer already existed."
    )
    assert found.run_id == "run-answered"
    assert found.answered is True, "a finished run cannot be told anything; it can be cited"


async def test_a_stale_answer_is_not_pointed_at() -> None:
    """Past the window, the condition is a recurrence and deserves a look."""
    store = await _store()
    old = _incident("first", subject=REDIS, run_ids=("run-old",))
    arriving = _incident("second", subject=REDIS)
    await _seed(
        store,
        incidents=(old, arriving),
        runs=(
            AgentRun(
                run_id="run-old",
                trigger="alert",
                status=RunStatus.COMPLETED,
                started_at=NOW - timedelta(hours=3),
                finished_at=NOW - timedelta(hours=3),
                summary="the container was stopped by hand",
            ),
        ),
    )

    async with store.begin(SCOPE) as uow:
        found = await investigation_to_join(
            arriving, incidents=uow.incidents, runs=uow.run_traces, now=NOW
        )

    assert found is None


async def test_a_live_run_is_preferred_over_a_finished_one() -> None:
    """Evidence beats a citation: a run that can still use the alert gets it."""
    store = await _store()
    answered = _incident("first", subject=REDIS, run_ids=("run-answered",))
    running = _incident("second", subject=REDIS, run_ids=("run-live",))
    arriving = _incident("third", subject=REDIS)
    await _seed(
        store,
        incidents=(answered, running, arriving),
        runs=(
            AgentRun(
                run_id="run-answered",
                trigger="alert",
                status=RunStatus.COMPLETED,
                started_at=NOW - timedelta(minutes=1),
                finished_at=NOW - timedelta(seconds=15),
            ),
            AgentRun(
                run_id="run-live",
                trigger="alert",
                status=RunStatus.RUNNING,
                started_at=NOW - timedelta(seconds=10),
            ),
        ),
    )

    async with store.begin(SCOPE) as uow:
        found = await investigation_to_join(
            arriving, incidents=uow.incidents, runs=uow.run_traces, now=NOW
        )

    assert found is not None
    assert found.run_id == "run-live", (
        "a finished run was chosen over one still able to use the alert. Evidence "
        "handed to a live investigation is worth more than a citation of an old one."
    )
    assert found.answered is False
